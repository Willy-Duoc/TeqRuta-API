"""Autenticación JWT, hash de contraseñas y control de acceso por roles (RBAC)."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps

import bcrypt
import jwt
from flask import current_app, g, request

from .models import User
from .utils import ApiError


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(user: User) -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    expires = now + current_app.config["JWT_ACCESS_TOKEN_EXPIRES"]
    payload = {
        "sub": user.email,
        "role": user.rol,
        "nombre": user.nombre,
        "iat": now,
        "exp": expires,
    }
    token = jwt.encode(payload, current_app.config["JWT_SECRET_KEY"], algorithm="HS256")
    return token, int((expires - now).total_seconds())


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            current_app.config["JWT_SECRET_KEY"],
            algorithms=["HS256"],
            options={"require": ["exp", "sub", "role"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise ApiError("El token ha expirado", 401, "token_expired") from exc
    except jwt.InvalidTokenError as exc:
        raise ApiError("Token inválido", 401, "invalid_token") from exc


def token_required(fn):
    """Valida el header `Authorization: Bearer <JWT>` y expone `g.current_user`."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header:
            raise ApiError("Se requiere un token de acceso", 401, "missing_token")
        parts = header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise ApiError(
                "El header Authorization debe tener el formato 'Bearer <token>'",
                401,
                "invalid_auth_header",
            )
        payload = _decode_token(parts[1])

        user = User.query.filter_by(email=payload["sub"], activo=True).first()
        if user is None:
            raise ApiError("El usuario del token no existe o está inactivo", 401, "invalid_token")

        g.current_user = {
            "sub": user.email,
            "role": user.rol,
            "nombre": user.nombre,
            "id": user.id,
        }
        return fn(*args, **kwargs)

    return wrapper


def roles_required(*roles: str):
    """Restringe el endpoint a los roles indicados. Debe ir bajo @token_required."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if g.current_user.get("role") not in roles:
                raise ApiError(
                    "No tienes permisos para realizar esta operación", 403, "forbidden"
                )
            return fn(*args, **kwargs)

        return wrapper

    return decorator
