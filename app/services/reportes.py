"""Servicio compartido de reportes (API JSON, CSV y dashboard web).

Centraliza filtros y agregaciones para que el endpoint REST y el panel
administrativo entreguen exactamente los mismos números.
"""

from __future__ import annotations

import calendar
import csv
import io
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

from ..models import Trip
from ..utils import ApiError, parse_epoch_ms


@dataclass(frozen=True)
class ReportFilters:
    start_ms: int | None = None
    end_ms: int | None = None
    cliente: str | None = None
    anio: int | None = None
    mes: int | None = None


def parse_filtros(args: Mapping[str, str]) -> ReportFilters:
    """Interpreta `desde`, `hasta`, `anio`, `mes` y `cliente`."""

    cliente = (args.get("cliente") or "").strip() or None

    start_ms = parse_epoch_ms(args["desde"], "desde") if args.get("desde") else None
    end_ms = parse_epoch_ms(args["hasta"], "hasta") if args.get("hasta") else None

    anio_raw = args.get("anio") or None
    mes_raw = args.get("mes") or None
    anio_i = mes_i = None
    if anio_raw or mes_raw:
        try:
            anio_i = int(anio_raw) if anio_raw else datetime.now(timezone.utc).year
            mes_i = int(mes_raw) if mes_raw else datetime.now(timezone.utc).month
            if not 1 <= mes_i <= 12 or not 2000 <= anio_i <= 2100:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise ApiError("anio/mes no válidos", 400, "validation_error") from exc

        first = datetime(anio_i, mes_i, 1, tzinfo=timezone.utc)
        last_day = calendar.monthrange(anio_i, mes_i)[1]
        last = datetime(anio_i, mes_i, last_day, 23, 59, 59, tzinfo=timezone.utc)
        month_start = int(first.timestamp() * 1000)
        month_end = int(last.timestamp() * 1000)
        start_ms = month_start if start_ms is None else max(start_ms, month_start)
        end_ms = month_end if end_ms is None else min(end_ms, month_end)

    return ReportFilters(
        start_ms=start_ms,
        end_ms=end_ms,
        cliente=cliente,
        anio=anio_i,
        mes=mes_i,
    )


def query_aprobados(filtros: ReportFilters):
    """Consulta de viajes aprobados ordenados cronológicamente."""

    query = Trip.query.filter(Trip.estado_aprobacion == "APROBADO")
    if filtros.start_ms is not None:
        query = query.filter(Trip.hora_inicio >= filtros.start_ms)
    if filtros.end_ms is not None:
        query = query.filter(Trip.hora_inicio <= filtros.end_ms)
    if filtros.cliente:
        query = query.filter(Trip.ruta_seleccionada.ilike(f"%{filtros.cliente}%"))
    return query.order_by(Trip.hora_inicio.asc())


def _agrupar(viajes: list[Trip], campo: str) -> list[dict]:
    grupos: dict[str, dict] = defaultdict(
        lambda: {"viajes": 0, "total": 0.0, "distancia": 0.0}
    )
    for trip in viajes:
        clave = str(getattr(trip, campo) or "No informado")
        grupos[clave]["viajes"] += 1
        grupos[clave]["total"] += float(trip.costo_total_calculado or 0)
        grupos[clave]["distancia"] += float(trip.distancia_declarada_km or 0)
    return [
        {
            "grupo": clave,
            "viajes": datos["viajes"],
            "costoTotal": round(datos["total"], 2),
            "distanciaKm": round(datos["distancia"], 2),
        }
        for clave, datos in sorted(
            grupos.items(), key=lambda item: item[1]["total"], reverse=True
        )
    ]


def resumen_reporte(viajes: list[Trip]) -> dict:
    """Mismo contrato que `GET /api/reportes/mensual`."""

    total = sum(float(trip.costo_total_calculado or 0) for trip in viajes)
    distancia = sum(float(trip.distancia_declarada_km or 0) for trip in viajes)
    peajes = sum(float(trip.total_monto_peajes or 0) for trip in viajes)
    combustible = sum(float(trip.costo_combustible_estimado or 0) for trip in viajes)
    cantidad = len(viajes)

    return {
        "resumen": {
            "viajesAprobados": cantidad,
            "costoTotal": round(total, 2),
            "promedioPorVisita": round(total / cantidad, 2) if cantidad else 0.0,
            "distanciaTotalKm": round(distancia, 2),
            "costoCombustible": round(combustible, 2),
            "totalPeajes": round(peajes, 2),
            "moneda": "CLP",
        },
        "porCliente": _agrupar(viajes, "ruta_seleccionada"),
        "porTecnico": _agrupar(viajes, "tecnico_email"),
        "porVehiculo": _agrupar(viajes, "vehiculo_patente"),
    }


def csv_aprobados(viajes: list[Trip]) -> str:
    """CSV con BOM y separador `;` para compatibilidad con Excel en español."""

    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow(
        [
            "uuid",
            "fecha_inicio",
            "cliente_o_ruta",
            "tecnico_email",
            "vehiculo_patente",
            "odometro_inicio",
            "odometro_fin",
            "distancia_km",
            "distancia_oficial_km",
            "desviacion_pct",
            "combustible_clp",
            "peajes_clp",
            "costo_total_clp",
            "estado",
            "observacion_jefe",
        ]
    )
    for trip in viajes:
        fecha = (
            datetime.fromtimestamp(
                trip.hora_inicio / 1000, tz=timezone.utc
            ).strftime("%Y-%m-%d %H:%M")
            if trip.hora_inicio
            else ""
        )
        writer.writerow(
            [
                trip.uuid,
                fecha,
                trip.ruta_seleccionada,
                trip.tecnico_email,
                trip.vehiculo_patente,
                trip.odometro_inicio,
                trip.odometro_fin,
                trip.distancia_declarada_km,
                trip.distancia_oficial_km
                if trip.distancia_oficial_km is not None
                else "",
                trip.desviacion_porcentaje
                if trip.desviacion_porcentaje is not None
                else "",
                trip.costo_combustible_estimado,
                trip.total_monto_peajes,
                trip.costo_total_calculado,
                trip.estado_aprobacion,
                trip.observacion_jefe or "",
            ]
        )
    return output.getvalue()
