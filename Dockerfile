# Imagen de producción: Gunicorn detrás de Nginx, sin privilegios de root.
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Usuario sin privilegios: si el contenedor se compromete, no es root.
RUN groupadd --system teqruta \
    && useradd --system --gid teqruta --home-dir /app teqruta

# Las dependencias se copian primero para aprovechar la caché de capas.
COPY requirements.txt requirements-prod.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements-prod.txt

COPY . .
RUN mkdir -p /app/instance \
    && chown -R teqruta:teqruta /app

USER teqruta

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)" || exit 1

# Gunicorn escucha en la red interna de Docker; Nginx es el único expuesto.
CMD ["gunicorn", "--config", "gunicorn.conf.py", "wsgi:app"]
