
from flask import Flask, render_template, request, redirect, url_for, session  # Flask y utilidades web
import os  # acceso a variables de entorno y rutas del sistema
import json  # manejo básico de JSON (no usado ampliamente aquí pero disponible)
import secrets  # generación de tokens seguros (ids y tokens)
from datetime import datetime, timedelta  # manejo de fechas y tiempos
import smtplib  # envío de correos via SMTP
import logging  # registro de eventos / debugging
from pymongo import MongoClient  # cliente para MongoDB

# MongoDB connection: prefer `MONGODB_URI` desde las variables de entorno;
# si no está definido, usamos un fallback local para desarrollo.
MONGODB_URI = os.environ.get('MONGODB_URI') or 'mongodb://localhost:27017'

MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')  # servidor SMTP (por defecto Gmail)
MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))  # puerto SMTP (STARTTLS por defecto)
# Credenciales de correo: mantener en variables de entorno por seguridad
MAIL_USERNAME = os.environ.get('MAIL_USERNAME')  # usuario SMTP (email)
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')  # contraseña SMTP
# Dirección remitente por defecto: usa MAIL_DEFAULT_SENDER, o la cuenta SMTP si está disponible
MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or MAIL_USERNAME or 'no-reply@example.com'

app = Flask(__name__)  # app Flask
# Clave secreta para sesiones; en producción debe venir de una variable segura
app.secret_key = os.environ.get('FLASK_SECRET', 'dev-secret')
logging.basicConfig(level=logging.INFO)  # configurar logging en INFO

# Connect to MongoDB Atlas
client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)  # inicializa cliente MongoDB
try:
    # Intento rápido para comprobar conexión
    client.admin.command('ping')
    logging.info('Conectado a MongoDB.')
except Exception as e:
    # Si falla, no hacemos exit; solo avisamos — util en desarrollo sin Atlas configurado
    logging.warning('No se pudo conectar a MongoDB: %s', e)
    logging.warning('Se continuará, pero algunas operaciones de BD pueden fallar hasta que se configure la conexión.')

def get_db():
    # Devuelve el objeto de base de datos que usaremos en las rutas
    return client['gestor_tareas']

# Simple helpers
def normalize_tag(value):
    # Normaliza una etiqueta: trim, lowercase, colapsa múltiples espacios
    return ' '.join(value.strip().lower().split())

def parse_tags(value):
    # Recibe un string con etiquetas separadas por comas y devuelve lista única normalizada
    tags = []
    for part in value.split(','):
        t = normalize_tag(part)
        if t and t not in tags:
            tags.append(t)
    return tags

# Email sending: if SMTP env variables provided, try sending; otherwise print link to console.
def send_email(subject, sender, recipients, body):
    # Asegurar que `recipients` sea una lista
    if not isinstance(recipients, (list, tuple)):
        recipients = [recipients]

    # Si hay credenciales SMTP configuradas, intentamos enviar el correo
    if MAIL_SERVER and MAIL_USERNAME and MAIL_PASSWORD:
        try:
            server = smtplib.SMTP(MAIL_SERVER, MAIL_PORT, timeout=10)
            server.ehlo()
            server.starttls()  # usar TLS
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
        # Si no hay SMTP configurado, imprimimos en logs (útil en desarrollo)
        logging.info('Simulating email (SMTP not configured). To enable, set MAIL_SERVER, MAIL_USERNAME, MAIL_PASSWORD.')
        logging.info('To: %s', recipients)
        logging.info('Subject: %s', subject)
        logging.info('%s', body)
        return True


@app.route('/')
def index():
    # Página principal
    return render_template('pagina_de_inicio.html')

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        # Registro de nuevo usuario: crear documento en la colección `usuarios`
        db = get_db()
        usuario = {
            '_id': secrets.token_hex(16),  # id seguro
            'nombre': request.form.get('nombre'),
            'email': request.form.get('email'),
            'password': request.form.get('password'),
            'genero': request.form.get('genero'),
            'fecha_nacimiento': request.form.get('fecha_nac'),
            'fecha_registro': datetime.utcnow().isoformat()
        }
        db.usuarios.insert_one(usuario)
        return redirect(url_for('index'))
    # GET -> mostrar formulario de registro
    return render_template('registro.html')

@app.route('/sesion', methods=['POST'])
def inicio_sesion():
    # Maneja el POST del formulario de inicio de sesión
    db = get_db()
    email = request.form.get('email')
    password = request.form.get('password')
    user = db.usuarios.find_one({'email': email, 'password': password})
    if user:
        # Guardar datos mínimos en sesión
        session['usuario_id'] = user.get('_id')
        session['usuario_nombre'] = user.get('nombre')
        return redirect(url_for('index'))
    # En caso de fallo, redirigimos (podrías mostrar un mensaje de error)
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    # Cierra la sesión del usuario
    session.clear()
    return redirect(url_for('index'))


@app.route('/login')
def login():
    # Mostrar formulario de login (aquí reutiliza `index.html` según diseño previo)
    return render_template('index.html')

@app.route('/crear_chiste', methods=['GET', 'POST'])
def crear_chiste():
    # Solo usuarios autenticados pueden acceder a crear chiste
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    db = get_db()
    # Obtener etiquetas existentes para mostrarlas en el formulario
    etiquetas_actuales = [e['nombre'] for e in db.etiquetas.find().sort('nombre', 1)]

    if request.method == 'POST':
        # Lectura y validación básica del formulario
        contenido = request.form.get('contenido', '').strip()
        etiquetas = parse_tags(request.form.get('etiquetas', ''))
        if not contenido or not etiquetas:
            # Volver a mostrar el formulario con error y las etiquetas disponibles
            return render_template('crear_chiste.html', error='Contenido y etiquetas requeridos.', etiquetas=etiquetas_actuales)

        # Guardar/asegurar etiquetas en colección `etiquetas`
        for t in etiquetas:
            db.etiquetas.update_one({'nombre': t}, {'$setOnInsert': {'nombre': t}}, upsert=True)

        # Construir documento del chiste
        chiste = {
            '_id': secrets.token_hex(16),
            'contenido': contenido,
            'tipo_humor': request.form.get('tipo_humor', 'General'),
            'temas': etiquetas,
            'autor_id': session['usuario_id'],
            'autor_nombre': session.get('usuario_nombre'),
            'creado_en': datetime.utcnow().isoformat()
        }

        # Insertar y redirigir: si es humor 'Negro' vamos a la vista específica
        db.chistes.insert_one(chiste)
        if chiste.get('tipo_humor', '').strip().lower() == 'negro':
            return redirect(url_for('ver_chistes_negros'))
        return redirect(url_for('ver_chistes'))

    # GET -> mostrar formulario con etiquetas disponibles
    return render_template('crear_chiste.html', etiquetas=etiquetas_actuales)

@app.route('/ver_chistes')
def ver_chistes():
    # Mostrar todos los chistes (vista genérica)
    db = get_db()
    chistes = list(db.chistes.find().sort('creado_en', -1))
    etiquetas = [e['nombre'] for e in db.etiquetas.find().sort('nombre', 1)]
    return render_template('ver_chistes.html', chistes=chistes, etiquetas=etiquetas, search='')


@app.route('/ver_chistes_negros')
def ver_chistes_negros():
    db = get_db()
    q = request.args.get('q', '').strip()
    tag = request.args.get('tag', '')

    filtros = [{'tipo_humor': 'Negro'}]
    if q:
        filtros.append({'$or': [
            {'contenido': {'$regex': q, '$options': 'i'}},
            {'autor_nombre': {'$regex': q, '$options': 'i'}}
        ]})
    if tag:
        filtros.append({'temas': tag})

    query = {'$and': filtros} if len(filtros) > 1 else filtros[0]
    chistes = list(db.chistes.find(query).sort('creado_en', -1))
    etiquetas = [e['nombre'] for e in db.etiquetas.find().sort('nombre', 1)]
    return render_template('ver_chistes_negros.html', chistes=chistes, etiquetas=etiquetas, search=q, selected_tag=tag)

@app.route('/tus_chistes', methods=['GET', 'POST'])
def tus_chistes():
    # Mostrar y gestionar chistes del usuario autenticado
    if 'usuario_id' not in session:
        return redirect(url_for('index'))
    db = get_db()
    user_id = session['usuario_id']

    if request.method == 'POST':
        action = request.form.get('action')
        chiste_id = request.form.get('chiste_id')
        if action == 'delete':
            # Borrar solo si el autor coincide
            db.chistes.delete_one({'_id': chiste_id, 'autor_id': user_id})
        elif action == 'update':
            # Actualizar contenido y etiquetas
            contenido_n = request.form.get('contenido')
            temas_n = parse_tags(request.form.get('etiquetas', ''))
            db.chistes.update_one({'_id': chiste_id, 'autor_id': user_id}, {'$set': {'contenido': contenido_n, 'temas': temas_n}})
        return redirect(url_for('tus_chistes'))

    chistes = list(db.chistes.find({'autor_id': user_id}))
    return render_template('tus_chistes.html', chistes=chistes)

def generate_reset_token():
    # Genera un token seguro para recuperación de contraseñas
    return secrets.token_urlsafe(32)

@app.route('/recuperar', methods=['GET', 'POST'])
def recuperar_contrasena():
    if request.method == 'POST':
        # Inicio de flujo de recuperación: generar token y enviar correo si existe usuario
        email = request.form.get('email')
        db = get_db()
        user = db.usuarios.find_one({'email': email})
        if user:
            token = generate_reset_token()
            expire_iso = (datetime.utcnow() + timedelta(hours=1)).isoformat()
            # Guardar token y expiración en documento del usuario
            db.usuarios.update_one({'_id': user.get('_id')}, {'$set': {'reset_token': token, 'reset_expire': expire_iso}})
            reset_url = url_for('reset_password', token=token, _external=True)
            # Construir mensaje simple
            body = 'Hola ' + (user.get('nombre') or '') + '\n\n'
            body += 'Usa este enlace para cambiar tu contraseña:\n' + reset_url + '\n\n'
            body += 'Si no lo solicitaste, ignora este mensaje.'
            send_email('Restablece tu contraseña', MAIL_DEFAULT_SENDER, email, body)
        # Mostrar página que instruye al usuario a revisar su correo (independiente de si el email existía)
        return render_template('esperar_correo.html', email=email)
    # GET -> mostrar formulario para solicitar recuperación
    return render_template('recuperar.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    # Reset de contraseña vía token
    db = get_db()
    user = db.usuarios.find_one({'reset_token': token})
    if user is None:
        return 'Enlace no válido o expirado.'
    expire = datetime.fromisoformat(user.get('reset_expire'))
    if datetime.utcnow() > expire:
        return 'El enlace ha expirado.'
    if request.method == 'POST':
        # Validar campos y actualizar contraseña
        new_password = request.form.get('password')
        confirm = request.form.get('confirm')
        if not new_password or not confirm:
            return render_template('cambiar_contra.html', email=user.get('email'), error='Rellena ambos campos.')
        if new_password != confirm:
            return render_template('cambiar_contra.html', email=user.get('email'), error='Las contraseñas no coinciden.')
        db.usuarios.update_one({'_id': user.get('_id')}, {'$set': {'password': new_password}, '$unset': {'reset_token': '', 'reset_expire': ''}})
        return redirect(url_for('index'))
    # GET -> mostrar formulario para cambiar contraseña
    return render_template('cambiar_contra.html', email=user.get('email'))

if __name__ == '__main__':
    # Ejecutar app en modo debug para desarrollo
    app.run(debug=True)
