from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from pymongo import MongoClient

app = Flask(__name__)
CORS(app)

# Conexión a MongoDB (Usa la variable de entorno que configuraste en Vercel)
MONGO_URI = os.environ.get('MONGO_URI')
client = MongoClient(MONGO_URI)
db = client['el_potrillo_db']  # Nombre de tu base de datos

# --- RUTAS DE MENÚ ---
@app.route('/api/menu', methods=['GET'])
def get_menu():
    try:
        # Buscamos en la colección 'menu'
        # {'_id': 0} es vital para que no falle el JSON que espera el frontend
        menu = list(db.menu.find({}, {'_id': 0}))
        return jsonify(menu), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- RUTAS DE VENTAS ---
@app.route('/api/ventas', methods=['POST'])
def guardar_venta():
    try:
        data = request.json
        # Guardamos el documento tal cual llega del frontend
        db.ventas.insert_one(data)
        return jsonify({'status': 'Venta registrada con éxito'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- RUTAS DE CLIENTES ---
@app.route('/api/clientes', methods=['GET'])
def get_clientes():
    try:
        clientes = list(db.Clientess.find({}, {'_id': 0}))
        return jsonify(clientes), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)