"""Configuración de Gunicorn para producción.

El contenedor de la API solo es alcanzable desde la red interna de Docker;
Nginx termina TLS y reenvía las cabeceras `X-Forwarded-*`.
"""

from __future__ import annotations

import multiprocessing
import os

# En Docker se fuerza 0.0.0.0:8000 mediante GUNICORN_BIND. Nunca se publica
# ese puerto al host: docker-compose solo expone 80/443 en Nginx.
bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8000")

# Fórmula recomendada para cargas con I/O (consultas SQL y llamadas HTTP).
workers = int(
    os.getenv("WEB_CONCURRENCY", str(min(8, multiprocessing.cpu_count() * 2 + 1)))
)
threads = int(os.getenv("GUNICORN_THREADS", "2"))
worker_class = os.getenv("GUNICORN_WORKER_CLASS", "gthread")

timeout = int(os.getenv("GUNICORN_TIMEOUT", "60"))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "5"))

# Recicla workers para evitar fugas de memoria en procesos de larga vida.
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", "1000"))
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", "100"))

accesslog = os.getenv("GUNICORN_ACCESS_LOG", "-")
errorlog = os.getenv("GUNICORN_ERROR_LOG", "-")
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
access_log_format = (
    '%({x-forwarded-for}i)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s '
    '"%(f)s" "%(a)s" %(D)sµs'
)

# Gunicorn acepta X-Forwarded-* solo desde el proxy. En Docker, Nginx llega
# desde la red interna; se restringe con FORWARDED_ALLOW_IPS si se desea.
forwarded_allow_ips = os.getenv("FORWARDED_ALLOW_IPS", "*")
proxy_allow_ips = forwarded_allow_ips

# No cargar la app en el proceso maestro.
preload_app = os.getenv("GUNICORN_PRELOAD", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
