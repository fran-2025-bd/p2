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
