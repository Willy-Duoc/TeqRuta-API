from conftest import auth, make_viaje

UUID = "44444444-4444-4444-8444-444444444444"


def _sincronizar_y_aprobar(client, tokens):
    client.post(
        "/api/viajes/sync",
        json={"viajes": [make_viaje(UUID)]},
        headers=auth(tokens["tecnico"]),
    )
    aprobacion = client.patch(
        f"/api/viajes/{UUID}/aprobacion",
        json={"estado": "APROBADO"},
        headers=auth(tokens["jefe"]),
    )
    assert aprobacion.status_code == 200
    assert aprobacion.get_json()["data"]["estadoAprobacion"] == "APROBADO"


def test_aprobacion_y_reporte_financiero(client, tokens):
    _sincronizar_y_aprobar(client, tokens)

    reporte = client.get(
        "/api/reportes/mensual?cliente=RedSalud", headers=auth(tokens["gerencia"])
    )
    assert reporte.status_code == 200
    resumen = reporte.get_json()["data"]["resumen"]
    assert resumen["viajesAprobados"] == 1
    assert resumen["costoTotal"] == 3694.0
    assert resumen["promedioPorVisita"] == 3694.0
    assert reporte.get_json()["data"]["porCliente"][0]["grupo"].startswith("Sede Concepción")


def test_exportacion_csv(client, tokens):
    _sincronizar_y_aprobar(client, tokens)
    response = client.get("/api/reportes/mensual.csv", headers=auth(tokens["gerencia"]))
    assert response.status_code == 200
    assert "text/csv" in response.content_type
    body = response.get_data(as_text=True)
    assert UUID in body
    assert "costo_total_clp" in body


def test_reporte_desviaciones(client, tokens):
    _sincronizar_y_aprobar(client, tokens)
    response = client.get("/api/reportes/desviaciones", headers=auth(tokens["jefe"]))
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["total"] == 1
    assert data["viajes"][0]["desviacionPorcentaje"] == 84.0


def test_observacion_requiere_comentario(client, tokens):
    client.post(
        "/api/viajes/sync",
        json={"viajes": [make_viaje()]},
        headers=auth(tokens["tecnico"]),
    )
    response = client.patch(
        "/api/viajes/11111111-1111-4111-8111-111111111111/aprobacion",
        json={"estado": "OBSERVADO"},
        headers=auth(tokens["jefe"]),
    )
    assert response.status_code == 400
