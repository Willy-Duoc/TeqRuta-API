"""Integración con la fuente pública de precios de combustible (RF12).

Por defecto se consume el JSON público de AhorraHogar.cl que consolida datos
oficiales de la CNE / Bencina en Línea:

    https://ahorrahogar.cl/datos/datos.json
    -> bencina.combustibles["93"].regiones["8"].mediana   (Biobío)

Si la fuente falla, se conserva la última tarifa válida o se usa el valor
configurado en `FUEL_DEFAULT_PRICE`, dejando constancia del origen en la BD.
"""

from __future__ import annotations

import json

import requests
from flask import current_app

from ..extensions import db
from ..models import Tariff
from ..utils import now_utc

_ALIASES = {
    "93": "93",
    "GASOLINA 93": "93",
    "95": "95",
    "GASOLINA 95": "95",
    "97": "97",
    "GASOLINA 97": "97",
    "DIESEL": "diesel",
    "PETROLEO DIESEL": "diesel",
    "PETRÓLEO DIESEL": "diesel",
    "PARAFINA": "parafina",
    "KEROSENE": "parafina",
}


def normalize_combustible(combustible: str | None) -> str:
    key = str(combustible or "93").strip().upper()
    return _ALIASES.get(key, key.lower())


def fetch_external_price(combustible: str = "93") -> tuple[float | None, dict | None]:
    """Consulta la API pública y devuelve `(precio, metadata)`."""

    url = current_app.config.get("FUEL_PRICE_URL")
    if not url:
        return None, None

    key = normalize_combustible(combustible)
    try:
        response = requests.get(
            url,
            timeout=current_app.config["FUEL_PRICE_TIMEOUT"],
            headers={"User-Agent": "TeqRuta-API/1.0 (+Flask)"},
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        current_app.logger.warning("Fuente externa de combustible no disponible: %s", exc)
        return None, None

    try:
        bloque = payload["bencina"]["combustibles"][key]
        region_code = str(current_app.config["FUEL_REGION_CODE"])
        region_info = bloque.get("regiones", {}).get(region_code, {})
        nacional = bloque.get("nacional", {})
        precio = region_info.get("mediana") or nacional.get("mediana")
        if precio is None:
            raise KeyError("mediana")
        precio = float(precio)
        if precio <= 0:
            raise ValueError("precio no positivo")
    except (KeyError, TypeError, ValueError) as exc:
        current_app.logger.warning("Estructura inesperada de la fuente externa: %s", exc)
        return None, None

    metadata = {
        "combustible": key,
        "nombre": bloque.get("nombre"),
        "region": region_info.get("region"),
        "precio_nacional": nacional.get("mediana"),
        "verificado": payload.get("bencina", {}).get("verificado") or payload.get("verificado"),
        "fuente_oficial": payload.get("bencina", {}).get("fuente"),
        "estado": payload.get("bencina", {}).get("estado"),
    }
    return precio, metadata


def _deactivate_others(combustible: str) -> None:
    Tariff.query.filter_by(combustible=combustible, activa=True).update({"activa": False})


def set_active_tariff(
    combustible: str,
    precio: float,
    origen: str,
    fuente: str | None,
    detalle: dict | None = None,
) -> Tariff:
    key = normalize_combustible(combustible)
    _deactivate_others(key)
    tariff = Tariff(
        combustible=key,
        precio_litro=float(precio),
        moneda="CLP",
        origen=origen,
        fuente=fuente,
        vigente_desde=now_utc(),
        activa=True,
        detalle=json.dumps(detalle, ensure_ascii=False) if detalle else None,
    )
    db.session.add(tariff)
    db.session.commit()
    return tariff


def _fallback_tariff(combustible: str) -> Tariff:
    return set_active_tariff(
        combustible,
        current_app.config["FUEL_DEFAULT_PRICE"],
        "FALLBACK",
        "Valor por defecto (fuente externa no disponible)",
        {"motivo": "fuente_externa_no_disponible"},
    )


def refresh_tariff(combustible: str = "93") -> Tariff:
    """Fuerza una consulta a la fuente externa; mantiene/crea un fallback si falla."""

    key = normalize_combustible(combustible)
    precio, metadata = fetch_external_price(key)
    if precio is None:
        activa = Tariff.query.filter_by(combustible=key, activa=True).first()
        return activa or _fallback_tariff(key)

    return set_active_tariff(
        key,
        precio,
        "API_EXTERNA",
        (metadata or {}).get("fuente_oficial") or current_app.config["FUEL_PRICE_URL"],
        metadata,
    )


def set_manual_tariff(combustible: str, precio: float, fuente: str = "Overwrite manual") -> Tariff:
    return set_active_tariff(combustible, precio, "MANUAL", fuente, {"origen": "administrador"})


def list_tarifas() -> list[Tariff]:
    """Devuelve el historial completo de tarifas, ordenado por vigencia."""

    return Tariff.query.order_by(Tariff.vigente_desde.desc(), Tariff.id.desc()).all()


def get_active_tariff(combustible: str = "93") -> Tariff | None:
    """Devuelve la tarifa vigente, refrescándola si está antigua (1 vez al día)."""

    key = normalize_combustible(combustible)
    activa = Tariff.query.filter_by(combustible=key, activa=True).first()
    ahora = now_utc()
    es_antigua = True
    if activa and activa.vigente_desde:
        horas = (ahora - activa.vigente_desde).total_seconds() / 3600
        es_antigua = horas >= current_app.config["FUEL_PRICE_CACHE_HOURS"]

    if activa is None or es_antigua:
        refrescada = refresh_tariff(key)
        if refrescada is not None:
            return refrescada
    return activa
