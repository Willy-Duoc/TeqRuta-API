"""Pruebas del dashboard web: sesión, CSRF, RBAC, CRUD y reportes."""

from __future__ import annotations

from conftest import auth, make_viaje

from app.extensions import db
from app.models import Destination, Notification, Tariff, User, Vehicle


def _csrf(client) -> str:
    with client.session_transaction() as sess:
        return sess["_csrf"]


def _login(client, email: str = "admin@teqmed.cl", password: str = "admin123"):
    client.get("/admin/login")
    return client.post(
        "/admin/login",
        data={"_csrf": _csrf(client), "email": email, "password": password},
    )


def _crear_viaje(client, tokens, uuid_value: str = "55555555-5555-4555-8555-555555555555"):
    response = client.post(
        "/api/viajes/sync",
        json={"viajes": [make_viaje(uuid_value)]},
        headers=auth(tokens["tecnico"]),
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    return uuid_value


def test_panel_requiere_login_y_admin_entra(client):
    response = client.get("/admin/")
    assert response.status_code == 302
    assert "/admin/login" in response.headers["Location"]

    login_page = client.get("/admin/login")
    assert login_page.status_code == 200
    assert "Ingreso administrativo" in login_page.get_data(as_text=True)

    malo = client.post(
        "/admin/login",
        data={
            "_csrf": _csrf(client),
            "email": "admin@teqmed.cl",
            "password": "incorrecta",
        },
    )
    assert malo.status_code == 401

    correcto = _login(client)
    assert correcto.status_code == 302
    assert correcto.headers["Location"].endswith("/admin/")

    panel = client.get("/admin/")
    assert panel.status_code == 200
    html = panel.get_data(as_text=True)
    assert "Resumen operativo" in html
    assert "admin@teqmed.cl" not in html  # no se expone el email en la cabecera
    assert "Administrador TeqMed" in html


def test_tecnico_no_puede_entrar_al_panel(client):
    response = _login(client, "tecnico@teqmed.cl", "tecnico123")
    assert response.status_code == 401
    assert "sin acceso" in response.get_data(as_text=True)


def test_csrf_es_obligatorio(client, tokens):
    client.get("/admin/login")
    sin_token = client.post(
        "/admin/login", data={"email": "admin@teqmed.cl", "password": "admin123"}
    )
    assert sin_token.status_code == 400

    assert _login(client).status_code == 302
    uuid_value = _crear_viaje(client, tokens)
    sin_csrf = client.post(
        f"/admin/viajes/{uuid_value}/aprobacion", data={"estado": "APROBADO"}
    )
    assert sin_csrf.status_code == 400


def test_aprobar_viaje_con_notificacion(client, tokens):
    uuid_value = _crear_viaje(client, tokens)
    assert _login(client).status_code == 302

    listado = client.get("/admin/viajes")
    assert listado.status_code == 200
    assert uuid_value in listado.get_data(as_text=True)

    detalle = client.get(f"/admin/viajes/{uuid_value}")
    assert detalle.status_code == 200
    assert "Aprobación de jefatura" in detalle.get_data(as_text=True)

    aprobacion = client.post(
        f"/admin/viajes/{uuid_value}/aprobacion",
        data={
            "_csrf": _csrf(client),
            "estado": "APROBADO",
            "observacionJefe": "Conforme",
        },
    )
    assert aprobacion.status_code == 302

    viaje = client.get(
        f"/api/viajes/{uuid_value}", headers=auth(tokens["jefe"])
    ).get_json()["data"]
    assert viaje["estadoAprobacion"] == "APROBADO"
    assert viaje["observacionJefe"] == "Conforme"

    with client.application.app_context():
        nota = Notification.query.filter_by(viaje_uuid=uuid_value).one()
        assert nota.tipo == "VIAJE_APROBADO"
        assert nota.destinatario == "tecnico@teqmed.cl"


def test_gerencia_no_aprueba_y_jefe_si(client, tokens):
    uuid_value = _crear_viaje(client, tokens)

    assert _login(client, "gerencia@teqmed.cl", "gerencia123").status_code == 302
    gerencia = client.post(
        f"/admin/viajes/{uuid_value}/aprobacion",
        data={"_csrf": _csrf(client), "estado": "APROBADO"},
    )
    assert gerencia.status_code == 403

    client.post("/admin/logout", data={"_csrf": _csrf(client)})
    assert _login(client, "jefe@teqmed.cl", "jefe123").status_code == 302
    jefe = client.post(
        f"/admin/viajes/{uuid_value}/aprobacion",
        data={"_csrf": _csrf(client), "estado": "OBSERVADO", "observacionJefe": "Revisar"},
    )
    assert jefe.status_code == 302

    viaje = client.get(
        f"/api/viajes/{uuid_value}", headers=auth(tokens["tecnico"])
    ).get_json()["data"]
    assert viaje["estadoAprobacion"] == "OBSERVADO"


def test_crud_vehiculo_destino_y_usuario(client):
    assert _login(client).status_code == 302

    vehiculo = client.post(
        "/admin/vehiculos/nuevo",
        data={
            "_csrf": _csrf(client),
            "patente": "TT-1234",
            "modelo": "Toyota Test",
            "rendimiento": "9.5",
            "kilometrajeActual": "1234",
            "tecnicoEmail": "tecnico@teqmed.cl",
            "activo": "on",
        },
    )
    assert vehiculo.status_code == 302
    with client.application.app_context():
        assert Vehicle.query.filter_by(patente="TT-1234").one().rendimiento_km_l == 9.5

    destino = client.post(
        "/admin/destinos/nuevo",
        data={
            "_csrf": _csrf(client),
            "nombre": "Clínica de Prueba",
            "region": "Biobío",
            "comuna": "Concepción",
            "distanciaOficialKm": "15.5",
            "latitud": "-36.82",
            "longitud": "-73.05",
            "activo": "on",
        },
    )
    assert destino.status_code == 302
    with client.application.app_context():
        assert Destination.query.filter_by(nombre="Clínica de Prueba").one().distancia_oficial_km == 15.5

    usuario = client.post(
        "/admin/usuarios/nuevo",
        data={
            "_csrf": _csrf(client),
            "email": "nuevo@teqmed.cl",
            "nombre": "Usuario Nuevo",
            "rol": "jefe",
            "cargo": "Jefatura",
            "password": "ClaveSegura123",
            "activo": "on",
        },
    )
    assert usuario.status_code == 302
    with client.application.app_context():
        creado = User.query.filter_by(email="nuevo@teqmed.cl").one()
        assert creado.rol == "jefe"
        assert creado.activo is True

    assert client.get("/admin/vehiculos/TT-1234/editar").status_code == 200
    assert client.get("/admin/usuarios").status_code == 200


def test_tarifa_manual_y_reporte_csv(client, tokens):
    uuid_value = _crear_viaje(client, tokens)
    client.patch(
        f"/api/viajes/{uuid_value}/aprobacion",
        json={"estado": "APROBADO"},
        headers=auth(tokens["jefe"]),
    )
    assert _login(client).status_code == 302

    tarifa = client.post(
        "/admin/tarifas/manual",
        data={
            "_csrf": _csrf(client),
            "combustible": "93",
            "precioLitro": "1800",
            "fuente": "Prueba dashboard",
        },
    )
    assert tarifa.status_code == 302
    with client.application.app_context():
        activa = Tariff.query.filter_by(combustible="93", activa=True).one()
        assert activa.origen == "MANUAL"
        assert activa.precio_litro == 1800.0

    reporte = client.get("/admin/reportes?anio=2025&mes=11")
    assert reporte.status_code == 200
    assert "Reportes financieros" in reporte.get_data(as_text=True)

    csv_response = client.get("/admin/reportes.csv?anio=2025&mes=11")
    assert csv_response.status_code == 200
    assert "text/csv" in csv_response.content_type
    cuerpo = csv_response.get_data(as_text=True)
    assert uuid_value in cuerpo
    assert "costo_total_clp" in cuerpo


def test_listado_de_tarifas_api_no_recursa(client, tokens):
    response = client.get("/api/mantenedores/tarifas", headers=auth(tokens["admin"]))
    assert response.status_code == 200
    assert isinstance(response.get_json()["data"], list)
    assert response.get_json()["data"]
