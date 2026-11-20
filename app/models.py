"""Modelos SQLAlchemy del dominio TeqRuta.

Los nombres de columnas son snake_case en la BD; la capa de serialización
los expone en camelCase para que coincidan con el `data class Viaje` de Kotlin.
"""

from __future__ import annotations

from .extensions import db
from .utils import now_utc

ROLES = ("tecnico", "jefe", "gerencia", "admin")
ESTADOS_APROBACION = ("PENDIENTE", "APROBADO", "OBSERVADO")


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=now_utc, nullable=False)
    updated_at = db.Column(db.DateTime, default=now_utc, onupdate=now_utc, nullable=False)


class User(TimestampMixin, db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    nombre = db.Column(db.String(120), nullable=False)
    rol = db.Column(db.String(20), nullable=False, default="tecnico", index=True)
    cargo = db.Column(db.String(120), nullable=True)
    vehiculo_asignado = db.Column(db.String(20), nullable=True)
    activo = db.Column(db.Boolean, nullable=False, default=True)


class Vehicle(TimestampMixin, db.Model):
    __tablename__ = "vehiculos"

    id = db.Column(db.Integer, primary_key=True)
    patente = db.Column(db.String(20), unique=True, nullable=False, index=True)
    modelo = db.Column(db.String(120), nullable=False)
    rendimiento_km_l = db.Column(db.Float, nullable=False, default=10.0)
    kilometraje_actual = db.Column(db.Integer, nullable=False, default=0)
    tecnico_email = db.Column(db.String(120), nullable=True)
    activo = db.Column(db.Boolean, nullable=False, default=True)


class Destination(TimestampMixin, db.Model):
    __tablename__ = "destinos"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(180), unique=True, nullable=False, index=True)
    region = db.Column(db.String(80), nullable=True)
    comuna = db.Column(db.String(80), nullable=True)
    distancia_oficial_km = db.Column(db.Float, nullable=False)
    latitud = db.Column(db.Float, nullable=True)
    longitud = db.Column(db.Float, nullable=True)
    activo = db.Column(db.Boolean, nullable=False, default=True)


class Tariff(TimestampMixin, db.Model):
    """Historial de tarifas. Solo un registro por combustible está `activa`."""

    __tablename__ = "tarifas"

    id = db.Column(db.Integer, primary_key=True)
    combustible = db.Column(db.String(20), nullable=False, index=True)
    precio_litro = db.Column(db.Float, nullable=False)
    moneda = db.Column(db.String(3), nullable=False, default="CLP")
    origen = db.Column(db.String(20), nullable=False, default="FALLBACK")
    fuente = db.Column(db.Text, nullable=True)
    vigente_desde = db.Column(db.DateTime, nullable=False, default=now_utc)
    activa = db.Column(db.Boolean, nullable=False, default=False, index=True)
    detalle = db.Column(db.Text, nullable=True)


class Trip(TimestampMixin, db.Model):
    """Un viaje sincronizado desde la app Android (entidad `Viaje`)."""

    __tablename__ = "viajes"

    # Identificador generado en el cliente: garantiza idempotencia offline.
    uuid = db.Column(db.String(36), primary_key=True)

    ruta_seleccionada = db.Column(db.String(255), nullable=False, index=True)
    odometro_inicio = db.Column(db.Integer, nullable=False)
    odometro_fin = db.Column(db.Integer, nullable=False)
    foto_odometro_inicio = db.Column(db.Text, nullable=True)
    foto_odometro_fin = db.Column(db.Text, nullable=True)

    total_monto_peajes = db.Column(db.Float, nullable=False, default=0.0)
    fotos_peajes = db.Column(db.Text, nullable=False, default="")

    hora_inicio = db.Column(db.BigInteger, nullable=False, index=True)
    hora_fin = db.Column(db.BigInteger, nullable=False)

    eventos_extra = db.Column(db.Text, nullable=False, default="")
    latitud_inicio = db.Column(db.Float, nullable=True)
    longitud_inicio = db.Column(db.Float, nullable=True)
    latitud_fin = db.Column(db.Float, nullable=True)
    longitud_fin = db.Column(db.Float, nullable=True)

    tecnico_email = db.Column(db.String(120), nullable=False, index=True)
    vehiculo_patente = db.Column(db.String(20), nullable=False, index=True)

    sincronizado = db.Column(db.Boolean, nullable=False, default=True)
    estado_aprobacion = db.Column(
        db.String(20), nullable=False, default="PENDIENTE", index=True
    )
    observacion_jefe = db.Column(db.Text, nullable=False, default="")

    # Resultado del motor centralizado de cálculo.
    distancia_declarada_km = db.Column(db.Float, nullable=False, default=0.0)
    distancia_oficial_km = db.Column(db.Float, nullable=True)
    desviacion_porcentaje = db.Column(db.Float, nullable=True)
    alerta_desviacion = db.Column(db.Boolean, nullable=False, default=False, index=True)
    rendimiento_usado_km_l = db.Column(db.Float, nullable=False, default=0.0)
    tarifa_usada_clp_l = db.Column(db.Float, nullable=False, default=0.0)
    fuente_tarifa = db.Column(db.String(20), nullable=False, default="CONFIG")
    costo_combustible_estimado = db.Column(db.Float, nullable=False, default=0.0)
    costo_total_calculado = db.Column(db.Float, nullable=False, default=0.0)


class Notification(TimestampMixin, db.Model):
    """Registro de la notificación simulada por correo al técnico."""

    __tablename__ = "notificaciones"

    id = db.Column(db.Integer, primary_key=True)
    viaje_uuid = db.Column(db.String(36), nullable=False, index=True)
    destinatario = db.Column(db.String(120), nullable=False)
    tipo = db.Column(db.String(40), nullable=False)
    mensaje = db.Column(db.Text, nullable=False)
    leida = db.Column(db.Boolean, nullable=False, default=False)
