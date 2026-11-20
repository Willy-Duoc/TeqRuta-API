from conftest import auth, make_viaje


def test_sync_idempotente_y_calculo_centralizado(client, tokens):
    payload = {"viajes": [make_viaje()]}

    primera = client.post("/api/viajes/sync", json=payload, headers=auth(tokens["tecnico"]))
    assert primera.status_code == 200, primera.get_data(as_text=True)
    resumen = primera.get_json()["data"]["resumen"]
    assert resumen == {
        "recibidos": 1,
        "insertados": 1,
        "duplicados": 0,
        "rechazados": 0,
    }

    segunda = client.post("/api/viajes/sync", json=payload, headers=auth(tokens["tecnico"]))
    assert segunda.status_code == 200
    assert segunda.get_json()["data"]["resumen"]["duplicados"] == 1

    detalle = client.get(
        "/api/viajes/11111111-1111-4111-8111-111111111111",
        headers=auth(tokens["tecnico"]),
    )
    assert detalle.status_code == 200
    viaje = detalle.get_json()["data"]

    # 23 km / 11.5 km/L * $1597 = $3194 + $500 peajes = $3694
    assert viaje["distanciaDeclaradaKm"] == 23.0
    assert viaje["rendimientoUsadoKmL"] == 11.5
    assert viaje["tarifaUsadaClpL"] == 1597.0
    assert viaje["costoCombustibleEstimado"] == 3194.0
    assert viaje["costoTotalCalculado"] == 3694.0
    assert viaje["estadoAprobacion"] == "PENDIENTE"
    assert viaje["alertaDesviacion"] is True  # 23 vs 12.5 km oficiales
    assert viaje["sincronizado"] is True


def test_sync_rechaza_datos_invalidos_y_viajes_ajenos(client, tokens):
    payload = {
        "viajes": [
            make_viaje(
                uuid="22222222-2222-4222-8222-222222222222",
                odometroFin=900,
            ),
            make_viaje(
                uuid="33333333-3333-4333-8333-333333333333",
                tecnicoEmail="otro@teqmed.cl",
            ),
        ]
    }
    response = client.post("/api/viajes/sync", json=payload, headers=auth(tokens["tecnico"]))
    assert response.status_code == 207
    data = response.get_json()["data"]
    assert data["resumen"]["rechazados"] == 2
    assert len(data["rechazados"]) == 2


def test_listado_filtrado_por_rol_y_estado(client, tokens):
    client.post(
        "/api/viajes/sync",
        json={"viajes": [make_viaje()]},
        headers=auth(tokens["tecnico"]),
    )
    listado = client.get("/api/viajes?estado=PENDIENTE", headers=auth(tokens["jefe"]))
    assert listado.status_code == 200
    assert listado.get_json()["meta"]["total"] == 1

    otro_tecnico = client.post(
        "/api/auth/register",
        json={
            "email": "otro@teqmed.cl",
            "password": "otro123",
            "nombre": "Otro Técnico",
        },
    )
    assert otro_tecnico.status_code == 201
    token = client.post(
        "/api/auth/login",
        json={"email": "otro@teqmed.cl", "password": "otro123"},
    ).get_json()["data"]["access_token"]
    sin_viajes = client.get("/api/viajes", headers=auth(token))
    assert sin_viajes.get_json()["meta"]["total"] == 0
