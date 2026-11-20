import pytest

from app import create_app
from app.config import TestingConfig
from app.extensions import db


@pytest.fixture()
def app():
    application = create_app(TestingConfig)
    application.config.update(TESTING=True)
    with application.app_context():
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def tokens(client):
    def login(email: str, password: str) -> str:
        response = client.post(
            "/api/auth/login", json={"email": email, "password": password}
        )
        assert response.status_code == 200, response.get_data(as_text=True)
        return response.get_json()["data"]["access_token"]

    return {
        "tecnico": login("tecnico@teqmed.cl", "tecnico123"),
        "jefe": login("jefe@teqmed.cl", "jefe123"),
        "gerencia": login("gerencia@teqmed.cl", "gerencia123"),
        "admin": login("admin@teqmed.cl", "admin123"),
    }


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def make_viaje(
    uuid_value: str = "11111111-1111-4111-8111-111111111111",
    **overrides,
) -> dict:
    viaje = {
        "uuid": uuid_value,
        "rutaSeleccionada": "Sede Concepción - Clínica RedSalud Concepción",
        "odometroInicio": 1000,
        "odometroFin": 1023,
        "fotoOdometroInicio": "odometro_ini.jpg",
        "fotoOdometroFin": "odometro_fin.jpg",
        "totalMontoPeajes": 500,
        "fotosPeajes": "1 comprobante(s)",
        "horaInicio": 1763500000000,
        "horaFin": 1763503600000,
        "eventosExtra": "Tráfico normal",
        "latitudInicio": -36.82,
        "longitudInicio": -73.06,
        "latitudFin": -36.83,
        "longitudFin": -73.05,
        "tecnicoEmail": "tecnico@teqmed.cl",
        "vehiculoPatente": "HK-8932",
        "sincronizado": False,
        "estadoAprobacion": "PENDIENTE",
        "observacionJefe": "",
        "costoCombustibleEstimado": 0.0,
    }
    viaje.update(overrides)
    return viaje
