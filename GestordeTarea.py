from flask import Flask, render_template, request, redirect, url_for, session, g
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
from pymongo.server_api import ServerApi
import os
from flask_mail import Mail, Message

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


uri = "mongodb+srv://Said_Ramirez:NfT1w9CGzgETVGuV@escuela.5rt7g7m.mongodb.net/?appName=Escuela"
# Create a new client and connect to the server
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
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.sendgrid.net')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')

mail = Mail(app)

def get_db():
    if 'db' not in g:
        g.db = client['gestor_tareas']
    return g.db


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
                msg = Message('Recuperar contraseña', sender=os.getenv('MAIL_DEFAULT_SENDER'), recipients=[email])
                msg.body = f'Hola {user["nombre"]},\n\nTu contraseña es: {user["password"]}\n\nNo compartas esto con nadie.'
                mail.send(msg)
                return "Correo enviado correctamente. Revisa tu bandeja de entrada."
            except Exception as e:
                return f"Error al enviar el correo: {str(e)}"
        else:
            return "El correo no existe en nuestro sistema."
    
    return render_template('recuperar.html')


if __name__ == '__main__':
    app.run(debug=True)
    
    


