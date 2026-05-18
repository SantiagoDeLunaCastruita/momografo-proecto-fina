from flask import Flask, render_template, request, redirect, url_for, session, g
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
from pymongo.server_api import ServerApi
import os

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

def get_db():
    if 'db' not in g:
        g.db = client['gestor_tareas']
    return g.db


@app.route('/')
def index():
    return render_template('pagina_de_inicio.html')

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

# --- RUTA DE SESIÓN ---
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
        return redirect(url_for('ver_tareas'))
    return redirect(url_for('index'))

@app.route('/tareas')
def ver_tareas():
    if 'usuario_id' not in session: return redirect(url_for('index'))
    return "<h1>Bienvenido</h1>"

if __name__ == '__main__':
    app.run(debug=True)
    
    


