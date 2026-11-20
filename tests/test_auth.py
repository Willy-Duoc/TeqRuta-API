from conftest import auth


def test_root_y_health_publicos(client):
    assert client.get("/").status_code == 200
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.get_json()["database"] == "ok"


def test_login_devuelve_jwt_y_perfil(client, tokens):
    response = client.get("/api/auth/me", headers=auth(tokens["tecnico"]))
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["rol"] == "tecnico"
    assert data["email"] == "tecnico@teqmed.cl"


def test_login_credenciales_invalidas(client):
    response = client.post(
        "/api/auth/login", json={"email": "tecnico@teqmed.cl", "password": "mala"}
    )
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "invalid_credentials"


def test_token_requerido_y_rbac(client, tokens):
    assert client.get("/api/viajes").status_code == 401

    response = client.get(
        "/api/reportes/mensual", headers=auth(tokens["tecnico"])
    )
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"
