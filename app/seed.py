"""Datos iniciales para desarrollo y demostración académica."""

from __future__ import annotations

from datetime import datetime

from .extensions import db
from .models import Destination, Tariff, User, Vehicle
from .security import hash_password

DEMO_USERS = [
    {
        "email": "tecnico@teqmed.cl",
        "password": "tecnico123",
        "nombre": "Hans Morales",
        "rol": "tecnico",
        "cargo": "Técnico de Servicio",
        "vehiculo_asignado": "HK-8932",
    },
    {
        "email": "jefe@teqmed.cl",
        "password": "jefe123",
        "nombre": "Martina Norambuena",
        "rol": "jefe",
        "cargo": "Jefe de Servicio Técnico",
        "vehiculo_asignado": None,
    },
    {
        "email": "gerencia@teqmed.cl",
        "password": "gerencia123",
        "nombre": "Williams Contreras",
        "rol": "gerencia",
        "cargo": "Gerencia y Finanzas",
        "vehiculo_asignado": None,
    },
    {
        "email": "admin@teqmed.cl",
        "password": "admin123",
        "nombre": "Administrador TeqMed",
        "rol": "admin",
        "cargo": "Administrador del Sistema",
        "vehiculo_asignado": None,
    },
]

DEMO_VEHICLES = [
    {
        "patente": "HK-8932",
        "modelo": "Toyota Hilux 2.8",
        "rendimiento_km_l": 11.5,
        "kilometraje_actual": 84210,
        "tecnico_email": "tecnico@teqmed.cl",
    },
    {
        "patente": "CJ-4521",
        "modelo": "Chevrolet D-Max",
        "rendimiento_km_l": 10.2,
        "kilometraje_actual": 61780,
        "tecnico_email": None,
    },
]

DEMO_DESTINATIONS = [
    {
        "nombre": "Clínica RedSalud Concepción",
        "region": "Biobío",
        "comuna": "Concepción",
        "distancia_oficial_km": 12.5,
        "latitud": -36.827,
        "longitud": -73.048,
    },
    {
        "nombre": "Clínica RedSalud Rancagua",
        "region": "O'Higgins",
        "comuna": "Rancagua",
        "distancia_oficial_km": 87.0,
        "latitud": -34.169,
        "longitud": -70.744,
    },
    {
        "nombre": "Hospital Regional de Chillán",
        "region": "Ñuble",
        "comuna": "Chillán",
        "distancia_oficial_km": 315.0,
        "latitud": -36.606,
        "longitud": -72.104,
    },
    {
        "nombre": "Centro de Diálisis Los Ángeles",
        "region": "Biobío",
        "comuna": "Los Ángeles",
        "distancia_oficial_km": 185.0,
        "latitud": -37.469,
        "longitud": -72.354,
    },
    {
        "nombre": "Hospital Regional de Temuco",
        "region": "Araucanía",
        "comuna": "Temuco",
        "distancia_oficial_km": 470.0,
        "latitud": -38.735,
        "longitud": -72.590,
    },
]


def seed_database(app) -> None:
    """Crea usuarios, flota, destinos y una tarifa base si no existen."""

    with app.app_context():
        changed = False

        for item in DEMO_USERS:
            if User.query.filter_by(email=item["email"]).first() is None:
                db.session.add(
                    User(
                        email=item["email"],
                        password_hash=hash_password(item["password"]),
                        nombre=item["nombre"],
                        rol=item["rol"],
                        cargo=item["cargo"],
                        vehiculo_asignado=item["vehiculo_asignado"],
                        activo=True,
                    )
                )
                changed = True

        for item in DEMO_VEHICLES:
            if Vehicle.query.filter_by(patente=item["patente"]).first() is None:
                db.session.add(Vehicle(**item, activo=True))
                changed = True

        for item in DEMO_DESTINATIONS:
            if Destination.query.filter_by(nombre=item["nombre"]).first() is None:
                db.session.add(Destination(**item, activo=True))
                changed = True

        combustible = app.config["COSTO_COMBUSTIBLE_TIPO"]
        if Tariff.query.filter_by(combustible=combustible, activa=True).first() is None:
            # Marca una fecha antigua para que el servicio externo la refresque
            # en el primer cálculo (RF12), manteniendo un valor válido offline.
            db.session.add(
                Tariff(
                    combustible=combustible,
                    precio_litro=app.config["FUEL_DEFAULT_PRICE"],
                    moneda="CLP",
                    origen="FALLBACK",
                    fuente="Valor inicial (sin conexión)",
                    vigente_desde=datetime(2000, 1, 1),
                    activa=True,
                    detalle="Tarifa base hasta la primera consulta a la fuente pública",
                )
            )
            changed = True

        if changed:
            db.session.commit()
