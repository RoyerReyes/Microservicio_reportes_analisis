"""
Generador de reportes en formato PDF con gráficos.
"""
import io
import logging
from datetime import datetime
from typing import Dict, Any, List
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, PageBreak, Image
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT

logger = logging.getLogger(__name__)


class PDFGenerator:
    """
    Generador de reportes PDF con diseño profesional.
    """

    def __init__(self, company_name: str = "SOA Minimarket", logo_path: str = None):
        """
        Inicializa el generador de PDF.

        Args:
            company_name: Nombre de la empresa
            logo_path: Ruta al logo (opcional)
        """
        self.company_name = company_name
        self.logo_path = logo_path
        self.styles = getSampleStyleSheet()

        # Estilos personalizados
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Title'],
            fontSize=24,
            textColor=colors.HexColor('#2563eb'),
            spaceAfter=30,
            alignment=TA_CENTER
        ))

        self.styles.add(ParagraphStyle(
            name='CustomHeading',
            parent=self.styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#1e40af'),
            spaceBefore=20,
            spaceAfter=12
        ))

    def _create_header(self, report_title: str, period: str) -> List:
        """
        Crea el encabezado del reporte.

        Args:
            report_title: Título del reporte
            period: Periodo del reporte

        Returns:
            Lista de elementos Platypus
        """
        elements = []

        # Título
        title = Paragraph(
            f"{self.company_name}<br/>{report_title}",
            self.styles['CustomTitle']
        )
        elements.append(title)

        # Metadata
        now = datetime.now().strftime("%d/%m/%Y %H:%M")
        metadata_text = f"<b>Periodo:</b> {period} | <b>Generado:</b> {now}"
        metadata = Paragraph(metadata_text, self.styles['Normal'])
        elements.append(metadata)
        elements.append(Spacer(1, 20))

        return elements

    def _create_summary_table(self, summary_data: Dict[str, Any]) -> Table:
        """
        Crea tabla de resumen con métricas clave.

        Args:
            summary_data: Dict con métricas

        Returns:
            Tabla de resumen
        """
        data = [
            ['Métrica', 'Valor']
        ]

        for key, value in summary_data.items():
            # Formatear key para display
            display_key = key.replace('_', ' ').title()

            # Formatear valor
            if isinstance(value, float):
                if 'porcentaje' in key.lower() or 'growth' in key.lower():
                    display_value = f"{value:.2f}%"
                else:
                    display_value = f"S/ {value:,.2f}"
            elif isinstance(value, int):
                display_value = f"{value:,}"
            else:
                display_value = str(value)

            data.append([display_key, display_value])

        table = Table(data, colWidths=[3*inch, 2*inch])
        table.setStyle(TableStyle([
            # Header
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),

            # Body
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f3f4f6')),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9fafb')]),

            # Grid
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#d1d5db'))
        ]))

        return table

    def _create_data_table(self, data: List[Dict[str, Any]], columns: List[str], title: str = None) -> List:
        """
        Crea tabla con datos del reporte.

        Args:
            data: Lista de dicts con datos
            columns: Lista de columnas a mostrar
            title: Título de la sección (opcional)

        Returns:
            Lista de elementos Platypus
        """
        elements = []

        if title:
            elements.append(Paragraph(title, self.styles['CustomHeading']))

        if not data:
            elements.append(Paragraph("No hay datos disponibles para este periodo.", self.styles['Normal']))
            return elements

        # Crear headers
        table_data = [[col.replace('_', ' ').title() for col in columns]]

        # Agregar filas
        for row in data:
            table_row = []
            for col in columns:
                value = row.get(col, '')

                # Formatear según tipo
                if isinstance(value, float):
                    if 'porcentaje' in col.lower():
                        table_row.append(f"{value:.2f}%")
                    elif 'precio' in col.lower() or 'total' in col.lower() or 'revenue' in col.lower() or 'gastado' in col.lower() or 'ventas' in col.lower() or 'ticket' in col.lower():
                        table_row.append(f"S/ {value:,.2f}")
                    else:
                        table_row.append(f"{value:.2f}")
                elif isinstance(value, int):
                    table_row.append(f"{value:,}")
                else:
                    table_row.append(str(value))

            table_data.append(table_row)

        # Calcular ancho de columnas
        col_width = 6.5 * inch / len(columns)
        table = Table(table_data, colWidths=[col_width] * len(columns))

        table.setStyle(TableStyle([
            # Header
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563eb')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),

            # Body
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#eff6ff')]),

            # Grid
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#93c5fd'))
        ]))

        elements.append(table)
        elements.append(Spacer(1, 20))

        return elements

    def generate_sales_report(self, report_data: Dict[str, Any], period: str) -> io.BytesIO:
        """
        Genera PDF del reporte de ventas.

        Args:
            report_data: Datos del reporte
            period: Periodo del reporte

        Returns:
            BytesIO con el PDF generado
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []

        try:
            # Header
            elements.extend(self._create_header("Reporte de Ventas", period.capitalize()))

            # Resumen
            data = report_data.get('data', {})
            summary = {
                'Total Revenue': data.get('total_revenue', 0),
                'Total Pedidos': data.get('total_orders', 0),
                'Ticket Promedio': data.get('average_ticket', 0)
            }
            elements.append(self._create_summary_table(summary))
            elements.append(Spacer(1, 30))

            # Tabla detallada
            sales_data = data.get('data', [])
            if sales_data:
                columns = ['periodo', 'total_ventas', 'numero_pedidos', 'ticket_promedio']
                elements.extend(self._create_data_table(sales_data, columns, "Ventas por Día"))

            # Build PDF
            doc.build(elements)
            buffer.seek(0)

            logger.info("✅ PDF de ventas generado exitosamente")
            return buffer

        except Exception as e:
            logger.error(f"Error generando PDF de ventas: {e}")
            raise

    def generate_products_report(self, report_data: Dict[str, Any], period: str) -> io.BytesIO:
        """
        Genera PDF del reporte de productos.

        Args:
            report_data: Datos del reporte
            period: Periodo del reporte

        Returns:
            BytesIO con el PDF generado
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []

        try:
            # Header
            elements.extend(self._create_header("Reporte de Productos Más Vendidos", period.capitalize()))

            # Resumen
            data = report_data.get('data', {})
            summary = {
                'Total Productos': data.get('total_products', 0),
                'Total Unidades': data.get('total_units_sold', 0)
            }
            elements.append(self._create_summary_table(summary))
            elements.append(Spacer(1, 30))

            # Tabla de productos
            products_data = data.get('data', [])
            if products_data:
                columns = ['nombre', 'categoria', 'total_vendido', 'revenue', 'porcentaje_ventas']
                elements.extend(self._create_data_table(products_data, columns, "Top 10 Productos"))

            doc.build(elements)
            buffer.seek(0)

            logger.info("✅ PDF de productos generado exitosamente")
            return buffer

        except Exception as e:
            logger.error(f"Error generando PDF de productos: {e}")
            raise

    def generate_customers_report(self, report_data: Dict[str, Any], period: str) -> io.BytesIO:
        """
        Genera PDF del reporte de clientes.

        Args:
            report_data: Datos del reporte
            period: Periodo del reporte

        Returns:
            BytesIO con el PDF generado
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []

        try:
            # Header
            elements.extend(self._create_header("Reporte de Clientes Top", period.capitalize()))

            # Resumen
            data = report_data.get('data', {})
            summary = {
                'Total Clientes': data.get('total_customers', 0)
            }
            elements.append(self._create_summary_table(summary))
            elements.append(Spacer(1, 30))

            # Tabla de clientes
            customers_data = data.get('data', [])
            if customers_data:
                columns = ['nombre_completo', 'cantidad_pedidos', 'total_gastado', 'ticket_promedio']
                elements.extend(self._create_data_table(customers_data, columns, "Top 20 Clientes"))

            doc.build(elements)
            buffer.seek(0)

            logger.info("✅ PDF de clientes generado exitosamente")
            return buffer

        except Exception as e:
            logger.error(f"Error generando PDF de clientes: {e}")
            raise

    def generate_generic_report(self, report_data: Dict[str, Any], title: str, period: str) -> io.BytesIO:
        """
        Genera PDF genérico para cualquier tipo de reporte.

        Args:
            report_data: Datos del reporte
            title: Título del reporte
            period: Periodo del reporte

        Returns:
            BytesIO con el PDF generado
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []

        try:
            # Header
            elements.extend(self._create_header(title, period.capitalize()))

            # Contenido
            data = report_data.get('data', {})
            if isinstance(data, dict) and 'data' in data:
                items = data.get('data', [])
                if items and len(items) > 0:
                    # Detectar columnas automáticamente
                    columns = list(items[0].keys())
                    elements.extend(self._create_data_table(items, columns, "Datos del Reporte"))
            else:
                elements.append(Paragraph(str(data), self.styles['Normal']))

            doc.build(elements)
            buffer.seek(0)

            logger.info(f"✅ PDF genérico generado: {title}")
            return buffer

        except Exception as e:
            logger.error(f"Error generando PDF genérico: {e}")
            raise
