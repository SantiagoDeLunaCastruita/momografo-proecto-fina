
# Este archivo es el servidor Flask principal de la aplicación.
# Define rutas, gestiona la base de datos MongoDB y envía correos para recuperación de contraseña.

from flask import Flask, render_template, request, redirect, url_for, session
import os
import json
import secrets
from datetime import datetime, timedelta
import smtplib
import logging
from pymongo import MongoClient

# La URI de MongoDB se toma de la variable de entorno para no hardcodear credenciales.
MONGODB_URI = ("mongodb+srv://Said_Ramirez:NfT1w9CGzgETVGuV@escuela.5rt7g7m.mongodb.net/?appName=Escuela")
if not MONGODB_URI:
    raise RuntimeError('MONGODB_URI no está configurado. Define la variable de entorno con tu cadena de conexión de MongoDB Atlas.')

# MongoDB connection: prefer MONGODB_URI env var, fallback to localhost
MONGODB_URI = os.environ.get('mongodb+srv://Said_Ramirez:NfT1w9CGzgETVGuV@escuela.5rt7g7m.mongodb.net/?appName=Escuela') or 'mongodb://localhost:27017'

# Configuración de correo para enviar mensajes de recuperación de contraseña.
MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
# Use standard env var names for username/password
MAIL_USERNAME = os.environ.get('fruterialospapus@gmail.com')
MAIL_PASSWORD = os.environ.get('vdsb uadx wkzu rukg')
MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or MAIL_USERNAME or 'no-reply@example.com'

# Inicializa la aplicación Flask y la clave secreta para sesiones.
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET', 'dev-secret')
logging.basicConfig(level=logging.INFO)

# Conectar a MongoDB Atlas y verificar la conexión.
client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
try:
    client.admin.command('ping')
    logging.info('Conectado a MongoDB.')
except Exception as e:
    logging.warning('No se pudo conectar a MongoDB: %s', e)
    logging.warning('Se continuará, pero algunas operaciones de BD pueden fallar hasta que se configure la conexión.')

# Devuelve el objeto de base de datos que usaremos en todas las rutas.
def get_db():
    return client['gestor_tareas']

# Helpers pequeños para normalizar y parsear etiquetas desde un campo CSV.
def normalize_tag(value):
    # Quita espacios extra y convierte todo a minúsculas.
    return ' '.join(value.strip().lower().split())

def parse_tags(value):
    tags = []
    for part in value.split(','):
        t = normalize_tag(part)
        if t and t not in tags:
            tags.append(t)
    return tags

# Función para enviar correo electrónico usando SMTP.
# Si no hay credenciales de SMTP, solo registra el mensaje en la consola.
def send_email(subject, sender, recipients, body):
    if not isinstance(recipients, (list, tuple)):
        recipients = [recipients]
    if MAIL_SERVER and MAIL_USERNAME and MAIL_PASSWORD:
        try:
            # Conectar al servidor SMTP y enviar el correo.
            server = smtplib.SMTP(MAIL_SERVER, MAIL_PORT, timeout=10)
            server.ehlo()
            server.starttls()
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            message = f"Subject: {subject}\nFrom: {sender}\nTo: {', '.join(recipients)}\n\n{body}"
            server.sendmail(sender, recipients, message)
            server.quit()
            logging.info('Correo enviado a %s', recipients)
            return True
        except Exception as e:
            logging.exception('Fallo al enviar correo: %s', e)
            return False
    else:
        # No hay SMTP configurado, así que se imprime el correo en la consola.
        logging.info('Simulating email (SMTP not configured). To enable, set MAIL_SERVER, MAIL_USERNAME, MAIL_PASSWORD.')
        logging.info('To: %s', recipients)
        logging.info('Subject: %s', subject)
        logging.info('%s', body)
        return True


# Ruta principal que muestra la página de inicio.
@app.route('/')
def index():
    return render_template('pagina_de_inicio.html')

# Registro de usuarios. En GET muestra el formulario, en POST guarda el usuario en MongoDB.
@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        db = get_db()
        usuario = {
            '_id': secrets.token_hex(16),
            'nombre': request.form.get('nombre'),
            'email': request.form.get('email'),
            'password': request.form.get('password'),
            'genero': request.form.get('genero'),
            'fecha_nacimiento': request.form.get('fecha_nac'),
            'fecha_registro': datetime.utcnow().isoformat()
        }
        db.usuarios.insert_one(usuario)
        return redirect(url_for('index'))
    return render_template('registro.html')

# Inicio de sesión: valida email y contraseña y almacena datos de usuario en sesión.
@app.route('/sesion', methods=['POST'])
def inicio_sesion():
    db = get_db()
    email = request.form.get('email')
    password = request.form.get('password')
    user = db.usuarios.find_one({'email': email, 'password': password})
    if user:
        session['usuario_id'] = user.get('_id')
        session['usuario_nombre'] = user.get('nombre')
        return redirect(url_for('index'))
    return redirect(url_for('index'))

# Cierra la sesión del usuario.
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# Muestra pantalla de login.
@app.route('/login')
def login():
    return render_template('index.html')

# Crear un chiste nuevo. Solo usuarios autenticados pueden acceder.
@app.route('/crear_chiste', methods=['GET', 'POST'])
def crear_chiste():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
    db = get_db()
    # obtener etiquetas actuales para mostrar en el formulario
    etiquetas_actuales = [e['nombre'] for e in db.etiquetas.find().sort('nombre', 1)]
    if request.method == 'POST':
        contenido = request.form.get('contenido', '').strip()
        etiquetas = parse_tags(request.form.get('etiquetas', ''))
        if not contenido or not etiquetas:

            # Si falta contenido o etiquetas, se vuelve a mostrar el formulario con error.
            return render_template('crear_chiste.html', error='Contenido y etiquetas requeridos.', etiquetas=etiquetas_actuales)

        for t in etiquetas:
            # Asegura que cada etiqueta exista en la colección de etiquetas.
            db.etiquetas.update_one({'nombre': t}, {'$setOnInsert': {'nombre': t}}, upsert=True)
        chiste = {
            '_id': secrets.token_hex(16),
            'contenido': contenido,
            'tipo_humor': request.form.get('tipo_humor', 'General'),
            'temas': etiquetas,
            'autor_id': session['usuario_id'],
            'autor_nombre': session.get('usuario_nombre'),
            'creado_en': datetime.utcnow().isoformat()
        }
        db.chistes.insert_one(chiste)
        if chiste.get('tipo_humor', '').strip().lower() == 'negro':
            return redirect(url_for('ver_chistes_negros'))
        return redirect(url_for('ver_chistes'))
    return render_template('crear_chiste.html', etiquetas=etiquetas_actuales)

# Mostrar todos los chistes ordenados por fecha de creación descendente.
@app.route('/ver_chistes')
def ver_chistes():
    db = get_db()
    chistes = list(db.chistes.find().sort('creado_en', -1))
    etiquetas = [e['nombre'] for e in db.etiquetas.find().sort('nombre', 1)]
    return render_template('ver_chistes.html', chistes=chistes, etiquetas=etiquetas, search='')


# Página de usuario donde puede ver, eliminar o actualizar sus propios chistes.
@app.route('/tus_chistes', methods=['GET', 'POST'])
def tus_chistes():
    if 'usuario_id' not in session:
        return redirect(url_for('index'))
    db = get_db()
    user_id = session['usuario_id']
    if request.method == 'POST':
        action = request.form.get('action')
        chiste_id = request.form.get('chiste_id')
        if action == 'delete':
            # Elimina solo si el chiste pertenece al usuario.
            db.chistes.delete_one({'_id': chiste_id, 'autor_id': user_id})
        elif action == 'update':
            contenido_n = request.form.get('contenido')
            temas_n = parse_tags(request.form.get('etiquetas', ''))
            db.chistes.update_one({'_id': chiste_id, 'autor_id': user_id}, {'$set': {'contenido': contenido_n, 'temas': temas_n}})
        return redirect(url_for('tus_chistes'))
    chistes = list(db.chistes.find({'autor_id': user_id}))
    return render_template('tus_chistes.html', chistes=chistes)

# Genera un token seguro para recuperación de contraseña.
def generate_reset_token():
    return secrets.token_urlsafe(32)

# Formulario de recuperación de contraseña. Envía un enlace con token al correo del usuario.
@app.route('/recuperar', methods=['GET', 'POST'])
def recuperar_contrasena():
    if request.method == 'POST':
        email = request.form.get('email')
        db = get_db()
        user = db.usuarios.find_one({'email': email})
        if user:
            token = generate_reset_token()
            expire_iso = (datetime.utcnow() + timedelta(hours=1)).isoformat()
            db.usuarios.update_one({'_id': user.get('_id')}, {'$set': {'reset_token': token, 'reset_expire': expire_iso}})
            reset_url = url_for('reset_password', token=token, _external=True)
            body = 'Hola ' + (user.get('nombre') or '') + '\n\n'
            body += 'Usa este enlace para cambiar tu contraseña:\n' + reset_url + '\n\n'
            body += 'Si no lo solicitaste, ignora este mensaje.'
            send_email('Restablece tu contraseña', MAIL_DEFAULT_SENDER, email, body)
        # Mostrar página que indica al usuario revisar su correo, incluso si no existe el email.
        return render_template('esperar_correo.html', email=email)
    return render_template('recuperar.html')

# Página de cambio de contraseña usando el token enviado por correo.
@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    db = get_db()
    user = db.usuarios.find_one({'reset_token': token})
    if user is None:
        return 'Enlace no válido o expirado.'
    expire = datetime.fromisoformat(user.get('reset_expire'))
    if datetime.utcnow() > expire:
        return 'El enlace ha expirado.'
    if request.method == 'POST':
        new_password = request.form.get('password')
        confirm = request.form.get('confirm')
        if not new_password or not confirm:
            return render_template('cambiar_contra.html', email=user.get('email'), error='Rellena ambos campos.')
        if new_password != confirm:
            return render_template('cambiar_contra.html', email=user.get('email'), error='Las contraseñas no coinciden.')
        db.usuarios.update_one({'_id': user.get('_id')}, {'$set': {'password': new_password}, '$unset': {'reset_token': '', 'reset_expire': ''}})
        return redirect(url_for('index'))
    return render_template('cambiar_contra.html', email=user.get('email'))

# Ejecuta la aplicación en modo debug cuando se lanza directamente.
if __name__ == '__main__':
    app.run(debug=True)
