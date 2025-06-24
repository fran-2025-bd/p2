from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, make_response, send_file
import os
import json
import gspread
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import locale
import traceback
import re
import requests
from functools import wraps
import calendar
import base64
from fpdf import FPDF
import io

# Configuración de idioma
try:
    locale.setlocale(locale.LC_TIME, 'es_ES.utf8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_TIME, 'es_AR.utf8')
    except locale.Error:
        locale.setlocale(locale.LC_TIME, '')

app = Flask(__name__)
app.secret_key = 'clave_secreta_para_sesiones'  # Clave fija para las sesiones
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True

# --- CONFIGURACIÓN GOOGLE SHEETS ---
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

if os.path.exists("credentials.json"):
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
else:
    json_str = os.getenv("GOOGLE_SERVICE_ACCOUNT")
    if not json_str:
        raise Exception("ERROR: No se encontró 'GOOGLE_SERVICE_ACCOUNT' en variables de entorno ni 'credentials.json' local.")
    
    try:
        cred_dict = json.loads(base64.b64decode(json_str).decode('utf-8'))
    except (TypeError, json.JSONDecodeError) as e:
        try:
            cred_dict = json.loads(json_str)
        except json.JSONDecodeError as json_e:
            raise Exception(f"ERROR: La variable de entorno 'GOOGLE_SERVICE_ACCOUNT' no contiene JSON válido: {json_e}")

    creds = ServiceAccountCredentials.from_json_keyfile_dict(cred_dict, scope)

client = gspread.authorize(creds)

# --- ENCABEZADOS ESPERADOS ---
CREDITOCAP_HEADERS = [
    "n° de factura", "fecha de venta", "nombre completo", "dni", "tel", "domicilio",
    "articulo vendido", "tipo de pago", "vendedor", "monto", "detalle de venta",
    "pago_adicional_1_factura", "pago_adicional_1_fecha", "pago_adicional_1_tipo", "monto_adicional_1",
    "pago_adicional_2_factura", "pago_adicional_2_fecha", "pago_adicional_2_tipo", "monto_adicional_2",
    "pago_adicional_3_factura", "pago_adicional_3_fecha", "pago_adicional_3_tipo", "monto_adicional_3",
    "pago_adicional_4_factura", "pago_adicional_4_fecha", "pago_adicional_4_tipo", "monto_adicional_4",
    "pago_adicional_5_factura", "pago_adicional_5_fecha", "pago_adicional_5_tipo", "monto_adicional_5"
]

# --- USUARIOS Y ROLES (CONTRASEÑAS EN TEXTO PLANO) ---
USERS = {
    "admin": {
        "password": "admin123",  # Contraseña en texto plano
        "role": "admin"
    },
    "cristian": {
        "password": "rivadavia620",
        "role": "supervisor"
    },
    "delfi": {
        "password": "rivadavia620",
        "role": "supervisor"
    },
    "trento": {
        "password": "trento",
        "role": "supervisor"
    },
    "tete": {
        "password": "tete123",
        "role": "interior"
    },
    "int2": {
        "password": "int456",
        "role": "interior"
    },
    "int3": {
        "password": "int789",
        "role": "interior"
    }
}

# --- Decorador para rutas protegidas ---
def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get('logged_in'):
                flash("Por favor inicia sesión", "warning")
                return redirect(url_for('login'))
            if role and session.get('role') != role:
                flash("No tienes permisos", "danger")
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- RUTAS PRINCIPALES ---
@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = USERS.get(username)
        
        # Verificación directa de contraseña en texto plano
        if user and user['password'] == password:
            session['logged_in'] = True
            session['user'] = username
            session['role'] = user['role']
            
            # Redirección según rol
            if user['role'] == 'admin':
                return redirect(url_for('menu1'))
            elif user['role'] == 'supervisor':
                return redirect(url_for('menu2'))
            else:
                return redirect(url_for('menu3'))
        else:
            flash("Usuario o contraseña incorrectos", "danger")

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- RUTAS DE MENÚ ---
@app.route('/menu1')
@login_required(role='admin')
def menu1():
    return render_template('menu1.html', user=session.get('user'))

@app.route('/menu2')
@login_required(role='supervisor')
def menu2():
    return render_template('menu2.html', username=session.get('user'), role=session.get('role'))

@app.route('/menu3')
@login_required(role='interior')
def menu3():
    return render_template('menu3.html', user=session.get('user'))

# (Aquí irían el resto de tus rutas para manejar Google Sheets, PDFs, etc.)


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
