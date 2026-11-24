#!/usr/bin/env python3
"""Salida pública de TeqRuta API mediante Ngrok.

El servidor Flask escucha en 127.0.0.1 (nunca en la LAN) y este script crea un
túnel HTTPS público. La URL resultante se escribe en `.ngrok-url` y, si existe
el proyecto Android hermano, en su `local.properties` para que Gradle la use:

    python scripts/tunel.py iniciar
    python scripts/tunel.py estado
    python scripts/tunel.py smoke
    python scripts/tunel.py detener

Comandos:
    iniciar   Levanta Flask (si hace falta), crea el túnel y valida /api/health.
    estado    Muestra el túnel actual y comprueba que el puerto siga oculto.
    smoke     Prueba login, RBAC, destinos, tarifa y sincronización contra la URL
              pública (o contra --base-url).
    detener   Cierra Ngrok y el Flask que haya iniciado este script.

Variables de entorno (normalmente en .env):
    NGROK_AUTHTOKEN   Token de https://dashboard.ngrok.com/get-started/your-authtoken
    NGROK_DOMAIN      Dominio reservado opcional, ej. teqruta.ngrok-free.app
    TEQRUTA_APP_DIR   Ruta del proyecto Android (default: ../TeqRuta)
    HOST              Host local de Flask (default 127.0.0.1)
    PORT              Puerto local de Flask (default 5000)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib import error, parse, request

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_APP_DIR = ROOT.parent / "TeqRuta"
RUN_DIR = ROOT / ".run"
TOOLS_DIR = ROOT / ".tools"
URL_FILE = ROOT / ".ngrok-url"
PORT_FILE = RUN_DIR / "port"
NGROK_PID = RUN_DIR / "ngrok.pid"
FLASK_PID = RUN_DIR / "flask.pid"
NGROK_LOG = RUN_DIR / "ngrok.log"
FLASK_LOG = RUN_DIR / "flask.log"
NGROK_CONFIG = RUN_DIR / "ngrok.yml"
NGROK_API = "http://127.0.0.1:4040/api/tunnels"
HEADERS = {
    "Accept": "application/json",
    "Ngrok-Skip-Browser-Warning": "1",
    "User-Agent": "TeqRuta-Tunnel/1.0",
}


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def cargar_env() -> None:
    """Carga .env sin sobrescribir variables ya definidas en el shell."""

    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_file, override=False)
        return
    except ImportError:
        pass
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def ngrok_bin() -> str | None:
    for candidate in (
        shutil.which("ngrok"),
        TOOLS_DIR / "ngrok",
        TOOLS_DIR / "ngrok.exe",
    ):
        if candidate and Path(candidate).exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def config_global_ngrok() -> Path | None:
    candidates = [
        Path.home() / ".config" / "ngrok" / "ngrok.yml",
        Path.home() / ".ngrok2" / "ngrok.yml",
    ]
    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        candidates.append(Path(local_appdata) / "ngrok" / "ngrok.yml")
    for path in candidates:
        if path.exists():
            return path
    return None


def preparar_config_ngrok() -> Path | None:
    """Crea una config temporal con el token para no exponerlo en `ps`."""

    token = os.getenv("NGROK_AUTHTOKEN", "").strip()
    if not token:
        return None

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    contenido = (
        'version: "3"\n'
        "agent:\n"
        f"  authtoken: {json.dumps(token)}\n"
        "  web_addr: 127.0.0.1:4040\n"
    )
    NGROK_CONFIG.write_text(contenido, encoding="utf-8")
    try:
        NGROK_CONFIG.chmod(0o600)
    except OSError:
        pass
    return NGROK_CONFIG


def _popen_kwargs() -> dict:
    if os.name == "nt":  # pragma: no cover - el entorno de desarrollo es Linux
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _http_json(
    url: str,
    method: str = "GET",
    payload: dict | None = None,
    headers: dict | None = None,
    timeout: float = 10.0,
) -> tuple[int, object]:
    data = None
    req_headers = {**HEADERS, **(headers or {})}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    req = request.Request(url, data=data, method=method, headers=req_headers)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return response.status, json.loads(raw) if raw.strip() else None
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {"raw": raw[:500]}
        return exc.code, body


def _leer_log(path: Path, max_lineas: int = 12) -> str:
    if not path.exists():
        return "(sin log)"
    lineas = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lineas[-max_lineas:])


def _pid_vivo(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _leer_pid(path: Path) -> int | None:
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return pid if _pid_vivo(pid) else None


def _guardar_pid(path: Path, pid: int) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{pid}\n", encoding="utf-8")


def detener_pid(path: Path) -> bool:
    pid = _leer_pid(path)
    if pid is None:
        path.unlink(missing_ok=True)
        return False

    try:
        if os.name == "nt":  # pragma: no cover
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                capture_output=True,
            )
        else:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
            for _ in range(20):
                if not _pid_vivo(pid):
                    break
                time.sleep(0.25)
            if _pid_vivo(pid):
                os.killpg(os.getpgid(pid), signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass
    path.unlink(missing_ok=True)
    return True


def puerto_configurado() -> int:
    """Puerto usado en el último `iniciar` (o PORT/.env como respaldo)."""

    try:
        return int(PORT_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return int(os.getenv("PORT", "5000"))


def esperar_health(url: str, timeout: float = 25.0) -> tuple[bool, str]:
    base = url.rstrip("/")
    fin = time.time() + timeout
    ultimo = "sin respuesta"
    while time.time() < fin:
        try:
            status, body = _http_json(f"{base}/api/health", timeout=4)
            if status == 200 and isinstance(body, dict) and body.get("status") == "ok":
                return True, "ok"
            ultimo = f"HTTP {status}: {body}"
        except Exception as exc:  # noqa: BLE001 - se reintenta y se reporta
            ultimo = str(exc)
        time.sleep(0.6)
    return False, ultimo


def puerto_local_activo(host: str, port: int) -> bool:
    ok, _ = esperar_health(f"http://{host}:{port}", timeout=2)
    return ok


def iniciar_flask(host: str, port: int) -> subprocess.Popen | None:
    if puerto_local_activo(host, port):
        print(f"[tunel] Flask ya responde en http://{host}:{port}")
        return None

    python = ROOT / ".venv" / "bin" / "python"
    if not python.exists():
        python = Path(sys.executable)

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "HOST": host,
            "PORT": str(port),
            "FLASK_DEBUG": "false",  # sin reloader: un solo proceso y un solo PID
            "PYTHONUNBUFFERED": "1",
        }
    )
    with FLASK_LOG.open("w", encoding="utf-8") as log:
        proceso = subprocess.Popen(
            [str(python), "run.py"],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            **_popen_kwargs(),
        )
    _guardar_pid(FLASK_PID, proceso.pid)

    ok, detalle = esperar_health(f"http://{host}:{port}", timeout=25)
    if not ok:
        detener_pid(FLASK_PID)
        raise RuntimeError(
            f"Flask no levantó en http://{host}:{port} ({detalle}).\n"
            f"--- {FLASK_LOG} ---\n{_leer_log(FLASK_LOG)}"
        )
    print(f"[tunel] Flask escuchando en http://{host}:{port} (solo local)")
    return proceso


def leer_url_publica(timeout: float = 2.0) -> str | None:
    try:
        status, body = _http_json(NGROK_API, timeout=timeout)
    except Exception:  # noqa: BLE001 - el agente aún no abre la API
        return None
    if status != 200 or not isinstance(body, dict):
        return None
    for tunel in body.get("tunnels", []):
        public_url = str(tunel.get("public_url") or "")
        if public_url.startswith("https://"):
            return public_url.rstrip("/")
    return None


def iniciar_ngrok(port: int, dominio: str = "") -> subprocess.Popen:
    binario = ngrok_bin()
    if not binario:
        raise RuntimeError(
            "Ngrok no está instalado. Ejecuta `bash scripts/instalar_ngrok.sh` "
            "o descárgalo desde https://ngrok.com/download."
        )

    config = preparar_config_ngrok()
    if config is None and config_global_ngrok() is None:
        raise RuntimeError(
            "Falta NGROK_AUTHTOKEN. Crea una cuenta gratuita, copia tu token en "
            "`.env` (NGROK_AUTHTOKEN=...) o ejecuta `ngrok config add-authtoken ...`."
        )

    comando = [binario]
    if config is not None:
        comando.extend(["--config", str(config)])
    comando.extend(
        [
            "http",
            str(port),
            "--log=stdout",
            "--log-format=json",
            "--log-level=info",
        ]
    )
    if dominio:
        dominio = dominio.removeprefix("https://").removeprefix("http://").strip("/")
        comando.extend(["--url", f"https://{dominio}"])

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    with NGROK_LOG.open("w", encoding="utf-8") as log:
        proceso = subprocess.Popen(
            comando,
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            **_popen_kwargs(),
        )
    _guardar_pid(NGROK_PID, proceso.pid)

    fin = time.time() + 30
    while time.time() < fin:
        if proceso.poll() is not None:
            raise RuntimeError(
                "Ngrok terminó antes de crear el túnel.\n"
                f"--- {NGROK_LOG} ---\n{_leer_log(NGROK_LOG, 20)}"
            )
        url = leer_url_publica()
        if url:
            return proceso
        time.sleep(0.7)

    detener_pid(NGROK_PID)
    raise RuntimeError(
        "Ngrok no publicó una URL HTTPS a tiempo.\n"
        f"--- {NGROK_LOG} ---\n{_leer_log(NGROK_LOG, 20)}"
    )


def ruta_app_android() -> Path:
    """Ruta del proyecto Android; `TEQRUTA_APP_DIR` permite otro checkout."""

    valor = os.getenv("TEQRUTA_APP_DIR", "").strip()
    if not valor:
        return DEFAULT_APP_DIR
    ruta = Path(valor).expanduser()
    if not ruta.is_absolute():
        ruta = (ROOT.parent / ruta).resolve()
    return ruta


def actualizar_local_properties(url: str) -> Path | None:
    """Actualiza solo la propiedad de la API, preservando sdk.dir y comentarios."""

    app_dir = ruta_app_android()
    if not app_dir.exists():
        return None
    local_props = app_dir / "local.properties"
    lineas: list[str] = []
    if local_props.exists():
        lineas = local_props.read_text(encoding="utf-8").splitlines()

    nueva = f"teqrutaApiBaseUrl={url.rstrip('/')}/"
    salida: list[str] = []
    reemplazada = False
    for linea in lineas:
        if re.match(r"\s*teqrutaApiBaseUrl\s*=", linea):
            if not reemplazada:
                salida.append(nueva)
                reemplazada = True
        else:
            salida.append(linea)
    if not reemplazada:
        if salida and salida[-1].strip():
            salida.append("")
        salida.append(nueva)
    local_props.write_text("\n".join(salida) + "\n", encoding="utf-8")
    return local_props


def verificar_puerto_oculto(port: int) -> tuple[bool | None, str]:
    """Comprueba si el puerto responde desde alguna IP no-loopback del equipo."""

    ips: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                ips.add(ip)
    except OSError:
        pass
    try:
        sonda = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sonda.settimeout(0.2)
        sonda.connect(("8.8.8.8", 80))
        ips.add(sonda.getsockname()[0])
        sonda.close()
    except OSError:
        pass
    ips.discard("0.0.0.0")

    if not ips:
        return None, "no se pudo determinar una IP de LAN"

    alcanzables = []
    for ip in sorted(ips):
        try:
            with socket.create_connection((ip, port), timeout=0.5):
                alcanzables.append(ip)
        except OSError:
            pass
    if alcanzables:
        return False, f"puerto {port} accesible en {', '.join(alcanzables)}"
    return True, f"puerto {port} solo responde en loopback"


# ---------------------------------------------------------------------------
# Smoke test end-to-end
# ---------------------------------------------------------------------------


def _resultado(nombre: str, ok: bool, detalle: str) -> dict:
    return {"nombre": nombre, "ok": ok, "detalle": detalle}


def ejecutar_smoke(base_url: str, incluir_limpieza: bool = True) -> list[dict]:
    base = base_url.rstrip("/")
    resultados: list[dict] = []

    def check(nombre: str, fn) -> None:
        try:
            detalle = fn()
            resultados.append(_resultado(nombre, True, str(detalle or "ok")))
        except Exception as exc:  # noqa: BLE001 - cada check reporta su error
            resultados.append(_resultado(nombre, False, str(exc)))

    def url(path: str) -> str:
        return f"{base}{path}"

    def body_data(body: object) -> object:
        if isinstance(body, dict) and "data" in body:
            return body["data"]
        return body

    estado: dict[str, object] = {}

    def health() -> str:
        status, body = _http_json(url("/api/health"))
        if status != 200 or not isinstance(body, dict) or body.get("status") != "ok":
            raise AssertionError(f"HTTP {status}: {body}")
        return f"HTTP {status} · database={body.get('database')}"

    def indice() -> str:
        status, body = _http_json(url("/"))
        if status != 200 or not isinstance(body, dict):
            raise AssertionError(f"HTTP {status}: {body}")
        if "TeqRuta" not in str(body.get("nombre", "")):
            raise AssertionError(f"respuesta inesperada: {body}")
        return "información del API"

    def login() -> str:
        status, body = _http_json(
            url("/api/auth/login"),
            method="POST",
            payload={"email": "tecnico@teqmed.cl", "password": "tecnico123"},
        )
        data = body_data(body)
        if status != 200 or not isinstance(data, dict) or not data.get("access_token"):
            raise AssertionError(f"HTTP {status}: {body}")
        estado["token"] = data["access_token"]
        return f"JWT emitido para {data.get('user', {}).get('email', 'técnico')}"

    def auth_headers() -> dict:
        token = estado.get("token")
        if not token:
            raise AssertionError("no hay token de login")
        return {"Authorization": f"Bearer {token}"}

    def me() -> str:
        status, body = _http_json(url("/api/auth/me"), headers=auth_headers())
        data = body_data(body)
        if status != 200 or not isinstance(data, dict):
            raise AssertionError(f"HTTP {status}: {body}")
        return f"perfil {data.get('email')} · rol={data.get('rol')}"

    def config_publica() -> str:
        status, body = _http_json(url("/api/auth/config"))
        data = body_data(body)
        if status != 200 or not isinstance(data, dict):
            raise AssertionError(f"HTTP {status}: {body}")
        return f"umbral={data.get('desviacionUmbralPct')}% · combustible={data.get('combustibleReferencia')}"

    def destinos() -> str:
        status, body = _http_json(
            url("/api/mantenedores/destinos"), headers=auth_headers()
        )
        data = body_data(body)
        if status != 200 or not isinstance(data, list):
            raise AssertionError(f"HTTP {status}: {body}")
        if not data:
            raise AssertionError("el catálogo de destinos está vacío")
        return f"{len(data)} destinos"

    def tarifa() -> str:
        status, body = _http_json(
            url("/api/mantenedores/tarifas/vigente"), headers=auth_headers()
        )
        data = body_data(body)
        if status != 200 or not isinstance(data, dict):
            raise AssertionError(f"HTTP {status}: {body}")
        precio = data.get("precioLitro") or data.get("precio_litro")
        if precio is None:
            raise AssertionError(f"sin precioLitro: {body}")
        return f"{precio} CLP/L · origen={data.get('origen') or data.get('fuente')}"

    def sync() -> str:
        ahora = int(time.time() * 1000)
        viaje_uuid = str(uuid.uuid4())
        estado["viaje_uuid"] = viaje_uuid
        payload = {
            "viajes": [
                {
                    "uuid": viaje_uuid,
                    "rutaSeleccionada": "Smoke test túnel público",
                    "odometroInicio": 41000,
                    "odometroFin": 41012,
                    "fotoOdometroInicio": "smoke_inicio.jpg",
                    "fotoOdometroFin": "smoke_fin.jpg",
                    "totalMontoPeajes": 0,
                    "fotosPeajes": "",
                    "horaInicio": ahora - 3_600_000,
                    "horaFin": ahora,
                    "eventosExtra": "verificación automática de ngrok",
                    "latitudInicio": -36.826,
                    "longitudInicio": -73.049,
                    "latitudFin": -36.830,
                    "longitudFin": -73.055,
                    "tecnicoEmail": "tecnico@teqmed.cl",
                    "vehiculoPatente": "HK-8932",
                    "sincronizado": False,
                    "estadoAprobacion": "PENDIENTE",
                }
            ]
        }
        status, body = _http_json(
            url("/api/viajes/sync"),
            method="POST",
            payload=payload,
            headers=auth_headers(),
        )
        data = body_data(body)
        if status not in (200, 207) or not isinstance(data, dict):
            raise AssertionError(f"HTTP {status}: {body}")
        resumen = data.get("resumen") or {}
        aceptados = int(resumen.get("insertados") or 0) + int(
            resumen.get("duplicados") or 0
        )
        if aceptados != 1:
            raise AssertionError(f"no aceptado: {body}")
        estado["admin_token"] = None
        return f"UUID {viaje_uuid[:8]}… sincronizado (HTTP {status})"

    def listado() -> str:
        status, body = _http_json(
            url("/api/viajes?page=1&per_page=5"), headers=auth_headers()
        )
        data = body_data(body)
        if status != 200 or not isinstance(data, list):
            raise AssertionError(f"HTTP {status}: {body}")
        return f"{len(data)} viajes visibles"

    def rbac() -> str:
        status, body = _http_json(
            url("/api/reportes/mensual"), headers=auth_headers()
        )
        if status != 403:
            raise AssertionError(f"se esperaba 403 para técnico, llegó HTTP {status}: {body}")
        return "técnico bloqueado en reportes (403)"

    def url_sin_puerto() -> str:
        partes = parse.urlsplit(base)
        if partes.scheme == "https" and partes.port not in (None, 443):
            raise AssertionError(f"la URL pública expone el puerto {partes.port}")
        if partes.scheme == "http":
            return "URL local de prueba (sin túnel)"
        return f"host={partes.hostname} · puerto implícito 443"

    check("Salud del API", health)
    check("Información pública", indice)
    check("Login JWT", login)
    check("Perfil autenticado", me)
    check("Configuración pública", config_publica)
    check("Catálogo de destinos", destinos)
    check("Tarifa vigente", tarifa)
    check("Sincronización offline", sync)
    check("Listado de viajes", listado)
    check("RBAC de reportes", rbac)
    check("URL pública sin puerto interno", url_sin_puerto)

    if incluir_limpieza:
        def limpieza() -> str:
            viaje_uuid = estado.get("viaje_uuid")
            if not viaje_uuid:
                return "nada que limpiar"
            status, body = _http_json(
                url("/api/auth/login"),
                method="POST",
                payload={"email": "admin@teqmed.cl", "password": "admin123"},
            )
            data = body_data(body)
            if status != 200 or not isinstance(data, dict) or not data.get("access_token"):
                raise AssertionError(f"login admin HTTP {status}: {body}")
            status, body = _http_json(
                url(f"/api/viajes/{viaje_uuid}"),
                method="DELETE",
                headers={"Authorization": f"Bearer {data['access_token']}"},
            )
            if status not in (200, 404):
                raise AssertionError(f"HTTP {status}: {body}")
            return "viaje de prueba eliminado"

        check("Limpieza de datos de prueba", limpieza)

    return resultados


def imprimir_resultados(resultados: list[dict]) -> None:
    for item in resultados:
        marca = "OK   " if item["ok"] else "FALLA"
        print(f"  [{marca}] {item['nombre']}: {item['detalle']}")


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------


def cmd_iniciar(args: argparse.Namespace) -> int:
    cargar_env()
    if args.app_dir:
        os.environ["TEQRUTA_APP_DIR"] = args.app_dir
    host = os.getenv("HOST", "127.0.0.1")
    port = int(args.puerto or os.getenv("PORT", "5000"))
    dominio = (args.dominio or os.getenv("NGROK_DOMAIN", "")).strip()

    if not ngrok_bin():
        print(
            "[tunel] Ngrok no está instalado.\n"
            "        Ejecuta: bash scripts/instalar_ngrok.sh\n"
            "        o descárgalo desde https://ngrok.com/download",
            file=sys.stderr,
        )
        return 1

    if not os.getenv("NGROK_AUTHTOKEN", "").strip() and config_global_ngrok() is None:
        print(
            "[tunel] Falta NGROK_AUTHTOKEN.\n"
            "        1) Crea una cuenta gratuita en https://dashboard.ngrok.com/signup\n"
            "        2) Copia el token de https://dashboard.ngrok.com/get-started/your-authtoken\n"
            "        3) Agrégalo a .env como NGROK_AUTHTOKEN=...\n"
            "        También puedes ejecutar: ngrok config add-authtoken <token>",
            file=sys.stderr,
        )
        return 1

    # Evita dos agentes peleando por la API local :4040.
    if _leer_pid(NGROK_PID):
        print("[tunel] Cerrando túnel anterior…")
        detener_pid(NGROK_PID)

    try:
        iniciar_flask(host, port)
        print("[tunel] Creando túnel HTTPS con Ngrok…")
        iniciar_ngrok(port, dominio)
        url_publica = leer_url_publica(timeout=5)
        if not url_publica:
            raise RuntimeError("Ngrok no devolvió una URL pública.")

        ok, detalle = esperar_health(url_publica, timeout=30)
        if not ok:
            raise RuntimeError(f"la URL pública no responde /api/health: {detalle}")

        URL_FILE.write_text(url_publica + "\n", encoding="utf-8")
        PORT_FILE.write_text(f"{port}\n", encoding="utf-8")
        local_props = actualizar_local_properties(url_publica)
        oculto, detalle_puerto = verificar_puerto_oculto(port)

        print()
        print("=" * 68)
        print("  TeqRuta API publicada con Ngrok")
        print("=" * 68)
        print(f"  URL pública : {url_publica}")
        print(f"  Destino     : http://{host}:{port} (solo loopback)")
        print(f"  Health      : {url_publica}/api/health")
        print(f"  Puerto      : {detalle_puerto}")
        if local_props:
            print(f"  Android     : {local_props}")
        else:
            print(f"  Android     : no se encontró {ruta_app_android()}")
            print("                usa TEQRUTA_APP_DIR=/ruta/a/TeqRuta o --app-dir")
        print()
        print("  Prueba E2E  : python scripts/tunel.py smoke")
        print("  Detener     : python scripts/tunel.py detener")
        print("=" * 68)
        return 0 if oculto is not False else 2
    except Exception as exc:  # noqa: BLE001 - se reporta al usuario
        print(f"[tunel] ERROR: {exc}", file=sys.stderr)
        detener_pid(NGROK_PID)
        return 1


def cmd_detener(_: argparse.Namespace) -> int:
    ngrok_detenido = detener_pid(NGROK_PID)
    flask_detenido = detener_pid(FLASK_PID)
    URL_FILE.unlink(missing_ok=True)
    PORT_FILE.unlink(missing_ok=True)
    print(
        f"[tunel] Ngrok {'detenido' if ngrok_detenido else 'no estaba activo'}; "
        f"Flask {'detenido' if flask_detenido else 'no fue iniciado por este script'}."
    )
    return 0


def cmd_estado(_: argparse.Namespace) -> int:
    cargar_env()
    port = puerto_configurado()
    url_publica = URL_FILE.read_text(encoding="utf-8").strip() if URL_FILE.exists() else ""
    ngrok_pid = _leer_pid(NGROK_PID)
    flask_pid = _leer_pid(FLASK_PID)
    print(f"  Ngrok PID   : {ngrok_pid or 'no activo'}")
    print(f"  Flask PID   : {flask_pid or 'no iniciado por el script'}")
    print(f"  URL pública : {url_publica or 'sin URL registrada'}")
    print(f"  Puerto      : {verificar_puerto_oculto(port)[1]}")
    if not url_publica:
        return 1
    ok, detalle = esperar_health(url_publica, timeout=6)
    print(f"  Health      : {'OK' if ok else 'FALLA'} ({detalle})")
    return 0 if ok else 1


def cmd_smoke(args: argparse.Namespace) -> int:
    cargar_env()
    base = args.base_url
    if not base:
        if URL_FILE.exists():
            base = URL_FILE.read_text(encoding="utf-8").strip()
        else:
            base = f"http://127.0.0.1:{puerto_configurado()}"
    print(f"[smoke] Objetivo: {base}")
    resultados = ejecutar_smoke(base)
    imprimir_resultados(resultados)
    fallos = [item for item in resultados if not item["ok"]]
    print()
    if fallos:
        print(f"[smoke] {len(fallos)} prueba(s) fallaron.")
        return 1
    print(f"[smoke] {len(resultados)} pruebas OK. La API está funcional.")
    return 0


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Publica TeqRuta API con Ngrok sin exponer el puerto interno."
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    iniciar = sub.add_parser("iniciar", help="levanta Flask y el túnel HTTPS")
    iniciar.add_argument("--puerto", type=int, help="puerto local de Flask (default PORT/5000)")
    iniciar.add_argument("--dominio", help="dominio reservado de Ngrok, ej. teqruta.ngrok-free.app")
    iniciar.add_argument(
        "--app-dir",
        help="ruta del proyecto Android si no está en ../TeqRuta (o usa TEQRUTA_APP_DIR)",
    )
    iniciar.set_defaults(func=cmd_iniciar)

    estado = sub.add_parser("estado", help="muestra el estado del túnel y del puerto")
    estado.set_defaults(func=cmd_estado)

    smoke = sub.add_parser("smoke", help="prueba end-to-end contra la URL pública")
    smoke.add_argument("--base-url", help="URL a probar (default: .ngrok-url o localhost)")
    smoke.set_defaults(func=cmd_smoke)

    detener = sub.add_parser("detener", help="cierra Ngrok y Flask")
    detener.set_defaults(func=cmd_detener)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
