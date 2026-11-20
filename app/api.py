"""Endpoints públicos de información y health-check."""

from __future__ import annotations

from flask import Blueprint, jsonify
from sqlalchemy import text

from .extensions import db

bp = Blueprint("api", __name__)

ENDPOINTS = {
    "auth": ["/api/auth/login", "/api/auth/me", "/api/auth/logout"],
    "viajes": [
        "/api/viajes",
        "/api/viajes/<uuid>",
        "/api/viajes/sync",
        "/api/viajes/<uuid>/aprobacion",
    ],
    "reportes": [
        "/api/reportes/mensual",
        "/api/reportes/mensual.csv",
        "/api/reportes/desviaciones",
    ],
    "mantenedores": [
        "/api/mantenedores/vehiculos",
        "/api/mantenedores/destinos",
        "/api/mantenedores/usuarios",
        "/api/mantenedores/tarifas",
    ],
}


@bp.get("/")
def index():
    return jsonify(
        {
            "nombre": "TeqRuta API",
            "version": "1.0.0",
            "descripcion": "API REST Flask para la app móvil TeqRuta (TEQMED SpA)",
            "formato": "JSON",
            "autenticacion": "JWT Bearer",
            "endpoints": ENDPOINTS,
        }
    )


@bp.get("/api/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
        database = "ok"
    except Exception:  # pragma: no cover - solo fallos reales de infraestructura
        database = "error"
    return jsonify({"status": "ok" if database == "ok" else "degraded", "database": database}), (
        200 if database == "ok" else 503
    )
