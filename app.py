from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import os
from pymongo import MongoClient

app = Flask(__name__)
CORS(app)

# Conexión MongoDB
MONGO_URI = os.environ.get('MONGO_URI')
client = MongoClient(MONGO_URI)
db = client['el_potrillo_db'] 

# --- SECCIÓN 1: VISTAS (Frontend - Lo que ve el usuario) ---
# Aquí es donde Flask busca tus archivos HTML en la carpeta 'templates'

@app.route('/')
def index():
    return render_template('indexlogin.html')

@app.route('/menu')
def pagina_menu():
    return render_template('menu.html') # Asegúrate de que este archivo exista en /templates

@app.route('/ventas')
def pagina_ventas():
    return render_template('ventas.html') # Asegúrate de que este archivo exista en /templates

@app.route('/clientes')
def pagina_clientes():
    return render_template('clientes.html') # Asegúrate de que este archivo exista en /templates


# --- SECCIÓN 2: API (Backend - Lo que usa tu código JS para guardar datos) ---

# API Menú
@app.route('/api/menu', methods=['GET'])
def get_menu():
    try:
        items = list(db.menu.find({}, {'_id': 0}))
        return jsonify(items), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# API Ventas
@app.route('/api/ventas', methods=['POST'])
def guardar_venta():
    try:
        data = request.json
        db.ventas.insert_one(data)
        return jsonify({'status': 'Venta registrada'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# API Clientes
@app.route('/api/clientes', methods=['GET'])
def get_clientes():
    try:
        clientes = list(db.Clientess.find({}, {'_id': 0}))
        return jsonify(clientes), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)