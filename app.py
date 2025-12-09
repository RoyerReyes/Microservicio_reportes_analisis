from flask import Flask, request, send_file, jsonify
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import io
import logging
from flask_cors import CORS
from dotenv import load_dotenv
import reports # Importar la lógica de datos existente
import db

def create_app():
    load_dotenv()
    app = Flask(__name__)
    CORS(app)
    
    # Configurar logging
    logging.basicConfig(level=logging.INFO)
    
    db.init_app_db(app)
    app.teardown_appcontext(db.close_db)

    @app.route('/health', methods=['GET'])
    def health_check():
        return jsonify({"status": "ok", "service": "reportes"}), 200

    @app.route('/api/reportes', methods=['GET'])
    def get_reportes_json():
        periodo = request.args.get('periodo', 'semana')
        try:
            data = {
                'ventas': reports.get_ventas_report(periodo),
                'productos_mas_vendidos': reports.get_productos_mas_vendidos_report(periodo),
                'pedidos_por_cliente': reports.get_pedidos_por_cliente_report(periodo)
            }
            return jsonify(data)
        except Exception as e:
            app.logger.error(f"Error json: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/api/reportes/export/pdf', methods=['GET'])
    def export_pdf():
        periodo = request.args.get('periodo', 'semana')
        
        try:
            # Obtener datos usando la lógica existente
            ventas = reports.get_ventas_report(periodo)
            productos = reports.get_productos_mas_vendidos_report(periodo)
            
            # Crear buffer en memoria
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=letter)
            elements = []
            styles = getSampleStyleSheet()

            # Título
            elements.append(Paragraph(f"Reporte de Ventas - Periodo: {periodo.capitalize()}", styles['Title']))
            elements.append(Spacer(1, 12))

            # Sección Ventas
            elements.append(Paragraph("Resumen de Ventas", styles['Heading2']))
            if sales_data := [['Fecha', 'Total (S/)']] + [[v['periodo'], f"{v['total_ventas']:.2f}"] for v in ventas]:
                t = Table(sales_data)
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black)
                ]))
                elements.append(t)
            else:
                elements.append(Paragraph("No hay ventas registradas.", styles['Normal']))
            
            elements.append(Spacer(1, 24))

            # Sección Top Productos
            elements.append(Paragraph("Top Productos", styles['Heading2']))
            if prod_data := [['Producto', 'Unidades Vendidas']] + [[p['nombre'], p['total_vendido']] for p in productos]:
                t2 = Table(prod_data)
                t2.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.blue),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black)
                ]))
                elements.append(t2)
            
            doc.build(elements)
            buffer.seek(0)
            
            return send_file(
                buffer,
                as_attachment=True,
                download_name=f'reporte_{periodo}.pdf',
                mimetype='application/pdf'
            )

        except Exception as e:
            app.logger.error(f"Error PDF: {e}")
            return jsonify({"error": "Error generando PDF"}), 500

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=5001)