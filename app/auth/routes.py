"""RF1: autenticación segura con JWT y control de roles."""

from __future__ import annotations

from flask import Blueprint, current_app, g

from ..extensions import db
from ..models import User
from ..security import create_access_token, hash_password, token_required, verify_password
from ..serializers import user_to_json
from ..utils import ApiError, api_ok, first_value, get_request_json

bp = Blueprint("auth", __name__)


@bp.post("/login")
def login():
    data = get_request_json()
    email = str(first_value(data, "email", "usuario", "correo") or "").strip().lower()
    password = str(first_value(data, "password", "contraseña", "contrasena") or "")

    if not email or not password:
        raise ApiError("Email y contraseña son obligatorios", 400, "validation_error")

    user = User.query.filter_by(email=email, activo=True).first()
    if user is None or not verify_password(password, user.password_hash):
        raise ApiError("Credenciales inválidas", 401, "invalid_credentials")

    token, expires_in = create_access_token(user)
    return api_ok(
        {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": expires_in,
            "user": user_to_json(user),
        },
        "Inicio de sesión correcto",
    )


@bp.get("/me")
@token_required
def me():
    user = db.session.get(User, g.current_user["id"])
    if user is None:
        raise ApiError("Usuario no encontrado", 404, "not_found")
    return api_ok(user_to_json(user))


@bp.post("/logout")
@token_required
def logout():
    # JWT es stateless: la app debe descartar el token en el cliente.
    return api_ok({"logged_out": True}, "Sesión cerrada. Elimina el token almacenado.")


@bp.post("/register")
def register():
    """Registro público de técnicos (útil para pruebas; en producción usar admin)."""

    data = get_request_json()
    email = str(data.get("email") or "").strip().lower()
    password = str(data.get("password") or "")
    nombre = str(data.get("nombre") or "").strip()

    if not email or not password or not nombre:
        raise ApiError("email, password y nombre son obligatorios", 400, "validation_error")
    from ..utils import validate_email

    if not validate_email(email):
        raise ApiError("Email no válido", 400, "validation_error")
    if len(password) < 4:
        raise ApiError("La contraseña debe tener al menos 4 caracteres", 400, "validation_error")
    if User.query.filter_by(email=email).first():
        raise ApiError("El email ya está registrado", 409, "conflict")

    user = User(
        email=email,
        password_hash=hash_password(password),
        nombre=nombre,
        rol="tecnico",
        cargo=data.get("cargo") or "Técnico de Servicio",
        vehiculo_asignado=data.get("vehiculoAsignado"),
        activo=True,
    )
    db.session.add(user)
    db.session.commit()
    return api_ok(user_to_json(user), "Usuario creado", 201)


@bp.get("/config")
def public_config():
    """Configuración pública necesaria para el cálculo en el cliente (sin secretos)."""

    return api_ok(
        {
            "desviacionUmbralPct": current_app.config["DESVIACION_UMBRAL_PCT"],
            "combustibleReferencia": current_app.config["COSTO_COMBUSTIBLE_TIPO"],
            "moneda": "CLP",
        }
    )
