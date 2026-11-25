"""RF7, RF9, RF10: desviaciones, dashboard de costos y exportación CSV."""

from __future__ import annotations

from flask import Blueprint, current_app, request

from ..models import Trip
from ..security import roles_required, token_required
from ..serializers import trip_to_json
from ..services.reportes import (
    csv_aprobados,
    parse_filtros,
    query_aprobados,
    resumen_reporte,
)
from ..utils import api_ok

bp = Blueprint("reportes", __name__)

ROLES_REPORTE = ("gerencia", "admin", "jefe")


@bp.get("/mensual")
@token_required
@roles_required(*ROLES_REPORTE)
def resumen_mensual():
    """RF9: gasto mensual, promedio por visita y desgloses por cliente/técnico/vehículo."""

    viajes = query_aprobados(parse_filtros(request.args)).all()
    return api_ok(resumen_reporte(viajes))


@bp.get("/mensual.csv")
@token_required
@roles_required(*ROLES_REPORTE)
def exportar_csv():
    """RF10: detalle granular en CSV con BOM para Excel."""

    viajes = query_aprobados(parse_filtros(request.args)).all()
    response = current_app.response_class(
        csv_aprobados(viajes), mimetype="text/csv; charset=utf-8"
    )
    response.headers["Content-Disposition"] = (
        'attachment; filename="teqruta_reporte_mensual.csv"'
    )
    return response


@bp.get("/desviaciones")
@token_required
@roles_required(*ROLES_REPORTE)
def desviaciones():
    """RF7: viajes cuya distancia declarada supera el umbral de la oficial."""

    viajes = Trip.query.filter(Trip.alerta_desviacion.is_(True))
    cliente = (request.args.get("cliente") or "").strip()
    if cliente:
        viajes = viajes.filter(Trip.ruta_seleccionada.ilike(f"%{cliente}%"))
    viajes = viajes.order_by(Trip.hora_inicio.desc()).all()
    return api_ok(
        {
            "umbralPct": current_app.config["DESVIACION_UMBRAL_PCT"],
            "total": len(viajes),
            "viajes": [trip_to_json(trip) for trip in viajes],
        }
    )
