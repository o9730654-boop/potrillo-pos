from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from pymongo import MongoClient
from bson import ObjectId
import jwt
import datetime
import os
from functools import wraps

app = Flask(__name__, template_folder='../templates', static_folder='../static')
CORS(app)

SECRET_KEY = os.environ.get('SECRET_KEY', 'tu_super_clave_secreta_12345')
MONGO_URI = os.environ.get('MONGO_URI')

# Conexión centralizada a MongoDB Atlas
client = MongoClient(MONGO_URI)
db = client['elpotrillo_db']

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'message': 'Token de autenticación faltante.'}), 401
        try:
            token = token.split()[1]
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            current_user = data['user_id']
        except Exception:
            return jsonify({'message': 'Token inválido o expirado.'}), 401
        return f(current_user, *args, **kwargs)
    return decorated

# ─── RUTAS HTML (Exactamente iguales a tu archivo original) ───────────────────
@app.route('/')
def index():
    return render_template('indexlogin.html')

@app.route('/menu')
def menu_page():
    return render_template('indexmenu.html')

@app.route('/mesas')
def mesas_page():
    return render_template('mesas.html')

@app.route('/reporte')
def reporte_page():
    return render_template('reporte.html.html')

@app.route('/cocina')
def view_cocina():
    return render_template('cocina.html')

@app.route('/reporte-ventas')
def reporte_ventas_page():
    return render_template('reportedeventas.html')

@app.route('/inventario')
def inventario_page():
    return render_template('inventario.html')

# ─── API: LOGIN ───────────────────────────────────────────────────────────────
@app.route('/api/login', methods=['POST'])
def login():
    data     = request.get_json()
    username = data.get('username')
    password = data.get('password')
    usuarios = {
        "admin":  {"pass": "12345", "rol": "admin"},
        "cocina": {"pass": "1",     "rol": "cocinero"},
        "hoster": {"pass": "2",     "rol": "hoster"},
        "mesero": {"pass": "3",     "rol": "mesero"},
        "cajero": {"pass": "4",     "rol": "cajero"}
    }
    user_data = usuarios.get(username)
    if user_data and user_data['pass'] == password:
        token_payload = {
            'user_id': username,
            'rol': user_data['rol'],
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }
        token = jwt.encode(token_payload, SECRET_KEY, algorithm="HS256")
        return jsonify({'message': 'Éxito', 'token': token, 'rol': user_data['rol']}), 200
    return jsonify({'message': 'Credenciales incorrectas'}), 401

# ─── API: MENÚ ────────────────────────────────────────────────────────────────
@app.route('/api/menu', methods=['GET'])
def get_menu():
    try:
        rows = list(db.menu.find())
        result = []
        for r in rows:
            result.append({
                "id_plato": r.get("id_plato", str(r.get("_id"))),
                "Mnu_nombre_plato": r.get("Mnu_nombre_plato", r.get("nombre")),
                "Mnu_descripcion": r.get("Mnu_descripcion", r.get("descripcion", "")),
                "Mnu_precio": float(r.get("Mnu_precio", r.get("precio", 0)))
            })
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'message': str(e)}), 500

# ─── API: PEDIDOS DE COCINA ───────────────────────────────────────────────────
@app.route('/api/cocina/pedidos', methods=['GET'])
@login_required
def get_pedidos_cocina(current_user):
    try:
        tz_mx = datetime.timezone(datetime.timedelta(hours=-7))
        hoy_str = datetime.datetime.now(tz_mx).strftime('%Y-%m-%d')
        
        # Filtramos en Mongo usando la fecha en formato texto YYYY-MM-DD
        query = {
            "estado": "Pendiente",
            "fecha": {"$regex": f"^{hoy_str}"}
        }
        rows = list(db.formulario.find(query).sort("ticket_id", 1))
        result = []
        for r in rows:
            result.append({
                "ticket_id": r.get("ticket_id"),
                "cliente": r.get("cliente"),
                "producto": r.get("producto"),
                "cantidad": r.get("cantidad"),
                "estado": r.get("estado")
            })
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─── API: CHECKOUT con descuento automático de inventario ────────────────────
@app.route('/api/checkout', methods=['POST'])
@login_required
def register_sale(current_user):
    data    = request.get_json()
    cliente = data.get('cliente', 'Mostrador')
    metodo  = data.get('metodo_pago', 'Pendiente')
    items   = data.get('items', [])
    
    tz_mx = datetime.timezone(datetime.timedelta(hours=-7))
    ahora = datetime.datetime.now(tz_mx).strftime('%Y-%m-%d %H:%M:%S')
    
    try:
        # Obtener el MAX ticket_id de la colección formulario
        last_ticket = db.formulario.find_one({}, sort=[("ticket_id", -1)])
        nuevo_ticket = (last_ticket['ticket_id'] + 1) if last_ticket else 1

        for item in items:
            # Registrar en formulario de MongoDB
            db.formulario.insert_one({
                "cliente": cliente,
                "telefono": "",
                "producto": item['name'],
                "precio": item['price'],
                "cantidad": item['qty'],
                "fecha": ahora,
                "metodo_pago": metodo,
                "estado": 'Pendiente',
                "ticket_id": nuevo_ticket
            })

            # Buscar id_plato por nombre del platillo (Case Insensitive)
            plato = db.menu.find_one({"Mnu_nombre_plato": {"$regex": f"^{item['name']}$", "$options": "i"}})
            if plato:
                id_plato = plato.get("id_plato")
                
                # Buscar recetas vinculadas a ese plato
                recetas = list(db.recetas.find({"id_plato": id_plato}))
                for r in recetas:
                    id_insumo = r.get("id_insumo")
                    cant_requerida = float(r.get("cantidad_requerida", 0))
                    
                    # Descontar del inventario
                    inv_item = db.inventario.find_one({"id_insumo": id_insumo})
                    if inv_item:
                        cant_actual = float(inv_item.get("cantidad_actual", 0))
                        nuevo_stock = max(0, cant_actual - (cant_requerida * item['qty']))
                        
                        db.inventario.update_one(
                            {"id_insumo": id_insumo},
                            {"$set": {
                                "cantidad_actual": nuevo_stock,
                                "fecha_actualizacion": datetime.datetime.now(tz_mx).strftime('%Y-%m-%d')
                            }}
                        )
        return jsonify({'message': 'Venta registrada', 'ticket': nuevo_ticket}), 201
    except Exception as e:
        return jsonify({'message': f'Error al guardar: {str(e)}'}), 500

# ─── API: REPORTE DETALLADO (Equivalente al STRING_AGG de Postgres) ──────────
@app.route('/api/reporte/detallado', methods=['GET'])
@login_required
def get_reporte_detallado(current_user):
    try:
        tz_mx = datetime.timezone(datetime.timedelta(hours=-7))
        hoy_str = datetime.datetime.now(tz_mx).strftime('%Y-%m-%d')
        
        # Agrupamos por ticket_id de forma análoga a tu consulta SQL anterior
        pipeline = [
            {"$match": {"fecha": {"$regex": f"^{hoy_str}"}}},
            {"$group": {
                "_id": {
                    "ticket_id": "$ticket_id",
                    "cliente": "$cliente",
                    "metodo_pago": "$metodo_pago"
                },
                "items": {"$push": {"producto": "$producto", "cantidad": "$cantidad"}},
                "total_items": {"$sum": "$cantidad"},
                "gran_total": {"$sum": {"$multiply": ["$precio", "$cantidad"]}},
                "max_fecha": {"$max": "$fecha"}
            }},
            {"$sort": {"_id.ticket_id": -1}}
        ]
        
        rows = list(db.formulario.aggregate(pipeline))
        result = []
        for r in rows:
            # Recreamos el formato HTML de productos: "Tacos (2)<br>Refresco (1)"
            prod_list = [f"{i['producto']} ({i['cantidad']})" for i in r['items']]
            prod_list.sort()
            productos_html = "<br>".join(prod_list)
            
            result.append({
                "ticket_id": r["_id"]["ticket_id"],
                "cliente": r["_id"]["cliente"],
                "productos": productos_html,
                "total_items": r["total_items"],
                "gran_total": r["gran_total"],
                "metodo_pago": r["_id"]["metodo_pago"],
                "fecha": r["max_fecha"]
            })
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─── API: CORTE DE CAJA ───────────────────────────────────────────────────────
@app.route('/api/reporte/corte', methods=['GET'])
@login_required
def get_corte_reporte(current_user):
    try:
        tz_mx = datetime.timezone(datetime.timedelta(hours=-7))
        hoy_str = datetime.datetime.now(tz_mx).strftime('%Y-%m-%d')
        
        # Ventas en Efectivo
        efectivo_items = list(db.formulario.find({"fecha": {"$regex": f"^{hoy_str}"}, "metodo_pago": "Efectivo"}))
        efectivo = sum(float(r['precio']) * float(r['cantidad']) for r in efectivo_items)
        
        # Ventas en Tarjeta
        tarjeta_items = list(db.formulario.find({"fecha": {"$regex": f"^{hoy_str}"}, "metodo_pago": "Tarjeta"}))
        tarjeta = sum(float(r['precio']) * float(r['cantidad']) for r in tarjeta_items)
        
        return jsonify({
            'fecha_corte': hoy_str, 
            'ventas_efectivo': efectivo,
            'ventas_tarjeta': tarjeta, 
            'total_general': efectivo + tarjeta
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─── API: FINALIZAR / COBRAR TICKET ──────────────────────────────────────────
@app.route('/api/cocina/finalizar_ticket/<int:tid>', methods=['POST'])
@login_required
def finalizar_ticket(current_user, tid):
    try:
        db.formulario.update_many({"ticket_id": tid}, {"$set": {"estado": "Terminado"}})
        return jsonify({'message': f'Ticket #{tid} listo'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cobrar/ticket/<int:tid>', methods=['PUT'])
@login_required
def cobrar_ticket_id(current_user, tid):
    data = request.get_json()
    try:
        db.formulario.update_many({"ticket_id": tid}, {"$set": {"metodo_pago": data.get('metodo_pago')}})
        return jsonify({'message': 'Cobro realizado'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─── API: NOTIFICACIONES ──────────────────────────────────────────────────────
@app.route('/api/notificaciones/listos', methods=['GET'])
@login_required
def obtener_notificaciones(current_user):
    try:
        tz_mx = datetime.timezone(datetime.timedelta(hours=-7))
        hoy_str = datetime.datetime.now(tz_mx).strftime('%Y-%m-%d')
        
        pipeline = [
            {"$match": {"estado": "Terminado", "fecha": {"$regex": f"^{hoy_str}"}}},
            {"$group": {"_id": {"ticket_id": "$ticket_id", "cliente": "$cliente"}}},
            {"$limit": 5}
        ]
        rows = list(db.formulario.aggregate(pipeline))
        result = [{"ticket_id": r["_id"]["ticket_id"], "cliente": r["_id"]["cliente"]} for r in rows]
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─── API: INVENTARIO ─────────────────────────────────────────────────────────
@app.route('/api/inventario', methods=['GET'])
@login_required
def get_inventario(current_user):
    try:
        rows = list(db.inventario.find().sort([("categoria", 1), ("nombre_insumo", 1)]))
        result = []
        for r in rows:
            result.append({
                "id": r.get("id_insumo"),
                "nombre": r.get("nombre_insumo"),
                "categoria": r.get("categoria"),
                "cantidad": r.get("cantidad_actual"),
                "unidad": r.get("unidad_medida"),
                "stock_min": r.get("punto_reorden"),
                "ultimo_costo": r.get("ultimo_costo"),
                "proveedor_id": r.get("proveedor_id"),
                "fecha_actualizacion": r.get("fecha_actualizacion")
            })
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/inventario', methods=['POST'])
@login_required
def crear_ingrediente(current_user):
    d = request.get_json()
    try:
        tz_mx = datetime.timezone(datetime.timedelta(hours=-7))
        hoy_str = datetime.datetime.now(tz_mx).strftime('%Y-%m-%d')
        
        last_item = db.inventario.find_one({}, sort=[("id_insumo", -1)])
        nuevo_id = (last_item['id_insumo'] + 1) if last_item else 1
        
        db.inventario.insert_one({
            "id_insumo": nuevo_id,
            "nombre_insumo": d['nombre'],
            "categoria": d.get('categoria', 'Otros'),
            "cantidad_actual": d['cantidad'],
            "command_medida": d.get('unidad', 'piezas'),
            "punto_reorden": d.get('stock_min', 5),
            "fecha_actualizacion": hoy_str
        })
        return jsonify({"id": nuevo_id, "nombre": d['nombre'], "categoria": d.get('categoria','Otros')}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/inventario/<int:iid>', methods=['PUT'])
@login_required
def actualizar_ingrediente(current_user, iid):
    d = request.get_json()
    try:
        tz_mx = datetime.timezone(datetime.timedelta(hours=-7))
        hoy_str = datetime.datetime.now(tz_mx).strftime('%Y-%m-%d')
        
        db.inventario.update_one(
            {"id_insumo": iid},
            {"$set": {
                "nombre_insumo": d['nombre'],
                "categoria": d.get('categoria', 'Otros'),
                "cantidad_actual": d['cantidad'],
                "unidad_medida": d.get('unidad', 'piezas'),
                "punto_reorden": d.get('stock_min', 5),
                "fecha_actualizacion": hoy_str
            }}
        )
        return jsonify({"id": iid, "nombre": d['nombre']}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/inventario/<int:iid>', methods=['DELETE'])
@login_required
def eliminar_ingrediente(current_user, iid):
    try:
        db.inventario.delete_one({"id_insumo": iid})
        return jsonify({'message': 'Eliminado'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/inventario/<int:iid>/ajustar', methods=['POST'])
@login_required
def ajustar_stock(current_user, iid):
    d    = request.get_json()
    tipo = d.get('tipo')
    cant = float(d.get('cantidad', 0))
    try:
        tz_mx = datetime.timezone(datetime.timedelta(hours=-7))
        hoy_str = datetime.datetime.now(tz_mx).strftime('%Y-%m-%d')
        
        item = db.inventario.find_one({"id_insumo": iid})
        if not item: return jsonify({'error': 'No encontrado'}), 404
        
        cant_actual = float(item.get("cantidad_actual", 0))
        nueva_cant = cant_actual + cant if tipo == 'sumar' else max(0, cant_actual - cant) if tipo == 'restar' else cant
        
        db.inventario.update_one({"id_insumo": iid}, {"$set": {"cantidad_actual": nueva_cant, "fecha_actualizacion": hoy_str}})
        return jsonify({'cantidad': nueva_cant}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─── API: RECETAS ─────────────────────────────────────────────────────────────
@app.route('/api/recetas', methods=['GET'])
@login_required
def get_recetas(current_user):
    try:
        recetas = list(db.recetas.find())
        result = []
        for r in recetas:
            plato = db.menu.find_one({"id_plato": r.get("id_plato")})
            insumo = db.inventario.find_one({"id_insumo": r.get("id_insumo")})
            
            result.append({
                "id_plato": r.get("id_plato"),
                "id_insumo": r.get("id_insumo"),
                "cantidad_requerida": r.get("cantidad_requerida"),
                "nombre_platillo": plato.get("Mnu_nombre_plato") if plato else "Desconocido",
                "ingrediente": insumo.get("nombre_insumo") if insumo else "Desconocido",
                "unidad": insumo.get("unidad_medida") if insumo else "uds"
            })
        result.sort(key=lambda x: (x['nombre_platillo'], x['ingrediente']))
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/recetas', methods=['POST'])
@login_required
def crear_receta(current_user):
    d = request.get_json()
    try:
        db.recetas.insert_one({
            "id_plato": d['id_plato'],
            "id_insumo": d['id_ingrediente'],
            "cantidad_requerida": d['cantidad_usar']
        })
        return jsonify({'message': 'Receta creada'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/recetas/<int:id_plato>/<int:id_insumo>', methods=['DELETE'])
@login_required
def eliminar_receta(current_user, id_plato, id_insumo):
    try:
        db.recetas.delete_one({"id_plato": id_plato, "id_insumo": id_insumo})
        return jsonify({'message': 'Eliminado'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─── API: MENÚ PARA RECETAS (id + nombre) ────────────────────────────────────
@app.route('/api/menu/lista', methods=['GET'])
@login_required
def get_menu_lista(current_user):
    try:
        rows = list(db.menu.find().sort("Mnu_nombre_plato", 1))
        result = [{"id": r.get("id_plato"), "nombre": r.get("Mnu_nombre_plato")} for r in rows]
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─── DEBUG Y VERIFICACIÓN ─────────────────────────────────────────────────────
@app.route('/api/debug/tablas', methods=['GET'])
def debug_tablas():
    try:
        colecciones = db.list_collection_names()
        return jsonify({'colecciones_en_mongo': colecciones}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/loaderio-02da15920fabcf6b26e0709c27fafdd9.txt')
def verify_loader_io():
    return "loaderio-02da15920fabcf6b26e0709c27fafdd9"

app = app