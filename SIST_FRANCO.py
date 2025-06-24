from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, make_response, send_file
import os
import json
import gspread
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import locale
import traceback # Importar para depuración
import re # Importar para usar expresiones regulares
import requests # Importar para hacer peticiones HTTP a URLs de imagen
from werkzeug.security import generate_password_hash, check_password_hash # Importar para hashing de contraseñas
from functools import wraps # Importar wraps para el decorador
import calendar # Importar el módulo calendar
import base64 # Importar para decodificar Base64

# Para la generación de PDF
from fpdf import FPDF
import io

# Configurar idioma español para los meses y fechas
# Intenta con 'es_ES.utf8' para Linux/macOS o 'Spanish_Spain.1252' para Windows
# Si falla, usa una configuración más genérica o vacío
try:
    locale.setlocale(locale.LC_TIME, 'es_ES.utf8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_TIME, 'es_AR.utf8') # Para Argentina específicamente
    except locale.Error:
        locale.setlocale(locale.LC_TIME, '') # Configuración genérica del sistema

# Cargar variables de entorno desde el archivo .env
load_dotenv()

app = Flask(__name__)
# Obtener la clave secreta de las variables de entorno o usar una por defecto para desarrollo
# IMPORTANTE: CAMBIA 'una_clave_secreta_muy_segura_para_produccion' EN RENDER CON UNA CLAVE LARGA Y ALEATORIA.
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'una_clave_secreta_muy_segura_para_produccion')

# --- CONFIGURACIÓN GOOGLE SHEETS ---
# Define los alcances de acceso para Google Sheets y Drive
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

# Carga las credenciales del servicio de Google Sheets
# Primero intenta cargar desde un archivo local 'credentials.json' (para desarrollo local)
if os.path.exists("credentials.json"):
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        print("DEBUG: Credenciales cargadas desde 'credentials.json'.")
    except Exception as e:
        raise Exception(f"ERROR: Error al cargar credenciales desde 'credentials.json': {e}")
else:
    # Si no encuentra el archivo, intenta cargar desde la variable de entorno (para Render/producción)
    json_str = os.getenv("GOOGLE_SERVICE_ACCOUNT")
    
    # --- Logging adicional para depuración ---
    # Imprime los primeros 50 caracteres para evitar mostrar toda la clave si es muy larga,
    # pero para verificar si hay algo.
    print(f"DEBUG: Valor de GOOGLE_SERVICE_ACCOUNT (primeros 50 chars): {json_str[:50]}..." if json_str else "DEBUG: GOOGLE_SERVICE_ACCOUNT está vacía o no definida.")
    # --- Fin Logging adicional ---

    if not json_str:
        # Lanza una excepción si las credenciales no se encuentran en ningún lugar
        raise Exception("ERROR: No se encontró 'GOOGLE_SERVICE_ACCOUNT' en variables de entorno ni 'credentials.json' local.")
    
    # Decodificar el Base64 si la variable de entorno se cargó como tal (práctica segura)
    try:
        # Esto asume que el JSON está codificado en Base64. Si no, quita el b64decode.
        cred_dict = json.loads(base64.b64decode(json_str).decode('utf-8'))
        print("DEBUG: Credenciales decodificadas de Base64 y JSON cargado exitosamente.")
    except (TypeError, json.JSONDecodeError) as e: # Catch TypeError for non-base64 input
        # Si no es Base64 válido o JSON inválido, asume que es JSON en texto plano
        print(f"Advertencia: 'GOOGLE_SERVICE_ACCOUNT' no es una cadena Base64 válida o JSON inválido. Intentando interpretar como JSON plano. Error: {e}")
        try:
            cred_dict = json.loads(json_str)
            print("DEBUG: Credenciales cargadas como JSON plano exitosamente.")
        except json.JSONDecodeError as json_e:
            raise Exception(f"ERROR: La variable de entorno 'GOOGLE_SERVICE_ACCOUNT' no contiene JSON válido ni Base64 válido: {json_e}")

    creds = ServiceAccountCredentials.from_json_keyfile_dict(cred_dict, scope)

# Autoriza al cliente de gspread con las credenciales obtenidas
client = gspread.authorize(creds)

# --- ENCABEZADOS ESPERADOS PARA LA HOJA "creditocap" ---
# ¡IMPORTANTE! ESTA LISTA DEBE COINCIDIR EXACTAMENTE EN ORDEN Y NOMBRE
# CON LA PRIMERA FILA (ENCABEZADOS) DE TU HOJA DE GOOGLE SHEETS "creditocap".
# Se ha ajustado el orden de 'vendedor', 'monto' y 'detalle de venta'.
CREDITOCAP_HEADERS = [
    "n° de factura",             # A (0)
    "fecha de venta",            # B (1)
    "nombre completo",           # C (2)
    "dni",                       # D (3)
    "tel",                       # E (4)
    "domicilio",                 # F (5)
    "articulo vendido",          # G (6)
    "tipo de pago",              # H (7)
    "vendedor",                  # I (8) <-- POSICIÓN CORRECTA
    "monto",                     # J (9) <-- POSICIÓN CORRECTA
    "detalle de venta",          # K (10)
    # Pagos adicionales (4 columnas por cada pago, hasta 5 pagos adicionales, haciendo un total de 31 columnas)
    "pago_adicional_1_factura",  # L (11)
    "pago_adicional_1_fecha",    # M (12)
    "pago_adicional_1_tipo",     # N (13)
    "monto_adicional_1",         # O (14)
    "pago_adicional_2_factura",  # P (15)
    "pago_adicional_2_fecha",    # Q (16)
    "pago_adicional_2_tipo",     # R (17)
    "monto_adicional_2",         # S (18)
    "pago_adicional_3_factura",  # T (19)
    "pago_adicional_3_fecha",    # U (20)
    "pago_adicional_3_tipo",     # V (21)
    "monto_adicional_3",         # W (22)
    "pago_adicional_4_factura",  # X (23)
    "pago_adicional_4_fecha",    # Y (24)
    "pago_adicional_4_tipo",     # Z (25)
    "monto_adicional_4",         # AA (26)
    "pago_adicional_5_factura",  # AB (27)
    "pago_adicional_5_fecha",    # AC (28)
    "pago_adicional_5_tipo",     # AD (29)
    "monto_adicional_5"          # AE (30)
]


# --- USUARIOS Y ROLES ---
# IMPORTANTE: ESTE DICCIONARIO CON CONTRASEÑAS HARDCODEADAS ES UNA VULNERABILIDAD DE SEGURIDAD.
# PARA PRODUCCIÓN, DEBERÍAS HASHEAR LAS CONTRASEÑAS Y ALMACENAR LOS USUARIOS EN UNA BASE DE DATOS.
# TODAS LAS CONTRASEÑAS DEBEN SER HASHEADAS CON generate_password_hash().
USERS = {
    "admin": {
        "password": generate_password_hash(os.getenv('ADMIN_PASSWORD', 'admin123')),
        "role": "admin"
    },
    "cristian": {
        "password": generate_password_hash(os.getenv('CRISTIAN_PASSWORD', 'rivadavia620')), # Contraseña hasheada
        "role": "supervisor"
    },
    "delfi": {
        "password": generate_password_hash(os.getenv('DELFI_PASSWORD', 'rivadavia620')), # Contraseña hasheada
        "role": "supervisor"
    },
    "trento": {
        "password": generate_password_hash(os.getenv('TRENTO_PASSWORD', 'trento')), # Contraseña hasheada
        "role": "supervisor"
    },
    "tete": {
        "password": generate_password_hash(os.getenv('TETE_PASSWORD', 'tete123')), # Contraseña hasheada
        "role": "interior"
    },
    "int2": {
        "password": generate_password_hash(os.getenv('INT2_PASSWORD', 'int456')), # Contraseña hasheada
        "role": "interior"
    },
    "int3": {
        "password": generate_password_hash(os.getenv('INT3_PASSWORD', 'int789')), # Contraseña hasheada
        "role": "interior"
    }
}

# --- Decorador para rutas que requieren autenticación ---
def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get('logged_in'):
                flash("Por favor, inicia sesión para acceder a esta página.", "info")
                return redirect(url_for('login'))
            if role and session.get('role') != role:
                flash("No tienes permisos para acceder a esta página.", "danger")
                # Redirige al menú del rol actual si no tiene permiso para el solicitado
                current_role_menu = {
                    "admin": "menu1",
                    "supervisor": "menu2",
                    "interior": "menu3"
                }.get(session.get('role'), 'login')
                return redirect(url_for(current_role_menu))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- RUTAS DE LA APLICACIÓN ---

# Redirige la ruta raíz a la página de login
@app.route('/')
def home():
    return redirect(url_for('login'))

# Ruta para el login de usuarios
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username') # Obtiene el nombre de usuario del formulario
        password = request.form.get('password') # Obtiene la contraseña del formulario
        
        print(f"DEBUG_LOGIN: Intento de login para usuario: '{username}'")
        print(f"DEBUG_LOGIN: Contraseña recibida (sin hash): '{password}' (¡No mostrar en producción!)") # Cuidado al imprimir contraseñas
        
        user = USERS.get(username) # Busca el usuario en el diccionario USERS

        if user:
            print(f"DEBUG_LOGIN: Usuario '{username}' encontrado en la lista de usuarios.")
            if check_password_hash(user["password"], password):
                print(f"DEBUG_LOGIN: Contraseña para '{username}' verificada correctamente. ¡Login exitoso!")
                session['logged_in'] = True # Establece la sesión como logueada
                session['user'] = username # Guarda el nombre de usuario en la sesión
                session['role'] = user["role"] # Guarda el rol del usuario en la sesión

                # Redirige según el rol del usuario
                if user["role"] == "admin":
                    print(f"DEBUG_LOGIN: Redirigiendo a menu1 para admin.")
                    return redirect(url_for('menu1'))
                elif user["role"] == "supervisor":
                    print(f"DEBUG_LOGIN: Redirigiendo a menu2 para supervisor.")
                    # Pasa el usuario y rol a menu2
                    return redirect(url_for('menu2', username=session['user'], role=session['role']))
                elif user["role"] == "interior":
                    print(f"DEBUG_LOGIN: Redirigiendo a menu3 para interior.")
                    return redirect(url_for('menu3'))
            else:
                print(f"DEBUG_LOGIN: Fallo de verificación de contraseña para '{username}'.")
                flash("Usuario o contraseña incorrectos", "danger") # Mensaje de error si las credenciales son inválidas
        else:
            print(f"DEBUG_LOGIN: Usuario '{username}' NO encontrado en la lista de usuarios.")
            flash("Usuario o contraseña incorrectos", "danger") # Mensaje de error si las credenciales son inválidas

    return render_template('login.html') # Renderiza la plantilla de login

# Ruta para cerrar sesión
@app.route('/logout')
def logout():
    session.clear() # Limpia todas las variables de sesión
    print("DEBUG_LOGOUT: Sesión limpiada. Redirigiendo a login.")
    return redirect(url_for('login')) # Redirige a la página de login

# Rutas de menú para diferentes roles
@app.route('/menu1')
@login_required(role='admin')
def menu1():
    return render_template('menu1.html', user=session.get('user')) # Renderiza el menú para admin

@app.route('/menu2')
@login_required(role='supervisor')
def menu2():
    # Asegúrate de pasar el usuario y rol a la plantilla, ya que el decorador ya validó el acceso
    return render_template('menu2.html', username=session.get('user'), role=session.get('role')) # Renderiza el menú para supervisor, pasando username y role

@app.route('/menu3')
@login_required(role='interior')
def menu3():
    return render_template('menu3.html', user=session.get('user'))

# Rutas de productos
@app.route('/lista1')
@login_required()
def lista1():
    try:
        client = get_google_sheets_client()
        spreadsheet = client.open(SPREADSHEET_NAME)
        hoja = spreadsheet.worksheet("lista1")
        registros = hoja.get_all_records()
        return render_template('lista1.html', registros=registros)
    except Exception as e:
        app.logger.error(f"Error en lista1: {str(e)}")
        flash("Error al cargar los datos del catálogo", "danger")
        return render_template('lista1.html', registros=[])

@app.route('/product_catalog')
@login_required()
def product_catalog():
    return redirect(url_for('lista1'))

# API de productos
@app.route('/api/get_lista1_items', methods=['GET'])
@login_required()
def get_lista1_items():
    try:
        client = get_google_sheets_client()
        spreadsheet = client.open(SPREADSHEET_NAME)
        hoja = spreadsheet.worksheet("lista1")
        data = hoja.get_all_values()

        if not data:
            return jsonify([])

        headers = [h.strip() for h in data[0]]
        items = []

        for row in data[1:]:
            item_data = {}
            for col_index, header in enumerate(headers):
                value = row[col_index].strip() if col_index < len(row) else ""

                if header in ['cont efectivo', 'PRECIO FINAL', '2 CUOTAS DE', '3 CUOTAS DE', 
                             '6 CUOTAS DE', '9 CUOTAS DE', '12 CUOTAS DE']:
                    try:
                        clean_value = value.replace(',', '.')
                        item_data[header] = float(clean_value)
                    except ValueError:
                        item_data[header] = 0.0
                elif header == 'URL Imagen':
                    item_data['image_id'] = get_drive_file_id(value) or 'NO_IMAGE'
                else:
                    item_data[header] = value
            
            if item_data.get('Nombre Producto'):
                items.append(item_data)
        
        return jsonify(items)

    except Exception as e:
        app.logger.error(f"Error en get_lista1_items: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/get_image/<string:file_id>')
@login_required()
def get_image(file_id):
    if not file_id or file_id == 'NO_IMAGE':
        return redirect('https://placehold.co/100x100/A0A0A0/FFFFFF?text=Sin%20Imagen')

    try:
        drive_url = f"https://drive.google.com/uc?export=view&id={file_id}"
        response = requests.get(drive_url, stream=True, timeout=10)
        response.raise_for_status()
        return send_file(BytesIO(response.content), mimetype=response.headers.get('Content-Type', 'image/jpeg'))
    except Exception as e:
        app.logger.error(f"Error en get_image: {str(e)}")
        return redirect('https://placehold.co/100x100/FF0000/FFFFFF?text=Error%20Imagen')

# Rutas de presupuestos
@app.route('/presupuesto_creator')
@login_required()
def presupuesto_creator():
    return render_template('presupuesto_creator.html')

@app.route('/presupuesto')
@login_required()
def presupuesto():
    try:
        client = get_google_sheets_client()
        spreadsheet = client.open(SPREADSHEET_NAME)
        hoja = spreadsheet.worksheet("presupuestos")
        registros = hoja.get_all_records()
        return render_template('presupuesto.html', registros=registros)
    except Exception as e:
        app.logger.error(f"Error en presupuesto: {str(e)}")
        flash("Error al cargar los presupuestos", "danger")
        return render_template('presupuesto.html', registros=[])

# Rutas de créditos y pagarés
@app.route('/registro_credito', methods=['GET', 'POST'])
@login_required()
def registro_credito():
    if request.method == 'POST':
        try:
            client = get_google_sheets_client()
            spreadsheet = client.open(SPREADSHEET_NAME)
            hoja = spreadsheet.worksheet("creditocap")

            # Validación de datos
            required_fields = ['factura', 'fecha', 'nombre', 'dni', 'articulo', 'tipo_pago']
            for field in required_fields:
                if not request.form.get(field):
                    flash(f"El campo {field.replace('_', ' ')} es requerido", "danger")
                    return redirect(url_for('registro_credito'))

            # Procesamiento de datos
            data = [
                request.form.get("factura"),
                request.form.get("fecha"),
                request.form.get("nombre"),
                request.form.get("dni"),
                request.form.get("tel"),
                request.form.get("domicilio"),
                request.form.get("articulo"),
                request.form.get("tipo_pago"),
                request.form.get("detalle"),
                '', '',  # Columnas intermedias
            ]

            # Pagos adicionales
            for i in range(1, 7):  # Máximo 6 pagos adicionales
                data.extend([
                    request.form.get(f"pago_adicional_{i}_factura", ''),
                    request.form.get(f"pago_adicional_{i}_fecha", ''),
                    request.form.get(f"pago_adicional_{i}_tipo", ''),
                    request.form.get(f"monto_adicional_{i}", '')
                ])

            # Datos finales
            data.extend([
                session.get("user"),
                float(request.form.get("monto", 0))
            ])

            hoja.append_row(data)
            flash("✅ Venta registrada correctamente.", "success")
            return redirect(url_for('registro_credito'))

        except Exception as e:
            app.logger.error(f"Error en registro_credito (POST): {str(e)}")
            flash("❌ Error al registrar la venta", "danger")
            return redirect(url_for('registro_credito'))

    # GET: Mostrar registros
    try:
        client = get_google_sheets_client()
        spreadsheet = client.open(SPREADSHEET_NAME)
        hoja = spreadsheet.worksheet("creditocap")
        registros = hoja.get_all_records()
        return render_template('pagarecap.html', all_registros=registros)
    except Exception as e:
        app.logger.error(f"Error en registro_credito (GET): {str(e)}")
        flash("❌ Error al cargar los registros", "danger")
        return render_template('pagarecap.html', all_registros=[])

# API para créditos
@app.route('/api/get_credit_details/<string:dni_cliente>', methods=['GET'])
@login_required()
def get_credit_details_json(dni_cliente):
    try:
        client = get_google_sheets_client()
        spreadsheet = client.open(SPREADSHEET_NAME)
        hoja = spreadsheet.worksheet("creditocap")
        all_records = hoja.get_all_records()
        
        credit_data = next((r for r in all_records if str(r.get('dni', '')).strip() == dni_cliente.strip()), None)
        if not credit_data:
            return jsonify({"error": "No se encontró el crédito"}), 404

        # Procesamiento de pagos y fechas esperadas (similar al original)
        # ...

        return jsonify({
            "credit_data": credit_data,
            # ... otros datos
        })

    except Exception as e:
        app.logger.error(f"Error en get_credit_details_json: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Exportación a PDF
@app.route('/exportar_creditos_pdf')
@login_required()
def exportar_creditos_pdf():
    try:
        client = get_google_sheets_client()
        spreadsheet = client.open(SPREADSHEET_NAME)
        hoja = spreadsheet.worksheet("creditocap")
        registros = hoja.get_all_records()

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=10)

        # Cabeceras
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 10, "Resumen de Registros de Créditos", 0, 1, 'C')
        pdf.ln(5)

        # Contenido (similar al original)
        # ...

        pdf_output = pdf.output(dest='S')
        response = make_response(pdf_output)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = 'attachment; filename=registros_creditos.pdf'
        return response

    except Exception as e:
        app.logger.error(f"Error en exportar_creditos_pdf: {str(e)}")
        flash("❌ Error al generar el PDF", "danger")
        return redirect(url_for('registro_credito'))

# Configuración para producción
if __name__ == '__main__':
    debug = os.getenv('FLASK_DEBUG', 'False') == 'True'
    app.run(debug=debug, host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
