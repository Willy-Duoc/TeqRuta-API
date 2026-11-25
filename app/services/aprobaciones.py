"""Reglas compartidas de aprobación/observación de viajes.

Las usan tanto la API móvil (PATCH JSON) como el dashboard web (formulario).
No hacen commit: el llamador decide la transacción.
"""

from __future__ import annotations

from ..extensions import db
from ..models import Notification, Trip
from ..utils import ApiError, now_utc


def aplicar_aprobacion(trip: Trip, estado: str, observacion: str = "") -> Trip:
    """Valida y aplica `APROBADO`/`OBSERVADO`, creando la notificación."""

    estado = (estado or "").strip().upper()
    if estado == "RECHAZADO":  # compatibilidad con versiones antiguas de la app
        estado = "OBSERVADO"
    if estado not in {"APROBADO", "OBSERVADO"}:
        raise ApiError(
            "estado debe ser APROBADO u OBSERVADO",
            400,
            "validation_error",
        )

    observacion = (observacion or "").strip()
    if estado == "OBSERVADO" and not observacion:
        raise ApiError(
            "Se requiere observacionJefe al observar un viaje",
            400,
            "validation_error",
        )

    trip.estado_aprobacion = estado
    trip.observacion_jefe = observacion
    trip.updated_at = now_utc()

    tipo = "VIAJE_APROBADO" if estado == "APROBADO" else "VIAJE_OBSERVADO"
    mensaje = (
        f"Tu viaje {trip.uuid} hacia {trip.ruta_seleccionada} fue aprobado."
        if estado == "APROBADO"
        else f"Tu viaje {trip.uuid} fue observado: {observacion}"
    )
    db.session.add(
        Notification(
            viaje_uuid=trip.uuid,
            destinatario=trip.tecnico_email,
            tipo=tipo,
            mensaje=mensaje,
        )
    )
    return trip
