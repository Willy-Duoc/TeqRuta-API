"""Manejo uniforme de errores HTTP en formato JSON."""

from __future__ import annotations

from flask import current_app, jsonify
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.exceptions import HTTPException

from .extensions import db
from .utils import ApiError


def register_error_handlers(app) -> None:
    @app.errorhandler(ApiError)
    def handle_api_error(error: ApiError):
        return jsonify(error.to_dict()), error.status_code

    @app.errorhandler(404)
    def handle_404(error):
        return (
            jsonify(
                {
                    "error": {
                        "code": "not_found",
                        "message": "Recurso no encontrado",
                    }
                }
            ),
            404,
        )

    @app.errorhandler(405)
    def handle_405(error):
        return (
            jsonify(
                {
                    "error": {
                        "code": "method_not_allowed",
                        "message": "Método HTTP no permitido para este recurso",
                    }
                }
            ),
            405,
        )

    @app.errorhandler(IntegrityError)
    def handle_integrity_error(error: IntegrityError):
        db.session.rollback()
        current_app.logger.warning("Conflicto de integridad: %s", error)
        return (
            jsonify(
                {
                    "error": {
                        "code": "conflict",
                        "message": "El registro ya existe o viola una restricción de integridad",
                    }
                }
            ),
            409,
        )

    @app.errorhandler(HTTPException)
    def handle_http_exception(error: HTTPException):
        return (
            jsonify(
                {
                    "error": {
                        "code": "http_error",
                        "message": error.description,
                    }
                }
            ),
            error.code or 500,
        )

    @app.errorhandler(SQLAlchemyError)
    def handle_sqlalchemy_error(error: SQLAlchemyError):
        db.session.rollback()
        current_app.logger.exception("Error de base de datos")
        return (
            jsonify(
                {
                    "error": {
                        "code": "database_error",
                        "message": "No fue posible completar la operación en la base de datos",
                    }
                }
            ),
            500,
        )

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        db.session.rollback()
        current_app.logger.exception("Error no controlado")
        message = (
            str(error)
            if current_app.config.get("TESTING") or current_app.debug
            else "Error interno del servidor"
        )
        return (
            jsonify({"error": {"code": "internal_error", "message": message}}),
            500,
        )
