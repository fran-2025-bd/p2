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
    try:
        spreadsheet = get_google_sheets_client().open(SPREADSHEET_NAME) # Abre la hoja de cálculo "rivadavia"
        hoja = spreadsheet.worksheet("lista1") # Selecciona la hoja "lista1"
        # Asume que 'lista1' no tiene el problema de encabezados duplicados,
        # si lo tuviera, también necesitaría un expected_headers aquí.
        registros = hoja.get_all_records() # Obtiene todos los registros de la hoja
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
        hoja = spreadsheet.worksheet("lista1")
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
    try:
        spreadsheet = get_google_sheets_client().open(SPREADSHEET_NAME) # Abre la hoja de cálculo
        hoja = spreadsheet.worksheet("presupuestos") # Selecciona la hoja "presupuestos"
        registros = hoja.get_all_records() # Obtiene todos los registros
    except Exception as e:
        flash(f"Error al cargar la hoja de presupuestos: {str(e)}", "danger")
        registros = []

    return render_template('presupuesto.html', registros=registros)

# --- RUTA PARA VISUALIZAR TODOS LOS REGISTROS DE CREDITOCAP ---
@app.route('/creditocap')
@login_required()
def creditocap():
    try:
        spreadsheet = get_google_sheets_client().open(SPREADSHEET_NAME)
        hoja = spreadsheet.worksheet("creditocap")  # Accede a la hoja "creditocap"
        registros = hoja.get_all_records(expected_headers=CREDITOCAP_HEADERS) 
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
            hoja = spreadsheet.worksheet("creditocap") # Hoja de créditos

            monto_str = request.form.get("monto")
            monto_total = None 
            if monto_str:
                try:
                    monto_total = float(monto_str)
                except ValueError:
                    flash("❌ Error: El Monto Total ingresado no es un número válido.", "danger")
                    return redirect(url_for("registro_credito"))

            pagos_adicionales_data = []
            # Máximo de conjuntos de columnas para pagos adicionales (5 pagos adicionales * 4 columnas/pago = 20 columnas)
            # Se ha ajustado a 5, coincidiendo con la definición de CREDITOCAP_HEADERS
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
                
                # Asegúrate de que estos valores se añaden en el orden correcto de las columnas en tu hoja
                # Las columnas son: factura, fecha, tipo, monto (4 columnas por cada pago adicional)
                pagos_adicionales_data.extend([
                    factura_pa, 
                    fecha_pa, 
                    tipo_pa, 
                    monto_pa if monto_pa is not None else '' # Guarda el float o una cadena vacía
                ])

            # ¡ORDEN DE LOS DATOS AJUSTADO SEGÚN LOS ENCABEZADOS DE CREDITOCAP_HEADERS!
            # Asegura que las columnas de vendedor, monto y detalle de venta estén en su posición correcta.
            data = [
                request.form.get("factura"),      # A (Index 0)
                request.form.get("fecha"),        # B (Index 1)
                request.form.get("nombre"),       # C (Index 2)
                request.form.get("dni"),          # D (Index 3)
                request.form.get("tel"),          # E (Index 4)
                request.form.get("domicilio"),    # F (Index 5)
                request.form.get("articulo"),     # G (Index 6)
                request.form.get("tipo_pago"),    # H (Index 7)
                session.get("user"),              # I (Index 8) - Vendedor
                monto_total,                      # J (Index 9) - Monto Total
                request.form.get("detalle"),      # K (Index 10) - Detalle de Venta
            ]
            
            # Los pagos adicionales deben venir después de Detalle de Venta (desde columna L, Index 11)
            data.extend(pagos_adicionales_data)

            # Convertir índice a letra de columna de Excel para depuración
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
                print(f"  Col {col_letter} (Index {idx}): '{header_name}' -> '{item}'")

            hoja.append_row(data) # Añade una nueva fila a la hoja
            flash("✅ Venta registrada correctamente.", "success") # Mensaje de éxito
        except Exception as e:
            print(f"ERROR CRÍTICO al guardar registro_credito: {e}")
            traceback.print_exc() # Imprime el traceback para depuración
            flash(f"❌ Error al guardar los datos: {str(e)}", "danger") # Mensaje de error

        return redirect(url_for("registro_credito")) # Redirige para evitar reenvío del formulario

    # --- Modo GET: Carga y muestra todos los registros para la tabla plana ---
    try:
        spreadsheet = get_google_sheets_client().open(SPREADSHEET_NAME)
        hoja = spreadsheet.worksheet("creditocap")
        # ¡IMPORTANTE! Usar expected_headers aquí
        all_registros = hoja.get_all_records(expected_headers=CREDITOCAP_HEADERS) # Obtiene todos los registros sin agrupar
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
        hoja = spreadsheet.worksheet("creditocap")
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
    hoja = None
    try:
        spreadsheet = get_google_sheets_client().open(SPREADSHEET_NAME)
        hoja = spreadsheet.worksheet("creditocap")
        # ¡IMPORTANTE! Usar expected_headers aquí para que `all_records_raw` use el nuevo orden
        # Esta línea se mueve para que esté disponible tanto para POST como para GET
        all_records_raw = hoja.get_all_records(expected_headers=CREDITOCAP_HEADERS) 

        if request.method == 'POST':
            # Manejar el envío del formulario de pago adicional
            dni_cliente = request.form.get('dni_cliente_hidden', '').strip()
            new_factura = request.form.get('new_factura', '').strip()
            new_fecha = request.form.get('new_fecha', '').strip()
            new_tipo = request.form.get('new_tipo', '').strip()
            new_monto_str = request.form.get('new_monto', '').strip() # Captura el monto adicional
            slot_to_update_str = request.form.get('next_slot_to_fill', '')

            print(f"DEBUG POST /pagarecap: DNI={dni_cliente}, Slot={slot_to_update_str}, Factura={new_factura}, Fecha={new_fecha}, Tipo={new_tipo}, Monto={new_monto_str}")

            if not all([dni_cliente, slot_to_update_str, new_factura, new_fecha, new_tipo, new_monto_str]):
                flash("❌ Error: Faltan datos para registrar el pago adicional.", "danger")
                return redirect(url_for('pagarecap', dni=dni_cliente))

            try:
                slot_to_update = int(slot_to_update_str)
                new_monto = float(new_monto_str) # Convertir a float
            except ValueError:
                flash("❌ Error: El número de pago o el monto no son válidos.", "danger")
                return redirect(url_for('pagarecap', dni=dni_cliente))

            # Buscar la fila por DNI en los registros ya obtenidos con los headers correctos
            credit_data = None
            row_index = -1

            # `all_records_raw` ya tiene los datos con los nombres de columna correctos gracias a `expected_headers`
            for i, record in enumerate(all_records_raw):
                dni_in_sheet = str(record.get('dni', '')).strip()
                if dni_in_sheet == dni_cliente:
                    credit_data = record
                    row_index = i + 2 # +2 para la notación A1 de gspread (1 para encabezado, 1 para 0-index a 1-index)
                    break
            
            if not credit_data:
                flash(f"❌ Error: No se encontró el crédito para el DNI: {dni_cliente}.", "danger")
                return redirect(url_for('pagarecap', dni=dni_cliente))
            
            tipo_pago_original = str(credit_data.get('tipo de pago', '')).strip().lower()
            
            # Definir cuántos pagos *extras* se esperan para cada tipo de pagaré
            num_extra_payments_expected_for_credit = 0
            if 'pagaré' in tipo_pago_original:
                if tipo_pago_original == 'pagaré 3':
                    num_extra_payments_expected_for_credit = 2
                elif tipo_pago_original == 'pagaré 6':
                    num_extra_payments_expected_for_credit = 5
            elif tipo_pago_original in ['contado', 'tarjeta', 'otros']:
                 flash(f"❌ Error: El crédito con DNI {dni_cliente} no es un pagaré y no permite pagos adicionales.", "danger")
                 return redirect(url_for('pagarecap', dni=dni_cliente))

            # CORREGIDO a 5: Máximo de slots que tu hoja soporta
            max_additional_slots_in_sheet = 5 
            if slot_to_update < 1 or slot_to_update > num_extra_payments_expected_for_credit or slot_to_update > max_additional_slots_in_sheet:
                flash(f"❌ Error: El número de pago {slot_to_update} excede el límite permitido de pagos adicionales para este tipo de pagaré ({num_extra_payments_expected_for_credit}) o la estructura de la hoja ({max_additional_slots_in_sheet}).", "danger")
                return redirect(url_for('pagarecap', dni=dni_cliente))

            # Determinar las columnas exactas para actualizar usando CREDITOCAP_HEADERS
            # Esto es más robusto ante cambios de orden en los encabezados
            try:
                base_col_index = CREDITOCAP_HEADERS.index(f'pago_adicional_{slot_to_update}_factura') + 1 
            except ValueError:
                flash(f"❌ Error interno: No se encontró el encabezado para el pago adicional {slot_to_update}. Contacte a soporte.", "danger")
                return redirect(url_for('pagarecap', dni=dni_cliente))


            hoja.update_cell(row_index, base_col_index, new_factura)
            hoja.update_cell(row_index, base_col_index + 1, new_fecha)
            hoja.update_cell(row_index, base_col_index + 2, new_tipo)
            hoja.update_cell(row_index, base_col_index + 3, new_monto) # Actualiza la columna de monto
            
            flash("✅ Pago adicional registrado correctamente.", "success")
            return redirect(url_for('pagarecap', dni=dni_cliente))
            
    except ValueError as ve:
        flash(f"❌ Error de configuración en la hoja o datos: {str(ve)}. Asegúrese de que las columnas de pagos adicionales existen y son correctas.", "danger")
        print(f"ValueError en pagarecap POST: {ve}")
        traceback.print_exc() # Imprime el traceback
    except Exception as e:
        flash(f"❌ Error inesperado al procesar el pago: {str(e)}", "danger")
        print(f"ERROR en pagarecap POST: {e}")
        traceback.print_exc() # Imprime el traceback
    
    # Lógica para GET (mostrar la tabla)
    try:
        # all_records_raw ya fue obtenido con expected_headers al inicio de la función
        pagares_registros = []
        # CORREGIDO a 5: El máximo de slots que tu HTML y hoja soportan físicamente
        max_additional_slots_in_sheet = 5

        for reg in all_records_raw: # Usamos los registros ya procesados
            tipo_pago = str(reg.get('tipo de pago', '')).strip().lower()
            
            if 'pagaré' in tipo_pago:
                current_reg = reg.copy() # Trabajar en una copia para añadir nuevas claves

                # Número TOTAL de pagos esperados (inicial + extras)
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
                        
                all_payments_complete = (registered_payments_count >= num_extra_payments_expected)
                
                # Si el número de pagos extras esperados excede los slots físicos, no puede estar completo.
                if num_extra_payments_expected > max_additional_slots_in_sheet:
                    all_payments_complete = False 

                current_reg['all_payments_complete'] = all_payments_complete
                pagares_registros.append(current_reg)

    except Exception as e:
        flash(f"❌ Error al cargar los registros de pagarés: {str(e)}", "danger")
        print(f"ERROR al cargar registros en pagarecap GET: {e}")
        traceback.print_exc() # Imprime el traceback
        pagares_registros = []

    # Renderiza la plantilla 'creditocap.html' pasando los registros filtrados, headers y flag (para vista de pagarés)
    return render_template(
        'creditocap.html',
        all_registros=pagares_registros,
        creditocap_headers=CREDITOCAP_HEADERS, # Pasa los encabezados a la plantilla
        is_pagare_view=True # Flag para indicar que es la vista de pagarés
    )


# --- NUEVA RUTA API para obtener detalles del crédito (JSON) ---
@app.route('/api/get_credit_details/<string:dni_cliente>', methods=['GET'])
@login_required()
def get_credit_details_json(dni_cliente):
    try:
        spreadsheet = get_google_sheets_client().open(SPREADSHEET_NAME)
        hoja = spreadsheet.worksheet("creditocap")
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
                    'slot': i,
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
                num_total_payments_expected_for_api = 3
            elif tipo_pago_original == 'pagaré 6':
                num_total_payments_expected_for_api = 6
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

    except Exception as e:
        print(f"ERROR CRÍTICO en get_credit_details_json: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Error interno del servidor: {str(e)}"}), 500

@app.route('/product_catalog')
@login_required()
def product_catalog():
    return render_template('product_catalog.html')

# --- PUNTO DE ENTRADA PRINCIPAL ---
if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_DEBUG', '1') == '1'
    app.run(debug=debug_mode, host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
