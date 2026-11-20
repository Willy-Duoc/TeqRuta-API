"""RF3-RF8: registro, sincronización idempotente y validación de viajes."""

from __future__ import annotations

import uuid as uuid_lib
from datetime import datetime, timezone

from flask import Blueprint, g, request

from ..extensions import db
from ..models import ESTADOS_APROBACION, Notification, Trip
from ..security import roles_required, token_required
from ..serializers import trip_to_json
from ..services.cost_calculator import calcular_costo
from ..utils import (
    ApiError,
    api_ok,
    as_float,
    as_int,
    first_value,
    get_pagination,
    get_request_json,
    parse_epoch_ms,
    validate_email,
)

bp = Blueprint("viajes", __name__)


def normalize_trip(data: dict) -> tuple[dict | None, list[str]]:
    """Valida un viaje del cliente y lo convierte al modelo del servidor."""

    if not isinstance(data, dict):
        return None, ["Cada viaje debe ser un objeto JSON"]

    errors: list[str] = []

    uuid_value = str(first_value(data, "uuid", "id") or "").strip()
    if not uuid_value:
        errors.append("uuid es obligatorio")
    else:
        try:
            uuid_lib.UUID(uuid_value)
        except (ValueError, AttributeError):
            errors.append("uuid no tiene un formato UUID válido")

    ruta = str(first_value(data, "rutaSeleccionada", "ruta_seleccionada") or "").strip()
    if not ruta:
        errors.append("rutaSeleccionada es obligatoria")

    odometro_inicio = as_int(
        first_value(data, "odometroInicio", "odometro_inicio"), "odometroInicio", errors
    )
    odometro_fin = as_int(
        first_value(data, "odometroFin", "odometro_fin"), "odometroFin", errors
    )
    if odometro_inicio is not None and not 0 < odometro_inicio <= 999_999:
        errors.append("odometroInicio debe estar entre 1 y 999999")
    if odometro_fin is not None and not 0 < odometro_fin <= 999_999:
        errors.append("odometroFin debe estar entre 1 y 999999")
    if odometro_inicio is not None and odometro_fin is not None:
        if odometro_fin <= odometro_inicio:
            errors.append("odometroFin debe ser mayor que odometroInicio")
        elif odometro_fin - odometro_inicio > 2000:
            errors.append("La distancia declarada no puede superar 2000 km")

    peajes = as_float(
        first_value(data, "totalMontoPeajes", "total_monto_peajes") or 0,
        "totalMontoPeajes",
        errors,
        required=False,
    )
    if peajes is None:
        peajes = 0.0
    elif peajes < 0 or peajes > 1_000_000:
        errors.append("totalMontoPeajes debe estar entre 0 y 1000000")

    try:
        hora_inicio = parse_epoch_ms(
            first_value(data, "horaInicio", "hora_inicio"), "horaInicio"
        )
    except ApiError as exc:
        hora_inicio = 0
        errors.append(exc.message)
    try:
        hora_fin = parse_epoch_ms(first_value(data, "horaFin", "hora_fin"), "horaFin")
    except ApiError as exc:
        hora_fin = 0
        errors.append(exc.message)
    if hora_inicio and hora_fin and hora_fin < hora_inicio:
        errors.append("horaFin no puede ser menor que horaInicio")

    tecnico_email = str(
        first_value(data, "tecnicoEmail", "tecnico_email") or ""
    ).strip().lower()
    if not validate_email(tecnico_email):
        errors.append("tecnicoEmail no es válido")

    patente = str(first_value(data, "vehiculoPatente", "vehiculo_patente") or "").strip().upper()
    if not patente:
        errors.append("vehiculoPatente es obligatoria")

    estado = str(
        first_value(data, "estadoAprobacion", "estado_aprobacion") or "PENDIENTE"
    ).strip().upper()
    if estado == "RECHAZADO":  # valor usado en RoleScreens.kt
        estado = "OBSERVADO"
    if estado not in ESTADOS_APROBACION:
        errors.append(f"estadoAprobacion debe ser uno de {', '.join(ESTADOS_APROBACION)}")

    lat_inicio = as_float(
        first_value(data, "latitudInicio", "latitud_inicio"), "latitudInicio", errors, required=False
    )
    lon_inicio = as_float(
        first_value(data, "longitudInicio", "longitud_inicio"), "longitudInicio", errors, required=False
    )
    lat_fin = as_float(
        first_value(data, "latitudFin", "latitud_fin"), "latitudFin", errors, required=False
    )
    lon_fin = as_float(
        first_value(data, "longitudFin", "longitud_fin"), "longitudFin", errors, required=False
    )

    if errors:
        return None, errors

    cleaned = {
        "uuid": uuid_value,
        "rutaSeleccionada": ruta,
        "odometroInicio": odometro_inicio,
        "odometroFin": odometro_fin,
        "fotoOdometroInicio": first_value(data, "fotoOdometroInicio", "foto_odometro_inicio"),
        "fotoOdometroFin": first_value(data, "fotoOdometroFin", "foto_odometro_fin"),
        "totalMontoPeajes": peajes,
        "fotosPeajes": str(first_value(data, "fotosPeajes", "fotos_peajes") or ""),
        "horaInicio": hora_inicio,
        "horaFin": hora_fin,
        "eventosExtra": str(first_value(data, "eventosExtra", "eventos_extra") or ""),
        "latitudInicio": lat_inicio,
        "longitudInicio": lon_inicio,
        "latitudFin": lat_fin,
        "longitudFin": lon_fin,
        "tecnicoEmail": tecnico_email,
        "vehiculoPatente": patente,
        "estadoAprobacion": estado,
        "observacionJefe": str(first_value(data, "observacionJefe", "observacion_jefe") or ""),
    }
    return cleaned, []


def _build_trip(cleaned: dict) -> Trip:
    trip = Trip(
        uuid=cleaned["uuid"],
        ruta_seleccionada=cleaned["rutaSeleccionada"],
        odometro_inicio=cleaned["odometroInicio"],
        odometro_fin=cleaned["odometroFin"],
        foto_odometro_inicio=cleaned["fotoOdometroInicio"],
        foto_odometro_fin=cleaned["fotoOdometroFin"],
        total_monto_peajes=cleaned["totalMontoPeajes"],
        fotos_peajes=cleaned["fotosPeajes"],
        hora_inicio=cleaned["horaInicio"],
        hora_fin=cleaned["horaFin"],
        eventos_extra=cleaned["eventosExtra"],
        latitud_inicio=cleaned["latitudInicio"],
        longitud_inicio=cleaned["longitudInicio"],
        latitud_fin=cleaned["latitudFin"],
        longitud_fin=cleaned["longitudFin"],
        tecnico_email=cleaned["tecnicoEmail"],
        vehiculo_patente=cleaned["vehiculoPatente"],
        # El servidor siempre controla estos campos (RF5/RF6/RF7).
        sincronizado=True,
        estado_aprobacion="PENDIENTE",
        observacion_jefe="",
    )
    for key, value in calcular_costo(cleaned).items():
        setattr(trip, key, value)
    return trip


def _can_access_trip(trip: Trip) -> bool:
    user = g.current_user
    if user["role"] == "tecnico":
        return trip.tecnico_email.lower() == user["sub"].lower()
    return True


def _process_trip(data: dict) -> tuple[Trip | None, str, str | None, list[str]]:
    """Inserta o detecta duplicado. No hace commit; lo hace el llamador."""

    cleaned, errors = normalize_trip(data)
    if errors:
        return None, "rechazado", None, errors

    if g.current_user["role"] == "tecnico" and cleaned["tecnicoEmail"] != g.current_user["sub"].lower():
        return (
            None,
            "rechazado",
            None,
            ["Un técnico solo puede sincronizar viajes asociados a su email"],
        )

    existente = db.session.get(Trip, cleaned["uuid"])
    if existente is not None:
        return existente, "duplicado", None, []

    db.session.add(_build_trip(cleaned))
    return None, "insertado", cleaned["uuid"], []


@bp.post("/sync")
@token_required
def sync():
    """RF6: recibe la cola offline y descarta UUIDs repetidos (idempotencia)."""

    data = get_request_json()
    viajes = data.get("viajes")
    if not isinstance(viajes, list) or not viajes:
        raise ApiError(
            "Se requiere un array 'viajes' con al menos un elemento",
            400,
            "validation_error",
        )
    if len(viajes) > 500:
        raise ApiError("Máximo 500 viajes por lote", 413, "payload_too_large")

    resultados = []
    rechazados = []
    insertados = duplicados = 0

    for indice, item in enumerate(viajes):
        trip, estado, uuid_value, errores = _process_trip(item)
        if estado == "rechazado":
            rechazados.append({"indice": indice, "errores": errores})
            continue
        if estado == "duplicado":
            duplicados += 1
            resultados.append(trip_to_json(trip))
            continue
        insertados += 1
        resultados.append({"uuid": uuid_value, "estado": "insertado"})

    db.session.commit()

    return api_ok(
        {
            "resumen": {
                "recibidos": len(viajes),
                "insertados": insertados,
                "duplicados": duplicados,
                "rechazados": len(rechazados),
            },
            "rechazados": rechazados,
            "viajes": resultados,
        },
        "Sincronización finalizada",
        200 if not rechazados else 207,
    )


@bp.post("")
@token_required
def create_trip():
    """Crea un único viaje (equivalente a /sync con un elemento)."""

    data = get_request_json()
    trip, estado, uuid_value, errores = _process_trip(data)
    if estado == "rechazado":
        raise ApiError("Viaje inválido", 422, "validation_error", errores)
    if estado == "duplicado":
        return api_ok(trip_to_json(trip), "El viaje ya estaba registrado (UUID duplicado)")

    db.session.commit()
    guardado = db.session.get(Trip, uuid_value)
    return api_ok(trip_to_json(guardado), "Viaje creado", 201)


@bp.get("")
@token_required
def list_trips():
    query = Trip.query
    user = g.current_user
    if user["role"] == "tecnico":
        query = query.filter(Trip.tecnico_email == user["sub"].lower())

    estado = request.args.get("estado")
    if estado:
        estado = estado.strip().upper()
        if estado not in ESTADOS_APROBACION:
            raise ApiError("Filtro 'estado' no válido", 400, "validation_error")
        query = query.filter(Trip.estado_aprobacion == estado)

    tecnico = request.args.get("tecnicoEmail")
    if tecnico:
        query = query.filter(Trip.tecnico_email == tecnico.strip().lower())
    patente = request.args.get("vehiculoPatente")
    if patente:
        query = query.filter(Trip.vehiculo_patente == patente.strip().upper())
    cliente = request.args.get("cliente")
    if cliente:
        query = query.filter(Trip.ruta_seleccionada.ilike(f"%{cliente.strip()}%"))
    if request.args.get("soloAlertas") in {"1", "true", "True"}:
        query = query.filter(Trip.alerta_desviacion.is_(True))

    desde = request.args.get("desde")
    hasta = request.args.get("hasta")
    if desde:
        query = query.filter(Trip.hora_inicio >= parse_epoch_ms(desde, "desde"))
    if hasta:
        query = query.filter(Trip.hora_inicio <= parse_epoch_ms(hasta, "hasta"))

    page, per_page = get_pagination()
    pagination = query.order_by(Trip.hora_inicio.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return api_ok(
        [trip_to_json(trip) for trip in pagination.items],
        meta={
            "page": pagination.page,
            "per_page": pagination.per_page,
            "total": pagination.total,
            "pages": pagination.pages,
        },
    )


@bp.get("/<uuid>")
@token_required
def get_trip(uuid: str):
    trip = db.session.get(Trip, uuid)
    if trip is None:
        raise ApiError("Viaje no encontrado", 404, "not_found")
    if not _can_access_trip(trip):
        raise ApiError("No tienes permisos para ver este viaje", 403, "forbidden")
    return api_ok(trip_to_json(trip))


@bp.patch("/<uuid>/aprobacion")
@token_required
@roles_required("jefe", "admin")
def update_approval(uuid: str):
    """RF8: jefatura aprueba u observa un gasto; notificación simulada por correo."""

    trip = db.session.get(Trip, uuid)
    if trip is None:
        raise ApiError("Viaje no encontrado", 404, "not_found")

    data = get_request_json()
    estado = str(data.get("estado") or data.get("estadoAprobacion") or "").strip().upper()
    if estado == "RECHAZADO":
        estado = "OBSERVADO"
    if estado not in {"APROBADO", "OBSERVADO"}:
        raise ApiError(
            "estado debe ser APROBADO u OBSERVADO",
            400,
            "validation_error",
        )
    observacion = str(
        data.get("observacionJefe") or data.get("observacion") or ""
    ).strip()
    if estado == "OBSERVADO" and not observacion:
        raise ApiError("Se requiere observacionJefe al observar un viaje", 400, "validation_error")

    trip.estado_aprobacion = estado
    trip.observacion_jefe = observacion
    trip.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

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
    db.session.commit()
    return api_ok(trip_to_json(trip), "Estado de aprobación actualizado")


@bp.delete("/<uuid>")
@token_required
@roles_required("admin")
def delete_trip(uuid: str):
    trip = db.session.get(Trip, uuid)
    if trip is None:
        raise ApiError("Viaje no encontrado", 404, "not_found")
    db.session.delete(trip)
    db.session.commit()
    return api_ok({"uuid": uuid}, "Viaje eliminado")
