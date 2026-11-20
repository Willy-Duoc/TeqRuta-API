import json

from app.services import fuel_price
from conftest import auth


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_actualizar_tarifa_desde_fuente_publica(client, tokens, monkeypatch):
    payload = {
        "verificado": "2026-11-19",
        "bencina": {
            "fuente": "https://www.bencinaenlinea.cl/",
            "estado": "ok",
            "combustibles": {
                "93": {
                    "nombre": "Gasolina 93",
                    "nacional": {"mediana": 1597},
                    "regiones": {
                        "8": {
                            "region": "Biobío",
                            "mediana": 1581,
                        }
                    },
                }
            },
        },
    }
    monkeypatch.setattr(
        fuel_price.requests, "get", lambda *args, **kwargs: FakeResponse(payload)
    )
    client.application.config["FUEL_PRICE_URL"] = "https://fake.local/datos.json"

    response = client.post(
        "/api/mantenedores/tarifas/actualizar", headers=auth(tokens["admin"])
    )
    assert response.status_code == 200
    tarifa = response.get_json()["data"]
    assert tarifa["origen"] == "API_EXTERNA"
    assert tarifa["precioLitro"] == 1581.0
    assert tarifa["activa"] is True
    assert json.loads(tarifa["detalle"])["region"] == "Biobío"


def test_fallback_cuando_falla_fuente(client, tokens, monkeypatch):
    def fallar(*args, **kwargs):
        raise ConnectionError("sin red")

    monkeypatch.setattr(fuel_price.requests, "get", fallar)
    response = client.post(
        "/api/mantenedores/tarifas/actualizar", headers=auth(tokens["admin"])
    )
    assert response.status_code == 200
    tarifa = response.get_json()["data"]
    assert tarifa["origen"] in {"FALLBACK", "API_EXTERNA"}
    assert tarifa["precioLitro"] > 0
