import os
import json
import re
from flask import Flask, request, redirect, url_for, session, flash, render_template
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')
SCOPES = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

# --- Usuarios y roles ---
USERS = {
    "admin": {
        "password": generate_password_hash(os.getenv('ADMIN_PASSWORD', 'admin123')),
        "role": "admin"
    },
    "cristian": {
        "password": generate_password_hash(os.getenv('CRISTIAN_PASSWORD', 'rivadavia620')),
        "role": "supervisor"
    },
    "delfi": {
        "password": generate_password_hash(os.getenv('DELFI_PASSWORD', 'rivadavia620')),
        "role": "supervisor"
    },
    "trento": {
        "password": generate_password_hash(os.getenv('TRENTO_PASSWORD', 'trento')),
        "role": "supervisor"
    },
    "tete": {
        "password": generate_password_hash(os.getenv('TETE_PASSWORD', 'tete123')),
        "role": "interior"
    },
    "int2": {
        "password": generate_password_hash(os.getenv('INT2_PASSWORD', 'int456')),
        "role": "interior"
    },
    "int3": {
        "password": generate_password_hash(os.getenv('INT3_PASSWORD', 'int789')),
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
                current_role_menu = {
                    "admin": "menu1",
                    "supervisor": "menu2",
                    "interior": "menu3"
                }.get(session.get('role'), 'login')
                return redirect(url_for(current_role_menu))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- Helpers ---
def get_google_sheets_client():
    if os.path.exists("credentials.json"):
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", SCOPES)
    else:
        cred_dict = json.loads(os.getenv("GOOGLE_SERVICE_ACCOUNT"))
        creds = ServiceAccountCredentials.from_json_keyfile_dict(cred_dict, SCOPES)
    return gspread.authorize(creds)

def get_drive_file_id(url):
    if not url:
        return ""
    match_id = re.search(r'(?:/d/|id=)([a-zA-Z0-9_-]+)', url)
    return match_id.group(1) if match_id else ""

# --- Rutas ---
@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form.get('usuario', '').strip()
        contraseña = request.form.get('contraseña', '').strip()

        user = USERS.get(usuario)
        if user and check_password_hash(user['password'], contraseña):
            session['logged_in'] = True
            session['usuario'] = usuario
            session['role'] = user['role']

            role_redirect = {
                "admin": "menu1",
                "supervisor": "menu2",
                "interior": "menu3"
            }
            return redirect(url_for(role_redirect.get(user['role'], 'login')))
        else:
            flash("Usuario o contraseña incorrectos", "danger")

    return render_template('login.html')


# Rutas de autenticación
@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form.get('usuario', '').strip()
        contraseña = request.form.get('contraseña', '').strip()

        user = USERS.get(usuario)
        if user and check_password_hash(user['password'], contraseña):
            session['logged_in'] = True
            session['usuario'] = usuario
            session['role'] = user['role']
            
            # Redirecciona al menú según el rol
            role_redirect = {
                "admin": "menu1",
                "supervisor": "menu2",
                "interior": "menu3"
            }
            return redirect(url_for(role_redirect.get(user['role'], 'login')))
        else:
            flash("Usuario o contraseña incorrectos", "danger")
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Rutas de menú
@app.route('/menu1')
@login_required(role='admin')
def menu1():
    return render_template('menu1.html', user=session.get('user'))

@app.route('/menu2')
@login_required(role='supervisor')
def menu2():
    return render_template('menu2.html', user=session.get('user'))

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
