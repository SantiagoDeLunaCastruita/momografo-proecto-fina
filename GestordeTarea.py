from flask import Flask, render_template, request, redirect, url_for, session, g
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
from pymongo.server_api import ServerApi
from email.message import EmailMessage
import os
import json
import re
import uuid
import copy
from types import SimpleNamespace

# Configuración fija en el código
MONGODB_URI = "mongodb+srv://Said_Ramirez:NfT1w9CGzgETVGuV@escuela.5rt7g7m.mongodb.net/gestor_tareas?retryWrites=true&w=majority"
MAIL_SERVER = "smtp.sendgrid.net"
MAIL_PORT = 587
MAIL_USE_TLS = True
MAIL_USERNAME = "apikey"
MAIL_PASSWORD = "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"
MAIL_DEFAULT_SENDER = "wikakax871@doreact.com"
MAIL_USE_SSL = False
NGROK_AUTHTOKEN = "3EXLGEPWW3aKirczcaRQUl9X6IK_82NWY7cc6HAKoQXS1vvnn"
NGROK_ENABLED = True
MONGODB_TLS_INSECURE = True  # Cambia a False en producción si tu entorno soporta TLS correctamente

import logging
import smtplib
import traceback
import io
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from pyngrok import ngrok


# Create a new client and connect to the server
uri = MONGODB_URI
LOCAL_DB_FILE = os.path.join(os.path.dirname(__file__), 'local_database.json')
MONGO_AVAILABLE = False
fallback_db = None

def serialize_value(value):
    if isinstance(value, datetime):
        return {'__datetime__': value.isoformat()}
    if isinstance(value, dict):
        return {k: serialize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [serialize_value(v) for v in value]
    return value


def deserialize_value(value):
    if isinstance(value, dict):
        if '__datetime__' in value:
            return datetime.fromisoformat(value['__datetime__'])
        return {k: deserialize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [deserialize_value(v) for v in value]
    return value


def load_local_data():
    if not os.path.exists(LOCAL_DB_FILE):
        return {'usuarios': [], 'chistes': [], 'etiquetas': []}
    with open(LOCAL_DB_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return {
        'usuarios': [deserialize_value(item) for item in data.get('usuarios', [])],
        'chistes': [deserialize_value(item) for item in data.get('chistes', [])],
        'etiquetas': [deserialize_value(item) for item in data.get('etiquetas', [])],
    }


def save_local_data(data):
    output = {
        'usuarios': [serialize_value(item) for item in data.get('usuarios', [])],
        'chistes': [serialize_value(item) for item in data.get('chistes', [])],
        'etiquetas': [serialize_value(item) for item in data.get('etiquetas', [])],
    }
    with open(LOCAL_DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)


class LocalCursor(list):
    def sort(self, key, direction):
        reverse = direction == -1
        return LocalCursor(sorted(self, key=lambda item: item.get(key), reverse=reverse))


class LocalCollection:
    def __init__(self, name, store):
        self.name = name
        self.store = store
        self.data = store[name]

    def _save(self):
        save_local_data(self.store)

    def _normalize_id(self, value):
        if isinstance(value, ObjectId):
            return str(value)
        return str(value)

    def _match_value(self, doc_value, filter_value):
        if isinstance(filter_value, ObjectId):
            filter_value = str(filter_value)
        if isinstance(doc_value, ObjectId):
            doc_value = str(doc_value)

        if isinstance(filter_value, dict) and '$regex' in filter_value:
            options = filter_value.get('$options', '')
            flags = re.IGNORECASE if 'i' in options else 0
            regex = re.compile(filter_value['$regex'], flags)
            if isinstance(doc_value, list):
                return any(regex.search(str(item)) for item in doc_value)
            return bool(regex.search(str(doc_value or '')))

        if isinstance(doc_value, list):
            return filter_value in doc_value

        return doc_value == filter_value

    def _match(self, doc, query):
        if not query:
            return True
        for key, value in query.items():
            if key == '$or':
                return any(self._match(doc, item) for item in value)
            if not self._match_value(doc.get(key), value):
                return False
        return True

    def find(self, query=None):
        results = [copy.deepcopy(doc) for doc in self.data if self._match(doc, query or {})]
        return LocalCursor(results)

    def find_one(self, query):
        for doc in self.data:
            if self._match(doc, query or {}):
                return copy.deepcopy(doc)
        return None

    def insert_one(self, document):
        new_doc = copy.deepcopy(document)
        if '_id' not in new_doc:
            new_doc['_id'] = str(uuid.uuid4())
        self.data.append(new_doc)
        self._save()
        return SimpleNamespace(inserted_id=new_doc['_id'])

    def delete_one(self, query):
        for index, doc in enumerate(self.data):
            if self._match(doc, query or {}):
                del self.data[index]
                self._save()
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)

    def update_one(self, query, update, upsert=False):
        for doc in self.data:
            if self._match(doc, query or {}):
                if '$setOnInsert' in update and not self._match(doc, query or {}):
                    pass
                if '$set' in update:
                    for key, value in update['$set'].items():
                        doc[key] = value
                self._save()
                return SimpleNamespace(matched_count=1, modified_count=1)

        if upsert:
            new_doc = {}
            if '$setOnInsert' in update:
                new_doc.update(update['$setOnInsert'])
            if '$set' in update:
                new_doc.update(update['$set'])
            if '_id' not in new_doc:
                new_doc['_id'] = str(uuid.uuid4())
            self.data.append(new_doc)
            self._save()
            return SimpleNamespace(upserted_id=new_doc['_id'], matched_count=0, modified_count=0)

        return SimpleNamespace(matched_count=0, modified_count=0)


class LocalDatabase:
    def __init__(self, store):
        self.store = store
        self.usuarios = LocalCollection('usuarios', store)
        self.chistes = LocalCollection('chistes', store)
        self.etiquetas = LocalCollection('etiquetas', store)


def create_mongo_client(uri):
    options = {
        'connectTimeoutMS': 30000,
        'socketTimeoutMS': 30000,
        'serverSelectionTimeoutMS': 30000,
        'tls': True,
    }

    if MONGODB_TLS_INSECURE:
        options.update({
            'tlsAllowInvalidCertificates': True,
            'tlsAllowInvalidHostnames': True,
        })

    client = MongoClient(uri, **options)
    return client

try:
    client = create_mongo_client(uri)
    client.admin.command('ping')
    MONGO_AVAILABLE = True
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    logging.warning("Error connecting to MongoDB on first attempt: %s", e)
    client = None
    fallback_db = LocalDatabase(load_local_data())
    print("MongoDB no disponible. Usando almacenamiento local.")

app = Flask(__name__)
app.secret_key = 'red_black_2026'

# Configurar Mail ANTES de las rutas
app.config['MAIL_SERVER'] = MAIL_SERVER
app.config['MAIL_PORT'] = MAIL_PORT
app.config['MAIL_USE_TLS'] = MAIL_USE_TLS
app.config['MAIL_USERNAME'] = MAIL_USERNAME
app.config['MAIL_PASSWORD'] = MAIL_PASSWORD
app.config['MAIL_DEFAULT_SENDER'] = MAIL_DEFAULT_SENDER
app.config['MAIL_USE_SSL'] = MAIL_USE_SSL
app.config['MAIL_DEBUG'] = True

logging.basicConfig(level=logging.DEBUG)

serializer = URLSafeTimedSerializer(app.secret_key)


def send_email(subject, sender, recipients, body, html=None):
    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = sender
    message['To'] = ', '.join(recipients) if isinstance(recipients, (list, tuple)) else recipients
    message.set_content(body)
    if html:
        message.add_alternative(html, subtype='html')

    if MAIL_USE_SSL or MAIL_PORT == 465:
        smtp_client = smtplib.SMTP_SSL(MAIL_SERVER, MAIL_PORT, timeout=20)
    else:
        smtp_client = smtplib.SMTP(MAIL_SERVER, MAIL_PORT, timeout=20)
        smtp_client.ehlo()
        smtp_client.starttls()
        smtp_client.ehlo()

    if MAIL_USERNAME and MAIL_PASSWORD:
        smtp_client.login(MAIL_USERNAME, MAIL_PASSWORD)

    smtp_client.send_message(message)
    smtp_client.quit()

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
    host = MAIL_SERVER
    port = MAIL_PORT
    username = MAIL_USERNAME
    password = MAIL_PASSWORD
    use_ssl = MAIL_USE_SSL

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
        if MONGO_AVAILABLE and client:
            g.db = client['gestor_tareas']
        else:
            g.db = fallback_db
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
        objeto = chiste_id
        if MONGO_AVAILABLE:
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
                body = (
                    f'Hola {user["nombre"]},\n\n'
                    f'Haz clic en el siguiente enlace para cambiar tu contraseña:\n{reset_url}\n\n'
                    'Si no solicitaste esto, ignora este mensaje.'
                )
                html = f"""
                    <p>Hola {user['nombre']},</p>
                    <p>Haz clic en el botón para cambiar tu contraseña:</p>
                    <p><a href=\"{reset_url}\" style=\"display:inline-block;padding:12px 24px;background:#1a73e8;color:#ffffff;text-decoration:none;border-radius:4px;\">Cambiar mi contraseña</a></p>
                    <p>Si no solicitaste este cambio, ignora este mensaje.</p>
                """
                send_email('Restablece tu contraseña', MAIL_DEFAULT_SENDER, [email], body, html)
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
    ngrok.set_auth_token(NGROK_AUTHTOKEN)
    if NGROK_ENABLED:
        try:
            public_url = ngrok.connect(5000)
            print(f"Tu URL pública es: {public_url}")
        except Exception as e:
            logging.warning("No se pudo iniciar ngrok: %s", e)
            print("ngrok no pudo iniciarse. Ejecuta la app localmente en http://127.0.0.1:5000")
    else:
        print("ngrok está deshabilitado. Ejecuta la app localmente en http://127.0.0.1:5000")

    app.run(debug=True, host='0.0.0.0', port=5000)