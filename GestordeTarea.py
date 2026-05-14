from flask import Flask, render_template, request, redirect, url_for, session, g
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()

MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://127.0.0.1:27017/')
client = MongoClient(MONGODB_URI)

app = Flask(__name__)
app.secret_key = 'red_black_2026'

def get_db():
    if 'db' not in g:
        g.db = client['gestor_tareas']
    return g.db


@app.route('/')
def index():
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
    return "<h1>Bienvenido al Panel Rojo y Negro</h1>"

if __name__ == '__main__':
    app.run(debug=True)
    
    


