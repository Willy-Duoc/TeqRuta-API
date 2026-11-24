# Atajos de desarrollo y despliegue para TeqRuta API.
PYTHON ?= .venv/bin/python

.PHONY: help setup venv test instalar-ngrok publicar estado smoke smoke-local detener

help:
	@echo "make setup         Prepara .venv, dependencias, Ngrok y .env"
	@echo "make venv          Solo crea .venv e instala dependencias"
	@echo "make test          Ejecuta pytest"
	@echo "make instalar-ngrok Descarga el agente Ngrok en .tools/"
	@echo "make publicar      Levanta Flask + túnel HTTPS y actualiza la app Android"
	@echo "make estado        Muestra URL pública, PIDs y puerto oculto"
	@echo "make smoke         Prueba end-to-end contra la URL pública"
	@echo "make smoke-local   Prueba end-to-end contra 127.0.0.1:5000"
	@echo "make detener       Cierra Ngrok y el Flask iniciado por el script"

.venv/bin/python:
	python3 -m venv .venv

.venv/.instalado: .venv/bin/python requirements.txt requirements-dev.txt
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
