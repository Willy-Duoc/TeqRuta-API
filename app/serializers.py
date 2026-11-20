"""Serialización de modelos a JSON (camelCase, compatible con Kotlin)."""

from __future__ import annotations

from datetime import datetime

from .models import Destination, Notification, Tariff, Trip, User, Vehicle


def _dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat() + "Z"


def _money(value: float | None) -> float:
    return round(float(value or 0.0), 2)


def user_to_json(user: User) -> dict:
    return {
        "email": user.email,
        "nombre": user.nombre,
        "rol": user.rol,
        "cargo": user.cargo,
        "vehiculoAsignado": user.vehiculo_asignado,
        "activo": bool(user.activo),
    }


def vehicle_to_json(vehicle: Vehicle) -> dict:
    return {
        "id": vehicle.id,
        "patente": vehicle.patente,
        "modelo": vehicle.modelo,
        "rendimiento": vehicle.rendimiento_km_l,
        "rendimientoKmL": vehicle.rendimiento_km_l,
        "kilometrajeActual": vehicle.kilometraje_actual,
        "tecnicoEmail": vehicle.tecnico_email,
        "activo": bool(vehicle.activo),
        "createdAt": _dt(vehicle.created_at),
        "updatedAt": _dt(vehicle.updated_at),
    }


def destination_to_json(destination: Destination) -> dict:
    return {
        "id": destination.id,
        "nombre": destination.nombre,
        "region": destination.region,
        "comuna": destination.comuna,
        "distanciaOficialKm": destination.distancia_oficial_km,
        "latitud": destination.latitud,
        "longitud": destination.longitud,
        "activo": bool(destination.activo),
        "createdAt": _dt(destination.created_at),
        "updatedAt": _dt(destination.updated_at),
    }


def tariff_to_json(tariff: Tariff) -> dict:
    return {
        "id": tariff.id,
        "combustible": tariff.combustible,
        "precioLitro": _money(tariff.precio_litro),
        "moneda": tariff.moneda,
        "origen": tariff.origen,
        "fuente": tariff.fuente,
        "vigenteDesde": _dt(tariff.vigente_desde),
        "activa": bool(tariff.activa),
        "detalle": tariff.detalle,
    }


def trip_to_json(trip: Trip) -> dict:
    """Devuelve exactamente los campos de `Viaje.kt` más métricas calculadas."""

    return {
        # --- Campos del data class de la app ---
        "uuid": trip.uuid,
        "rutaSeleccionada": trip.ruta_seleccionada,
        "odometroInicio": trip.odometro_inicio,
        "fotoOdometroInicio": trip.foto_odometro_inicio,
        "odometroFin": trip.odometro_fin,
        "fotoOdometroFin": trip.foto_odometro_fin,
        "totalMontoPeajes": _money(trip.total_monto_peajes),
        "fotosPeajes": trip.fotos_peajes or "",
        "horaInicio": trip.hora_inicio,
        "horaFin": trip.hora_fin,
        "eventosExtra": trip.eventos_extra or "",
        "latitudInicio": trip.latitud_inicio,
        "longitudInicio": trip.longitud_inicio,
        "latitudFin": trip.latitud_fin,
        "longitudFin": trip.longitud_fin,
        "tecnicoEmail": trip.tecnico_email,
        "vehiculoPatente": trip.vehiculo_patente,
        "sincronizado": bool(trip.sincronizado),
        "estadoAprobacion": trip.estado_aprobacion,
        "observacionJefe": trip.observacion_jefe or "",
        "costoCombustibleEstimado": _money(trip.costo_combustible_estimado),
        # --- Métricas centralizadas (auditoría) ---
        "costoTotalCalculado": _money(trip.costo_total_calculado),
        "distanciaDeclaradaKm": _money(trip.distancia_declarada_km),
        "distanciaOficialKm": _money(trip.distancia_oficial_km)
        if trip.distancia_oficial_km is not None
        else None,
        "desviacionPorcentaje": round(float(trip.desviacion_porcentaje), 2)
        if trip.desviacion_porcentaje is not None
        else None,
        "alertaDesviacion": bool(trip.alerta_desviacion),
        "rendimientoUsadoKmL": _money(trip.rendimiento_usado_km_l),
        "tarifaUsadaClpL": _money(trip.tarifa_usada_clp_l),
        "fuenteTarifa": trip.fuente_tarifa,
        "createdAt": _dt(trip.created_at),
        "updatedAt": _dt(trip.updated_at),
    }


def notification_to_json(notification: Notification) -> dict:
    return {
        "id": notification.id,
        "viajeUuid": notification.viaje_uuid,
        "destinatario": notification.destinatario,
        "tipo": notification.tipo,
        "mensaje": notification.mensaje,
        "leida": bool(notification.leida),
        "createdAt": _dt(notification.created_at),
    }
