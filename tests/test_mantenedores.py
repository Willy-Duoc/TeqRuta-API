from conftest import auth, make_viaje


def test_abm_vehiculos_y_permisos(client, tokens):
    creacion = client.post(
        "/api/mantenedores/vehiculos",
        json={
            "patente": "ZZ-9999",
            "modelo": "Nissan Frontier",
            "rendimiento": 9.5,
            "kilometrajeActual": 100,
        },
        headers=auth(tokens["admin"]),
    )
    assert creacion.status_code == 201
    assert creacion.get_json()["data"]["rendimientoKmL"] == 9.5

    sin_permiso = client.post(
        "/api/mantenedores/vehiculos",
        json={"patente": "AA-1111", "modelo": "Test", "rendimiento": 10},
        headers=auth(tokens["tecnico"]),
    )
    assert sin_permiso.status_code == 403

    actualizacion = client.put(
        "/api/mantenedores/vehiculos/ZZ-9999",
        json={"rendimiento": 12.0},
        headers=auth(tokens["admin"]),
    )
    assert actualizacion.status_code == 200
    assert actualizacion.get_json()["data"]["rendimientoKmL"] == 12.0


def test_tarifa_manual_se_refleja_en_nuevo_viaje(client, tokens):
    override = client.put(
        "/api/mantenedores/tarifas/93",
        json={"precioLitro": 2000, "fuente": "Prueba manual"},
        headers=auth(tokens["admin"]),
    )
    assert override.status_code == 200
    assert override.get_json()["data"]["origen"] == "MANUAL"

    client.post(
        "/api/viajes/sync",
        json={"viajes": [make_viaje()]},
        headers=auth(tokens["tecnico"]),
    )
    viaje = client.get(
        "/api/viajes/11111111-1111-4111-8111-111111111111",
        headers=auth(tokens["tecnico"]),
    ).get_json()["data"]
    assert viaje["tarifaUsadaClpL"] == 2000.0
    assert viaje["costoCombustibleEstimado"] == 4000.0
    assert viaje["costoTotalCalculado"] == 4500.0


def test_destinos_disponibles_para_cache_offline(client, tokens):
    response = client.get("/api/mantenedores/destinos", headers=auth(tokens["tecnico"]))
    assert response.status_code == 200
    nombres = [item["nombre"] for item in response.get_json()["data"]]
    assert "Hospital Regional de Chillán" in nombres
