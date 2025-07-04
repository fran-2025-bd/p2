# pdf_generator.py

import io
import os
import json
from fpdf import FPDF
from datetime import date

def create_budget_pdf(app, items):
    if not items:
        print("No se proporcionaron artículos para el presupuesto.")
        return None

    class PDF(FPDF):
        def header(self):
            # Logo de la empresa (asegúrate de que 'logo.png' exista en static/uploads)
            # Si no tienes logo, puedes comentar o eliminar esta sección
            logo_path = os.path.join(app.config['UPLOAD_FOLDER'], 'logo.png')
            if os.path.exists(logo_path):
                self.image(logo_path, 10, 8, 33) # Posición y tamaño del logo
            
            # Nombre de la Empresa
            self.set_font('Arial', 'B', 18) # Fuente más grande para el nombre de la empresa
            self.set_text_color(25, 118, 210) # Un azul más vibrante
            self.cell(0, 10, 'SAN NICOLAS SRL', 0, 1, 'C') 
            
            # Título del documento
            self.ln(5) 
            self.set_font('Arial', 'B', 20) # Título más grande y en negrita
            self.set_text_color(50, 50, 50) # Gris oscuro para el título
            self.cell(0, 10, 'PRESUPUESTO DE PRODUCTOS', 0, 1, 'C') # Título más descriptivo
            self.ln(5)

            # Información del presupuesto (Fecha)
            self.set_font('Arial', '', 10)
            self.set_text_color(80, 80, 80) # Gris medio
            self.cell(0, 5, f"Fecha: {date.today().strftime('%d/%m/%Y')}", 0, 1, 'R')
            self.line(10, self.get_y(), self.w - 10, self.get_y()) # Línea divisoria
            self.ln(10) # Espacio antes del contenido principal

        def footer(self):
            self.set_y(-15) # Posición a 1.5 cm del final
            self.set_font('Arial', 'I', 8) # Itálica
            self.set_text_color(100, 100, 100) # Gris claro
            
            # Centrar número de página
            self.cell(0, 10, f'Página {self.page_no()}/{{nb}}', 0, 0, 'C')
            
            # Mover a la derecha para información de contacto
            # self.w - (ancho total del texto + margen derecho)
            contact_info_width = self.get_string_width('Contacto: info@tuempresa.com.ar | Cel: (3804-626251)') + 5 # +5 para un pequeño margen
            self.set_x(self.w - contact_info_width - 10) # 10mm de margen derecho
            self.cell(contact_info_width, 10, 'Contacto: Oficina Av Rivadavia 620 | Cel: (3804-626251)', 0, 0, 'R')
            
    pdf = PDF(format='A4', unit='mm')
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Colores para la tabla
    pdf.set_fill_color(60, 140, 240) # Azul para cabecera de tabla
    pdf.set_text_color(255, 255, 255) # Texto blanco en cabecera
    pdf.set_draw_color(100, 100, 100) # Bordes grises oscuros para la tabla

    col_widths = {
        'img': 15, 'nombre': 75, 'codigo': 25, 'cantidad': 10,
        'precio_unitario': 25, 'subtotal': 25
    }
    total_table_width = sum(col_widths.values())
    
    # Cabecera de la tabla
    pdf.set_font("Arial", style='B', size=9)
    start_x = (pdf.w - total_table_width) / 2
    pdf.set_x(start_x)
    
    pdf.cell(col_widths['img'], 10, "Imagen", border=1, align='C', fill=True)
    pdf.cell(col_widths['nombre'], 10, "Artículo", border=1, align='C', fill=True)
    pdf.cell(col_widths['codigo'], 10, "Código", border=1, align='C', fill=True)
    pdf.cell(col_widths['cantidad'], 10, "Cant.", border=1, align='C', fill=True)
    pdf.cell(col_widths['precio_unitario'], 10, "P. Unitario", border=1, align='C', fill=True)
    pdf.cell(col_widths['subtotal'], 10, "Subtotal", border=1, align='C', fill=True)
    pdf.ln()

    # Contenido de la tabla
    pdf.set_font("Arial", size=9)
    total_precio_final = 0
    total_cont_efectivo = 0
    total_cuotas_2 = 0; total_cuotas_3 = 0; total_cuotas_6 = 0
    total_cuotas_9 = 0; total_cuotas_12 = 0

    row_height = 15
    fill_row = False # Para alternar colores de fila
    
    for item in items:
        nombre = item.get('Nombre Producto', 'N/A')
        codigo = item.get('Código', 'N/A')
        cantidad = item.get('cantidad', 0)
        precio_final_unitario = item.get('PRECIO FINAL', 0)
        cont_efectivo_unitario = item.get('cont efectivo', 0)
        cuotas_2_unitario = item.get('2 CUOTAS DE', 0)
        cuotas_3_unitario = item.get('3 CUOTAS DE', 0)
        cuotas_6_unitario = item.get('6 CUOTAS DE', 0)
        cuotas_9_unitario = item.get('9 CUOTAS DE', 0)
        cuotas_12_unitario = item.get('12 CUOTAS DE', 0)

        subtotal_precio_final = precio_final_unitario * cantidad
        subtotal_cont_efectivo = cont_efectivo_unitario * cantidad
        subtotal_cuotas_2 = cuotas_2_unitario * cantidad
        subtotal_cuotas_3 = cuotas_3_unitario * cantidad
        subtotal_cuotas_6 = cuotas_6_unitario * cantidad
        subtotal_cuotas_9 = cuotas_9_unitario * cantidad
        subtotal_cuotas_12 = cuotas_12_unitario * cantidad

        total_precio_final += subtotal_precio_final
        total_cont_efectivo += subtotal_cont_efectivo
        total_cuotas_2 += subtotal_cuotas_2
        total_cuotas_3 += subtotal_cuotas_3
        total_cuotas_6 += subtotal_cuotas_6
        total_cuotas_9 += subtotal_cuotas_9
        total_cuotas_12 += subtotal_cuotas_12

        # Alternar colores de fila para el cuerpo de la tabla
        if fill_row: 
            pdf.set_fill_color(250, 248, 255) # Azul muy claro (Alice Blue)
            pdf.set_text_color(50,50,50) # Texto un poco más oscuro
        else: 
            pdf.set_fill_color(255, 255, 255) # Blanco
            pdf.set_text_color(0,0,0) # Texto negro
        fill_row = not fill_row

        pdf.set_x(start_x) # Asegurar alineación
        current_y = pdf.get_y()

        image_name = item.get('image_id', 'no_image.png')
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_name)
        if not os.path.exists(image_path) or not os.path.isfile(image_path):
             image_path = os.path.join(app.config['UPLOAD_FOLDER'], 'no_image.png') 
        
        try:
            img_width = 12; img_height = 12
            img_x = pdf.get_x() + (col_widths['img'] - img_width) / 2
            img_y = pdf.get_y() + (row_height - img_height) / 2
            pdf.image(image_path, x=img_x, y=img_y, w=img_width, h=img_height)
            pdf.cell(col_widths['img'], row_height, '', border=1, ln=0, fill=True)
        except Exception as e:
            print(f"Error al añadir imagen {image_path}: {e}")
            pdf.cell(col_widths['img'], row_height, "N/I", border=1, align='C', ln=0, fill=True)

        # Usar multi_cell para nombre del producto y luego restablecer posición
        pdf.multi_cell(col_widths['nombre'], row_height/3, nombre, border=0, align='L')
        # Restablecer la posición X e Y para el resto de las celdas en esta fila
        pdf.set_xy(start_x + col_widths['img'] + col_widths['nombre'], current_y)
        
        pdf.cell(col_widths['codigo'], row_height, str(codigo), border=1, align='C', fill=True)
        pdf.cell(col_widths['cantidad'], row_height, str(cantidad), border=1, align='C', fill=True)
        
        # Precios unitarios y subtotales SIN DECIMALES
        pdf.cell(col_widths['precio_unitario'], row_height, f"{precio_final_unitario:,.0f} ARS", border=1, align='R', fill=True)
        pdf.cell(col_widths['subtotal'], row_height, f"{subtotal_precio_final:,.0f} ARS", border=1, align='R', fill=True)
        pdf.ln()

    # Resumen de Totales
    pdf.ln(10)
    pdf.set_font("Arial", style='B', size=12)
    pdf.set_fill_color(200, 220, 240) # Azul más suave para el bloque de totales
    pdf.set_draw_color(100, 100, 100)
    pdf.set_text_color(0, 0, 0)

    total_block_width = 80
    pdf.set_x(pdf.w - total_block_width - 10)

    # TOTAL PRECIO FINAL (mantener 2 decimales para totales de dinero)
    pdf.cell(total_block_width, 10, f"TOTAL PRECIO FINAL: {total_precio_final:,.0f} ARS", border=1, align='R', fill=True)
    pdf.ln()
    pdf.set_x(pdf.w - total_block_width - 10)
    pdf.set_font("Arial", style='', size=10) # Fuente más pequeña para otros totales
    
    # Otros Totales (mantener 2 decimales)
    pdf.cell(total_block_width, 8, f"Total Contado Efectivo: {total_cont_efectivo:,.0f} ARS", border=1, align='R', fill=True)
    pdf.ln()
    pdf.set_x(pdf.w - total_block_width - 10)
    pdf.cell(total_block_width, 8, f"Total 2 Cuotas: {total_cuotas_2:,.0f} ARS", border=1, align='R', fill=True)
    pdf.ln()
    pdf.set_x(pdf.w - total_block_width - 10)
    pdf.cell(total_block_width, 8, f"Total 3 Cuotas: {total_cuotas_3:,.0f} ARS", border=1, align='R', fill=True)
    pdf.ln()
    pdf.set_x(pdf.w - total_block_width - 10)
    pdf.cell(total_block_width, 8, f"Total 6 Cuotas: {total_cuotas_6:,.0f} ARS", border=1, align='R', fill=True)
    pdf.ln()
    pdf.set_x(pdf.w - total_block_width - 10)
    pdf.cell(total_block_width, 8, f"Total 9 Cuotas: {total_cuotas_9:,.0f} ARS", border=1, align='R', fill=True)
    pdf.ln()
    pdf.set_x(pdf.w - total_block_width - 10)
    pdf.cell(total_block_width, 8, f"Total 12 Cuotas: {total_cuotas_12:,.0f} ARS", border=1, align='R', fill=True)
    pdf.ln(10)

    # Nota o Términos y Condiciones
    pdf.set_font("Arial", style='I', size=8)
    pdf.set_text_color(100, 100, 100)
    pdf.multi_cell(0, 5, "Nota: Este presupuesto tiene una validez de 7 días. Los precios pueden variar sin previo aviso. Consulte disponibilidad. Los montos de las cuotas son meramente informativos y están sujetos a las políticas de financiación vigentes.", 0, 'L')

    pdf_file = io.BytesIO()
    pdf.output(pdf_file)
    pdf_file.seek(0)

    return pdf_file