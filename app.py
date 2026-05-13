from flask import Flask, render_template, request, jsonify
from pymongo import MongoClient
from dotenv import load_dotenv
import os
from bson.objectid import ObjectId

load_dotenv()

app = Flask(__name__)

# Conexión a MongoDB Atlas
MONGODB_URI = os.getenv('MONGODB_URI')
client = MongoClient(MONGODB_URI)
db = client['chistes']  # Nombre de MONGODB_URI=mongodb+srv://tu_usuario:tu_contraseña@cluster.mongodb.net/chistes?retryWrites=true&w=majoritytu base de datos
chistes_collection = db['chistes']  # Colección de chistes

@app.route('/')
def home():
    return render_template('base.html')

@app.route('/api/chistes', methods=['GET'])
def obtener_chistes():
    chistes = list(chistes_collection.find({}, {'_id': 1, 'titulo': 1, 'contenido': 1, 'autor': 1}))
    for chiste in chistes:
        chiste['_id'] = str(chiste['_id'])
    return jsonify(chistes)

@app.route('/api/chistes', methods=['POST'])
def crear_chiste():
    datos = request.get_json()
    resultado = chistes_collection.insert_one({
        'titulo': datos.get('titulo'),
        'contenido': datos.get('contenido'),
        'autor': datos.get('autor')
    })
    return jsonify({'id': str(resultado.inserted_id)}), 201

if __name__ == '__main__':
    app.run(debug=True)