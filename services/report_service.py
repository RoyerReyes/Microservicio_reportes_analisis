"""
Servicio de reportes con lógica de negocio.
Coordina DatabaseManager y CacheManager para generar reportes.
"""
import logging
import time
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional, Tuple
from models import (
    ReportPeriod, ReportType, ReportRequest,
    SalesReport, SalesReportItem,
    ProductsReport, ProductReportItem,
    CustomersReport, CustomerReportItem,
    RevenueByCategoryReport, RevenueByCategoryItem,
    HourlySalesReport, HourlySalesItem,
    SummaryMetrics,
    PaginationMetadata
)
from .database_manager import DatabaseManager
from .cache_manager import CacheManager

logger = logging.getLogger(__name__)


class ReportService:
    """
    Servicio principal de reportes.
    Maneja generación, caché e invalidación de reportes.
    """

    def __init__(self, db_manager: DatabaseManager, cache_manager: CacheManager):
        """
        Inicializa el servicio de reportes.

        Args:
            db_manager: Gestor de base de datos
            cache_manager: Gestor de caché
        """
        self.db = db_manager
        self.cache = cache_manager

    def _get_date_range(self, period: ReportPeriod, start_date: Optional[date] = None, end_date: Optional[date] = None) -> Tuple[date, date]:
        """
        Calcula el rango de fechas basado en el periodo.

        Args:
            period: Periodo del reporte
            start_date: Fecha inicio (para CUSTOM)
            end_date: Fecha fin (para CUSTOM)

        Returns:
            Tupla (fecha_inicio, fecha_fin)
        """
        today = datetime.now().date()

        if period == ReportPeriod.CUSTOM:
            if not start_date or not end_date:
                raise ValueError("start_date y end_date son requeridos para periodo 'personalizado'")
            return start_date, end_date

        elif period == ReportPeriod.DAY:
            return today, today

        elif period == ReportPeriod.WEEK:
            start = today - timedelta(days=7)
            return start, today

        elif period == ReportPeriod.MONTH:
            start = today - timedelta(days=30)
            return start, today

        elif period == ReportPeriod.QUARTER:
            start = today - timedelta(days=90)
            return start, today

        elif period == ReportPeriod.YEAR:
            start = today - timedelta(days=365)
            return start, today

        else:
            # Default: semana
            start = today - timedelta(days=7)
            return start, today

    def _apply_filters(self, base_query: str, request: ReportRequest) -> Tuple[str, List[Any]]:
        """
        Aplica filtros adicionales a una query.

        Args:
            base_query: Query SQL base
            request: Request con filtros

        Returns:
            Tupla (query modificada, parámetros)
        """
        params = []
        conditions = []

        if not request.filters:
            return base_query, params

        filters = request.filters

        if filters.customer_id:
            conditions.append("p.cliente_id = ?")
            params.append(filters.customer_id)

        if filters.product_id:
            conditions.append("dp.producto_id = ?")
            params.append(filters.product_id)

        if filters.category_id:
            conditions.append("prod.categoria_id = ?")
            params.append(filters.category_id)

        if filters.status:
            conditions.append("p.estado = ?")
            params.append(filters.status.value)

        if filters.min_amount:
            conditions.append("p.total >= ?")
            params.append(filters.min_amount)

        if filters.max_amount:
            conditions.append("p.total <= ?")
            params.append(filters.max_amount)

        # Agregar condiciones a la query
        if conditions:
            if 'WHERE' in base_query:
                base_query += " AND " + " AND ".join(conditions)
            else:
                base_query += " WHERE " + " AND ".join(conditions)

        return base_query, params

    def _apply_pagination(self, query: str, request: ReportRequest) -> Tuple[str, int, int]:
        """
        Aplica paginación a una query.

        Args:
            query: Query SQL
            request: Request con parámetros de paginación

        Returns:
            Tupla (query con LIMIT/OFFSET, page, page_size)
        """
        if not request.pagination:
            return query, 1, 50

        page = request.pagination.page
        page_size = request.pagination.page_size
        offset = (page - 1) * page_size

        # Agregar ordenamiento si está especificado
        if request.pagination.sort_by:
            query += f" ORDER BY {request.pagination.sort_by} {request.pagination.order.upper()}"

        # Agregar LIMIT y OFFSET
        query += f" LIMIT {page_size} OFFSET {offset}"

        return query, page, page_size

    def get_sales_report(self, request: ReportRequest) -> Dict[str, Any]:
        """
        Genera reporte de ventas por periodo.

        Args:
            request: Request del reporte

        Returns:
            Dict con datos del reporte
        """
        start_time = time.time()

        # Verificar caché
        cache_key = self.cache._generate_cache_key(
            'report:sales',
            period=request.period.value,
            start=request.date_range.start_date if request.date_range else None,
            end=request.date_range.end_date if request.date_range else None
        )

        cached = self.cache.get(cache_key)
        if cached:
            logger.info(f"✅ Reporte de ventas obtenido del caché: {cache_key}")
            cached['cached'] = True
            return cached

        # Calcular rango de fechas
        start_date, end_date = self._get_date_range(
            request.period,
            request.date_range.start_date if request.date_range else None,
            request.date_range.end_date if request.date_range else None
        )

        # Query
        query = """
            SELECT
                DATE(fecha_pedido) as periodo,
                SUM(total) as total_ventas,
                COUNT(*) as numero_pedidos,
                AVG(total) as ticket_promedio
            FROM pedidos_pedido
            WHERE estado = 'COMPLETADO'
                AND fecha_pedido >= ?
                AND fecha_pedido <= ?
            GROUP BY DATE(fecha_pedido)
            ORDER BY periodo
        """

        try:
            results = self.db.execute_query(query, (start_date, end_date))

            # Convertir a modelos Pydantic
            items = [
                SalesReportItem(
                    periodo=str(row['periodo']),
                    total_ventas=float(row['total_ventas']),
                    numero_pedidos=int(row['numero_pedidos']),
                    ticket_promedio=float(row['ticket_promedio'])
                )
                for row in results
            ]

            # Calcular totales
            total_revenue = sum(item.total_ventas for item in items)
            total_orders = sum(item.numero_pedidos for item in items)
            average_ticket = total_revenue / total_orders if total_orders > 0 else 0.0

            report = SalesReport(
                data=items,
                total_revenue=total_revenue,
                total_orders=total_orders,
                average_ticket=average_ticket
            )

            result = {
                'report_type': 'ventas',
                'period': request.period.value,
                'data': report.model_dump(),
                'cached': False,
                'execution_time_ms': (time.time() - start_time) * 1000
            }

            # Guardar en caché
            self.cache.set(cache_key, result, ttl=600)  # 10 minutos

            return result

        except Exception as e:
            logger.error(f"Error generando reporte de ventas: {e}")
            raise

    def get_products_report(self, request: ReportRequest) -> Dict[str, Any]:
        """
        Genera reporte de productos más vendidos.

        Args:
            request: Request del reporte

        Returns:
            Dict con datos del reporte
        """
        start_time = time.time()

        # Calcular rango de fechas
        start_date, end_date = self._get_date_range(
            request.period,
            request.date_range.start_date if request.date_range else None,
            request.date_range.end_date if request.date_range else None
        )

        # Query
        query = """
            SELECT
                p.id as producto_id,
                p.nombre,
                COALESCE(c.nombre, 'Sin categoría') as categoria,
                SUM(dp.cantidad) as total_vendido,
                SUM(dp.precio * dp.cantidad) as revenue
            FROM pedidos_detallepedido dp
            JOIN pedidos_producto p ON dp.producto_id = p.id
            LEFT JOIN pedidos_categoria c ON p.categoria_id = c.id
            JOIN pedidos_pedido pe ON dp.pedido_id = pe.id
            WHERE pe.estado = 'COMPLETADO'
                AND pe.fecha_pedido >= ?
                AND pe.fecha_pedido <= ?
            GROUP BY p.id, p.nombre, c.nombre
            ORDER BY total_vendido DESC
            LIMIT 10
        """

        try:
            results = self.db.execute_query(query, (start_date, end_date))

            # Calcular total revenue para porcentajes
            total_revenue = sum(float(row['revenue']) for row in results)

            items = [
                ProductReportItem(
                    producto_id=int(row['producto_id']),
                    nombre=row['nombre'],
                    categoria=row['categoria'],
                    total_vendido=int(row['total_vendido']),
                    revenue=float(row['revenue']),
                    porcentaje_ventas=round((float(row['revenue']) / total_revenue * 100), 2) if total_revenue > 0 else 0.0
                )
                for row in results
            ]

            report = ProductsReport(
                data=items,
                total_products=len(items),
                total_units_sold=sum(item.total_vendido for item in items)
            )

            result = {
                'report_type': 'productos',
                'period': request.period.value,
                'data': report.model_dump(),
                'cached': False,
                'execution_time_ms': (time.time() - start_time) * 1000
            }

            return result

        except Exception as e:
            logger.error(f"Error generando reporte de productos: {e}")
            raise

    def get_customers_report(self, request: ReportRequest) -> Dict[str, Any]:
        """
        Genera reporte de clientes top.

        Args:
            request: Request del reporte

        Returns:
            Dict con datos del reporte
        """
        start_time = time.time()

        start_date, end_date = self._get_date_range(
            request.period,
            request.date_range.start_date if request.date_range else None,
            request.date_range.end_date if request.date_range else None
        )

        query = """
            SELECT
                u.id as cliente_id,
                u.username,
                CONCAT(u.first_name, ' ', u.last_name) as nombre_completo,
                COUNT(p.id) as cantidad_pedidos,
                SUM(p.total) as total_gastado,
                AVG(p.total) as ticket_promedio,
                MAX(p.fecha_pedido) as ultimo_pedido
            FROM auth_user u
            JOIN pedidos_pedido p ON u.id = p.cliente_id
            WHERE p.fecha_pedido >= ? AND p.fecha_pedido <= ?
            GROUP BY u.id, u.username, u.first_name, u.last_name
            ORDER BY total_gastado DESC
            LIMIT 20
        """

        try:
            results = self.db.execute_query(query, (start_date, end_date))

            items = [
                CustomerReportItem(
                    cliente_id=int(row['cliente_id']),
                    username=row['username'],
                    nombre_completo=row['nombre_completo'] if row['nombre_completo'].strip() else row['username'],
                    cantidad_pedidos=int(row['cantidad_pedidos']),
                    total_gastado=float(row['total_gastado']),
                    ticket_promedio=float(row['ticket_promedio']),
                    ultimo_pedido=str(row['ultimo_pedido'])[:10] if row['ultimo_pedido'] else None
                )
                for row in results
            ]

            report = CustomersReport(
                data=items,
                total_customers=len(items)
            )

            result = {
                'report_type': 'clientes',
                'period': request.period.value,
                'data': report.model_dump(),
                'cached': False,
                'execution_time_ms': (time.time() - start_time) * 1000
            }

            return result

        except Exception as e:
            logger.error(f"Error generando reporte de clientes: {e}")
            raise

    def get_revenue_by_category(self, request: ReportRequest) -> Dict[str, Any]:
        """
        Genera reporte de revenue por categoría.

        Args:
            request: Request del reporte

        Returns:
            Dict con datos del reporte
        """
        start_date, end_date = self._get_date_range(
            request.period,
            request.date_range.start_date if request.date_range else None,
            request.date_range.end_date if request.date_range else None
        )

        query = """
            SELECT
                COALESCE(c.nombre, 'Sin categoría') as categoria,
                SUM(dp.precio * dp.cantidad) as revenue,
                SUM(dp.cantidad) as unidades_vendidas
            FROM pedidos_detallepedido dp
            JOIN pedidos_producto p ON dp.producto_id = p.id
            LEFT JOIN pedidos_categoria c ON p.categoria_id = c.id
            JOIN pedidos_pedido pe ON dp.pedido_id = pe.id
            WHERE pe.estado = 'COMPLETADO'
                AND pe.fecha_pedido >= ?
                AND pe.fecha_pedido <= ?
            GROUP BY c.nombre
            ORDER BY revenue DESC
        """

        try:
            results = self.db.execute_query(query, (start_date, end_date))

            total_revenue = sum(float(row['revenue']) for row in results)

            items = [
                RevenueByCategoryItem(
                    categoria=row['categoria'],
                    revenue=float(row['revenue']),
                    porcentaje=round((float(row['revenue']) / total_revenue * 100), 2) if total_revenue > 0 else 0.0,
                    unidades_vendidas=int(row['unidades_vendidas'])
                )
                for row in results
            ]

            report = RevenueByCategoryReport(
                data=items,
                total_revenue=total_revenue
            )

            return {
                'report_type': 'revenue_categoria',
                'period': request.period.value,
                'data': report.model_dump(),
                'cached': False
            }

        except Exception as e:
            logger.error(f"Error generando reporte de categorías: {e}")
            raise

    def get_summary_dashboard(self) -> Dict[str, Any]:
        """
        Genera métricas resumidas del dashboard.

        Returns:
            Dict con métricas del día
        """
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)

        # Revenue de hoy
        query_today = """
            SELECT
                COUNT(*) as total_orders,
                SUM(total) as total_revenue,
                AVG(total) as average_ticket
            FROM pedidos_pedido
            WHERE DATE(fecha_pedido) = ? AND estado = 'COMPLETADO'
        """

        # Revenue de ayer para comparación
        query_yesterday = """
            SELECT SUM(total) as total_revenue
            FROM pedidos_pedido
            WHERE DATE(fecha_pedido) = ? AND estado = 'COMPLETADO'
        """

        # Top producto de hoy
        query_top_product = """
            SELECT p.nombre, SUM(dp.cantidad) as total
            FROM pedidos_detallepedido dp
            JOIN pedidos_producto p ON dp.producto_id = p.id
            JOIN pedidos_pedido pe ON dp.pedido_id = pe.id
            WHERE DATE(pe.fecha_pedido) = ? AND pe.estado = 'COMPLETADO'
            GROUP BY p.nombre
            ORDER BY total DESC
            LIMIT 1
        """

        # Clientes activos
        query_customers = """
            SELECT COUNT(DISTINCT cliente_id) as total_customers
            FROM pedidos_pedido
            WHERE fecha_pedido >= ? AND estado = 'COMPLETADO'
        """

        try:
            today_data = self.db.execute_query(query_today, (today,), fetch_one=True)
            yesterday_data = self.db.execute_query(query_yesterday, (yesterday,), fetch_one=True)
            top_product_data = self.db.execute_query(query_top_product, (today,), fetch_one=True)
            customers_data = self.db.execute_query(query_customers, (today - timedelta(days=30),), fetch_one=True)

            today_revenue = float(today_data[0]['total_revenue'] or 0) if today_data else 0
            yesterday_revenue = float(yesterday_data[0]['total_revenue'] or 0) if yesterday_data else 0

            growth = 0.0
            if yesterday_revenue > 0:
                growth = round(((today_revenue - yesterday_revenue) / yesterday_revenue) * 100, 2)

            metrics = SummaryMetrics(
                total_revenue_today=today_revenue,
                total_orders_today=int(today_data[0]['total_orders'] or 0) if today_data else 0,
                average_ticket_today=float(today_data[0]['average_ticket'] or 0) if today_data else 0,
                total_customers=int(customers_data[0]['total_customers'] or 0) if customers_data else 0,
                top_product_today=top_product_data[0]['nombre'] if top_product_data else None,
                revenue_growth_vs_yesterday=growth
            )

            return {
                'report_type': 'resumen',
                'data': metrics.model_dump(),
                'cached': False
            }

        except Exception as e:
            logger.error(f"Error generando dashboard: {e}")
            raise

    def generate_report(self, request: ReportRequest) -> Dict[str, Any]:
        """
        Genera un reporte según el tipo solicitado.

        Args:
            request: Request del reporte

        Returns:
            Dict con datos del reporte

        Raises:
            ValueError: Si el tipo de reporte no es válido
        """
        report_type = request.report_type

        if report_type == ReportType.SALES:
            return self.get_sales_report(request)

        elif report_type == ReportType.PRODUCTS:
            return self.get_products_report(request)

        elif report_type == ReportType.CUSTOMERS:
            return self.get_customers_report(request)

        elif report_type == ReportType.REVENUE_BY_CATEGORY:
            return self.get_revenue_by_category(request)

        elif report_type == ReportType.SUMMARY:
            return self.get_summary_dashboard()

        else:
            raise ValueError(f"Tipo de reporte no soportado: {report_type}")
