from flask import Flask, render_template
from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)

# Conexión a MongoDB
client = MongoClient(os.getenv('MONGODB_URI'))
db = client['chistes']

@app.route('/')
def home():
    return render_template('layout.html')

if __name__ == '__main__':
    app.run(debug=True)

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