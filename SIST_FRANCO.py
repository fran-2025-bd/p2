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
# No importamos werkzeug.security ya que no se usará el hashing
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

# Se han eliminado las siguientes líneas para simplificar la depuración,
# pero se recomienda activarlas en producción con HTTPS:
# app.config['SESSION_COOKIE_SECURE'] = True
# app.config['SESSION_COOKIE_HTTPONLY'] = True

# --- CONFIGURACIÓN GOOGLE SHEETS ---
# Define los alcances de acceso para Google Sheets y Drive
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

# Nombre de la hoja de cálculo principal
SPREADSHEET_NAME = "rivadavia" 

# Función para obtener el cliente de Google Sheets
def get_google_sheets_client():
    if not hasattr(app, 'gspread_client'):
        creds = None # Inicializar 'creds' a None al inicio de la función

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
            
            # --- Logging adicional para depuración de GOOGLE_SERVICE_ACCOUNT ---
            print(f"DEBUG_CREDS: Valor de GOOGLE_SERVICE_ACCOUNT (longitud: {len(json_str) if json_str else 0}): '{json_str[:100]}...'")
            # --- Fin Logging adicional ---

            if not json_str:
                raise Exception("ERROR: No se encontró 'GOOGLE_SERVICE_ACCOUNT' en variables de entorno ni 'credentials.json' local.")
            
            cred_dict = None
            try:
                # Intenta cargar como JSON plano primero
                cred_dict = json.loads(json_str)
                print("DEBUG_CREDS: Credenciales cargadas como JSON plano exitosamente.")
            except json.JSONDecodeError as plain_json_error:
                print(f"DEBUG_CREDS: Advertencia: 'GOOGLE_SERVICE_ACCOUNT' no es JSON plano válido. Intentando decodificar de Base64. Error: {plain_json_error}")
                try:
                    # Si falla como JSON plano, intenta decodificar de Base64
                    cred_dict = json.loads(base64.b64decode(json_str).decode('utf-8'))
                    print("DEBUG_CREDS: Credenciales decodificadas de Base64 y JSON cargado exitosamente.")
                except (TypeError, json.JSONDecodeError, UnicodeDecodeError) as base64_error:
                    raise Exception(f"ERROR: La variable de entorno 'GOOGLE_SERVICE_ACCOUNT' no contiene JSON válido (ni plano ni Base64 codificado): {base64_error}")
            
            # Asignar el objeto ServiceAccountCredentials a 'creds'
            if cred_dict:
                creds = ServiceAccountCredentials.from_json_keyfile_dict(cred_dict, scope)
            else:
                raise Exception("ERROR: cred_dict es None después de todos los intentos de carga. Esto no debería ocurrir.")
        
        # Autorizar al cliente de gspread solo si 'creds' ha sido exitosamente inicializado
        if creds: # Se asegura que 'creds' tiene un valor antes de intentar autorizar
            app.gspread_client = gspread.authorize(creds)
        else:
            # Este caso solo debería ocurrir si las excepciones anteriores no atraparon un problema
            raise Exception("ERROR: No se pudieron obtener las credenciales de Google Sheets para la autorización.")

    return app.gspread_client


import os
import json
import base64
import locale
import re
import io
import traceback
from functools import wraps

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from dotenv import load_dotenv
import requests

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

# Se han eliminado las siguientes líneas para simplificar la depuración,
# pero se recomienda activarlas en producción con HTTPS:
# app.config['SESSION_COOKIE_SECURE'] = True
# app.config['SESSION_COOKIE_HTTPONLY'] = True

# --- CONFIGURACIÓN GOOGLE SHEETS ---
# Define los alcances de acceso para Google Sheets y Drive
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

# Nombre de la hoja de cálculo principal
SPREADSHEET_NAME = "rivadavia" 

# Función para obtener el cliente de Google Sheets
def get_google_sheets_client():
    if not hasattr(app, 'gspread_client'):
        creds = None # Inicializar 'creds' a None al inicio de la función

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
            
            # --- Logging adicional para depuración de GOOGLE_SERVICE_ACCOUNT ---
            print(f"DEBUG_CREDS: Valor de GOOGLE_SERVICE_ACCOUNT (longitud: {len(json_str) if json_str else 0}): '{json_str[:100]}...'")
            # --- Fin Logging adicional ---

            if not json_str:
                raise Exception("ERROR: No se encontró 'GOOGLE_SERVICE_ACCOUNT' en variables de entorno ni 'credentials.json' local.")
            
            cred_dict = None
            try:
                # Intenta cargar como JSON plano primero
                cred_dict = json.loads(json_str)
                print("DEBUG_CREDS: Credenciales cargadas como JSON plano exitosamente.")
            except json.JSONDecodeError as plain_json_error:
                print(f"DEBUG_CREDS: Advertencia: 'GOOGLE_SERVICE_ACCOUNT' no es JSON plano válido. Intentando decodificar de Base64. Error: {plain_json_error}")
                try:
                    # Si falla como JSON plano, intenta decodificar de Base64
                    cred_dict = json.loads(base64.b64decode(json_str).decode('utf-8'))
                    print("DEBUG_CREDS: Credenciales decodificadas de Base64 y JSON cargado exitosamente.")
                except (TypeError, json.JSONDecodeError, UnicodeDecodeError) as base64_error:
                    raise Exception(f"ERROR: La variable de entorno 'GOOGLE_SERVICE_ACCOUNT' no contiene JSON válido (ni plano ni Base64 codificado): {base64_error}")
            
            # Asignar el objeto ServiceAccountCredentials a 'creds'
            if cred_dict:
                creds = ServiceAccountCredentials.from_json_keyfile_dict(cred_dict, scope)
            else:
                raise Exception("ERROR: cred_dict es None después de todos los intentos de carga. Esto no debería ocurrir.")
        
        # Autorizar al cliente de gspread solo si 'creds' ha sido exitosamente inicializado
        if creds: # Se asegura que 'creds' tiene un valor antes de intentar autorizar
            app.gspread_client = gspread.authorize(creds)
        else:
            # Este caso solo debería ocurrir si las excepciones anteriores no atraparon un problema
            raise Exception("ERROR: No se pudieron obtener las credenciales de Google Sheets para la autorización.")

    return app.gspread_client


# --- ENCABEZADOS ESPERADOS PARA LA HOJA "creditocap" ---
# ¡IMPORTANTE! ESTA LISTA DEBE COINCIDIR EXACTAMENTE EN ORDEN Y NOMBRE
# CON LA PRIMERA FILA (ENCABEZADOS) DE TU HOJA DE GOOGLE SHEETS "creditocap".
# Se ha ajustado el orden de 'detalle de venta', 'vendedor' y 'monto'.
CREDITOCAP_HEADERS = [
    "n° de factura",             # A (0)
    "fecha de venta",            # B (1)
    "nombre completo",           # C (2)
    "dni",                       # D (3)
    "tel",                       # E (4)
    "domicilio",                 # F (5)
    "articulo vendido",          # G (6)
    "tipo de pago",              # H (7)
    "detalle de venta",          # I (8)
    "vendedor",                  # J (9)
    "monto",                     # K (10)
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
    "monto_adicional_5",         # AE (30)
    "forma_de_pago"              # AF (31) <--- ¡Nombre ajustado a guiones bajos!
]


# --- USUARIOS Y ROLES (SIN HASHING DE CONTRASEÑAS) ---
# ADVERTENCIA: Esta configuración NO es segura para entornos de producción.
# Las contraseñas están en texto plano.
USERS = {
    "admin": {
        "password": os.getenv('ADMIN_PASSWORD', 'admin123'), # Contraseña en texto plano
        "role": "admin"
    },
    "cristian": {
        "password": os.getenv('CRISTIAN_PASSWORD', 'rivadavia620'), # Contraseña en texto plano
        "role": "supervisor"
    },
    "delfi": {
        "password": os.getenv('DELFI_PASSWORD', 'rivadavia620'), # Contraseña en texto plano
        "role": "supervisor"
    },
    "trento": {
        "password": os.getenv('TRENTO_PASSWORD', 'trento'), # Contraseña en texto plano
        "role": "supervisor"
    },
    "tete": {
        "password": os.getenv('TETE_PASSWORD', 'tete123'), # Contraseña en texto plano
        "role": "interior"
    },
    "int2": {
        "password": os.getenv('INT2_PASSWORD', 'int456'), # Contraseña en texto plano
        "role": "interior"
    },
    "int3": {
        "password": os.getenv('INT3_PASSWORD', 'int789'), # Contraseña en texto plano
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
            # *** CAMBIO IMPORTANTE: Comparación de contraseña sin hashing ***
            if user["password"] == password:
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
# Ruta para la lista1
@app.route('/lista1')
@login_required() # Requiere login, pero sin rol específico
def lista1():
    registros = [] # Asegurar que registros siempre es una lista por defecto
    try:
        spreadsheet = get_google_sheets_client().open(SPREADSHEET_NAME) # Abre la hoja de cálculo "rivadavia"
        if spreadsheet is None: # Si open() por alguna razón devuelve None
            raise gspread.exceptions.SpreadsheetNotFound(f"La hoja de cálculo '{SPREADSHEET_NAME}' no pudo ser abierta.")
            
        hoja = spreadsheet.worksheet("lista1") # Selecciona la hoja "lista1"
        if hoja is None: # Si worksheet() por alguna razón devuelve None
            raise gspread.exceptions.WorksheetNotFound(f"La hoja 'lista1' no pudo ser encontrada en '{SPREADSHEET_NAME}'.")

        registros = hoja.get_all_records() # Obtiene todos los registros de la hoja
    except gspread.exceptions.SpreadsheetNotFound as e:
        flash(f"❌ Error: La hoja de cálculo principal no se encontró o no hay permisos: {str(e)}", "danger")
        registros = []
    except gspread.exceptions.WorksheetNotFound as e:
        flash(f"❌ Error: La hoja 'lista1' no se encontró o no hay permisos: {str(e)}", "danger")
        registros = []
    except Exception as e:
        flash(f"Ocurrió un error al cargar los datos: {str(e)}", "danger") # Muestra mensaje de error
        registros = [] # Deja la lista de registros vacía en caso de error

    return render_template('lista1.html', registros=registros) # Renderiza la plantilla lista1

# Función para convertir URL de Google Drive a ID de archivo
def get_drive_file_id(url):
    """
    Extrae el ID de un archivo de Google Drive de varias URLs.
    """
    if not url:
        print("DEBUG: URL de imagen vacía, devolviendo ID vacío.")
        return ""

    # Regex para extraer el ID del archivo de URLs de Google Drive
    # Soporta formatos como /file/d/ID/view, /open?id=ID, /thumbnail?id=ID, y el formato de la vista de carpeta
    match_id = re.search(r'(?:/d/|id=)([a-zA-Z0-9_-]+)', url)
    if match_id:
        file_id = match_id.group(1)
        print(f"DEBUG: ID de imagen extraído de '{url}': {file_id}")
        return file_id
    
    print(f"DEBUG: No se pudo extraer el ID de la imagen de '{url}'. Devolviendo ID vacío.")
    return ""


# API para obtener items de lista1 con manejo de errores numéricos y URL de imagen
@app.route('/api/get_lista1_items', methods=['GET'])
@login_required()
def get_lista1_items():
    try:
        spreadsheet = get_google_sheets_client().open(SPREADSHEET_NAME)
        if spreadsheet is None:
            raise gspread.exceptions.SpreadsheetNotFound(f"La hoja de cálculo '{SPREADSHEET_NAME}' no pudo ser abierta.")
            
        hoja = spreadsheet.worksheet("lista1")
        if hoja is None:
            raise gspread.exceptions.WorksheetNotFound(f"La hoja 'lista1' no pudo ser encontrada en '{SPREADSHEET_NAME}'.")

        # Obtener todos los valores como una lista de listas (raw data)
        data = hoja.get_all_values()

        if not data:
            print("Advertencia: La hoja 'lista1' está vacía o no tiene datos.")
            return jsonify([])

        # La primera fila son los encabezados
        headers = [h.strip() for h in data[0]]
        items = []

        # Recorrer cada fila de datos (empezando desde la segunda fila)
        for row_index, row in enumerate(data[1:], start=2): # start=2 para logs más precisos
            item_data = {}
            for col_index, header in enumerate(headers):
                value = row[col_index].strip() if col_index < len(row) else ""

                # Intenta convertir a numérico solo para las columnas relevantes
                if header in ['cont efectivo', 'PRECIO FINAL', '2 CUOTAS DE', '3 CUOTAS DE', '6 CUOTAS DE', '9 CUOTAS DE', '12 CUOTAS DE']:
                    try:
                        # Reemplazar ',' por '.' para que Python lo interprete como decimal
                        clean_value = value.replace(',', '.')
                        numeric_value = float(clean_value)
                        item_data[header] = numeric_value
                    except ValueError:
                        print(f"DEBUG_NUMERIC_CONVERSION: Advertencia: El valor '{value}' (fila {row_index}, columna '{header}') no es numérico. Se usará 0.0.")
                        item_data[header] = 0.0
                elif header == 'URL Imagen': # <-- Manejar la URL de la imagen aquí
                    # Almacenar solo el ID del archivo de Google Drive
                    image_id = get_drive_file_id(value)
                    item_data['image_id'] = image_id if image_id else 'NO_IMAGE' # Usar 'NO_IMAGE' si no se encuentra ID
                    print(f"DEBUG: Producto '{item_data.get('Nombre Producto', 'N/A')}' Image ID enviado: {item_data['image_id']}")
                else:
                    item_data[header] = value
            items.append(item_data)
        
        return jsonify(items)

    except gspread.exceptions.SpreadsheetNotFound:
        print("Error: Hoja de cálculo 'rivadavia' no encontrada.")
        return jsonify({"error": "Hoja de cálculo no encontrada."}), 404
    except gspread.exceptions.WorksheetNotFound:
        print("Error: Hoja 'lista1' no encontrada en la hoja de cálculo 'rivadavia'.")
        return jsonify({"error": "Hoja 'lista1' no encontrada."}), 404
    except Exception as e:
        print(f"Error inesperado al cargar productos de lista1: {e}")
        traceback.print_exc() # Imprime el traceback completo para depuración
        return jsonify({"error": f"Error interno del servidor: {str(e)}"}), 500

# NUEVA RUTA PARA PROXY DE IMÁGENES
@app.route('/get_image/<string:file_id>')
@login_required()
def get_image(file_id):
    print(f"DEBUG: Solicitud de imagen recibida para ID: {file_id}")
    if not file_id or file_id == 'NO_IMAGE':
        print("DEBUG: ID de archivo inválido o 'NO_IMAGE'. Redirigiendo a placeholder 'Sin Imagen'.")
        return redirect('https://placehold.co/100x100/A0A0A0/FFFFFF?text=Sin%20Imagen')

    drive_url = f"https://drive.google.com/uc?export=view&id={file_id}"
    try:
        response = requests.get(drive_url, stream=True, timeout=10) # Usar stream=True para contenido binario grande, timeout
        response.raise_for_status() # Lanza un error para códigos de estado HTTP 4xx/5xx

        # Determinar el tipo de contenido (MIME type)
        content_type = response.headers.get('Content-Type', 'image/jpeg') # Default a jpeg if not detected
        print(f"DEBUG: Imagen para ID {file_id} obtenida. Content-Type: {content_type}")

        # Crear un objeto de archivo en memoria y enviar
        image_bytes = io.BytesIO(response.content)
        return send_file(image_bytes, mimetype=content_type, as_attachment=False)

    except requests.exceptions.RequestException as e:
        print(f"ERROR: Fallo en la solicitud al obtener imagen de Google Drive para ID {file_id}: {e}")
        # Redirige a un placeholder en caso de error de la solicitud
        return redirect('https://placehold.co/100x100/FF0000/FFFFFF?text=Error%20Imagen')
    except Exception as e:
        print(f"ERROR: Error inesperado al servir imagen para ID {file_id}: {e}")
        traceback.print_exc()
        # Redirige a un placeholder en caso de cualquier otro error
        return redirect('https://placehold.co/100x100/FF0000/FFFFFF?text=Error%20Imagen')


# Nueva ruta para el creador de presupuestos
@app.route('/presupuesto_creator')
@login_required()
def presupuesto_creator():
    return render_template('presupuesto_creator.html')


# Ruta para la hoja de presupuestos
@app.route('/presupuesto')
@login_required()
def presupuesto():
    registros = [] # Asegurar que registros siempre es una lista por defecto
    try:
        spreadsheet = get_google_sheets_client().open(SPREADSHEET_NAME) # Abre la hoja de cálculo
        if spreadsheet is None:
            raise gspread.exceptions.SpreadsheetNotFound(f"La hoja de cálculo '{SPREADSHEET_NAME}' no pudo ser abierta.")
            
        hoja = spreadsheet.worksheet("presupuestos") # Selecciona la hoja "presupuestos"
        if hoja is None:
            raise gspread.exceptions.WorksheetNotFound(f"La hoja 'presupuestos' no pudo ser encontrada en '{SPREADSHEET_NAME}'.")

        registros = hoja.get_all_records() # Obtiene todos los registros
    except gspread.exceptions.SpreadsheetNotFound as e:
        flash(f"❌ Error: La hoja de cálculo principal no se encontró o no hay permisos: {str(e)}", "danger")
        registros = []
    except gspread.exceptions.WorksheetNotFound as e:
        flash(f"❌ Error: La hoja 'presupuestos' no se encontró o no hay permisos: {str(e)}", "danger")
        registros = []
    except Exception as e:
        flash(f"Error al cargar la hoja de presupuestos: {str(e)}", "danger")
        registros = []

    return render_template('presupuesto.html', registros=registros)

# --- RUTA PARA VISUALIZAR TODOS LOS REGISTROS DE CREDITOCAP ---
@app.route('/creditocap')
@login_required()
def creditocap():
    registros = [] # Asegurar que registros siempre es una lista por defecto
    try:
        spreadsheet = get_google_sheets_client().open(SPREADSHEET_NAME)
        if spreadsheet is None:
            raise gspread.exceptions.SpreadsheetNotFound(f"La hoja de cálculo '{SPREADSHEET_NAME}' no pudo ser abierta.")
            
        hoja = spreadsheet.worksheet("creditocap")  # Accede a la hoja "creditocap"
        if hoja is None:
            raise gspread.exceptions.WorksheetNotFound(f"La hoja 'creditocap' no pudo ser encontrada en '{SPREADSHEET_NAME}'.")
        
        registros = hoja.get_all_records(expected_headers=CREDITOCAP_HEADERS) 
    except gspread.exceptions.SpreadsheetNotFound as e:
        flash(f"❌ Error: La hoja de cálculo principal no se encontró o no hay permisos: {str(e)}", "danger")
        registros = []
    except gspread.exceptions.WorksheetNotFound as e:
        flash(f"❌ Error: La hoja 'creditocap' no se encontró o no hay permisos: {str(e)}", "danger")
        registros = []
    except Exception as e:
        flash(f"❌ Error al cargar registros de Creditocap: {str(e)}", "danger")
        registros = []

    # Pasar CREDITOCAP_HEADERS y is_pagare_view=False
    return render_template(
        'creditocap.html',
        all_registros=registros,
        creditocap_headers=CREDITOCAP_HEADERS, # Pasa los encabezados a la plantilla
        is_pagare_view=False # Flag para indicar que es la vista de "todas las ventas"
    )

# --- RUTA UNIFICADA PARA REGISTRO Y VISTA DE CRÉDITOS ---
@app.route('/registro_credito', methods=['GET', 'POST'])
@login_required()
def registro_credito():
    if request.method == 'POST':
        # Procesa el envío del formulario
        try:
            spreadsheet = get_google_sheets_client().open(SPREADSHEET_NAME)
            if spreadsheet is None:
                raise gspread.exceptions.SpreadsheetNotFound(f"La hoja de cálculo '{SPREADSHEET_NAME}' no pudo ser abierta.")
                
            hoja = spreadsheet.worksheet("creditocap") # Hoja de créditos
            if hoja is None:
                raise gspread.exceptions.WorksheetNotFound(f"La hoja 'creditocap' no pudo ser encontrada en '{SPREADSHEET_NAME}'.")

            monto_str = request.form.get("monto")
            monto_total = None 
            if monto_str:
                try:
                    monto_total = float(monto_str)
                except ValueError:
                    flash("❌ Error: El Monto Total ingresado no es un número válido.", "danger")
                    return redirect(url_for("registro_credito"))

            # Obtener el valor del campo "forma de pago" (asegúrate que el name en tu HTML es "forma_de_pago")
            forma_de_pago_value = request.form.get("forma_de_pago", '') # Usa '' como valor por defecto si no se encuentra

            # Inicializa la lista `data` con la longitud adecuada, llena de cadenas vacías
            # Esto es crucial para asegurar que la lista tenga suficientes elementos
            # antes de asignar un valor a un índice alto como el 31.
            data = [''] * len(CREDITOCAP_HEADERS) # Crea una lista con el tamaño exacto y vacía

            # Asigna los valores a sus posiciones correctas usando los índices de los encabezados
            # Se usa .get(header, '') para evitar KeyError si un encabezado no está en CREDITOCAP_HEADERS
            # pero ya hemos establecido que sí lo está, así que el .index() debería ser seguro.

            # Campos principales
            data[CREDITOCAP_HEADERS.index("n° de factura")] = request.form.get("factura", '')
            data[CREDITOCAP_HEADERS.index("fecha de venta")] = request.form.get("fecha", '')
            data[CREDITOCAP_HEADERS.index("nombre completo")] = request.form.get("nombre", '')
            data[CREDITOCAP_HEADERS.index("dni")] = request.form.get("dni", '')
            data[CREDITOCAP_HEADERS.index("tel")] = request.form.get("tel", '')
            data[CREDITOCAP_HEADERS.index("domicilio")] = request.form.get("domicilio", '')
            data[CREDITOCAP_HEADERS.index("articulo vendido")] = request.form.get("articulo", '')
            data[CREDITOCAP_HEADERS.index("tipo de pago")] = request.form.get("tipo_pago", '')
            data[CREDITOCAP_HEADERS.index("detalle de venta")] = request.form.get("detalle", '')
            data[CREDITOCAP_HEADERS.index("vendedor")] = session.get("user", '')
            data[CREDITOCAP_HEADERS.index("monto")] = monto_total if monto_total is not None else ''

            # Asigna el valor de "forma de pago" a su índice correcto (columna AF)
            # Ya se ha verificado que "forma_de_pago" está en CREDITOCAP_HEADERS
            data[CREDITOCAP_HEADERS.index("forma_de_pago")] = forma_de_pago_value

            # Pagos adicionales
            max_additional_payments_for_initial_form = 5 
            for i in range(1, max_additional_payments_for_initial_form + 1): 
                factura_pa = request.form.get(f"pago_adicional_{i}_factura", '')
                fecha_pa = request.form.get(f"pago_adicional_{i}_fecha", '')
                tipo_pa = request.form.get(f"pago_adicional_{i}_tipo", '')
                monto_pa_str = request.form.get(f"monto_adicional_{i}", '')
                
                monto_pa = None
                if monto_pa_str:
                    try:
                        monto_pa = float(monto_pa_str)
                    except ValueError:
                        print(f"Advertencia: Monto Adicional {i} inválido '{monto_pa_str}'. Se registrará como vacío.")
                        monto_pa = None 
                
                # Asigna los valores de pagos adicionales directamente en sus índices correctos
                # usando los encabezados definidos en CREDITOCAP_HEADERS
                try:
                    base_idx_factura = CREDITOCAP_HEADERS.index(f"pago_adicional_{i}_factura")
                    data[base_idx_factura] = factura_pa
                    data[CREDITOCAP_HEADERS.index(f"pago_adicional_{i}_fecha")] = fecha_pa
                    data[CREDITOCAP_HEADERS.index(f"pago_adicional_{i}_tipo")] = tipo_pa
                    data[CREDITOCAP_HEADERS.index(f"monto_adicional_{i}")] = monto_pa if monto_pa is not None else ''
                except ValueError as ve:
                    print(f"ERROR: No se encontró el encabezado para el pago adicional {i}: {ve}. Asegúrese que 'pago_adicional_{i}_factura', etc. están en CREDITOCAP_HEADERS.")
                    flash(f"❌ Error interno: Faltan encabezados para pagos adicionales.", "danger")
                    return redirect(url_for("registro_credito"))


            # Convertir índice a letra de columna de Excel para depuración (asegúrate de que esta función esté definida globalmente o aquí)
            def get_excel_column_letter(idx):
                result = ""
                while idx >= 0:
                    result = chr(65 + (idx % 26)) + result
                    idx = (idx // 26) - 1
                return result

            print(f"DEBUG: Datos a guardar en hoja 'creditocap' (longitud: {len(data)}):")
            for idx, item in enumerate(data):
                header_name = CREDITOCAP_HEADERS[idx] if idx < len(CREDITOCAP_HEADERS) else f"UNKNOWN_COL_{idx+1}"
                col_letter = get_excel_column_letter(idx)
                print(f"   Col {col_letter} (Index {idx}): '{header_name}' -> '{item}'")

            hoja.append_row(data) # Añade una nueva fila a la hoja
            flash("✅ Venta registrada correctamente.", "success") # Mensaje de éxito
        except gspread.exceptions.SpreadsheetNotFound as e:
            flash(f"❌ Error: La hoja de cálculo principal no se encontró o no hay permisos: {str(e)}", "danger")
        except gspread.exceptions.WorksheetNotFound as e:
            flash(f"❌ Error: La hoja 'creditocap' no se encontró o no hay permisos: {str(e)}", "danger")
        except Exception as e:
            print(f"ERROR CRÍTICO al guardar registro_credito: {e}")
            traceback.print_exc() # Imprime el traceback para depuración
            flash(f"❌ Error al guardar los datos: {str(e)}", "danger") # Mensaje de error

        return redirect(url_for("registro_credito")) # Redirige para evitar reenvío del formulario

    # --- Modo GET: Carga y muestra todos los registros para la tabla plana ---
    all_registros = [] # Asegurar que all_registros siempre es una lista por defecto
    try:
        spreadsheet = get_google_sheets_client().open(SPREADSHEET_NAME)
        if spreadsheet is None:
            raise gspread.exceptions.SpreadsheetNotFound(f"La hoja de cálculo '{SPREADSHEET_NAME}' no pudo ser abierta.")
            
        hoja = spreadsheet.worksheet("creditocap")
        if hoja is None:
            raise gspread.exceptions.WorksheetNotFound(f"La hoja 'creditocap' no pudo ser encontrada en '{SPREADSHEET_NAME}'.")

        # ¡IMPORTANTE! Usar expected_headers aquí
        all_registros = hoja.get_all_records(expected_headers=CREDITOCAP_HEADERS) # Obtiene todos los registros sin agrupar
    except gspread.exceptions.SpreadsheetNotFound as e:
        flash(f"❌ Error: La hoja de cálculo principal no se encontró o no hay permisos: {str(e)}", "danger")
        all_registros = []
    except gspread.exceptions.WorksheetNotFound as e:
        flash(f"❌ Error: La hoja 'creditocap' no se encontró o no hay permisos: {str(e)}", "danger")
        all_registros = []
    except Exception as e:
        flash(f"❌ Error al cargar registros: {str(e)}", "danger")
        all_registros = [] # Inicializa como lista vacía en caso de error

    # Renderiza la plantilla 'creditocap.html' pasando todos los registros, headers y flag (para todas las ventas)
    return render_template(
        'creditocap.html', 
        all_registros=all_registros,
        creditocap_headers=CREDITOCAP_HEADERS, # Pasa los encabezados a la plantilla
        is_pagare_view=False # Esta también es una vista de "todas las ventas"
    )


# --- RUTA PARA EXPORTAR A PDF ---
@app.route('/exportar_creditos_pdf')
@login_required()
def exportar_creditos_pdf():
    try:
        spreadsheet = get_google_sheets_client().open(SPREADSHEET_NAME)
        if spreadsheet is None:
            raise gspread.exceptions.SpreadsheetNotFound(f"La hoja de cálculo '{SPREADSHEET_NAME}' no pudo ser abierta.")
            
        hoja = spreadsheet.worksheet("creditocap")
        if hoja is None:
            raise gspread.exceptions.WorksheetNotFound(f"La hoja 'creditocap' no pudo ser encontrada en '{SPREADSHEET_NAME}'.")
            
        # ¡IMPORTANTE! Usar expected_headers aquí
        registros = hoja.get_all_records(expected_headers=CREDITOCAP_HEADERS) # Obtiene todos los registros para el PDF

        # Configuración del PDF
        pdf = FPDF(unit="mm", format="A4")
        pdf.add_page()
        pdf.set_font("Arial", size=10)

        # Título del documento
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(0, 10, "Resumen de Registros de Créditos", 0, 1, 'C')
        pdf.ln(5)

        # Cabeceras de la tabla
        pdf.set_font("Arial", 'B', 8)
        # Define los anchos de cada columna en mm (ajústalos según tus datos)
        # Se utilizan los encabezados reales de la hoja o los que deseas mostrar en el PDF
        # Asegúrate de que estos nombres coincidan con las claves en tus registros
        headers_to_export = ["Fecha de venta", "Nombre completo", "Artículo vendido", "Tipo de pago", "Detalle de venta", "Vendedor", "Monto"]
        col_widths = [25, 40, 35, 20, 35, 20, 15] # Ajusta anchos según necesidad

        for i, header in enumerate(headers_to_export):
            pdf.cell(col_widths[i], 8, header, 1, 0, 'C') # 1 = borde, 0 = no salto de línea, 'C' = centrado
        pdf.ln(8) # Salto de línea para la siguiente fila

        # Contenido de la tabla
        pdf.set_font("Arial", size=7) # Fuente más pequeña para el contenido de las filas
        for reg in registros:
            # Asegúrate de que las claves existan en cada registro o usa .get() con un valor por defecto
            fecha = reg.get('fecha de venta', '')
            nombre = reg.get('nombre completo', '')
            articulo = reg.get('articulo vendido', '')
            tipo_pago = reg.get('tipo de pago', '')
            detalle = reg.get('detalle de venta', '')
            vendedor = reg.get('vendedor', '') # Acceso directo con el nuevo header
            monto = reg.get('monto', '') # Acceso directo con el nuevo header

            # Limitar la longitud del detalle para evitar desbordamiento en celdas pequeñas del PDF
            detalle_display = (detalle[:32] + '...') if len(detalle) > 35 else detalle 

            # Añade las celdas con los datos del registro
            pdf.cell(col_widths[0], 6, fecha, 1, 0, 'L') # 'L' = alineado a la izquierda
            pdf.cell(col_widths[1], 6, nombre, 1, 0, 'L')
            pdf.cell(col_widths[2], 6, articulo, 1, 0, 'L')
            pdf.cell(col_widths[3], 6, tipo_pago, 1, 0, 'L')
            pdf.cell(col_widths[4], 6, detalle_display, 1, 0, 'L')
            pdf.cell(col_widths[5], 6, vendedor, 1, 0, 'L')
            pdf.cell(col_widths[6], 6, str(monto), 1, 0, 'R') # Monto alineado a la derecha
            pdf.ln(6) # Salto de línea para la siguiente fila

        # Guardar el PDF en un buffer de memoria y enviarlo como respuesta HTTP
        pdf_output = pdf.output(dest='S') # 'S' significa devolver el documento como una cadena
        response = make_response(pdf_output)
        response.headers['Content-Type'] = 'application/pdf' # Tipo de contenido para que el navegador sepa que es un PDF
        response.headers['Content-Disposition'] = 'attachment; filename=registros_creditos.pdf' # Fuerza la descarga y nombra el archivo
        return response

    except Exception as e:
        # En caso de error en la generación del PDF, muestra un mensaje y redirige
        print(f"ERROR CRÍTICO al intentar exportar el PDF: {e}")
        flash(f"❌ Error al intentar exportar el PDF: {str(e)}", "danger")
        return redirect(url_for('registro_credito'))


# --- RUTA: Pagarés (listado y manejo de pagos adicionales) ---
@app.route('/pagarecap', methods=['GET', 'POST'])
@login_required()
def pagarecap():
    print("DEBUG: Accediendo a la ruta /pagarecap") # Log para verificar si la ruta es alcanzada
    pagares_registros = [] # Asegurar que pagares_registros siempre es una lista por defecto
    all_records_raw = [] # Asegurar que all_records_raw siempre es una lista por defecto

    try:
        spreadsheet = get_google_sheets_client().open(SPREADSHEET_NAME)
        if spreadsheet is None:
            raise gspread.exceptions.SpreadsheetNotFound(f"La hoja de cálculo '{SPREADSHEET_NAME}' no pudo ser abierta.")
            
        hoja = spreadsheet.worksheet("creditocap")
        if hoja is None:
            raise gspread.exceptions.WorksheetNotFound(f"La hoja 'creditocap' no pudo ser encontrada en '{SPREADSHEET_NAME}'.")

        # ¡IMPORTANTE! Usar expected_headers aquí para que `all_records_raw` use el nuevo orden
        # Esta línea se mueve para que esté disponible tanto para POST como para GET
        all_records_raw = hoja.get_all_records(expected_headers=CREDITOCAP_HEADERS) 

        # La lógica POST para registrar pagos adicionales se ha movido a la ruta /ver_estado_credito_por_dni/<string:dni_cliente>
        # Sin embargo, si un formulario POST llega aquí por error, podríamos querer procesarlo o redirigirlo.
        # Por simplicidad, este POST aquí simplemente redirigirá, ya que la acción principal está en la vista de detalle.
        if request.method == 'POST':
            dni_cliente = request.form.get('dni_cliente_hidden', '').strip()
            flash("⚠️ La acción de pago debe realizarse desde la vista detallada del crédito. Redirigiendo...", "info")
            if dni_cliente:
                return redirect(url_for('ver_estado_credito_por_dni', dni_cliente=dni_cliente))
            else:
                return redirect(url_for('pagarecap')) # Si no hay DNI, vuelve a la lista

    except gspread.exceptions.SpreadsheetNotFound as e:
        flash(f"❌ Error: La hoja de cálculo principal no se encontró o no hay permisos: {str(e)}", "danger")
        pagares_registros = []
        all_records_raw = []
    except gspread.exceptions.WorksheetNotFound as e:
        flash(f"❌ Error: La hoja 'creditocap' no se encontró o no hay permisos: {str(e)}", "danger")
        pagares_registros = []
        all_records_raw = []
    except Exception as e:
        flash(f"❌ Error inesperado al procesar la solicitud: {str(e)}", "danger")
        print(f"ERROR en pagarecap (general): {e}")
        traceback.print_exc() # Imprime el traceback
        pagares_registros = []
        all_records_raw = []
    
    # Lógica para GET (mostrar la tabla de pagarés)
    # Filtrar solo los registros que son de tipo 'pagaré'
    try:
        pagares_registros = [] 
        max_additional_slots_in_sheet = 5 # El máximo de slots que tu hoja soporta físicamente

        for reg in all_records_raw: # Usamos los registros ya procesados
            tipo_pago = str(reg.get('tipo de pago', '')).strip().lower()
            
            print(f"DEBUG GET /pagarecap: Procesando registro DNI '{reg.get('dni', 'N/A')}', Tipo de Pago: '{tipo_pago}'")

            if 'pagaré' in tipo_pago:
                current_reg = reg.copy() # Trabajar en una copia para añadir nuevas claves

                num_total_payments_expected = 0
                if tipo_pago == 'pagaré 3':
                    num_total_payments_expected = 3
                elif tipo_pago == 'pagaré 6':
                    num_total_payments_expected = 6 
                else:
                    num_total_payments_expected = 1 # Por defecto para otros "pagarés" si no tienen lógica específica

                num_extra_payments_expected = num_total_payments_expected - 1
                if num_extra_payments_expected < 0:
                    num_extra_payments_expected = 0

                registered_payments_count = 0
                for i in range(1, max_additional_slots_in_sheet + 1):
                    factura_pa_key = f'pago_adicional_{i}_factura'
                    monto_pa_key = f'monto_adicional_{i}' # Clave para el monto
                    
                    if current_reg.get(factura_pa_key) and str(current_reg.get(factura_pa_key)).strip() != '' and \
                       current_reg.get(monto_pa_key) is not None and str(current_reg.get(monto_pa_key)).strip() != '':
                        try:
                            float(str(current_reg.get(monto_pa_key)).strip())
                            registered_payments_count += 1
                        except ValueError:
                            pass # No cuenta el pago si el monto no es válido
                        
                all_payments_complete = False
                
                # Si el número de pagos extras esperados excede los slots físicos, no puede estar completo.
                if num_extra_payments_expected > max_additional_slots_in_sheet:
                    all_payments_complete = False 
                elif registered_payments_count >= num_extra_payments_expected: # Solo si no excede, verifica si está completo
                    all_payments_complete = True

                current_reg['all_payments_complete'] = all_payments_complete
                pagares_registros.append(current_reg)
            else:
                print(f"DEBUG GET /pagarecap: Registro excluido (Tipo de Pago no es Pagaré): '{tipo_pago}' para DNI: {reg.get('dni', 'N/A')}")
    except Exception as e:
        flash(f"❌ Error al cargar los registros de pagarés para mostrar: {str(e)}", "danger")
        print(f"ERROR al cargar registros en pagarecap GET: {e}")
        traceback.print_exc()
        pagares_registros = []

    # Renderiza la NUEVA plantilla 'pagare_list.html' para la vista de lista de pagarés
    return render_template(
        'pagare_list.html', # <--- CAMBIO IMPORTANTE AQUÍ
        pagares_registros=pagares_registros, # Pasa los registros filtrados
        creditocap_headers=CREDITOCAP_HEADERS # Pasa los encabezados si es necesario para el listado
    )


# --- NUEVA RUTA: ver_estado_credito_por_dni (vista detallada de un solo crédito) ---
@app.route('/ver_estado_credito_por_dni/<string:dni_cliente>', methods=['GET', 'POST'])
@login_required()
def ver_estado_credito_por_dni(dni_cliente):
    if request.method == 'POST':
        # Manejar el envío del formulario de pago adicional desde esta vista
        try:
            spreadsheet = get_google_sheets_client().open(SPREADSHEET_NAME)
            if spreadsheet is None:
                raise gspread.exceptions.SpreadsheetNotFound(f"La hoja de cálculo '{SPREADSHEET_NAME}' no pudo ser abierta.")
                
            hoja = spreadsheet.worksheet("creditocap")
            if hoja is None:
                raise gspread.exceptions.WorksheetNotFound(f"La hoja 'creditocap' no pudo ser encontrada en '{SPREADSHEET_NAME}'.")

            new_factura = request.form.get('new_factura', '').strip()
            new_fecha = request.form.get('new_fecha', '').strip()
            new_tipo = request.form.get('new_tipo', '').strip()
            new_monto_str = request.form.get('new_monto', '').strip()
            slot_to_update_str = request.form.get('next_slot_to_fill', '')

            print(f"DEBUG POST /ver_estado_credito_por_dni: DNI={dni_cliente}, Slot={slot_to_update_str}, Factura={new_factura}, Fecha={new_fecha}, Tipo={new_tipo}, Monto={new_monto_str}")

            if not all([dni_cliente, slot_to_update_str, new_factura, new_fecha, new_tipo, new_monto_str]):
                flash("❌ Error: Faltan datos para registrar el pago adicional.", "danger")
                return redirect(url_for('ver_estado_credito_por_dni', dni_cliente=dni_cliente))

            try:
                slot_to_update = int(slot_to_update_str)
                new_monto = float(new_monto_str)
            except ValueError:
                flash("❌ Error: El número de pago o el monto no son válidos.", "danger")
                return redirect(url_for('ver_estado_credito_por_dni', dni_cliente=dni_cliente))

            all_records_raw = hoja.get_all_records(expected_headers=CREDITOCAP_HEADERS) 
            credit_data = None
            row_index = -1

            for i, record in enumerate(all_records_raw):
                dni_in_sheet = str(record.get('dni', '')).strip()
                if dni_in_sheet == dni_cliente:
                    credit_data = record
                    row_index = i + 2
                    break
            
            if not credit_data:
                flash(f"❌ Error: No se encontró el crédito para el DNI: {dni_cliente}.", "danger")
                return redirect(url_for('pagarecap')) # Si no se encuentra, volver a la lista general

            tipo_pago_original = str(credit_data.get('tipo de pago', '')).strip().lower()
            
            num_extra_payments_expected_for_credit = 0
            if 'pagaré' in tipo_pago_original:
                if tipo_pago_original == 'pagaré 3':
                    num_extra_payments_expected_for_credit = 2
                elif tipo_pago_original == 'pagaré 6':
                    num_extra_payments_expected_for_credit = 5
            elif tipo_pago_original in ['contado', 'tarjeta', 'otros']:
                 flash(f"❌ Error: El crédito con DNI {dni_cliente} no es un pagaré y no permite pagos adicionales.", "danger")
                 return redirect(url_for('ver_estado_credito_por_dni', dni_cliente=dni_cliente))

            max_additional_slots_in_sheet = 5 
            if slot_to_update < 1 or slot_to_update > num_extra_payments_expected_for_credit or slot_to_update > max_additional_slots_in_sheet:
                flash(f"❌ Error: El número de pago {slot_to_update} excede el límite permitido de pagos adicionales para este tipo de pagaré ({num_extra_payments_expected_for_credit}) o la estructura de la hoja ({max_additional_slots_in_sheet}).", "danger")
                return redirect(url_for('ver_estado_credito_por_dni', dni_cliente=dni_cliente))

            try:
                base_col_index = CREDITOCAP_HEADERS.index(f'pago_adicional_{slot_to_update}_factura') + 1 
            except ValueError:
                flash(f"❌ Error interno: No se encontró el encabezado para el pago adicional {slot_to_update}. Contacte a soporte.", "danger")
                return redirect(url_for('ver_estado_credito_por_dni', dni_cliente=dni_cliente))

            hoja.update_cell(row_index, base_col_index, new_factura)
            hoja.update_cell(row_index, base_col_index + 1, new_fecha)
            hoja.update_cell(row_index, base_col_index + 2, new_tipo)
            hoja.update_cell(row_index, base_col_index + 3, new_monto)
            
            flash("✅ Pago adicional registrado correctamente.", "success")
            return redirect(url_for('ver_estado_credito_por_dni', dni_cliente=dni_cliente))

        except Exception as e:
            flash(f"❌ Error al procesar el pago: {str(e)}", "danger")
            print(f"ERROR en ver_estado_credito_por_dni POST: {e}")
            traceback.print_exc()
            return redirect(url_for('ver_estado_credito_por_dni', dni_cliente=dni_cliente))
    
    # Lógica para GET: Obtener y mostrar los detalles del crédito
    credit_data = None
    payments_data = []
    next_payment_slot = None
    expected_payment_dates = []
    max_additional_payments_in_structure = 5 # Asumiendo 5 slots para pagos adicionales

    try:
        # Reutilizamos la lógica de la API para obtener los detalles, incluyendo pagos
        # Esto es más eficiente que duplicar la lógica de acceso a la hoja aquí.
        api_response = get_credit_details_json(dni_cliente)
        
        if api_response.status_code == 200:
            data = json.loads(api_response.data) # Convertir Bytes a string y luego a JSON
            credit_data = data.get('credit_data')
            payments_data = data.get('payments_data', [])
            next_payment_slot = data.get('next_payment_slot')
            max_additional_payments_in_structure = data.get('max_additional_payments')
            expected_payment_dates = data.get('expected_payment_dates', [])
        else:
            # Si la API devuelve un error, flashear el mensaje y redirigir
            error_data = json.loads(api_response.data)
            flash(f"❌ Error: {error_data.get('error', 'Error desconocido al cargar el crédito.')}", "danger")
            return redirect(url_for('pagarecap')) # Redirige a la lista de pagarés

    except Exception as e:
        flash(f"❌ Error inesperado al cargar detalles del crédito: {str(e)}", "danger")
        print(f"ERROR en ver_estado_credito_por_dni GET: {e}")
        traceback.print_exc()
        return redirect(url_for('pagarecap'))


    return render_template(
        'ver_estado_credito.html',
        credit_data=credit_data,
        payments_data=payments_data,
        next_payment_slot=next_payment_slot,
        max_additional_payments=max_additional_payments_in_structure,
        expected_payment_dates=expected_payment_dates
    )


# --- NUEVA RUTA API para obtener detalles del crédito (JSON) ---
@app.route('/api/get_credit_details/<string:dni_cliente>', methods=['GET'])
@login_required()
def get_credit_details_json(dni_cliente):
    try:
        spreadsheet = get_google_sheets_client().open(SPREADSHEET_NAME)
        if spreadsheet is None:
            raise gspread.exceptions.SpreadsheetNotFound(f"La hoja de cálculo '{SPREADSHEET_NAME}' no pudo ser abierta.")
            
        hoja = spreadsheet.worksheet("creditocap")
        if hoja is None:
            raise gspread.exceptions.WorksheetNotFound(f"La hoja 'creditocap' no pudo ser encontrada en '{SPREADSHEET_NAME}'.")
            
        # ¡IMPORTANTE! Usar expected_headers aquí para que `all_records` use el nuevo orden
        all_records = hoja.get_all_records(expected_headers=CREDITOCAP_HEADERS)
        
        credit_data = None
        for record in all_records:
            if str(record.get('dni', '')).strip() == dni_cliente.strip():
                credit_data = record
                break
        
        if not credit_data:
            return jsonify({"error": f"No se encontró un registro de crédito para el DNI: {dni_cliente}"}), 404

        payments_data = []
        next_payment_slot = None
        # CORREGIDO a 5: Máximo de slots que tu HTML y hoja soportan físicamente para pagos adicionales
        max_additional_payments_in_structure = 5 

        for i in range(1, max_additional_payments_in_structure + 1):
            factura_col_name = f'pago_adicional_{i}_factura'
            fecha_col_name = f'pago_adicional_{i}_fecha'
            tipo_col_name = f'pago_adicional_{i}_tipo'
            monto_col_name = f'monto_adicional_{i}' # Clave para el monto

            factura_val = str(credit_data.get(factura_col_name, '')).strip()
            fecha_val = str(credit_data.get(fecha_col_name, '')).strip()
            tipo_val = str(credit_data.get(tipo_col_name, '')).strip()
            monto_val = str(credit_data.get(monto_col_name, '')).strip() # Obtener el monto como string

            is_registered_payment = False
            if (factura_val or fecha_val or tipo_val):
                try:
                    if monto_val:
                        float(monto_val) # Solo para verificar si es un número
                    is_registered_payment = True
                except ValueError:
                    is_registered_payment = False
            
            if is_registered_payment:
                payments_data.append({
                    'slot': i ,
                    'factura': factura_val,
                    'fecha': fecha_val,
                    'tipo': tipo_val,
                    'monto': monto_val # Añadir el monto al JSON de respuesta (como string para evitar problemas de float en JS)
                })
            else:
                if next_payment_slot is None:
                    next_payment_slot = i 
        
        # Determinar el número TOTAL de pagos esperados según el tipo de pagaré
        tipo_pago_original = str(credit_data.get('tipo de pago', '')).strip().lower()
        num_total_payments_expected_for_api = 0
        
        if 'pagaré' in tipo_pago_original:
            if tipo_pago_original == 'pagaré 3':
                num_total_payments_expected_for_api = 2
            elif tipo_pago_original == 'pagaré 6':
                num_total_payments_expected_for_api = 5
            else:
                num_total_payments_expected_for_api = 1 # Asume 1 si es un pagaré no 3 o 6 específicamente

        # Número de pagos *extras* esperados (sin contar el inicial)
        num_extra_payments_expected_for_api = num_total_payments_expected_for_api - 1
        if num_extra_payments_expected_for_api < 0:
            num_extra_payments_expected_for_api = 0

        # Si ya se han registrado todos los pagos *extras* esperados,
        # o si el next_payment_slot encontrado excede el límite de pagos extras esperados,
        # entonces no hay más slots disponibles para el registro.
        if (len(payments_data) >= num_extra_payments_expected_for_api and num_extra_payments_expected_for_api > 0):
            next_payment_slot = None
        elif next_payment_slot is not None and next_payment_slot > num_extra_payments_expected_for_api:
            next_payment_slot = None


        expected_payment_dates = []
        fecha_venta_str = str(credit_data.get('fecha de venta', '')).strip()

        try:
            if fecha_venta_str:
                fecha_venta_obj = datetime.strptime(fecha_venta_str, '%Y-%m-%d')
                
                # Loop a través del número TOTAL de pagos esperados para mostrar las fechas
                for i in range(1, num_total_payments_expected_for_api + 1):
                    expected_date_obj = fecha_venta_obj # Start with the sale date itself for slot 0/initial
                    slot_status = "pendiente"

                    # For subsequent slots (1, 2, 3... which are the 'extra' payments)
                    # We are calculating expected dates for additional payments (slot 1 onwards for additional).
                    # If i=1 is the first additional payment, then it's fecha_venta_obj + 1 month.
                    # The `i` here represents the slot number (1 to X for additional payments).
                    # So, to get the correct month offset, it should be `i` months after the sale date.
                    
                    target_month = fecha_venta_obj.month + i
                    target_year = fecha_venta_obj.year + (target_month - 1) // 12
                    target_month = (target_month - 1) % 12 + 1
                    
                    last_day_of_target_month = calendar.monthrange(target_year, target_month)[1]
                    
                    target_day = min(fecha_venta_obj.day, last_day_of_target_month)
                    
                    expected_date_obj = datetime(target_year, target_month, target_day)
                    
                    expected_date_formatted = expected_date_obj.strftime('%d/%m/%Y')

                    # Check status for the current slot
                    is_this_slot_registered = any(p['slot'] == i for p in payments_data)
                    
                    if is_this_slot_registered:
                        slot_status = "registrado"
                    elif expected_date_obj.date() < datetime.now().date(): # Only if not registered, check for vencido
                        slot_status = "vencido"
                    
                    expected_payment_dates.append({
                        "slot": i, # This slot number corresponds to pago_adicional_X
                        "fecha_esperada": expected_date_formatted,
                        "estado": slot_status
                    })
            else:
                print(f"Advertencia: Fecha de venta '{fecha_venta_str}' vacía o inválida para calcular pagos esperados.")
        except ValueError as ve:
            print(f"Advertencia: La fecha de venta '{fecha_venta_str}' no es un formato válido (%Y-%m-%d) para calcular pagos esperados: {ve}")
            traceback.print_exc()
        except Exception as e:
            print(f"Error al calcular fechas esperadas en API: {e}")
            traceback.print_exc()

        return jsonify({
            "credit_data": credit_data,
            "payments_data": payments_data,
            "next_payment_slot": next_payment_slot,
            "max_additional_payments": max_additional_payments_in_structure,
            "expected_payment_dates": expected_payment_dates
        })

    except gspread.exceptions.SpreadsheetNotFound as e:
        print(f"ERROR CRÍTICO en get_credit_details_json: La hoja de cálculo principal no se encontró o no hay permisos: {str(e)}")
        return jsonify({"error": f"Error interno del servidor: La hoja de cálculo principal no se encontró o no hay permisos."}), 500
    except gspread.exceptions.WorksheetNotFound as e:
        print(f"ERROR CRÍTICO en get_credit_details_json: La hoja 'creditocap' no se encontró o no hay permisos: {str(e)}")
        return jsonify({"error": f"Error interno del servidor: La hoja 'creditocap' no se encontró o no hay permisos."}), 500
    except Exception as e:
        print(f"ERROR CRÍTICO en get_credit_details_json: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Error interno del servidor: {str(e)}"}), 500

@app.route('/product_catalog')
@login_required()
def product_catalog():
    return render_template('product_catalog.html')
# NUEVA RUTA PARA EL CALENDARIO DE ABORDAJE

# --- RUTA EXISTENTE PARA CALENDARIO DE ABORDAJE (MODIFICADA) ---
@app.route('/calendario_abordaje', methods=['GET', 'POST'])
@login_required()
def calendario_abordaje():
    # Encabezados específicos para la hoja "abordaje"
    ABORDAJE_HEADERS = [
        "visitas", # Esperamos AAAA-MM-DD
        "medico",
        "localidad",
        "pacientes_atendidos"
    ]

    if request.method == 'POST':
        try:
            spreadsheet = get_google_sheets_client().open(SPREADSHEET_NAME)
            if spreadsheet is None:
                raise gspread.exceptions.SpreadsheetNotFound(f"La hoja de cálculo '{SPREADSHEET_NAME}' no pudo ser abierta.")
            
            try:
                hoja = spreadsheet.worksheet("abordaje")
            except gspread.exceptions.WorksheetNotFound:
                print("DEBUG: La hoja 'abordaje' no existe. Creándola...")
                hoja = spreadsheet.add_worksheet(title="abordaje", rows="100", cols="20")
                hoja.append_row(ABORDAJE_HEADERS)
                print("DEBUG: Hoja 'abordaje' creada con encabezados.")

            fecha_visita_str = request.form.get('fecha_visita', '')
            medico = request.form.get('medico', '')
            localidad = request.form.get('localidad', '')
            pacientes_atendidos_str = request.form.get('pacientes_atendidos', '')

            if not fecha_visita_str:
                flash("❌ Error: La fecha de visita es obligatoria.", "danger")
                return redirect(url_for("calendario_abordaje"))
            try:
                datetime.strptime(fecha_visita_str, '%Y-%m-%d')
                visitas_formateada = fecha_visita_str
            except ValueError:
                flash("❌ Error: Formato de fecha inválido. Use AAAA-MM-DD.", "danger")
                return redirect(url_for("calendario_abordaje"))

            pacientes_atendidos = 0
            if pacientes_atendidos_str:
                try:
                    pacientes_atendidos = int(pacientes_atendidos_str)
                except ValueError:
                    flash("❌ Error: 'Pacientes Atendidos' debe ser un número válido.", "danger")
                    return redirect(url_for("calendario_abordaje"))

            data_to_append = [
                visitas_formateada,
                medico,
                localidad,
                pacientes_atendidos
            ]

            print(f"DEBUG: Datos a guardar en hoja 'abordaje': {data_to_append}")
            hoja.append_row(data_to_append)
            flash("✅ Registro de abordaje guardado correctamente.", "success")
            return redirect(url_for("calendario_abordaje"))

        except gspread.exceptions.SpreadsheetNotFound as e:
            flash(f"❌ Error: La hoja de cálculo principal no se encontró o no hay permisos: {str(e)}", "danger")
        except Exception as e:
            print(f"ERROR CRÍTICO al guardar registro de abordaje: {e}")
            traceback.print_exc()
            flash(f"❌ Error al guardar el registro de abordaje: {str(e)}", "danger")
        
        return redirect(url_for("calendario_abordaje"))

    # --- Modo GET: Mostrar registros existentes ---
    registros_abordaje = []
    events_for_calendar = [] 
    try:
        spreadsheet = get_google_sheets_client().open(SPREADSHEET_NAME)
        if spreadsheet is None:
            raise gspread.exceptions.SpreadsheetNotFound(f"La hoja de cálculo '{SPREADSHEET_NAME}' no pudo ser abierta.")

        hoja = spreadsheet.worksheet("abordaje")
        if hoja is None:
            raise gspread.exceptions.WorksheetNotFound(f"La hoja 'abordaje' no pudo ser encontrada en '{SPREADSHEET_NAME}'.")
        
        registros_abordaje = hoja.get_all_records(expected_headers=ABORDAJE_HEADERS)

        # Prepara los eventos para FullCalendar
        for registro in registros_abordaje:
            try:
                datetime.strptime(str(registro.get('visitas')), '%Y-%m-%d')
                event_date = str(registro.get('visitas'))
                
                # Modificamos el título del evento para ser más conciso en la vista de calendario
                event_title = f"{registro.get('medico', 'N/A')} ({registro.get('localidad', 'N/A')})"
                
                events_for_calendar.append({
                    'title': event_title,
                    'start': event_date,
                    # Aquí es donde guardamos todos los detalles del registro para el modal
                    'extendedProps': {
                        'fecha_visita': registro.get('visitas', ''),
                        'medico': registro.get('medico', ''),
                        'localidad': registro.get('localidad', ''),
                        'pacientes_atendidos': registro.get('pacientes_atendidos', 0)
                    }
                })
            except ValueError:
                print(f"Advertencia: Registro con fecha inválida '{registro.get('visitas')}' para FullCalendar. Ignorando.")
            except Exception as e:
                print(f"Error al procesar registro para FullCalendar: {e}")

    except gspread.exceptions.SpreadsheetNotFound as e:
        flash(f"❌ Error: La hoja de cálculo principal no se encontró o no hay permisos: {str(e)}", "danger")
    except gspread.exceptions.WorksheetNotFound:
        flash("ℹ️ La hoja 'abordaje' aún no existe o está vacía. Crea el primer registro.", "info")
    except Exception as e:
        print(f"ERROR al cargar registros de abordaje: {e}")
        traceback.print_exc()
        flash(f"❌ Error al cargar los registros de abordaje: {str(e)}", "danger")

    return render_template('calendario.html', registros=registros_abordaje, events=json.dumps(events_for_calendar))
@app.route('/editar_abordaje', methods=['GET', 'POST'])
@login_required()
def editar_abordaje():
    if request.method == 'POST':
        fecha = request.form.get('fecha')
        medico = request.form.get('medico')
    else:
        fecha = request.args.get('fecha')
        medico = request.args.get('medico')

    spreadsheet = get_google_sheets_client().open(SPREADSHEET_NAME)
    hoja = spreadsheet.worksheet("abordaje")
    registros = hoja.get_all_records()

    fila_encontrada = None
    for i, reg in enumerate(registros, start=2):  # Empieza en 2 por encabezado
        if reg['visitas'] == fecha and reg['medico'] == medico:
            fila_encontrada = i
            break

    if not fila_encontrada:
        flash("❌ No se encontró el registro para editar.", "danger")
        return redirect(url_for("calendario_abordaje"))

    if request.method == 'POST':
        localidad = request.form.get('localidad')
        pacientes = request.form.get('pacientes_atendidos')
        hoja.update(f'A{fila_encontrada}:D{fila_encontrada}', [[fecha, medico, localidad, pacientes]])
        flash("✅ Registro actualizado correctamente.", "success")
        return redirect(url_for("calendario_abordaje"))

    # Mostrar formulario para edición
    registro = registros[fila_encontrada - 2]  # Porque .get_all_records() es 0-index
    return render_template('editar_abordaje.html', registro=registro)


# ... (El resto de tu app.py, incluyendo if __name__ == '__main__':) ...
# --- PUNTO DE ENTRADA PRINCIPAL ---
if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_DEBUG', '1') == '1'
    app.run(debug=debug_mode, host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
