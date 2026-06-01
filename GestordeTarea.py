from flask import Flask, render_template, request, redirect, url_for, session, g
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
from pymongo.server_api import ServerApi
import os

# Cargar variables de entorno PRIMERO
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from flask_mail import Mail, Message
import logging
import smtplib
import traceback
import io
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from pyngrok import ngrok


# Create a new client and connect to the server
uri = os.getenv('MONGODB_URI') or os.getenv('MONGO_URI') or 'mongodb://localhost:27017'
client = MongoClient(uri, server_api=ServerApi('1'))
# Send a ping to confirm a successful connection
try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)
    
    
app = Flask(__name__)
app.secret_key = 'red_black_2026'

# Configurar Mail ANTES de las rutas
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'u107765140.wl141.sendgrid.net')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_DEBUG'] = True


logging.basicConfig(level=logging.DEBUG)

mail = Mail(app)

serializer = URLSafeTimedSerializer(app.secret_key)

def generate_reset_token(email):
    return serializer.dumps(email, salt='password-reset-salt')


def confirm_reset_token(token, expiration=3600):
    try:
        email = serializer.loads(token, salt='password-reset-salt', max_age=expiration)
    except SignatureExpired:
        return None
    except BadSignature:
        return None
    return email


def test_smtp_connection():
    host = os.getenv('MAIL_SERVER', 'smtp.sendgrid.net')
    port = int(os.getenv('MAIL_PORT', 587))
    username = os.getenv('MAIL_USERNAME')
    password = os.getenv('MAIL_PASSWORD')
    use_ssl_env = os.getenv('MAIL_USE_SSL')
    use_ssl = False
    if use_ssl_env is not None:
        use_ssl = str(use_ssl_env).lower() in ('1', 'true', 'yes')

    buf = io.StringIO()
    try:
        if use_ssl or port == 465:
            buf.write(f"Intentando conexión SSL a {host}:{port}\n")
            server = smtplib.SMTP_SSL(host, port, timeout=10)
            server.set_debuglevel(1)
            if username and password:
                server.login(username, password)
            server.quit()
            buf.write("Conexión SSL OK\n")
        else:
            buf.write(f"Intentando conexión STARTTLS a {host}:{port}\n")
            server = smtplib.SMTP(host, port, timeout=10)
            server.set_debuglevel(1)
            server.ehlo()
            server.starttls()
            server.ehlo()
            if username and password:
                server.login(username, password)
            server.quit()
            buf.write("Conexión STARTTLS OK\n")
    except Exception:
        traceback.print_exc(file=buf)
    return buf.getvalue()


@app.route('/smtp_test')
def smtp_test_route():
    """Ruta de diagnóstico que intenta conectar al servidor SMTP y muestra la traza."""
    result = test_smtp_connection()
    return f"<pre>{result}</pre>"

def get_db():
    if 'db' not in g:
        g.db = client['gestor_tareas']
    return g.db


def normalizar_etiqueta(valor):
    return ' '.join(valor.strip().lower().split())


def parsear_etiquetas(valor):
    etiquetas = []
    for parte in valor.split(','):
        etiqueta = normalizar_etiqueta(parte)
        if etiqueta and etiqueta not in etiquetas:
            etiquetas.append(etiqueta)
    return etiquetas


def asegurar_etiquetas(db, etiquetas):
    for etiqueta in etiquetas:
        db.etiquetas.update_one(
            {'nombre': etiqueta},
            {'$setOnInsert': {'nombre': etiqueta, 'creado_en': datetime.now()}},
            upsert=True
        )


def obtener_etiquetas(db):
    return [item['nombre'] for item in db.etiquetas.find().sort('nombre', 1)]


@app.route('/crear_chiste', methods=['GET', 'POST'])
def crear_chiste():
    db = get_db()

    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        contenido = request.form.get('contenido', '').strip()
        etiquetas = parsear_etiquetas(request.form.get('etiquetas', ''))

        if not contenido:
            return render_template('crear_chiste.html', error='Escribe el chiste antes de guardarlo.', etiquetas=obtener_etiquetas(db))

        if not etiquetas:
            return render_template('crear_chiste.html', error='Agrega al menos una etiqueta para guardar el chiste.', etiquetas=obtener_etiquetas(db))

        asegurar_etiquetas(db, etiquetas)

        db.chistes.insert_one({
            'contenido': contenido,
            'tipo_humor': request.form.get('tipo_humor', 'General'),
            'temas': etiquetas,
            'autor_id': session.get('usuario_id'),
            'autor_nombre': session.get('usuario_nombre'),
            'creado_en': datetime.now(),
        })

        return redirect(url_for('ver_chistes'))

    return render_template('crear_chiste.html', etiquetas=obtener_etiquetas(db))


@app.route('/tus_chistes', methods=['GET', 'POST'])
def tus_chistes():
    db = get_db()

    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        action = request.form.get('action')
        chiste_id = request.form.get('chiste_id')

        try:
            objeto = ObjectId(chiste_id)
        except Exception:
            return redirect(url_for('tus_chistes'))

        chiste = db.chistes.find_one({'_id': objeto, 'autor_id': session['usuario_id']})
        if not chiste:
            return redirect(url_for('tus_chistes'))

        if action == 'delete':
            db.chistes.delete_one({'_id': objeto})
            return redirect(url_for('tus_chistes'))

        if action == 'update':
            contenido = request.form.get('contenido', '').strip()
            etiquetas = parsear_etiquetas(request.form.get('etiquetas', ''))

            if not contenido or not etiquetas:
                return redirect(url_for('tus_chistes'))

            asegurar_etiquetas(db, etiquetas)
            db.chistes.update_one(
                {'_id': objeto},
                {'$set': {
                    'contenido': contenido,
                    'tipo_humor': request.form.get('tipo_humor', 'General'),
                    'temas': etiquetas,
                }}
            )

        return redirect(url_for('tus_chistes'))

    chistes = list(db.chistes.find({'autor_id': session['usuario_id']}).sort('creado_en', -1))
    return render_template('tus_chistes.html', chistes=chistes)


@app.route('/ver_chistes')
def ver_chistes():
    db = get_db()
    query = {}

    busqueda = request.args.get('q', '').strip()
    tipo_humor = request.args.get('humor', '').strip()
    etiqueta = normalizar_etiqueta(request.args.get('tag', ''))

    if busqueda:
        query['$or'] = [
            {'contenido': {'$regex': busqueda, '$options': 'i'}},
            {'autor_nombre': {'$regex': busqueda, '$options': 'i'}},
            {'temas': {'$regex': busqueda, '$options': 'i'}},
        ]

    if tipo_humor and tipo_humor != 'Todos':
        query['tipo_humor'] = tipo_humor

    if etiqueta:
        query['temas'] = etiqueta

    chistes = list(db.chistes.find(query).sort('creado_en', -1))
    etiquetas = obtener_etiquetas(db)

    return render_template(
        'ver_chistes.html',
        chistes=chistes,
        etiquetas=etiquetas,
        search=busqueda,
        selected_humor=tipo_humor or 'Todos',
        selected_tag=etiqueta,
    )


@app.route('/')
def index():
    return render_template('pagina_de_inicio.html')

@app.route('/login')
def login():
    return render_template('index.html')

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        db = get_db()

        db.usuarios.insert_one({
            "nombre": request.form.get('nombre'),
            "email": request.form.get('email'),
            "password": request.form.get('password'),
            "genero": request.form.get('genero'),
            "fecha_nacimiento": request.form.get('fecha_nac'),
            "fecha_registro": datetime.now()
        })
        return redirect(url_for('index')) 
    
    return render_template('registro.html')

@app.route('/sesion', methods=['POST'])
def inicio_sesion():
    db = get_db()
    user = db.usuarios.find_one({
        "email": request.form.get('email'), 
        "password": request.form.get('password')
    })
    if user:
        session['usuario_id'] = str(user['_id'])
        session['usuario_nombre'] = user['nombre']
        return redirect(url_for('index'))
    return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/tareas')
def ver_tareas():
    if 'usuario_id' not in session: return redirect(url_for('index'))
    return "<h1>Bienvenido</h1>"

@app.route('/recuperar', methods=['GET', 'POST'])
def recuperar_contrasena():
    if request.method == 'POST':
        email = request.form.get('email')
        db = get_db()
        user = db.usuarios.find_one({"email": email})
        
        if user:
            try:
                token = generate_reset_token(email)
                reset_url = url_for('reset_password', token=token, _external=True)
                msg = Message('Restablece tu contraseña', sender=os.getenv('MAIL_DEFAULT_SENDER'), recipients=[email])
                msg.body = f'Hola {user["nombre"]},\n\nHaz clic en el siguiente enlace para cambiar tu contraseña:\n{reset_url}\n\nSi no solicitaste esto, ignora este mensaje.'
                msg.html = f"""
                    <p>Hola {user['nombre']},</p>
                    <p>Haz clic en el botón para cambiar tu contraseña:</p>
                    <p><a href=\"{reset_url}\" style=\"display:inline-block;padding:12px 24px;background:#1a73e8;color:#ffffff;text-decoration:none;border-radius:4px;\">Cambiar mi contraseña</a></p>
                    <p>Si no solicitaste este cambio, ignora este mensaje.</p>
                """
                mail.send(msg)
                return "Correo enviado correctamente. Revisa tu bandeja de entrada."
            except Exception as e:
                logging.exception("Error enviando correo")
                return f"Error al enviar el correo: {e.__class__.__name__}: {str(e)}"
        else:
            return "El correo no existe en nuestro sistema."
    
    return render_template('recuperar.html')


@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    email = confirm_reset_token(token)
    if not email:
        return "El enlace de restablecimiento no es válido o ha expirado."
    if request.method == 'POST':
        new_password = request.form.get('password')
        db = get_db()
        db.usuarios.update_one({"email": email}, {"$set": {"password": new_password}})
        return "Contraseña actualizada correctamente. Ahora puedes iniciar sesión con tu nueva contraseña."
    return render_template('cambiar_contra.html', email=email)


if __name__ == '__main__':
    # Configurar token de ngrok desde .env
    auth_token = os.getenv('NGROK_AUTHTOKEN')
    if auth_token:
        ngrok.set_auth_token(auth_token)
    
    # Para usar ngrok, descomenta la siguiente línea:
    public_url = ngrok.connect(5000)
    print(f"Tu URL pública es: {public_url}")
    
    app.run(debug=True, host='0.0.0.0', port=5000)