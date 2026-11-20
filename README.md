# TeqRuta API

API REST externa desarrollada en **Flask** para la aplicación nativa Android **TeqRuta** (Kotlin + Jetpack Compose + MVVM) del caso **TEQMED SpA** (DSY1105 – Duoc UC).

La API centraliza la validación de viajes, el cálculo de costos de movilización, la aprobación por jefatura, los reportes financieros y los mantenedores de flota/destinos/tarifas. Se expone al dispositivo Android mediante **Ngrok**, que redirige un dominio HTTPS público hacia el servidor Flask local.

Repositorio de la app móvil: <https://github.com/hanspwd/TeqRuta.git>  
Repositorio de esta API: <https://github.com/Willy-Duoc/API-TeqRuta.git>

---

## 1. Contexto del caso

TEQMED SpA realiza traslados diarios desde Concepción a clínicas, hospitales y centros de diálisis del Gran Concepción, Chillán, Los Ángeles y Temuco. Hoy el gasto de movilización se estima en libreta, lo que impide:

- conocer el costo real por cliente, técnico o vehículo;
- verificar la distancia declarada frente a la distancia oficial;
- evitar duplicidades y diferencias entre lo declarado y lo autorizado.

TeqRuta digitaliza el registro en terreno (modo offline-first) y esta API entrega la **fuente única de verdad** para tarifas y cálculos, con trazabilidad y control por roles.

---

## 2. Arquitectura

| Capa | Tecnología | Responsabilidad |
|---|---|---|
| Cliente | Android Kotlin, Jetpack Compose, MVVM, Room | Registro offline, cámara, cola de viajes pendientes |
| Túnel | **Ngrok** | Exponer `localhost:5000` como URL HTTPS pública |
| API | **Flask 3 + Blueprints** | Auth, Viajes, Reportes y Mantenedores |
| Persistencia | SQLAlchemy (SQLite por defecto / PostgreSQL en producción) | Usuarios, vehículos, destinos, tarifas, viajes, notificaciones |
| Seguridad | JWT (PyJWT) + Bcrypt + RBAC | Token en cada petición y permisos por rol |
| Integración externa | API pública de precios de combustible | Tarifa diaria actualizable con sobreescritura manual |

### Blueprints

```
app/
├── auth/          → /api/auth         (login, me, logout, config pública)
├── viajes/        → /api/viajes       (sync, CRUD, aprobación)
├── reportes/      → /api/reportes     (dashboard, CSV, desviaciones)
├── mantenedores/  → /api/mantenedores (vehículos, destinos, usuarios, tarifas)
├── services/      → motor de costos + cliente de API externa de combustible
├── models.py      → entidades SQLAlchemy
├── serializers.py → JSON camelCase compatible con Kotlin
├── security.py    → JWT, Bcrypt y decoradores RBAC
└── errors.py      → respuestas JSON uniformes
```

### Roles (RBAC)

| Rol | Permisos principales |
|---|---|
| `tecnico` | Sincroniza sus propios viajes, consulta destinos y su historial |
| `jefe` | Ve todos los viajes, aprueba u observa gastos, revisa desviaciones |
| `gerencia` | Reportes financieros, métricas y exportación CSV |
| `admin` | ABM de vehículos, destinos, usuarios y tarifas; también aprueba |

Toda petición excepto `/`, `/api/health`, `/api/auth/login`, `/api/auth/register` y `/api/auth/config` requiere:

```http
Authorization: Bearer <access_token>
```

---

## 3. Requisitos previos

- Python 3.10 o superior
- pip y entorno virtual
- [Ngrok](https://ngrok.com/download) (para conexión desde Android/emulador)
- Opcional: PostgreSQL si se despliega en producción

---

## 4. Instalación y configuración

```bash
git clone https://github.com/Willy-Duoc/API-TeqRuta.git
cd API-TeqRuta

python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements-dev.txt
copy .env.example .env      # Windows
# cp .env.example .env      # Linux / macOS
```

### Variables de entorno principales

| Variable | Default | Descripción |
|---|---|---|
| `PORT` | `5000` | Puerto local de Flask |
| `FLASK_DEBUG` | `true` | Modo recarga en desarrollo |
| `SECRET_KEY` | valor dev | Clave de Flask |
| `JWT_SECRET_KEY` | `SECRET_KEY` | Secreto para firmar tokens (cambiar en producción) |
| `JWT_EXPIRE_HOURS` | `8` | Vigencia del token (jornada del técnico) |
| `DATABASE_URL` | `sqlite:///teqruta.db` | Cadena SQLAlchemy |
| `SEED_DEMO_USERS` | `true` | Carga usuarios/flota/destinos de ejemplo |
| `FUEL_PRICE_URL` | `https://ahorrahogar.cl/datos/datos.json` | Fuente pública de precios (datos CNE) |
| `FUEL_REGION_CODE` | `8` | Región usada (8 = Biobío) |
| `FUEL_PRICE_CACHE_HOURS` | `24` | Frecuencia de refresco (una vez al día) |
| `FUEL_DEFAULT_PRICE` | `1597` | Precio de respaldo si la fuente falla |
| `DEFAULT_RENDIMIENTO_KM_L` | `10` | Rendimiento por defecto si el vehículo no existe |
| `DESVIACION_UMBRAL_PCT` | `10` | Alerta cuando declarada vs oficial supera este % |

> El archivo SQLite se crea automáticamente en la carpeta `instance/`.

---

## 5. Ejecución local

```bash
python run.py
```

También es válido:

```bash
flask --app wsgi run --host 0.0.0.0 --port 5000
```

Verificación rápida:

- <http://127.0.0.1:5000/> → información del API
- <http://127.0.0.1:5000/api/health> → `{"status":"ok","database":"ok"}`

Producción (Gunicorn):

```bash
gunicorn --bind 0.0.0.0:5000 --workers 2 wsgi:app
```

---

## 6. Conexión con la app Android mediante Ngrok

Ngrok crea un túnel HTTPS desde Internet hacia tu Flask local, sin desplegar servidores.

### 6.1 Pasos

```bash
# 1. Autenticación única (opcional pero recomendado)
ngrok config add-authtoken TU_TOKEN_DE_NGROK

# 2. Iniciar Flask
python run.py

# 3. En otra terminal, exponer el puerto
ngrok http 5000
```

Ngrok mostrará algo como:

```text
Forwarding  https://a1b2-c3d4-5678.ngrok-free.app -> http://localhost:5000
```

### 6.2 Configuración en Kotlin

Usa la URL **HTTPS** (Android bloquea tráfico cleartext por defecto) y que termine en `/`:

```kotlin
const val BASE_URL = "https://a1b2-c3d4-5678.ngrok-free.app/"
const val NGROK_SKIP_BROWSER_WARNING = true // cabecera para el plan free
```

En el interceptor de OkHttp:

```kotlin
addInterceptor { chain ->
    val request = chain.request().newBuilder()
        .header("Authorization", "Bearer $token")
        .header("Ngrok-Skip-Browser-Warning", "1")
        .build()
    chain.proceed(request)
}
```

Añade el permiso al `AndroidManifest.xml`:

```xml
<uses-permission android:name="android.permission.INTERNET" />
```

> **Importante:** en el plan gratuito la URL cambia cada vez que se reinicia Ngrok. Actualiza `BASE_URL` en la app o usa un dominio reservado:
> `ngrok http --domain=teqruta.ngrok-free.app 5000`.

### 6.3 Flujo offline-first

1. El técnico registra el viaje sin señal → Room lo guarda con `sincronizado = false` y su `uuid`.
2. `NetworkHelper.isOnlineFlow` detecta conexión (o `WorkManager` periódicamente).
3. El ViewModel envía `POST /api/viajes/sync` con la cola pendiente.
4. El backend valida los UUID: los nuevos se insertan y calculan; los repetidos se ignoran.
5. La app marca como sincronizados solo los UUID aceptados.

---

## 7. Usuarios de demostración

Se crean automáticamente al iniciar con `SEED_DEMO_USERS=true`.

| Email | Contraseña | Rol |
|---|---|---|
| `tecnico@teqmed.cl` | `tecnico123` | tecnico |
| `jefe@teqmed.cl` | `jefe123` | jefe |
| `gerencia@teqmed.cl` | `gerencia123` | gerencia |
| `admin@teqmed.cl` | `admin123` | admin |

Ejemplo de login:

```bash
curl -X POST http://127.0.0.1:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"tecnico@teqmed.cl","password":"tecnico123"}'
```

Respuesta:

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

## 8. Endpoints

### Autenticación

| Método | Ruta | Acceso | Descripción |
|---|---|---|---|
| POST | `/api/auth/login` | público | Devuelve JWT + perfil |
| GET | `/api/auth/me` | autenticado | Perfil del token vigente |
| POST | `/api/auth/logout` | autenticado | Confirma cierre de sesión (JWT stateless) |
| POST | `/api/auth/register` | público | Registro de técnicos para pruebas |
| GET | `/api/auth/config` | público | Umbral de desviación y combustible de referencia |

### Viajes

| Método | Ruta | Acceso | Descripción |
|---|---|---|---|
| POST | `/api/viajes/sync` | autenticado | Sincronización por lote, idempotente por UUID |
| POST | `/api/viajes` | autenticado | Crear un viaje |
| GET | `/api/viajes` | autenticado | Listar (filtros: `estado`, `cliente`, `tecnicoEmail`, `vehiculoPatente`, `desde`, `hasta`, `soloAlertas`, `page`, `per_page`) |
| GET | `/api/viajes/<uuid>` | autenticado | Detalle |
| PATCH | `/api/viajes/<uuid>/aprobacion` | jefe, admin | Aprobar u observar |
| DELETE | `/api/viajes/<uuid>` | admin | Eliminar |

### Reportes

| Método | Ruta | Acceso | Descripción |
|---|---|---|---|
| GET | `/api/reportes/mensual` | gerencia, admin, jefe | Costo total, promedio por visita y desgloses |
| GET | `/api/reportes/mensual.csv` | gerencia, admin, jefe | Exportación CSV (BOM para Excel) |
| GET | `/api/reportes/desviaciones` | gerencia, admin, jefe | Viajes sobre el umbral de desviación |

Filtros de reporte: `anio`, `mes`, `cliente`, `desde`, `hasta`.

### Mantenedores

| Método | Ruta | Acceso | Descripción |
|---|---|---|---|
| GET/POST | `/api/mantenedores/vehiculos` | lectura: todos / escritura: admin | ABM de flota |
| GET/PUT/DELETE | `/api/mantenedores/vehiculos/<patente>` | admin | Detalle y edición |
| GET/POST | `/api/mantenedores/destinos` | lectura: todos / escritura: admin | Catastro de clínicas (cache offline) |
| GET/PUT/DELETE | `/api/mantenedores/destinos/<id>` | admin | Detalle y edición |
| GET/POST | `/api/mantenedores/usuarios` | admin | ABM de usuarios |
| GET/PUT/DELETE | `/api/mantenedores/usuarios/<id>` | admin | Detalle y edición |
| GET | `/api/mantenedores/tarifas` | autenticado | Historial de tarifas |
| GET | `/api/mantenedores/tarifas/vigente?combustible=93` | autenticado | Tarifa activa |
| PUT | `/api/mantenedores/tarifas/93` | admin | Sobreescritura manual |
| POST | `/api/mantenedores/tarifas/actualizar` | admin | Refresco forzado desde API externa |

---

## 9. Ejemplos de solicitudes

### 9.1 Sincronizar viajes

```json
POST /api/viajes/sync
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
    "resumen": {
      "recibidos": 1,
      "insertados": 1,
      "duplicados": 0,
      "rechazados": 0
    },
    "rechazados": [],
    "viajes": [{ "uuid": "1111...", "estado": "insertado" }]
  },
  "message": "Sincronización finalizada"
}
```

Si hay errores por viaje, el estado HTTP es `207 Multi-Status` y `rechazados` contiene `indice` y `errores`.

### 9.2 Aprobar u observar

```json
PATCH /api/viajes/<uuid>/aprobacion
{ "estado": "APROBADO" }
```

```json
PATCH /api/viajes/<uuid>/aprobacion
{ "estado": "OBSERVADO", "observacionJefe": "Distancia declarada superior a la oficial" }
```

`RECHAZADO` (valor usado en `RoleScreens.kt`) se convierte automáticamente a `OBSERVADO`.

### 9.3 Respuesta de un viaje

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

## 10. Motor de cálculo y auditoría

El cálculo queda **centralizado en el servidor**, no en el dispositivo:

```text
distancia declarada = odometroFin - odometroInicio
costo combustible   = (distancia declarada / rendimiento km/L) * precio $/L
costo total         = costo combustible + totalMontoPeajes
desviación %        = (declarada - oficial) / oficial * 100
alerta              = |desviación| > DESVIACION_UMBRAL_PCT (10%)
```

Cada viaje guarda la tarifa usada, su origen (`API_EXTERNA`, `MANUAL` o `FALLBACK`), el rendimiento aplicado y la distancia oficial, por lo que el gasto es **verificable** ante contratos y gerencia.

### Precio de combustible

- Fuente por defecto: <https://ahorrahogar.cl/datos/datos.json> (consolida datos oficiales de la CNE / Bencina en Línea).
- Se lee `bencina.combustibles["93"].regiones["8"].mediana` (Biobío), con respaldo al promedio nacional.
- Se actualiza como máximo una vez cada `FUEL_PRICE_CACHE_HOURS` (24 h por defecto).
- Si la fuente falla, se conserva la última tarifa o se usa `FUEL_DEFAULT_PRICE`, marcando el origen como `FALLBACK`.
- El administrador puede sobreescribir el valor manualmente desde `/api/mantenedores/tarifas/93`.

Datos de precios: © Comisión Nacional de Energía de Chile, consolidados por AhorraHogar.cl (CC BY 4.0).

---

## 11. Integración desde Kotlin (MVVM + Retrofit)

A continuación, un ejemplo mínimo para conectar el `ViajeViewModel` existente con esta API.

### Dependencias

```kotlin
// app/build.gradle.kts
implementation("com.squareup.retrofit2:retrofit:2.11.0")
implementation("com.squareup.retrofit2:converter-gson:2.11.0")
implementation("com.squareup.okhttp3:logging-interceptor:4.12.0")
```

### DTOs

```kotlin
data class LoginRequest(val email: String, val password: String)

data class LoginResponse(
    @SerializedName("access_token") val accessToken: String,
    @SerializedName("token_type") val tokenType: String,
    val user: UserDto
)

data class UserDto(val email: String, val nombre: String, val rol: String)

data class SyncRequest(val viajes: List<ViajeDto>)

data class SyncResponse(val data: SyncData)
data class SyncData(
    val resumen: ResumenSync,
    val viajes: List<ViajeDto>,
    val rechazados: List<RechazoDto>
)
data class ResumenSync(
    val recibidos: Int, val insertados: Int, val duplicados: Int, val rechazados: Int
)
data class RechazoDto(val indice: Int, val errores: List<String>)

data class ViajeDto(
    val uuid: String,
    val rutaSeleccionada: String,
    val odometroInicio: Int,
    val odometroFin: Int,
    val totalMontoPeajes: Double,
    val horaInicio: Long,
    val horaFin: Long,
    val tecnicoEmail: String,
    val vehiculoPatente: String,
    val estadoAprobacion: String = "PENDIENTE",
    val costoTotalCalculado: Double? = null,
    val alertaDesviacion: Boolean? = null
)
```

### Servicio Retrofit

```kotlin
interface TeqRutaApi {
    @POST("api/auth/login")
    suspend fun login(@Body body: LoginRequest): LoginResponse

    @GET("api/auth/me")
    suspend fun me(): UserDto

    @POST("api/viajes/sync")
    suspend fun sync(@Body body: SyncRequest): SyncResponse

    @GET("api/viajes")
    suspend fun listar(@Query("estado") estado: String? = null): List<ViajeDto>

    @PATCH("api/viajes/{uuid}/aprobacion")
    suspend fun aprobar(
        @Path("uuid") uuid: String,
        @Body body: Map<String, String>
    ): ViajeDto

    @GET("api/mantenedores/destinos")
    suspend fun destinos(): List<DestinoDto>
}
```

### ViewModel (extracto)

```kotlin
fun sincronizarPendientes() = viewModelScope.launch {
    val pendientes = viajeDao.getViajesPendientes().first()
    if (pendientes.isEmpty()) return@launch

    val respuesta = api.sync(SyncRequest(pendientes.map { it.toDto() }))
    viajeDao.marcarComoSincronizados(respuesta.data.viajes.map { it.uuid })

    // El estadoAPROBACION y el costoTotalCalculado vuelven desde la API.
    respuesta.data.viajes.forEach { viajeDao.actualizarDesdeServidor(it) }
}
```

> El repositorio Android actualmente no tiene Retrofit ni permiso `INTERNET`; este API está listo para que el equipo agregue esa capa sin cambiar el contrato de datos: los nombres de campo son idénticos a `Viaje.kt`.

---

## 12. Pruebas

```bash
pytest
```

Incluye pruebas para:

- login JWT, `.me` y RBAC;
- sincronización idempotente y validaciones;
- cálculo centralizado de costos y alerta de desviación;
- aprobación/observación y notificación;
- reportes y exportación CSV;
- mantenedores y tarifa manual;
- consumo de API externa con `requests` mockeado y fallback.

Las pruebas usan SQLite en memoria y desactivan la red, por lo que son deterministas.

---

## 13. Consideraciones de producción

- Cambiar `SECRET_KEY` y `JWT_SECRET_KEY` por secretos aleatorios largos.
- `SEED_DEMO_USERS=false`.
- Usar PostgreSQL: `DATABASE_URL=postgresql+psycopg://user:pass@host:5432/teqruta`.
- Servir siempre por HTTPS (Ngrok o reverse proxy) y restringir `CORS_ORIGINS`.
- Ejecutar con Gunicorn (2+ workers) detrás de Nginx.
- Registrar y auditar cambios de tarifa: el historial queda en `tarifas`.

---

## 14. Contexto académico

Proyecto desarrollado para la asignatura **Desarrollo de Aplicaciones Móviles (DSY1105)**, Escuela de Informática y Telecomunicaciones, Duoc UC. Uso académico y demostrativo; no se encuentra integrado al ERP contable de TEQMED SpA.

**Integrantes API:** Williams Contreras.  
**App Android:** Hans Morales, Martina Norambuena, Williams Contreras.
