"""
Modelos de datos y schemas para el servicio de reportes.
Usa Pydantic para validación de datos.
"""
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Literal
from enum import Enum
from pydantic import BaseModel, Field, field_validator


# ===== Enums =====

class ReportPeriod(str, Enum):
    """Periodos disponibles para reportes."""
    DAY = 'dia'
    WEEK = 'semana'
    MONTH = 'mes'
    QUARTER = 'trimestre'
    YEAR = 'año'
    CUSTOM = 'personalizado'


class ReportFormat(str, Enum):
    """Formatos de exportación de reportes."""
    JSON = 'json'
    PDF = 'pdf'
    EXCEL = 'excel'
    CSV = 'csv'


class ReportType(str, Enum):
    """Tipos de reportes disponibles."""
    SALES = 'ventas'
    PRODUCTS = 'productos'
    CUSTOMERS = 'clientes'
    REVENUE_BY_CATEGORY = 'revenue_categoria'
    HOURLY_SALES = 'ventas_horarias'
    SUMMARY = 'resumen'


class OrderStatus(str, Enum):
    """Estados de pedidos."""
    PENDING = 'PENDIENTE'
    CONFIRMED = 'CONFIRMADO'
    IN_PROGRESS = 'EN_PROCESO'
    COMPLETED = 'COMPLETADO'
    CANCELLED = 'CANCELADO'


# ===== Request Models =====

class DateRangeFilter(BaseModel):
    """Filtro por rango de fechas personalizado."""
    start_date: date = Field(..., description="Fecha inicio (YYYY-MM-DD)")
    end_date: date = Field(..., description="Fecha fin (YYYY-MM-DD)")

    @field_validator('end_date')
    @classmethod
    def validate_date_range(cls, v, info):
        """Valida que end_date sea mayor o igual a start_date."""
        if 'start_date' in info.data and v < info.data['start_date']:
            raise ValueError("end_date debe ser mayor o igual a start_date")
        return v


class ReportFilters(BaseModel):
    """Filtros opcionales para reportes."""
    customer_id: Optional[int] = Field(default=None, description="ID del cliente")
    product_id: Optional[int] = Field(default=None, description="ID del producto")
    category_id: Optional[int] = Field(default=None, description="ID de categoría")
    status: Optional[OrderStatus] = Field(default=None, description="Estado del pedido")
    min_amount: Optional[float] = Field(default=None, ge=0, description="Monto mínimo")
    max_amount: Optional[float] = Field(default=None, ge=0, description="Monto máximo")

    @field_validator('max_amount')
    @classmethod
    def validate_amount_range(cls, v, info):
        """Valida que max_amount sea mayor a min_amount."""
        if v is not None and 'min_amount' in info.data:
            min_amt = info.data['min_amount']
            if min_amt is not None and v < min_amt:
                raise ValueError("max_amount debe ser mayor a min_amount")
        return v


class PaginationParams(BaseModel):
    """Parámetros de paginación."""
    page: int = Field(default=1, ge=1, description="Número de página")
    page_size: int = Field(default=50, ge=1, le=500, description="Items por página")
    sort_by: Optional[str] = Field(default=None, description="Campo para ordenar")
    order: Literal['asc', 'desc'] = Field(default='desc', description="Orden ascendente o descendente")


class ReportRequest(BaseModel):
    """Request para generar un reporte."""
    report_type: ReportType = Field(..., description="Tipo de reporte")
    period: ReportPeriod = Field(default=ReportPeriod.WEEK, description="Periodo del reporte")
    date_range: Optional[DateRangeFilter] = Field(default=None, description="Rango de fechas personalizado")
    filters: Optional[ReportFilters] = Field(default=None, description="Filtros adicionales")
    pagination: Optional[PaginationParams] = Field(default=None, description="Parámetros de paginación")
    format: ReportFormat = Field(default=ReportFormat.JSON, description="Formato de salida")
    include_charts: bool = Field(default=True, description="Incluir gráficos en PDF/Excel")

    @field_validator('date_range')
    @classmethod
    def validate_custom_period(cls, v, info):
        """Valida que date_range esté presente si period es CUSTOM."""
        if 'period' in info.data and info.data['period'] == ReportPeriod.CUSTOM:
            if v is None:
                raise ValueError("date_range es requerido para periodo 'personalizado'")
        return v


# ===== Response Models - Sales Report =====

class SalesReportItem(BaseModel):
    """Item de reporte de ventas por periodo."""
    periodo: str = Field(..., description="Fecha del periodo (YYYY-MM-DD)")
    total_ventas: float = Field(..., description="Total de ventas en el periodo")
    numero_pedidos: int = Field(default=0, description="Número de pedidos")
    ticket_promedio: float = Field(default=0.0, description="Ticket promedio")

    class Config:
        json_schema_extra = {
            "example": {
                "periodo": "2024-12-04",
                "total_ventas": 1250.50,
                "numero_pedidos": 25,
                "ticket_promedio": 50.02
            }
        }


class SalesReport(BaseModel):
    """Reporte completo de ventas."""
    data: List[SalesReportItem] = Field(..., description="Datos de ventas")
    total_revenue: float = Field(..., description="Revenue total del periodo")
    total_orders: int = Field(..., description="Total de pedidos")
    average_ticket: float = Field(..., description="Ticket promedio")


# ===== Response Models - Products Report =====

class ProductReportItem(BaseModel):
    """Item de reporte de productos."""
    producto_id: int = Field(..., description="ID del producto")
    nombre: str = Field(..., description="Nombre del producto")
    categoria: Optional[str] = Field(default=None, description="Categoría")
    total_vendido: int = Field(..., description="Unidades vendidas")
    revenue: float = Field(..., description="Revenue generado")
    porcentaje_ventas: float = Field(default=0.0, description="% del total de ventas")

    class Config:
        json_schema_extra = {
            "example": {
                "producto_id": 1,
                "nombre": "Coca Cola 1.5L",
                "categoria": "Bebidas",
                "total_vendido": 150,
                "revenue": 450.00,
                "porcentaje_ventas": 15.5
            }
        }


class ProductsReport(BaseModel):
    """Reporte completo de productos."""
    data: List[ProductReportItem] = Field(..., description="Datos de productos")
    total_products: int = Field(..., description="Total de productos únicos vendidos")
    total_units_sold: int = Field(..., description="Total de unidades vendidas")


# ===== Response Models - Customers Report =====

class CustomerReportItem(BaseModel):
    """Item de reporte de clientes."""
    cliente_id: int = Field(..., description="ID del cliente")
    username: str = Field(..., description="Username")
    nombre_completo: Optional[str] = Field(default=None, description="Nombre completo")
    cantidad_pedidos: int = Field(..., description="Cantidad de pedidos")
    total_gastado: float = Field(..., description="Total gastado")
    ticket_promedio: float = Field(..., description="Ticket promedio")
    ultimo_pedido: Optional[str] = Field(default=None, description="Fecha último pedido")

    class Config:
        json_schema_extra = {
            "example": {
                "cliente_id": 1,
                "username": "juan_perez",
                "nombre_completo": "Juan Pérez",
                "cantidad_pedidos": 12,
                "total_gastado": 600.50,
                "ticket_promedio": 50.04,
                "ultimo_pedido": "2024-12-04"
            }
        }


class CustomersReport(BaseModel):
    """Reporte completo de clientes."""
    data: List[CustomerReportItem] = Field(..., description="Datos de clientes")
    total_customers: int = Field(..., description="Total de clientes únicos")


# ===== Response Models - Revenue by Category =====

class RevenueByCategoryItem(BaseModel):
    """Item de revenue por categoría."""
    categoria: str = Field(..., description="Nombre de la categoría")
    revenue: float = Field(..., description="Revenue total")
    porcentaje: float = Field(..., description="Porcentaje del total")
    unidades_vendidas: int = Field(..., description="Unidades vendidas")


class RevenueByCategoryReport(BaseModel):
    """Reporte de revenue por categoría."""
    data: List[RevenueByCategoryItem] = Field(..., description="Datos por categoría")
    total_revenue: float = Field(..., description="Revenue total")


# ===== Response Models - Hourly Sales =====

class HourlySalesItem(BaseModel):
    """Item de ventas por hora."""
    hora: int = Field(..., ge=0, le=23, description="Hora del día (0-23)")
    total_ventas: float = Field(..., description="Total de ventas")
    numero_pedidos: int = Field(..., description="Número de pedidos")


class HourlySalesReport(BaseModel):
    """Reporte de ventas por hora del día."""
    data: List[HourlySalesItem] = Field(..., description="Datos por hora")
    peak_hour: int = Field(..., description="Hora pico")
    peak_revenue: float = Field(..., description="Revenue en hora pico")


# ===== Response Models - Summary Dashboard =====

class SummaryMetrics(BaseModel):
    """Métricas resumidas del dashboard."""
    total_revenue_today: float = Field(..., description="Revenue de hoy")
    total_orders_today: int = Field(..., description="Pedidos de hoy")
    average_ticket_today: float = Field(..., description="Ticket promedio de hoy")
    total_customers: int = Field(..., description="Total clientes activos")
    top_product_today: Optional[str] = Field(default=None, description="Producto más vendido hoy")
    revenue_growth_vs_yesterday: float = Field(..., description="% crecimiento vs ayer")


# ===== Generic Response Models =====

class PaginationMetadata(BaseModel):
    """Metadata de paginación."""
    page: int = Field(..., description="Página actual")
    page_size: int = Field(..., description="Items por página")
    total_items: int = Field(..., description="Total de items")
    total_pages: int = Field(..., description="Total de páginas")
    has_next: bool = Field(..., description="Tiene siguiente página")
    has_previous: bool = Field(..., description="Tiene página anterior")


class ReportResponse(BaseModel):
    """Response genérica para reportes."""
    success: bool = Field(default=True, description="Indica si la operación fue exitosa")
    report_type: ReportType = Field(..., description="Tipo de reporte")
    period: ReportPeriod = Field(..., description="Periodo del reporte")
    generated_at: datetime = Field(default_factory=datetime.now, description="Timestamp de generación")
    data: Dict[str, Any] = Field(..., description="Datos del reporte")
    pagination: Optional[PaginationMetadata] = Field(default=None, description="Metadata de paginación")
    cached: bool = Field(default=False, description="Si el resultado vino del caché")
    execution_time_ms: Optional[float] = Field(default=None, description="Tiempo de ejecución en ms")


class ErrorResponse(BaseModel):
    """Response para errores."""
    success: bool = Field(default=False)
    error: str = Field(..., description="Mensaje de error")
    error_code: Optional[str] = Field(default=None, description="Código de error")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Detalles adicionales")


# ===== Health Check =====

class DatabaseHealth(BaseModel):
    """Estado de la base de datos."""
    connected: bool = Field(..., description="Si está conectada")
    type: str = Field(..., description="Tipo de base de datos")
    latency_ms: Optional[float] = Field(default=None, description="Latencia en ms")


class CacheHealth(BaseModel):
    """Estado del caché."""
    connected: bool = Field(..., description="Si está conectado")
    hit_rate: Optional[float] = Field(default=None, description="Tasa de aciertos")


class HealthCheckResponse(BaseModel):
    """Response del health check."""
    status: Literal['healthy', 'degraded', 'unhealthy'] = Field(..., description="Estado del servicio")
    version: str = Field(default='2.0.0', description="Versión del servicio")
    database: DatabaseHealth = Field(..., description="Estado de la base de datos")
    cache: Optional[CacheHealth] = Field(default=None, description="Estado del caché")
    uptime_seconds: int = Field(..., description="Tiempo activo en segundos")
