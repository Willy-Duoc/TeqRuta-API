"""Motor centralizado y auditable de cálculo de costos de movilización.

Fórmula:
    distancia_declarada = odometroFin - odometroInicio
    costo_combustible   = (distancia_declarada / rendimiento_km_l) * precio_litro
    costo_total         = costo_combustible + total_monto_peajes

Además compara la distancia declarada contra la distancia oficial parametrizada
para el destino y marca una alerta cuando la desviación supera el umbral (10%).
"""

from __future__ import annotations

from flask import current_app

from ..models import Destination, Vehicle
from .fuel_price import get_active_tariff


def _find_destination(ruta: str) -> Destination | None:
    texto = (ruta or "").strip().lower()
    if not texto:
        return None
    candidatos = [
        destino
        for destino in Destination.query.filter_by(activo=True).all()
        if destino.nombre.strip().lower() in texto or texto in destino.nombre.strip().lower()
    ]
    if not candidatos:
        return None
    return max(candidatos, key=lambda destino: len(destino.nombre))


def calcular_costo(viaje: dict) -> dict:
    """Calcula todas las métricas persistentes de un viaje."""

    patente = str(viaje.get("vehiculoPatente") or "").strip().upper()
    vehiculo = Vehicle.query.filter_by(patente=patente, activo=True).first()
    if vehiculo and vehiculo.rendimiento_km_l and vehiculo.rendimiento_km_l > 0:
        rendimiento = float(vehiculo.rendimiento_km_l)
    else:
        rendimiento = float(current_app.config["DEFAULT_RENDIMIENTO_KM_L"])

    destino = _find_destination(str(viaje.get("rutaSeleccionada") or ""))
    oficial = float(destino.distancia_oficial_km) if destino else None

    declarada = float(viaje["odometroFin"] - viaje["odometroInicio"])
    desviacion = None
    if oficial and oficial > 0:
        desviacion = ((declarada - oficial) / oficial) * 100

    umbral = float(current_app.config["DESVIACION_UMBRAL_PCT"])
    alerta = desviacion is not None and abs(desviacion) > umbral

    combustible = current_app.config["COSTO_COMBUSTIBLE_TIPO"]
    tarifa = get_active_tariff(combustible)
    precio_litro = float(tarifa.precio_litro) if tarifa else float(
        current_app.config["FUEL_DEFAULT_PRICE"]
    )

    costo_combustible = (declarada / rendimiento) * precio_litro
    peajes = float(viaje.get("totalMontoPeajes") or 0.0)
    costo_total = costo_combustible + peajes

    return {
        "distancia_declarada_km": round(declarada, 2),
        "distancia_oficial_km": round(oficial, 2) if oficial is not None else None,
        "desviacion_porcentaje": round(desviacion, 2) if desviacion is not None else None,
        "alerta_desviacion": bool(alerta),
        "rendimiento_usado_km_l": round(rendimiento, 2),
        "tarifa_usada_clp_l": round(precio_litro, 2),
        "fuente_tarifa": tarifa.origen if tarifa else "CONFIG",
        "costo_combustible_estimado": round(costo_combustible, 2),
        "costo_total_calculado": round(costo_total, 2),
    }
