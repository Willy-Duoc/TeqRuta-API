"""RF11, RF12: ABM de vehículos, destinos, usuarios y tarifas."""

from __future__ import annotations

from flask import Blueprint, current_app, g, request

from ..extensions import db
from ..models import ROLES, Destination, User, Vehicle
from ..security import hash_password, roles_required, token_required
from ..serializers import (
    destination_to_json,
    tariff_to_json,
    user_to_json,
    vehicle_to_json,
)
from ..services.fuel_price import (
    get_active_tariff,
    list_tarifas,
    refresh_tariff,
    set_manual_tariff,
)
from ..utils import ApiError, api_ok, get_request_json, validate_email

bp = Blueprint("mantenedores", __name__)

# ---------------------------------------------------------------------------
# Vehículos
# ---------------------------------------------------------------------------


@bp.get("/vehiculos")
@token_required
def list_vehicles():
    items = Vehicle.query.order_by(Vehicle.patente.asc()).all()
    return api_ok([vehicle_to_json(item) for item in items])


@bp.get("/vehiculos/<patente>")
@token_required
def get_vehicle(patente: str):
    item = Vehicle.query.filter_by(patente=patente.strip().upper()).first()
    if item is None:
        raise ApiError("Vehículo no encontrado", 404, "not_found")
    return api_ok(vehicle_to_json(item))


@bp.post("/vehiculos")
@token_required
@roles_required("admin")
def create_vehicle():
    data = get_request_json()
    patente = str(data.get("patente") or "").strip().upper()
    modelo = str(data.get("modelo") or "").strip()
    rendimiento = data.get("rendimiento") or data.get("rendimientoKmL")
    if not patente or not modelo:
        raise ApiError("patente y modelo son obligatorios", 400, "validation_error")
    try:
        rendimiento = float(rendimiento)
    except (TypeError, ValueError) as exc:
        raise ApiError("rendimiento debe ser numérico", 400, "validation_error") from exc
    if rendimiento <= 0:
        raise ApiError("rendimiento debe ser mayor que 0", 400, "validation_error")
    if Vehicle.query.filter_by(patente=patente).first():
        raise ApiError("La patente ya existe", 409, "conflict")

    item = Vehicle(
        patente=patente,
        modelo=modelo,
        rendimiento_km_l=rendimiento,
        kilometraje_actual=int(data.get("kilometrajeActual") or 0),
        tecnico_email=(data.get("tecnicoEmail") or None),
        activo=bool(data.get("activo", True)),
    )
    db.session.add(item)
    db.session.commit()
    return api_ok(vehicle_to_json(item), "Vehículo creado", 201)


@bp.put("/vehiculos/<patente>")
@token_required
@roles_required("admin")
def update_vehicle(patente: str):
    item = Vehicle.query.filter_by(patente=patente.strip().upper()).first()
    if item is None:
        raise ApiError("Vehículo no encontrado", 404, "not_found")
    data = get_request_json()
    if "modelo" in data:
        item.modelo = str(data["modelo"]).strip() or item.modelo
    if "rendimiento" in data or "rendimientoKmL" in data:
        valor = data.get("rendimiento") or data.get("rendimientoKmL")
        try:
            valor = float(valor)
        except (TypeError, ValueError) as exc:
            raise ApiError("rendimiento debe ser numérico", 400, "validation_error") from exc
        if valor <= 0:
            raise ApiError("rendimiento debe ser mayor que 0", 400, "validation_error")
        item.rendimiento_km_l = valor
    if "kilometrajeActual" in data:
        item.kilometraje_actual = int(data["kilometrajeActual"])
    if "tecnicoEmail" in data:
        item.tecnico_email = data["tecnicoEmail"] or None
    if "activo" in data:
        item.activo = bool(data["activo"])
    db.session.commit()
    return api_ok(vehicle_to_json(item), "Vehículo actualizado")


@bp.delete("/vehiculos/<patente>")
@token_required
@roles_required("admin")
def delete_vehicle(patente: str):
    item = Vehicle.query.filter_by(patente=patente.strip().upper()).first()
    if item is None:
        raise ApiError("Vehículo no encontrado", 404, "not_found")
    db.session.delete(item)
    db.session.commit()
    return api_ok({"patente": patente.upper()}, "Vehículo eliminado")


# ---------------------------------------------------------------------------
# Destinos / clínicas
# ---------------------------------------------------------------------------


@bp.get("/destinos")
@token_required
def list_destinations():
    """RF2: la app puede cachear este listado para uso sin conexión."""

    items = Destination.query.order_by(Destination.nombre.asc()).all()
    return api_ok([destination_to_json(item) for item in items])


@bp.get("/destinos/<int:item_id>")
@token_required
def get_destination(item_id: int):
    item = db.session.get(Destination, item_id)
    if item is None:
        raise ApiError("Destino no encontrado", 404, "not_found")
    return api_ok(destination_to_json(item))


@bp.post("/destinos")
@token_required
@roles_required("admin")
def create_destination():
    data = get_request_json()
    nombre = str(data.get("nombre") or "").strip()
    distancia = data.get("distanciaOficialKm") or data.get("distancia_oficial_km")
    if not nombre:
        raise ApiError("nombre es obligatorio", 400, "validation_error")
    try:
        distancia = float(distancia)
    except (TypeError, ValueError) as exc:
        raise ApiError("distanciaOficialKm debe ser numérico", 400, "validation_error") from exc
    if distancia <= 0:
        raise ApiError("distanciaOficialKm debe ser mayor que 0", 400, "validation_error")
    if Destination.query.filter_by(nombre=nombre).first():
        raise ApiError("El destino ya existe", 409, "conflict")

    item = Destination(
        nombre=nombre,
        region=data.get("region"),
        comuna=data.get("comuna"),
        distancia_oficial_km=distancia,
        latitud=data.get("latitud"),
        longitud=data.get("longitud"),
        activo=bool(data.get("activo", True)),
    )
    db.session.add(item)
    db.session.commit()
    return api_ok(destination_to_json(item), "Destino creado", 201)


@bp.put("/destinos/<int:item_id>")
@token_required
@roles_required("admin")
def update_destination(item_id: int):
    item = db.session.get(Destination, item_id)
    if item is None:
        raise ApiError("Destino no encontrado", 404, "not_found")
    data = get_request_json()
    if "nombre" in data:
        item.nombre = str(data["nombre"]).strip() or item.nombre
    if "distanciaOficialKm" in data or "distancia_oficial_km" in data:
        valor = data.get("distanciaOficialKm") or data.get("distancia_oficial_km")
        try:
            valor = float(valor)
        except (TypeError, ValueError) as exc:
            raise ApiError("distanciaOficialKm debe ser numérico", 400, "validation_error") from exc
        if valor <= 0:
            raise ApiError("distanciaOficialKm debe ser mayor que 0", 400, "validation_error")
        item.distancia_oficial_km = valor
    for key, attr in (("region", "region"), ("comuna", "comuna"), ("latitud", "latitud"), ("longitud", "longitud")):
        if key in data:
            setattr(item, attr, data[key])
    if "activo" in data:
        item.activo = bool(data["activo"])
    db.session.commit()
    return api_ok(destination_to_json(item), "Destino actualizado")


@bp.delete("/destinos/<int:item_id>")
@token_required
@roles_required("admin")
def delete_destination(item_id: int):
    item = db.session.get(Destination, item_id)
    if item is None:
        raise ApiError("Destino no encontrado", 404, "not_found")
    db.session.delete(item)
    db.session.commit()
    return api_ok({"id": item_id}, "Destino eliminado")


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------


@bp.get("/usuarios")
@token_required
@roles_required("admin")
def list_users():
    items = User.query.order_by(User.email.asc()).all()
    return api_ok([user_to_json(item) for item in items])


@bp.get("/usuarios/<int:item_id>")
@token_required
@roles_required("admin")
def get_user(item_id: int):
    item = db.session.get(User, item_id)
    if item is None:
        raise ApiError("Usuario no encontrado", 404, "not_found")
    return api_ok(user_to_json(item))


@bp.post("/usuarios")
@token_required
@roles_required("admin")
def create_user():
    data = get_request_json()
    email = str(data.get("email") or "").strip().lower()
    password = str(data.get("password") or "")
    rol = str(data.get("rol") or "tecnico").strip().lower()
    if not email or not password or not data.get("nombre"):
        raise ApiError("email, password y nombre son obligatorios", 400, "validation_error")
    if not validate_email(email):
        raise ApiError("Email no válido", 400, "validation_error")
    if rol not in ROLES:
        raise ApiError(f"rol debe ser uno de {', '.join(ROLES)}", 400, "validation_error")
    if User.query.filter_by(email=email).first():
        raise ApiError("El email ya está registrado", 409, "conflict")

    item = User(
        email=email,
        password_hash=hash_password(password),
        nombre=str(data["nombre"]).strip(),
        rol=rol,
        cargo=data.get("cargo"),
        vehiculo_asignado=data.get("vehiculoAsignado"),
        activo=bool(data.get("activo", True)),
    )
    db.session.add(item)
    db.session.commit()
    return api_ok(user_to_json(item), "Usuario creado", 201)


@bp.put("/usuarios/<int:item_id>")
@token_required
@roles_required("admin")
def update_user(item_id: int):
    item = db.session.get(User, item_id)
    if item is None:
        raise ApiError("Usuario no encontrado", 404, "not_found")
    data = get_request_json()
    if "email" in data:
        email = str(data["email"]).strip().lower()
        if not validate_email(email):
            raise ApiError("Email no válido", 400, "validation_error")
        item.email = email
    if "nombre" in data:
        item.nombre = str(data["nombre"]).strip() or item.nombre
    if "rol" in data:
        rol = str(data["rol"]).strip().lower()
        if rol not in ROLES:
            raise ApiError(f"rol debe ser uno de {', '.join(ROLES)}", 400, "validation_error")
        item.rol = rol
    if "password" in data and data["password"]:
        item.password_hash = hash_password(str(data["password"]))
    for key, attr in (("cargo", "cargo"), ("vehiculoAsignado", "vehiculo_asignado")):
        if key in data:
            setattr(item, attr, data[key])
    if "activo" in data:
        if item.id == g.current_user["id"] and not data["activo"]:
            raise ApiError("No puedes desactivar tu propio usuario", 400, "validation_error")
        item.activo = bool(data["activo"])
    db.session.commit()
    return api_ok(user_to_json(item), "Usuario actualizado")


@bp.delete("/usuarios/<int:item_id>")
@token_required
@roles_required("admin")
def delete_user(item_id: int):
    item = db.session.get(User, item_id)
    if item is None:
        raise ApiError("Usuario no encontrado", 404, "not_found")
    if item.id == g.current_user["id"]:
        raise ApiError("No puedes eliminar tu propio usuario", 400, "validation_error")
    db.session.delete(item)
    db.session.commit()
    return api_ok({"id": item_id}, "Usuario eliminado")


# ---------------------------------------------------------------------------
# Tarifas de combustible
# ---------------------------------------------------------------------------


@bp.get("/tarifas/vigente")
@token_required
def get_tarifa_vigente():
    combustible = request_combustible()
    tarifa = get_active_tariff(combustible)
    if tarifa is None:
        raise ApiError("No hay tarifa vigente", 404, "not_found")
    return api_ok(tariff_to_json(tarifa))


@bp.get("/tarifas")
@token_required
def list_tarifas():
    return api_ok([tariff_to_json(item) for item in list_tarifas()])


@bp.post("/tarifas/actualizar")
@token_required
@roles_required("admin")
def actualizar_tarifa():
    """Fuerza la consulta a la API pública de combustibles."""

    combustible = request_combustible()
    tarifa = refresh_tariff(combustible)
    return api_ok(tariff_to_json(tarifa), "Tarifa actualizada desde fuente externa")


@bp.put("/tarifas/<combustible>")
@token_required
@roles_required("admin")
def override_tarifa(combustible: str):
    """RF12: sobreescritura manual ante caída de la API externa."""

    data = get_request_json()
    precio = data.get("precioLitro") or data.get("precio_litro")
    try:
        precio = float(precio)
    except (TypeError, ValueError) as exc:
        raise ApiError("precioLitro debe ser numérico", 400, "validation_error") from exc
    if precio <= 0 or precio > 10_000_000:
        raise ApiError("precioLitro debe estar entre 0 y 10000000", 400, "validation_error")
    tarifa = set_manual_tariff(
        combustible,
        precio,
        fuente=str(data.get("fuente") or "Overwrite manual (administrador)"),
    )
    return api_ok(tariff_to_json(tarifa), "Tarifa actualizada manualmente")


def request_combustible() -> str:
    """Tipo de combustible solicitado o el configurado por defecto."""

    return str(
        request.args.get("combustible")
        or request.args.get("tipo")
        or current_app.config["COSTO_COMBUSTIBLE_TIPO"]
    )
