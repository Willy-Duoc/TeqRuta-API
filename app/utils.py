"""Utilidades comunes: respuestas JSON, errores de API y validaciones."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Iterable

from flask import jsonify, request

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

_DEFAULT_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    422: "unprocessable_entity",
    500: "internal_error",
}


class ApiError(Exception):
    """Error de dominio que se traduce a una respuesta JSON uniforme."""

    def __init__(
        self,
        message: str,
        status_code: int = 400,
        code: str | None = None,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code or _DEFAULT_CODES.get(status_code, "error")
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "error": {"code": self.code, "message": self.message}
        }
        if self.details is not None:
            payload["error"]["details"] = self.details
        return payload


def api_ok(
    data: Any = None,
    message: str | None = None,
    status: int = 200,
    meta: dict[str, Any] | None = None,
):
    """Construye una respuesta exitosa con el shape `{data, message, meta}`."""

    body: dict[str, Any] = {"data": data}
    if message:
        body["message"] = message
    if meta:
        body["meta"] = meta
    return jsonify(body), status


def get_request_json() -> dict[str, Any]:
    """Devuelve el cuerpo JSON de la petición o lanza un ApiError."""

    data = request.get_json(silent=True)
    if data is None:
        raise ApiError("Se requiere un cuerpo JSON válido", 400, "invalid_json")
    if not isinstance(data, dict):
        raise ApiError("El cuerpo JSON debe ser un objeto", 400, "invalid_json")
    return data


def first_value(data: dict[str, Any], *keys: str) -> Any:
    """Obtiene el primer valor presente entre varias claves (camelCase/snake_case)."""

    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def now_utc() -> datetime:
    """datetime naive en UTC, compatible con SQLAlchemy DateTime."""

    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_epoch_ms(value: datetime | None) -> int | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 1000)


def parse_epoch_ms(value: Any, field: str = "fecha") -> int:
    """Acepta epoch milisegundos (int/str) o ISO-8601 y devuelve epoch ms."""

    if value is None or isinstance(value, bool):
        raise ApiError(f"{field} debe ser una fecha válida", 400, "validation_error")

    if isinstance(value, (int, float)):
        milliseconds = int(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ApiError(f"{field} no puede estar vacío", 400, "validation_error")
        if text.lstrip("-").isdigit():
            milliseconds = int(text)
        else:
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ApiError(
                    f"{field} no tiene un formato de fecha válido",
                    400,
                    "validation_error",
                ) from exc
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            milliseconds = int(parsed.timestamp() * 1000)
    else:
        raise ApiError(f"{field} debe ser una fecha válida", 400, "validation_error")

    # Rango razonable: entre 2000 y un día por delante.
    min_ms = 946684800000
    max_ms = int(datetime.now(timezone.utc).timestamp() * 1000) + 86_400_000
    if not min_ms <= milliseconds <= max_ms:
        raise ApiError(f"{field} está fuera de rango", 400, "validation_error")
    return milliseconds


def validate_email(value: str) -> bool:
    return bool(value and EMAIL_RE.match(value))


def get_pagination(max_per_page: int = 100) -> tuple[int, int]:
    try:
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 20))
    except (TypeError, ValueError) as exc:
        raise ApiError("page y per_page deben ser enteros", 400, "validation_error") from exc
    return max(1, page), max(1, min(per_page, max_per_page))


def require_fields(data: dict[str, Any], *fields: str) -> None:
    missing = [field for field in fields if data.get(field) in (None, "")]
    if missing:
        raise ApiError(
            "Faltan campos obligatorios: " + ", ".join(missing),
            400,
            "validation_error",
            {"missing": missing},
        )


def as_float(value: Any, field: str, errors: list[str], *, required: bool = True) -> float | None:
    if value is None or isinstance(value, bool):
        if required:
            errors.append(f"{field} es obligatorio")
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        errors.append(f"{field} debe ser numérico")
        return None


def as_int(value: Any, field: str, errors: list[str], *, required: bool = True) -> int | None:
    if value is None or isinstance(value, bool):
        if required:
            errors.append(f"{field} es obligatorio")
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        errors.append(f"{field} debe ser un entero")
        return None


def unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
