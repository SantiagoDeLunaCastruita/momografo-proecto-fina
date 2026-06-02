"""
Gestor de tareas simple y didáctico.

Código pensado para principiantes: sólo Flask y librerías estándar.
Almacena datos en `local_database.json` (formato JSON) para evitar bases
de datos complejas. El envío de correo es opcional y configurable por
variables de entorno.

Ejecutar:
    python GestordeTarea.py

Rutas principales: /, /registro, /sesion, /logout, /crear_chiste,
/ver_chistes, /tus_chistes, /recuperar, /reset_password/<token>
"""

from flask import Flask, render_template, request, redirect, url_for, session
import os
import json
import uuid
from datetime import datetime, timedelta
import smtplib
import logging

APP_DB = os.path.join(os.path.dirname(__file__), 'local_database.json')
MAIL_SERVER = os.environ.get('MAIL_SERVER')
MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'no-reply@example.com')

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET', 'dev-secret')
logging.basicConfig(level=logging.INFO)

# Utility functions for simple JSON storage
def load_db():
    if not os.path.exists(APP_DB):
        return {'usuarios': [], 'chistes': [], 'etiquetas': []}
    with open(APP_DB, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_db(data):
    with open(APP_DB, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# Simple helpers
def normalize_tag(value):
    return ' '.join(value.strip().lower().split())

def parse_tags(value):
    tags = []
    for part in value.split(','):
        t = normalize_tag(part)
        if t and t not in tags:
            tags.append(t)
    return tags

# Email sending: if SMTP env variables provided, try sending; otherwise print link to console.
def send_email(subject, sender, recipients, body):
    if not isinstance(recipients, (list, tuple)):
        recipients = [recipients]
    if MAIL_SERVER and MAIL_USERNAME and MAIL_PASSWORD:
        try:
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
        # No SMTP configured: print the message for development
        logging.info('Simulating email (SMTP not configured). To enable, set MAIL_SERVER, MAIL_USERNAME, MAIL_PASSWORD.')
        logging.info('To: %s', recipients)
        logging.info('Subject: %s', subject)
        logging.info('%s', body)
        return True

# Routes
@app.route('/')
def index():
    return render_template('pagina_de_inicio.html')

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        db = load_db()
        usuario = {
            '_id': str(uuid.uuid4()),
            'nombre': request.form.get('nombre'),
            'email': request.form.get('email'),
            'password': request.form.get('password'),
            'genero': request.form.get('genero'),
            'fecha_nacimiento': request.form.get('fecha_nac'),
            'fecha_registro': datetime.utcnow().isoformat()
        }
        db['usuarios'].append(usuario)
        save_db(db)
        return redirect(url_for('index'))
    return render_template('registro.html')

@app.route('/sesion', methods=['POST'])
def inicio_sesion():
    db = load_db()
    email = request.form.get('email')
    password = request.form.get('password')
    # Buscar usuario con un bucle (más claro que next/comprehension)
    user = None
    for u in db.get('usuarios', []):
        if u.get('email') == email and u.get('password') == password:
            user = u
            break
    if user:
        session['usuario_id'] = user['_id']
        session['usuario_nombre'] = user['nombre']
        return redirect(url_for('index'))
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


@app.route('/login')
def login():
    # Muestra el formulario de inicio de sesión
    return render_template('index.html')

@app.route('/crear_chiste', methods=['GET', 'POST'])
def crear_chiste():
    if 'usuario_id' not in session:
        return redirect(url_for('inicio_sesion'))
    db = load_db()
    if request.method == 'POST':
        contenido = request.form.get('contenido', '').strip()
        etiquetas = parse_tags(request.form.get('etiquetas', ''))
        if not contenido or not etiquetas:
            return render_template('crear_chiste.html', error='Contenido y etiquetas requeridos.', etiquetas=[t for t in db.get('etiquetas', [])])
        # ensure tags
        for t in etiquetas:
            if t not in db.get('etiquetas', []):
                db.setdefault('etiquetas', []).append(t)
        chiste = {
            '_id': str(uuid.uuid4()),
            'contenido': contenido,
            'tipo_humor': request.form.get('tipo_humor', 'General'),
            'temas': etiquetas,
            'autor_id': session['usuario_id'],
            'autor_nombre': session.get('usuario_nombre'),
            'creado_en': datetime.utcnow().isoformat()
        }
        db.setdefault('chistes', []).append(chiste)
        save_db(db)
        return redirect(url_for('ver_chistes'))
    return render_template('crear_chiste.html', etiquetas=db.get('etiquetas', []))

@app.route('/ver_chistes')
def ver_chistes():
    db = load_db()
    chistes = db.get('chistes', [])[:]
    return render_template('ver_chistes.html', chistes=chistes, etiquetas=db.get('etiquetas', []), search='')

@app.route('/tus_chistes', methods=['GET', 'POST'])
def tus_chistes():
    if 'usuario_id' not in session:
        return redirect(url_for('index'))
    db = load_db()
    user_id = session['usuario_id']
    if request.method == 'POST':
        action = request.form.get('action')
        chiste_id = request.form.get('chiste_id')
        if action == 'delete':
            # Crear una nueva lista sin el chiste eliminado
            nuevos = []
            for c in db.get('chistes', []):
                if c.get('_id') == chiste_id and c.get('autor_id') == user_id:
                    # saltar (eliminar)
                    continue
                nuevos.append(c)
            db['chistes'] = nuevos
            save_db(db)
        elif action == 'update':
            for c in db.get('chistes', []):
                if c['_id'] == chiste_id and c['autor_id'] == user_id:
                    c['contenido'] = request.form.get('contenido', c['contenido'])
                    c['temas'] = parse_tags(request.form.get('etiquetas', ','.join(c.get('temas', []))))
                    break
            save_db(db)
        return redirect(url_for('tus_chistes'))
    chistes = []
    for c in db.get('chistes', []):
        if c.get('autor_id') == user_id:
            chistes.append(c)
    return render_template('tus_chistes.html', chistes=chistes)

# Password recovery: simple token stored in the user record with expiration
def generate_reset_token():
    return str(uuid.uuid4())

@app.route('/recuperar', methods=['GET', 'POST'])
def recuperar_contrasena():
    if request.method == 'POST':
        email = request.form.get('email')
        db = load_db()
        # Buscar usuario con un bucle claro
        user = None
        for u in db.get('usuarios', []):
            if u.get('email') == email:
                user = u
                break
        if user is not None:
            token = generate_reset_token()
            user['reset_token'] = token
            user['reset_expire'] = (datetime.utcnow() + timedelta(hours=1)).isoformat()
            save_db(db)
            reset_url = url_for('reset_password', token=token, _external=True)
            body = 'Hola ' + (user.get('nombre') or '') + '\n\n'
            body += 'Usa este enlace para cambiar tu contraseña:\n' + reset_url + '\n\n'
            body += 'Si no lo solicitaste, ignora este mensaje.'
            send_email('Restablece tu contraseña', MAIL_DEFAULT_SENDER, email, body)
        # Mostrar página que indica al usuario revisar su correo
        return render_template('esperar_correo.html', email=email)
    return render_template('recuperar.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    db = load_db()
    # Buscar usuario por token con un bucle claro
    user = None
    for u in db.get('usuarios', []):
        if u.get('reset_token') == token:
            user = u
            break
    if user is None:
        return 'Enlace no válido o expirado.'
    expire = datetime.fromisoformat(user.get('reset_expire'))
    if datetime.utcnow() > expire:
        return 'El enlace ha expirado.'
    if request.method == 'POST':
        # Obtener ambos campos y validar
        new_password = request.form.get('password')
        confirm = request.form.get('confirm')
        if not new_password or not confirm:
            return render_template('cambiar_contra.html', email=user.get('email'), error='Rellena ambos campos.')
        if new_password != confirm:
            return render_template('cambiar_contra.html', email=user.get('email'), error='Las contraseñas no coinciden.')
        # Actualizar contraseña y limpiar token
        user['password'] = new_password
        user.pop('reset_token', None)
        user.pop('reset_expire', None)
        save_db(db)
        # Redirigir al inicio
        return redirect(url_for('index'))
    return render_template('cambiar_contra.html', email=user.get('email'))

if __name__ == '__main__':
    app.run(debug=True)
