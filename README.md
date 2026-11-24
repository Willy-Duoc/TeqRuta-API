# TeqRuta API

API REST en **Flask** para la app Android **TeqRuta** (Kotlin + Jetpack Compose) del caso
**TEQMED SpA** (DSY1105 – Duoc UC). Centraliza autenticación JWT, sincronización
offline-first de viajes, cálculo de costos, aprobación por jefatura, reportes,
mantenedores de flota/destinos/tarifas y tarifas de combustible.

Se publica al dispositivo mediante **Ngrok**: Flask queda escuchando solo en
`127.0.0.1:5000` y el túnel entrega una URL **HTTPS** sin exponer el puerto interno.

- **Repositorio de esta API:** <https://github.com/Willy-Duoc/TeqRuta-API>
- **Repositorio de la app:** <https://github.com/hanspwd/TeqRuta>
- **Documento de integración de la app:** [`TeqRuta/docs/PREPARACION_API.md`](https://github.com/hanspwd/TeqRuta/blob/master/docs/PREPARACION_API.md)

---

## 1. Inicio rápido: de un clon a la app funcionando

### 1.1 Estructura recomendada

Clona ambos repositorios en la misma carpeta, manteniendo los nombres:

```text
teqruta/
├── TeqRuta-API/   # backend Flask
└── TeqRuta/       # app Android
```

```bash
mkdir teqruta && cd teqruta
git clone https://github.com/Willy-Duoc/TeqRuta-API.git
git clone https://github.com/hanspwd/TeqRuta.git
```

### 1.2 Preparar la API

Requisitos: **Python 3.10+**, `make`, `curl`, `tar`/`unzip` y una cuenta gratuita de
Ngrok. En Windows se recomienda **WSL**.

```bash
cd TeqRuta-API
make setup
```

`make setup`:

1. crea `.venv` e instala `requirements-dev.txt`;
2. descarga el agente Ngrok en `.tools/` si no existe uno en el sistema;
3. crea `.env` desde `.env.example` con `SECRET_KEY` y `JWT_SECRET_KEY` aleatorios;
4. si definiste `NGROK_AUTHTOKEN` en el entorno, lo copia al `.env`.

Obtén tu token en <https://dashboard.ngrok.com/get-started/your-authtoken> y edita
`.env`:

```dotenv
NGROK_AUTHTOKEN=tu_token_real
# Opcional pero muy recomendado para que la URL no cambie:
NGROK_DOMAIN=tu-dominio.ngrok-free.dev
```

También puedes evitar la edición manual:

```bash
NGROK_AUTHTOKEN=tu_token_real make publicar
```

### 1.3 Publicar y verificar

```bash
make publicar
make smoke
make estado
```

`make publicar` levanta Flask en loopback, crea el túnel, valida `/api/health`, guarda
la URL pública y actualiza `../TeqRuta/local.properties` para que Gradle la embeba.

Salida esperada:

```text
====================================================================
  TeqRuta API publicada con Ngrok
====================================================================
  URL pública : https://mi-dominio.ngrok-free.dev
  Destino     : http://127.0.0.1:5000 (solo loopback)
  Health      : https://mi-dominio.ngrok-free.dev/api/health
  Puerto      : puerto 5000 solo responde en loopback
  Android     : /ruta/teqruta/TeqRuta/local.properties
====================================================================
```

### 1.4 Abrir la app

```bash
cd ../TeqRuta
./gradlew :app:printApiBaseUrl    # debe mostrar la URL HTTPS del túnel
./gradlew :app:installDebug       # o abrir el proyecto en Android Studio
```

Con el emulador o dispositivo listo, inicia sesión con `tecnico@teqmed.cl` /
`tecnico123`. Si la app está en otra ruta, publica con:

```bash
TEQRUTA_APP_DIR=/ruta/a/TeqRuta make publicar
```

### 1.5 Detener

```bash
make detener
```

Cierra Ngrok y el Flask iniciado por el script. No borra la base de datos ni el `.env`.

---

## 2. Arquitectura

| Capa | Tecnología | Responsabilidad |
|---|---|---|
| Cliente | Android Kotlin, Compose, MVVM, Room | Registro offline, cámara, cola de pendientes |
| Túnel | Ngrok | HTTPS público hacia `127.0.0.1:5000` |
| API | Flask 3 + Blueprints | Auth, viajes, reportes y mantenedores |
| Persistencia | SQLAlchemy (SQLite/PostgreSQL) | Usuarios, flota, destinos, tarifas, viajes |
| Seguridad | JWT + Bcrypt + RBAC | Token por petición y permisos por rol |
| Externo | Precio de combustible (CNE/AhorraHogar) | Tarifa diaria con *fallback* |

### Blueprints y módulos

```text
app/
├── api.py               # blueprint raíz, / y /api/health
├── auth/                # /api/auth
├── viajes/              # /api/viajes
├── reportes/            # /api/reportes
├── mantenedores/        # /api/mantenedores
├── services/            # costos + precio de combustible
├── models.py            # entidades SQLAlchemy
├── serializers.py       # JSON camelCase para Kotlin
├── security.py          # JWT, Bcrypt y decoradores RBAC
├── seed.py              # datos demo
├── config.py            # configuración por entorno
└── errors.py            # respuestas JSON uniformes
```

### Roles

| Rol | Permisos |
|---|---|
| `tecnico` | Sincroniza y consulta sus viajes, destinos y tarifa |
| `jefe` | Ve todos los viajes, aprueba u observa, revisa desviaciones |
| `gerencia` | Reportes financieros y exportación CSV |
| `admin` | ABM de flota, destinos, usuarios y tarifas; también aprueba |

Rutas públicas: `/`, `/api/health`, `/api/auth/login`, `/api/auth/register` y
`/api/auth/config`. El resto exige:

```http
Authorization: Bearer <access_token>
```

---

## 3. Estructura del repositorio

```text
TeqRuta-API/
├── app/
│   ├── auth/                # login, perfil y config pública
│   ├── viajes/              # sync, CRUD y aprobación
│   ├── reportes/            # métricas, desviaciones y CSV
│   ├── mantenedores/        # vehículos, destinos, usuarios y tarifas
│   ├── services/            # cálculo de costos y combustible
│   ├── api.py               # health e índice
│   ├── config.py            # variables de entorno
│   ├── models.py            # SQLAlchemy
│   ├── security.py          # JWT/Bcrypt/RBAC
│   ├── seed.py              # datos demo
│   └── serializers.py
├── scripts/
│   ├── tunel.py             # orquesta Flask + Ngrok + URL de la app
│   ├── instalar_ngrok.sh    # descarga el agente en .tools/
│   └── preparar_env.py      # genera .env con secretos aleatorios
├── tests/                   # pytest (sin red)
├── Makefile                 # setup, test, publicar, smoke, detener
├── run.py                   # servidor de desarrollo
├── wsgi.py                  # entrada para Gunicorn
├── requirements.txt
├── requirements-dev.txt
└── .env.example
```

Archivos **no versionados**: `.env`, `.venv/`, `.tools/`, `.run/`, `.ngrok-url`,
`instance/`, bases SQLite, cachés y logs.

---

## 4. Requisitos

- Python **3.10 o superior** (probado con 3.14).
- `pip`, `venv`, `make`, `curl`, `tar`/`unzip`.
- Cuenta gratuita de [Ngrok](https://ngrok.com) y su authtoken.
- Opcional: Android Studio + SDK 37 para la app.
- Opcional: PostgreSQL y `psycopg[binary]` para producción.
- Sistema recomendado: Linux, macOS o WSL. El orquestador usa procesos POSIX; en
  Windows nativo ejecuta los comandos dentro de WSL.

---

## 5. Configuración

### 5.1 Crear `.env`

```bash
make setup            # recomendado: crea .env con secretos aleatorios
# o manualmente:
cp .env.example .env
```

`.env` está ignorado por Git y `make setup` le asigna permisos `600`. **Nunca** lo
subas al repositorio.

### 5.2 Variables principales

| Variable | Default | Descripción |
|---|---|---|
| `HOST` | `127.0.0.1` | Interfaz de Flask; loopback para que Ngrok sea la única salida |
| `PORT` | `5000` | Puerto local de Flask |
| `FLASK_DEBUG` | `false` | En `.env.example`; `tunel.py` siempre lo fuerza a `false` |
| `TRUST_PROXY` | `true` en loopback | Usa `X-Forwarded-Proto/Host/For` de Ngrok |
| `SECRET_KEY` | generado por setup | Clave de Flask |
| `JWT_SECRET_KEY` | generado por setup | Firma de JWT (mínimo 32 bytes) |
| `JWT_EXPIRE_HOURS` | `8` | Vigencia del token |
| `DATABASE_URL` | `sqlite:///teqruta.db` | SQLAlchemy; SQLite por defecto |
| `SEED_DEMO_USERS` | `true` | Carga usuarios/flota/destinos demo |
| `CORS_ORIGINS` | `*` | Orígenes permitidos; restringir en producción |
| `PUBLIC_BASE_URL` | vacío | URL canónica opcional para enlaces |
| `NGROK_AUTHTOKEN` | vacío | Token de Ngrok (obligatorio para publicar) |
| `NGROK_DOMAIN` | vacío | Dominio estático de Ngrok (recomendado) |
| `TEQRUTA_APP_DIR` | `../TeqRuta` | Ruta del proyecto Android |
| `FUEL_PRICE_URL` | AhorraHogar/CNE | Fuente de precios de combustible |
| `FUEL_REGION_CODE` | `8` | Región (8 = Biobío) |
| `FUEL_PRICE_CACHE_HOURS` | `24` | Refresco máximo de tarifa |
| `FUEL_DEFAULT_PRICE` | `1597` | Precio de respaldo |
| `DEFAULT_RENDIMIENTO_KM_L` | `10` | Rendimiento por defecto |
| `DESVIACION_UMBRAL_PCT` | `10` | Umbral de alerta de desviación |

La base SQLite se crea en `instance/` al iniciar. Para reiniciar datos demo, detén la
API y elimina `instance/teqruta.db`.

---

## 6. Publicación con Ngrok

### 6.1 Comandos

```bash
make setup       # una vez: venv, dependencias, Ngrok y .env
make publicar    # Flask loopback + túnel + health + URL en local.properties
make estado      # URL, PIDs, health y comprobación del puerto oculto
make smoke       # 12 verificaciones E2E contra la URL pública
make smoke-local # 12 verificaciones contra http://127.0.0.1:5000
make detener     # cierra Ngrok y Flask
```

El script `scripts/tunel.py`:

1. carga `.env` y valida el token;
2. arranca Flask con `HOST=127.0.0.1` y `FLASK_DEBUG=false`;
3. crea una configuración temporal de Ngrok con permisos `600` para no exponer el
   token en `ps`;
4. obtiene la URL HTTPS y espera `GET /api/health`;
5. guarda `.ngrok-url` y el puerto usado en `.run/`;
6. escribe `teqrutaApiBaseUrl` en `local.properties` de la app;
7. comprueba que el puerto no responda desde la IP de LAN.

### 6.2 URL fija vs. aleatoria

El plan gratuito puede entregar una URL distinta en cada inicio. Para un despliegue
estable:

1. Reserva un dominio estático en Ngrok.
2. Define `NGROK_DOMAIN=tu-dominio.ngrok-free.dev` en `.env`.
3. Publica con `make publicar`.

Con dominio fijo, el APK compilado sigue funcionando entre reinicios. Sin dominio fijo,
recompila la app cada vez que cambie la URL.

### 6.3 Modo manual

```bash
# Terminal 1
HOST=127.0.0.1 python run.py

# Terminal 2
ngrok http 5000
# o con dominio reservado:
ngrok http --url=https://tu-dominio.ngrok-free.dev 5000
```

La app debe apuntar a la URL HTTPS resultante (`local.properties`,
`TEQRUTA_API_BASE_URL` o `-PteqrutaApiBaseUrl`).

### 6.4 Producción con Gunicorn

```bash
gunicorn --bind 127.0.0.1:5000 --workers 2 wsgi:app
```

Mantén Gunicorn en loopback detrás de Ngrok, Nginx o un reverse proxy con TLS. Si
cambias a PostgreSQL:

```bash
pip install "psycopg[binary]"
# .env
DATABASE_URL=postgresql+psycopg://usuario:clave@host:5432/teqruta
```

---

## 7. Conexión con la app Android

La app resuelve la URL en este orden:

1. `-PteqrutaApiBaseUrl=https://.../`
2. variable `TEQRUTA_API_BASE_URL`
3. `local.properties` → `teqrutaApiBaseUrl=...`
4. fallback `http://10.0.2.2:5000/` (solo emulador, API Flask en el host)

Comprueba la URL embebida:

```bash
cd ../TeqRuta
./gradlew :app:printApiBaseUrl
```

Para un teléfono físico usa siempre la URL HTTPS de Ngrok. El cliente OkHttp ya envía
`Ngrok-Skip-Browser-Warning: 1`, `Accept: application/json` y el `Bearer` cuando hay
sesión. La app no necesita configuración de red adicional.

Pruebas de la app:

```bash
cd ../TeqRuta
./gradlew :app:testDebugUnitTest
./gradlew :app:assembleDebug
```

La prueba instrumentada contra el túnel se describe en el
[README de la app](https://github.com/hanspwd/TeqRuta#7-compilar-probar-e-instalar).

### Flujo offline-first

1. Sin señal, Room guarda el viaje con `sincronizado = false` y un UUID.
2. `SyncWorker` o el ViewModel detectan conexión.
3. `POST /api/viajes/sync` envía el lote con `tecnicoEmail` y `vehiculoPatente`.
4. El servidor inserta nuevos, ignora duplicados por UUID y rechaza inválidos.
5. La app marca como sincronizados solo los UUID aceptados.

---

## 8. Usuarios demo

Con `SEED_DEMO_USERS=true`:

| Email | Contraseña | Rol |
|---|---|---|
| `tecnico@teqmed.cl` | `tecnico123` | tecnico |
| `jefe@teqmed.cl` | `jefe123` | jefe |
| `gerencia@teqmed.cl` | `gerencia123` | gerencia |
| `admin@teqmed.cl` | `admin123` | admin |

```bash
curl -X POST http://127.0.0.1:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"tecnico@teqmed.cl","password":"tecnico123"}'
```

```json
{
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "Bearer",
    "expires_in": 28800,
    "user": {
      "email": "tecnico@teqmed.cl",
      "nombre": "Hans Morales",
      "rol": "tecnico",
      "cargo": "Técnico de Servicio",
      "vehiculoAsignado": "HK-8932",
      "activo": true
    }
  },
  "message": "Inicio de sesión correcto"
}
```

---

## 9. Endpoints

### Autenticación

| Método | Ruta | Acceso | Descripción |
|---|---|---|---|
| POST | `/api/auth/login` | público | JWT + perfil |
| GET | `/api/auth/me` | autenticado | Perfil del token |
| POST | `/api/auth/logout` | autenticado | Cierre stateless |
| POST | `/api/auth/register` | público | Registro de técnicos |
| GET | `/api/auth/config` | público | Umbral y combustible de referencia |

### Viajes

| Método | Ruta | Acceso | Descripción |
|---|---|---|---|
| POST | `/api/viajes/sync` | autenticado | Sincronización idempotente por UUID |
| POST | `/api/viajes` | autenticado | Crear viaje |
| GET | `/api/viajes` | autenticado | Listar con filtros y paginación |
| GET | `/api/viajes/<uuid>` | autenticado | Detalle |
| PATCH | `/api/viajes/<uuid>/aprobacion` | jefe/admin | Aprobar u observar |
| DELETE | `/api/viajes/<uuid>` | admin | Eliminar |

Filtros: `estado`, `cliente`, `tecnicoEmail`, `vehiculoPatente`, `desde`, `hasta`,
`soloAlertas`, `page`, `per_page`.

### Reportes

| Método | Ruta | Acceso | Descripción |
|---|---|---|---|
| GET | `/api/reportes/mensual` | jefe/gerencia/admin | Totales y desgloses |
| GET | `/api/reportes/mensual.csv` | jefe/gerencia/admin | CSV con BOM para Excel |
| GET | `/api/reportes/desviaciones` | jefe/gerencia/admin | Viajes sobre el umbral |

Filtros: `anio`, `mes`, `cliente`, `desde`, `hasta`.

### Mantenedores

| Método | Ruta | Acceso | Descripción |
|---|---|---|---|
| GET/POST | `/api/mantenedores/vehiculos` | lectura: autenticado / escritura: admin | Flota |
| GET/PUT/DELETE | `/api/mantenedores/vehiculos/<patente>` | admin | Detalle/edición |
| GET/POST | `/api/mantenedores/destinos` | lectura: autenticado / escritura: admin | Clínicas |
| GET/PUT/DELETE | `/api/mantenedores/destinos/<id>` | admin | Detalle/edición |
| GET/POST | `/api/mantenedores/usuarios` | admin | Usuarios |
| GET/PUT/DELETE | `/api/mantenedores/usuarios/<id>` | admin | Detalle/edición |
| GET | `/api/mantenedores/tarifas` | autenticado | Historial |
| GET | `/api/mantenedores/tarifas/vigente?combustible=93` | autenticado | Tarifa activa |
| PUT | `/api/mantenedores/tarifas/93` | admin | Sobreescritura manual |
| POST | `/api/mantenedores/tarifas/actualizar` | admin | Refresco externo |

---

## 10. Contrato de sincronización

```http
POST /api/viajes/sync
Content-Type: application/json
Authorization: Bearer <JWT>
```

```json
{
  "viajes": [
    {
      "uuid": "11111111-1111-4111-8111-111111111111",
      "rutaSeleccionada": "Sede Concepción - Clínica RedSalud Concepción",
      "odometroInicio": 1000,
      "odometroFin": 1023,
      "fotoOdometroInicio": "odometro_inicio.jpg",
      "fotoOdometroFin": "odometro_fin.jpg",
      "totalMontoPeajes": 500,
      "fotosPeajes": "1 comprobante(s)",
      "horaInicio": 1763500000000,
      "horaFin": 1763503600000,
      "eventosExtra": "Tráfico normal",
      "latitudInicio": -36.82,
      "longitudInicio": -73.06,
      "latitudFin": -36.83,
      "longitudFin": -73.05,
      "tecnicoEmail": "tecnico@teqmed.cl",
      "vehiculoPatente": "HK-8932",
      "sincronizado": false,
      "estadoAprobacion": "PENDIENTE"
    }
  ]
}
```

Respuesta:

```json
{
  "data": {
    "resumen": { "recibidos": 1, "insertados": 1, "duplicados": 0, "rechazados": 0 },
    "rechazados": [],
    "viajes": [{ "uuid": "1111...", "estado": "insertado" }]
  },
  "message": "Sincronización finalizada"
}
```

Si hay rechazos por viaje se responde `207 Multi-Status` y `rechazados` incluye
`indice` y `errores`. Los duplicados por UUID se consideran aceptados para mantener la
idempotencia.

### Aprobación

```json
PATCH /api/viajes/<uuid>/aprobacion
{ "estado": "APROBADO" }
```

```json
PATCH /api/viajes/<uuid>/aprobacion
{ "estado": "OBSERVADO", "observacionJefe": "Distancia superior a la oficial" }
```

`RECHAZADO` se normaliza a `OBSERVADO`.

### Respuesta de viaje

```json
{
  "uuid": "11111111-1111-4111-8111-111111111111",
  "rutaSeleccionada": "Sede Concepción - Clínica RedSalud Concepción",
  "odometroInicio": 1000,
  "odometroFin": 1023,
  "totalMontoPeajes": 500,
  "tecnicoEmail": "tecnico@teqmed.cl",
  "vehiculoPatente": "HK-8932",
  "estadoAprobacion": "PENDIENTE",
  "costoCombustibleEstimado": 3194.0,
  "costoTotalCalculado": 3694.0,
  "distanciaDeclaradaKm": 23.0,
  "distanciaOficialKm": 12.5,
  "desviacionPorcentaje": 84.0,
  "alertaDesviacion": true,
  "rendimientoUsadoKmL": 11.5,
  "tarifaUsadaClpL": 1597.0,
  "fuenteTarifa": "FALLBACK"
}
```

---

## 11. Motor de cálculo y tarifas

El cálculo se centraliza en el servidor:

```text
distancia declarada = odometroFin - odometroInicio
costo combustible   = (distancia declarada / rendimiento km/L) * precio $/L
costo total         = costo combustible + totalMontoPeajes
desviación %        = (declarada - oficial) / oficial * 100
alerta              = |desviación| > DESVIACION_UMBRAL_PCT
```

Cada viaje guarda tarifa usada, origen (`API_EXTERNA`, `MANUAL`, `FALLBACK`),
rendimiento y distancia oficial para auditoría.

- Fuente: <https://ahorrahogar.cl/datos/datos.json> (datos CNE).
- Región por defecto: Biobío (`FUEL_REGION_CODE=8`).
- Caché máxima: `FUEL_PRICE_CACHE_HOURS` (24 h).
- Si la fuente falla: última tarifa o `FUEL_DEFAULT_PRICE` con origen `FALLBACK`.
- Un admin puede forzar refresco o sobreescribir el valor.

---

## 12. Pruebas

```bash
make test        # pytest: 30 pruebas
make smoke-local # E2E contra 127.0.0.1:5000
make smoke       # 12 verificaciones E2E contra la URL pública
```

Cobertura:

- login JWT, `/me` y RBAC;
- sincronización idempotente y validaciones;
- cálculo centralizado y alerta de desviación;
- aprobación/observación;
- reportes y CSV;
- mantenedores y tarifa manual;
- API externa de combustible simulada + fallback;
- `ProxyFix` y cabeceras de seguridad;
- lectura de URL pública, configuración de Ngrok, generación de `.env` y
  actualización de `local.properties`;
- smoke test completo contra un servidor Flask real.

Las pruebas unitarias usan SQLite en memoria y no dependen de Internet. El smoke usa
HTTP real y elimina el viaje de prueba al terminar.

---

## 13. Producción: checklist

- Generar `SECRET_KEY` y `JWT_SECRET_KEY` largos y únicos (`make setup` ya lo hace).
- `SEED_DEMO_USERS=false`.
- PostgreSQL + `psycopg[binary]` y backups.
- Gunicorn con 2+ workers detrás de Nginx/Ngrok.
- HTTPS obligatorio; restringir `CORS_ORIGINS`.
- Mantener Flask/Gunicorn en `127.0.0.1`; nunca publicar el puerto 5000.
- Con `TRUST_PROXY=true`, no exponer Flask directamente a Internet (un cliente podría
  falsificar `X-Forwarded-For`).
- No versionar `.env`, `.run/`, `.tools/` ni bases SQLite.
- Rotar `NGROK_AUTHTOKEN` si se filtra.
- Firmar el APK release y distribuir por un canal controlado.

---

## 14. Solución de problemas

| Síntoma | Causa / solución |
|---|---|
| `Falta NGROK_AUTHTOKEN` | Edita `.env` o usa `NGROK_AUTHTOKEN=... make publicar`. |
| `Ngrok no está instalado` | `make setup` o `make instalar-ngrok`; también sirve un Ngrok del sistema. |
| Ngrok no publica URL | Revisa `.run/ngrok.log`; token inválido, dominio ocupado o sin red. |
| `puerto 5000 ya está en uso` | Detén el proceso previo: `make detener` o `ss -ltnp \| grep 5000`. |
| Health falla tras publicar | Mira `.run/flask.log`; suele ser una dependencia o error de BD. |
| La app sigue con URL antigua | Recompila tras `make publicar`; verifica con `:app:printApiBaseUrl`. |
| Ngrok devuelve HTML | Falta el header `Ngrok-Skip-Browser-Warning` (la app ya lo envía). |
| Cambia la URL al reiniciar | Configura `NGROK_DOMAIN` estático y recompila una vez. |
| `make: command not found` | Instala `make` o ejecuta `python scripts/tunel.py ...` directamente. |
| Windows nativo falla | Usa WSL; el orquestador y el Makefile son POSIX. |
| Quiero reiniciar datos demo | Detén la API y borra `instance/teqruta.db`. |
| App no encuentra el proyecto Android | `TEQRUTA_APP_DIR=/ruta/TeqRuta make publicar`. |

---

## 15. Contexto académico

Proyecto de **Desarrollo de Aplicaciones Móviles (DSY1105)**, Escuela de Informática y
Telecomunicaciones, Duoc UC, para TEQMED SpA.

**Integrantes API:** Williams Contreras.  
**App Android:** Hans Morales, Martina Norambuena, Williams Contreras.

Uso académico y demostrativo; no está integrado al ERP contable de TEQMED SpA.
