# Atajos de desarrollo y despliegue para TeqRuta API.
PYTHON ?= .venv/bin/python
COMPOSE ?= docker compose --env-file .env.production
TEST_DATABASE_URL ?= postgresql+psycopg://teqruta:teqruta@127.0.0.1:5432/teqruta_test

.PHONY: help setup venv test test-postgres instalar-ngrok publicar estado smoke \
	smoke-local detener prod-env prod-cert prod-config prod-build prod-up \
	prod-down prod-restart prod-logs prod-ps prod-init prod-admin

help:
	@echo "Desarrollo"
	@echo "  make setup         Prepara .venv, dependencias, Ngrok y .env"
	@echo "  make venv          Solo crea .venv e instala dependencias"
	@echo "  make test          Ejecuta pytest con SQLite en memoria"
	@echo "  make test-postgres Ejecuta pytest contra PostgreSQL (TEST_DATABASE_URL)"
	@echo "  make instalar-ngrok Descarga el agente Ngrok en .tools/"
	@echo "  make publicar      Levanta Flask + túnel HTTPS y actualiza la app Android"
	@echo "  make estado        Muestra URL pública, PIDs y puerto oculto"
	@echo "  make smoke         Prueba end-to-end contra la URL pública"
	@echo "  make smoke-local   Prueba end-to-end contra 127.0.0.1:5000"
	@echo "  make detener       Cierra Ngrok y el Flask iniciado por el script"
	@echo ""
	@echo "Producción (Docker: PostgreSQL + Gunicorn + Nginx)"
	@echo "  make prod-env      Crea .env.production con secretos aleatorios"
	@echo "  make prod-cert     Genera certificado autofirmado para pruebas"
	@echo "  make prod-config   Valida docker-compose.yml y .env.production"
	@echo "  make prod-build    Construye la imagen de la API"
	@echo "  make prod-up       Levanta el stack en segundo plano"
	@echo "  make prod-down     Detiene el stack (conserva el volumen de datos)"
	@echo "  make prod-restart  Reinicia API y Nginx"
	@echo "  make prod-logs     Sigue los logs de todos los servicios"
	@echo "  make prod-ps       Muestra el estado de los contenedores"
	@echo "  make prod-init     Crea las tablas en PostgreSQL"
	@echo "  make prod-admin    Crea un administrador de forma interactiva"

.venv/bin/python:
	python3 -m venv .venv

.venv/.instalado: .venv/bin/python requirements.txt requirements-prod.txt requirements-dev.txt
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements-dev.txt
	@touch .venv/.instalado

venv: .venv/.instalado

.env:
	python3 scripts/preparar_env.py

setup: .venv/.instalado .env
	@if ! command -v ngrok >/dev/null 2>&1 && [ ! -x .tools/ngrok ]; then \
		$(MAKE) instalar-ngrok; \
	fi
	@if grep -Eq '^NGROK_AUTHTOKEN=.+' .env; then \
		echo "[setup] Dependencias, Ngrok y .env listos. Ejecuta: make publicar"; \
	else \
		echo "[setup] Falta NGROK_AUTHTOKEN en .env."; \
		echo "[setup] Edita .env o ejecuta: NGROK_AUTHTOKEN=tu_token make publicar"; \
	fi

test: .venv/.instalado
	$(PYTHON) -m pytest

test-postgres: .venv/.instalado
	TEST_DATABASE_URL="$(TEST_DATABASE_URL)" $(PYTHON) -m pytest

instalar-ngrok:
	bash scripts/instalar_ngrok.sh

publicar: setup
	$(PYTHON) scripts/tunel.py iniciar

estado: .venv/.instalado
	$(PYTHON) scripts/tunel.py estado

smoke: .venv/.instalado
	$(PYTHON) scripts/tunel.py smoke

smoke-local: .venv/.instalado
	$(PYTHON) scripts/tunel.py smoke --base-url http://127.0.0.1:5000

detener: .venv/.instalado
	$(PYTHON) scripts/tunel.py detener

# ---------------------------------------------------------------------------
# Producción con Docker Compose
# ---------------------------------------------------------------------------

.env.production:
	python3 scripts/preparar_env_produccion.py

prod-env: .env.production

prod-cert:
	bash deploy/generar_certificado.sh

prod-config: .env.production
	$(COMPOSE) config --quiet
	@echo "[prod] Configuración válida."

prod-build: .env.production
	$(COMPOSE) build api

prod-up: .env.production
	@test -f deploy/certs/fullchain.pem || { \
		echo "[prod] Faltan certificados. Ejecuta: make prod-cert"; exit 1; }
	$(COMPOSE) up -d --build

prod-down: .env.production
	$(COMPOSE) down

prod-restart: .env.production
	$(COMPOSE) restart api nginx

prod-logs: .env.production
	$(COMPOSE) logs -f --tail=100

prod-ps: .env.production
	$(COMPOSE) ps

prod-init: .env.production
	$(COMPOSE) run --rm api flask --app wsgi init-db

prod-admin: .env.production
	$(COMPOSE) run --rm api flask --app wsgi create-admin
