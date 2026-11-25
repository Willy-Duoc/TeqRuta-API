"""Dashboard web administrativo de TeqRuta.

Autenticación por sesión con los mismos usuarios de la API. El JWT sigue
siendo exclusivo de la app móvil; aquí se usa una cookie HttpOnly firmada y
un token CSRF por sesión.

Roles con acceso: admin, jefe y gerencia. Solo admin y jefe aprueban viajes;
solo admin modifica usuarios, flota, destinos y tarifas.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from hmac import compare_digest
from typing import Any

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import func, or_

from ..extensions import db
from ..models import (
    ESTADOS_APROBACION,
    ROLES,
    Destination,
    Notification,
    Tariff,
    Trip,
    User,
    Vehicle,
)
from ..security import hash_password, verify_password
from ..services.aprobaciones import aplicar_aprobacion
from ..services.fuel_price import (
    normalize_combustible,
    refresh_tariff,
    set_manual_tariff,
)
from ..services.reportes import (
    csv_aprobados,
    parse_filtros,
    query_aprobados,
    resumen_reporte,
)
from ..utils import ApiError, now_utc, validate_email

bp = Blueprint("admin", __name__, template_folder="templates")

ROLES_PANEL = {"admin", "jefe", "gerencia"}
ROLES_APROBACION = {"admin", "jefe"}
COMBUSTIBLES = ("93", "95", "97", "diesel", "parafina")
POR_PAGINA = 15
MESES = (
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
)


# ---------------------------------------------------------------------------
# Seguridad de la sesión y utilidades
# ---------------------------------------------------------------------------


def _csrf_token() -> str:
    token = session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf"] = token
    return token


def _validar_csrf() -> None:
    enviado = request.form.get("_csrf", "")
    esperado = session.get("_csrf", "")
    if not enviado or not esperado or not compare_digest(enviado, esperado):
        abort(400, description="Token CSRF inválido o expirado. Recarga la página.")


@bp.before_request
def _proteger_panel():
    # `g` puede sobrevivir entre peticiones cuando el test client mantiene un
    # app context externo; se limpia para no reutilizar el usuario anterior.
    g.admin_user = None

    if request.method == "POST":
        _validar_csrf()

    if request.endpoint in {"admin.login", None}:
        return None

    user_id = session.get("admin_user_id")
    user = db.session.get(User, user_id) if user_id else None
    if not user or not user.activo or user.rol not in ROLES_PANEL:
        session.pop("admin_user_id", None)
        if request.endpoint == "admin.logout":
            return redirect(url_for("admin.login"))
        destino = request.full_path.rstrip("?")
        return redirect(url_for("admin.login", next=destino))
    g.admin_user = user
    return None


@bp.after_request
def _sin_cache(response):
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@bp.app_context_processor
def _contexto_plantillas():
    user = getattr(g, "admin_user", None)
    return {
        "admin_user": user,
        "csrf_token": _csrf_token(),
        "es_admin": bool(user and user.rol == "admin"),
        "puede_aprobar": bool(user and user.rol in ROLES_APROBACION),
        "combustibles": COMBUSTIBLES,
        "estados": ESTADOS_APROBACION,
        "roles": ROLES,
    }


@bp.app_template_filter("clp")
def _clp(value: Any) -> str:
    try:
        numero = float(value or 0)
    except (TypeError, ValueError):
        numero = 0.0
    return "$" + f"{numero:,.0f}".replace(",", ".")


@bp.app_template_filter("fecha_hora")
def _fecha_hora(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).strftime(
            "%d-%m-%Y %H:%M"
        )
    if isinstance(value, datetime):
        return value.strftime("%d-%m-%Y %H:%M")
    return str(value)


@bp.app_template_filter("fecha")
def _fecha(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%d-%m-%Y")
    return str(value)


@bp.app_template_filter("badge")
def _badge(estado: str) -> str:
    return {
        "PENDIENTE": "warn",
        "APROBADO": "ok",
        "OBSERVADO": "danger",
    }.get((estado or "").upper(), "neutral")


def _destino_seguro(value: str | None) -> str | None:
    if not value or not value.startswith("/") or value.startswith("//"):
        return None
    return value


def _pagina() -> int:
    try:
        return max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        return 1


def _rol_requerido(*roles: str) -> None:
    if not g.admin_user or g.admin_user.rol not in roles:
        abort(403)


def _rango_mes(anio: int, mes: int) -> tuple[int, int]:
    inicio = datetime(anio, mes, 1, tzinfo=timezone.utc)
    if mes == 12:
        fin = datetime(anio + 1, 1, 1, tzinfo=timezone.utc)
    else:
        fin = datetime(anio, mes + 1, 1, tzinfo=timezone.utc)
    return int(inicio.timestamp() * 1000), int(fin.timestamp() * 1000)


# ---------------------------------------------------------------------------
# Login / logout
# ---------------------------------------------------------------------------


@bp.route("/login", methods=["GET", "POST"])
def login():
    actual_id = session.get("admin_user_id")
    actual = db.session.get(User, actual_id) if actual_id else None
    if actual and actual.activo and actual.rol in ROLES_PANEL:
        return redirect(url_for("admin.dashboard"))

    error = None
    email = ""
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user = User.query.filter_by(email=email, activo=True).first()
        if (
            user is None
            or user.rol not in ROLES_PANEL
            or not verify_password(password, user.password_hash)
        ):
            error = "Credenciales inválidas o usuario sin acceso al panel."
        else:
            session.clear()
            session["admin_user_id"] = user.id
            session["_csrf"] = secrets.token_urlsafe(32)
            session.permanent = True
            flash(f"Bienvenido, {user.nombre}.", "success")
            destino = _destino_seguro(request.args.get("next"))
            return redirect(destino or url_for("admin.dashboard"))

    return (
        render_template(
            "admin/login.html",
            error=error,
            email=email,
            next_url=_destino_seguro(request.args.get("next")) or "",
        ),
        401 if error else 200,
    )


@bp.post("/logout")
def logout():
    session.clear()
    flash("Sesión cerrada.", "success")
    return redirect(url_for("admin.login"))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@bp.get("/")
def dashboard():
    ahora = now_utc()
    inicio_ms, fin_ms = _rango_mes(ahora.year, ahora.month)

    total_viajes = Trip.query.count()
    pendientes = Trip.query.filter_by(estado_aprobacion="PENDIENTE").count()
    aprobados = Trip.query.filter_by(estado_aprobacion="APROBADO").count()
    observados = Trip.query.filter_by(estado_aprobacion="OBSERVADO").count()
    alertas = Trip.query.filter(
        Trip.alerta_desviacion.is_(True), Trip.estado_aprobacion == "PENDIENTE"
    ).count()

    costo_aprobado = (
        db.session.query(func.coalesce(func.sum(Trip.costo_total_calculado), 0.0))
        .filter(Trip.estado_aprobacion == "APROBADO")
        .scalar()
        or 0.0
    )
    viajes_mes = (
        Trip.query.filter(
            Trip.estado_aprobacion == "APROBADO",
            Trip.hora_inicio >= inicio_ms,
            Trip.hora_inicio < fin_ms,
        )
        .order_by(Trip.hora_inicio.asc())
        .all()
    )
    resumen_mes = resumen_reporte(viajes_mes)
    clientes_mes = [dict(fila) for fila in resumen_mes["porCliente"][:5]]
    max_costo = clientes_mes[0]["costoTotal"] if clientes_mes else 0.0
    for fila in clientes_mes:
        fila["pct"] = (
            max(4, round(float(fila["costoTotal"]) / max_costo * 100))
            if max_costo
            else 0
        )
    recientes = Trip.query.order_by(Trip.hora_inicio.desc()).limit(8).all()
    tarifa = (
        Tariff.query.filter_by(
            combustible=current_app.config["COSTO_COMBUSTIBLE_TIPO"], activa=True
        ).first()
    )

    return render_template(
        "admin/dashboard.html",
        total_viajes=total_viajes,
        pendientes=pendientes,
        aprobados=aprobados,
        observados=observados,
        alertas=alertas,
        costo_aprobado=costo_aprobado,
        resumen_mes=resumen_mes,
        clientes_mes=clientes_mes,
        recientes=recientes,
        tarifa=tarifa,
        usuarios_activos=User.query.filter_by(activo=True).count(),
        vehiculos_activos=Vehicle.query.filter_by(activo=True).count(),
        mes_actual=f"{MESES[ahora.month - 1]} {ahora.year}",
    )


# ---------------------------------------------------------------------------
# Viajes
# ---------------------------------------------------------------------------


@bp.get("/viajes")
def viajes():
    query = Trip.query
    estado = (request.args.get("estado") or "").strip().upper()
    texto = (request.args.get("q") or "").strip()
    solo_alertas = request.args.get("alertas") == "1"

    if estado in ESTADOS_APROBACION:
        query = query.filter(Trip.estado_aprobacion == estado)
    if texto:
        patron = f"%{texto}%"
        query = query.filter(
            or_(
                Trip.ruta_seleccionada.ilike(patron),
                Trip.tecnico_email.ilike(patron),
                Trip.vehiculo_patente.ilike(patron),
                Trip.uuid.ilike(patron),
            )
        )
    if solo_alertas:
        query = query.filter(Trip.alerta_desviacion.is_(True))

    pagination = query.order_by(Trip.hora_inicio.desc()).paginate(
        page=_pagina(), per_page=POR_PAGINA, error_out=False
    )
    filtros = {
        key: value
        for key, value in {
            "estado": estado,
            "q": texto,
            "alertas": "1" if solo_alertas else "",
        }.items()
        if value
    }
    return render_template(
        "admin/viajes.html", pagination=pagination, filtros=filtros
    )


@bp.get("/viajes/<uuid>")
def viaje_detalle(uuid: str):
    trip = db.session.get(Trip, uuid)
    if trip is None:
        abort(404)
    notificaciones = (
        Notification.query.filter_by(viaje_uuid=uuid)
        .order_by(Notification.created_at.desc())
        .all()
    )
    return render_template(
        "admin/viaje_detalle.html", trip=trip, notificaciones=notificaciones
    )


@bp.post("/viajes/<uuid>/aprobacion")
def viaje_aprobar(uuid: str):
    _rol_requerido(*ROLES_APROBACION)
    trip = db.session.get(Trip, uuid)
    if trip is None:
        abort(404)
    estado = (request.form.get("estado") or "").strip().upper()
    observacion = (request.form.get("observacionJefe") or "").strip()
    try:
        aplicar_aprobacion(trip, estado, observacion)
        db.session.commit()
    except ApiError as exc:
        db.session.rollback()
        flash(exc.message, "error")
    else:
        flash(f"Viaje {trip.uuid} marcado como {estado}.", "success")
    return redirect(url_for("admin.viaje_detalle", uuid=uuid))


@bp.post("/viajes/<uuid>/eliminar")
def viaje_eliminar(uuid: str):
    _rol_requerido("admin")
    trip = db.session.get(Trip, uuid)
    if trip is None:
        abort(404)
    db.session.delete(trip)
    db.session.commit()
    flash(f"Viaje {uuid} eliminado.", "success")
    return redirect(url_for("admin.viajes"))


# ---------------------------------------------------------------------------
# Vehículos
# ---------------------------------------------------------------------------


def _datos_vehiculo() -> dict:
    return {
        "patente": (request.form.get("patente") or "").strip().upper(),
        "modelo": (request.form.get("modelo") or "").strip(),
        "rendimiento": (request.form.get("rendimiento") or "").strip(),
        "kilometrajeActual": (request.form.get("kilometrajeActual") or "0").strip(),
        "tecnicoEmail": (request.form.get("tecnicoEmail") or "").strip().lower(),
        "activo": request.form.get("activo") == "on",
    }


def _validar_vehiculo(data: dict, patente_original: str | None = None) -> dict[str, str]:
    errors: dict[str, str] = {}
    if not data["patente"]:
        errors["patente"] = "La patente es obligatoria."
    if not data["modelo"]:
        errors["modelo"] = "El modelo es obligatorio."
    try:
        rendimiento = float(data["rendimiento"])
        if rendimiento <= 0 or rendimiento > 100:
            errors["rendimiento"] = "El rendimiento debe estar entre 0 y 100 km/L."
    except (TypeError, ValueError):
        errors["rendimiento"] = "El rendimiento debe ser numérico."
    try:
        km = int(data["kilometrajeActual"])
        if km < 0:
            errors["kilometrajeActual"] = "El kilometraje no puede ser negativo."
    except (TypeError, ValueError):
        errors["kilometrajeActual"] = "El kilometraje debe ser un entero."
    if data["tecnicoEmail"] and not validate_email(data["tecnicoEmail"]):
        errors["tecnicoEmail"] = "El email del técnico no es válido."
    if not errors and (
        patente_original is None or data["patente"] != patente_original
    ):
        if Vehicle.query.filter_by(patente=data["patente"]).first():
            errors["patente"] = "Ya existe un vehículo con esa patente."
    return errors


@bp.get("/vehiculos")
def vehiculos():
    texto = (request.args.get("q") or "").strip()
    query = Vehicle.query
    if texto:
        patron = f"%{texto}%"
        query = query.filter(
            or_(
                Vehicle.patente.ilike(patron),
                Vehicle.modelo.ilike(patron),
                Vehicle.tecnico_email.ilike(patron),
            )
        )
    items = query.order_by(Vehicle.patente.asc()).all()
    return render_template("admin/vehiculos.html", items=items, q=texto)


@bp.route("/vehiculos/nuevo", methods=["GET", "POST"])
def vehiculo_nuevo():
    _rol_requerido("admin")
    data = {
        "patente": "",
        "modelo": "",
        "rendimiento": "",
        "kilometrajeActual": "0",
        "tecnicoEmail": "",
        "activo": True,
    }
    errors: dict[str, str] = {}
    if request.method == "POST":
        data = _datos_vehiculo()
        errors = _validar_vehiculo(data)
        if not errors:
            db.session.add(
                Vehicle(
                    patente=data["patente"],
                    modelo=data["modelo"],
                    rendimiento_km_l=float(data["rendimiento"]),
                    kilometraje_actual=int(data["kilometrajeActual"]),
                    tecnico_email=data["tecnicoEmail"] or None,
                    activo=data["activo"],
                )
            )
            db.session.commit()
            flash(f"Vehículo {data['patente']} creado.", "success")
            return redirect(url_for("admin.vehiculos"))
    return render_template(
        "admin/vehiculo_form.html", data=data, errors=errors, editando=False
    )


@bp.route("/vehiculos/<patente>/editar", methods=["GET", "POST"])
def vehiculo_editar(patente: str):
    _rol_requerido("admin")
    item = Vehicle.query.filter_by(patente=patente.strip().upper()).first()
    if item is None:
        abort(404)
    data = {
        "patente": item.patente,
        "modelo": item.modelo,
        "rendimiento": item.rendimiento_km_l,
        "kilometrajeActual": item.kilometraje_actual,
        "tecnicoEmail": item.tecnico_email or "",
        "activo": item.activo,
    }
    errors: dict[str, str] = {}
    if request.method == "POST":
        data = _datos_vehiculo()
        data["patente"] = item.patente
        errors = _validar_vehiculo(data, patente_original=item.patente)
        if not errors:
            item.modelo = data["modelo"]
            item.rendimiento_km_l = float(data["rendimiento"])
            item.kilometraje_actual = int(data["kilometrajeActual"])
            item.tecnico_email = data["tecnicoEmail"] or None
            item.activo = data["activo"]
            db.session.commit()
            flash(f"Vehículo {item.patente} actualizado.", "success")
            return redirect(url_for("admin.vehiculos"))
    return render_template(
        "admin/vehiculo_form.html", data=data, errors=errors, editando=True
    )


@bp.post("/vehiculos/<patente>/eliminar")
def vehiculo_eliminar(patente: str):
    _rol_requerido("admin")
    item = Vehicle.query.filter_by(patente=patente.strip().upper()).first()
    if item is None:
        abort(404)
    db.session.delete(item)
    db.session.commit()
    flash(f"Vehículo {patente.upper()} eliminado.", "success")
    return redirect(url_for("admin.vehiculos"))


# ---------------------------------------------------------------------------
# Destinos
# ---------------------------------------------------------------------------


def _datos_destino() -> dict:
    return {
        "nombre": (request.form.get("nombre") or "").strip(),
        "region": (request.form.get("region") or "").strip(),
        "comuna": (request.form.get("comuna") or "").strip(),
        "distanciaOficialKm": (request.form.get("distanciaOficialKm") or "").strip(),
        "latitud": (request.form.get("latitud") or "").strip(),
        "longitud": (request.form.get("longitud") or "").strip(),
        "activo": request.form.get("activo") == "on",
    }


def _validar_destino(data: dict, destino_id: int | None = None) -> dict[str, str]:
    errors: dict[str, str] = {}
    if not data["nombre"]:
        errors["nombre"] = "El nombre es obligatorio."
    try:
        distancia = float(data["distanciaOficialKm"])
        if distancia <= 0 or distancia > 5000:
            errors["distanciaOficialKm"] = "La distancia debe estar entre 0 y 5000 km."
    except (TypeError, ValueError):
        errors["distanciaOficialKm"] = "La distancia debe ser numérica."
    for campo, limite in (("latitud", 90), ("longitud", 180)):
        if data[campo]:
            try:
                valor = float(data[campo])
                if not -limite <= valor <= limite:
                    errors[campo] = f"El valor debe estar entre -{limite} y {limite}."
            except (TypeError, ValueError):
                errors[campo] = "Debe ser numérico."
    existente = Destination.query.filter_by(nombre=data["nombre"]).first()
    if existente and existente.id != destino_id:
        errors["nombre"] = "Ya existe un destino con ese nombre."
    return errors


@bp.get("/destinos")
def destinos():
    texto = (request.args.get("q") or "").strip()
    query = Destination.query
    if texto:
        patron = f"%{texto}%"
        query = query.filter(
            or_(
                Destination.nombre.ilike(patron),
                Destination.region.ilike(patron),
                Destination.comuna.ilike(patron),
            )
        )
    items = query.order_by(Destination.nombre.asc()).all()
    return render_template("admin/destinos.html", items=items, q=texto)


@bp.route("/destinos/nuevo", methods=["GET", "POST"])
def destino_nuevo():
    _rol_requerido("admin")
    data = {
        "nombre": "",
        "region": "",
        "comuna": "",
        "distanciaOficialKm": "",
        "latitud": "",
        "longitud": "",
        "activo": True,
    }
    errors: dict[str, str] = {}
    if request.method == "POST":
        data = _datos_destino()
        errors = _validar_destino(data)
        if not errors:
            db.session.add(
                Destination(
                    nombre=data["nombre"],
                    region=data["region"] or None,
                    comuna=data["comuna"] or None,
                    distancia_oficial_km=float(data["distanciaOficialKm"]),
                    latitud=float(data["latitud"]) if data["latitud"] else None,
                    longitud=float(data["longitud"]) if data["longitud"] else None,
                    activo=data["activo"],
                )
            )
            db.session.commit()
            flash(f"Destino {data['nombre']} creado.", "success")
            return redirect(url_for("admin.destinos"))
    return render_template(
        "admin/destino_form.html",
        data=data,
        errors=errors,
        editando=False,
        item_id=None,
    )


@bp.route("/destinos/<int:item_id>/editar", methods=["GET", "POST"])
def destino_editar(item_id: int):
    _rol_requerido("admin")
    item = db.session.get(Destination, item_id)
    if item is None:
        abort(404)
    data = {
        "nombre": item.nombre,
        "region": item.region or "",
        "comuna": item.comuna or "",
        "distanciaOficialKm": item.distancia_oficial_km,
        "latitud": item.latitud if item.latitud is not None else "",
        "longitud": item.longitud if item.longitud is not None else "",
        "activo": item.activo,
    }
    errors: dict[str, str] = {}
    if request.method == "POST":
        data = _datos_destino()
        errors = _validar_destino(data, destino_id=item.id)
        if not errors:
            item.nombre = data["nombre"]
            item.region = data["region"] or None
            item.comuna = data["comuna"] or None
            item.distancia_oficial_km = float(data["distanciaOficialKm"])
            item.latitud = float(data["latitud"]) if data["latitud"] else None
            item.longitud = float(data["longitud"]) if data["longitud"] else None
            item.activo = data["activo"]
            db.session.commit()
            flash(f"Destino {item.nombre} actualizado.", "success")
            return redirect(url_for("admin.destinos"))
    return render_template(
        "admin/destino_form.html",
        data=data,
        errors=errors,
        editando=True,
        item_id=item.id,
    )


@bp.post("/destinos/<int:item_id>/eliminar")
def destino_eliminar(item_id: int):
    _rol_requerido("admin")
    item = db.session.get(Destination, item_id)
    if item is None:
        abort(404)
    db.session.delete(item)
    db.session.commit()
    flash(f"Destino {item.nombre} eliminado.", "success")
    return redirect(url_for("admin.destinos"))


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------


def _datos_usuario() -> dict:
    return {
        "email": (request.form.get("email") or "").strip().lower(),
        "nombre": (request.form.get("nombre") or "").strip(),
        "rol": (request.form.get("rol") or "tecnico").strip().lower(),
        "cargo": (request.form.get("cargo") or "").strip(),
        "vehiculoAsignado": (request.form.get("vehiculoAsignado") or "").strip(),
        "password": request.form.get("password") or "",
        "activo": request.form.get("activo") == "on",
    }


def _validar_usuario(
    data: dict, usuario_id: int | None = None, *, crear: bool
) -> dict[str, str]:
    errors: dict[str, str] = {}
    if not validate_email(data["email"]):
        errors["email"] = "El email no es válido."
    if not data["nombre"]:
        errors["nombre"] = "El nombre es obligatorio."
    if data["rol"] not in ROLES:
        errors["rol"] = "El rol seleccionado no es válido."
    if crear and len(data["password"]) < 8:
        errors["password"] = "La contraseña debe tener al menos 8 caracteres."
    if not crear and data["password"] and len(data["password"]) < 8:
        errors["password"] = "La nueva contraseña debe tener al menos 8 caracteres."
    existente = User.query.filter_by(email=data["email"]).first()
    if existente and existente.id != usuario_id:
        errors["email"] = "Ya existe un usuario con ese email."
    return errors


@bp.get("/usuarios")
def usuarios():
    _rol_requerido("admin")
    items = User.query.order_by(User.email.asc()).all()
    return render_template("admin/usuarios.html", items=items)


@bp.route("/usuarios/nuevo", methods=["GET", "POST"])
def usuario_nuevo():
    _rol_requerido("admin")
    data = {
        "email": "",
        "nombre": "",
        "rol": "tecnico",
        "cargo": "",
        "vehiculoAsignado": "",
        "password": "",
        "activo": True,
    }
    errors: dict[str, str] = {}
    if request.method == "POST":
        data = _datos_usuario()
        errors = _validar_usuario(data, crear=True)
        if not errors:
            db.session.add(
                User(
                    email=data["email"],
                    password_hash=hash_password(data["password"]),
                    nombre=data["nombre"],
                    rol=data["rol"],
                    cargo=data["cargo"] or None,
                    vehiculo_asignado=data["vehiculoAsignado"] or None,
                    activo=data["activo"],
                )
            )
            db.session.commit()
            flash(f"Usuario {data['email']} creado.", "success")
            return redirect(url_for("admin.usuarios"))
    return render_template(
        "admin/usuario_form.html",
        data=data,
        errors=errors,
        editando=False,
        item_id=None,
    )


@bp.route("/usuarios/<int:item_id>/editar", methods=["GET", "POST"])
def usuario_editar(item_id: int):
    _rol_requerido("admin")
    item = db.session.get(User, item_id)
    if item is None:
        abort(404)
    data = {
        "email": item.email,
        "nombre": item.nombre,
        "rol": item.rol,
        "cargo": item.cargo or "",
        "vehiculoAsignado": item.vehiculo_asignado or "",
        "password": "",
        "activo": item.activo,
    }
    errors: dict[str, str] = {}
    if request.method == "POST":
        data = _datos_usuario()
        errors = _validar_usuario(data, usuario_id=item.id, crear=False)
        if item.id == g.admin_user.id and not data["activo"]:
            errors["activo"] = "No puedes desactivar tu propio usuario."
        if not errors:
            item.email = data["email"]
            item.nombre = data["nombre"]
            item.rol = data["rol"]
            item.cargo = data["cargo"] or None
            item.vehiculo_asignado = data["vehiculoAsignado"] or None
            item.activo = data["activo"]
            if data["password"]:
                item.password_hash = hash_password(data["password"])
            db.session.commit()
            flash(f"Usuario {item.email} actualizado.", "success")
            return redirect(url_for("admin.usuarios"))
    return render_template(
        "admin/usuario_form.html",
        data=data,
        errors=errors,
        editando=True,
        item_id=item.id,
    )


@bp.post("/usuarios/<int:item_id>/eliminar")
def usuario_eliminar(item_id: int):
    _rol_requerido("admin")
    item = db.session.get(User, item_id)
    if item is None:
        abort(404)
    if item.id == g.admin_user.id:
        flash("No puedes eliminar tu propio usuario.", "error")
        return redirect(url_for("admin.usuarios"))
    db.session.delete(item)
    db.session.commit()
    flash(f"Usuario {item.email} eliminado.", "success")
    return redirect(url_for("admin.usuarios"))


# ---------------------------------------------------------------------------
# Tarifas
# ---------------------------------------------------------------------------


@bp.get("/tarifas")
def tarifas():
    combustible = normalize_combustible(
        request.args.get("combustible")
        or current_app.config["COSTO_COMBUSTIBLE_TIPO"]
    )
    activa = (
        Tariff.query.filter_by(combustible=combustible, activa=True)
        .order_by(Tariff.vigente_desde.desc())
        .first()
    )
    historial = (
        Tariff.query.filter_by(combustible=combustible)
        .order_by(Tariff.vigente_desde.desc(), Tariff.id.desc())
        .limit(50)
        .all()
    )
    return render_template(
        "admin/tarifas.html",
        combustible=combustible,
        activa=activa,
        historial=historial,
    )


@bp.post("/tarifas/manual")
def tarifa_manual():
    _rol_requerido("admin")
    combustible = normalize_combustible(request.form.get("combustible"))
    try:
        precio = float(request.form.get("precioLitro") or 0)
        if not 0 < precio <= 10_000_000:
            raise ValueError
    except (TypeError, ValueError):
        flash("El precio debe ser numérico y estar entre 0 y 10.000.000 CLP/L.", "error")
        return redirect(url_for("admin.tarifas", combustible=combustible))

    fuente = (request.form.get("fuente") or "").strip() or "Overwrite manual (dashboard)"
    set_manual_tariff(combustible, precio, fuente=fuente)
    flash(
        f"Tarifa de {combustible} actualizada manualmente a {_clp(precio)}/L.",
        "success",
    )
    return redirect(url_for("admin.tarifas", combustible=combustible))


@bp.post("/tarifas/actualizar")
def tarifa_actualizar():
    _rol_requerido("admin")
    combustible = normalize_combustible(request.form.get("combustible"))
    tarifa = refresh_tariff(combustible)
    flash(
        f"Tarifa de {combustible}: {_clp(tarifa.precio_litro)}/L (origen {tarifa.origen}).",
        "success" if tarifa.origen == "API_EXTERNA" else "warning",
    )
    return redirect(url_for("admin.tarifas", combustible=combustible))


# ---------------------------------------------------------------------------
# Reportes
# ---------------------------------------------------------------------------


def _filtros_reporte() -> tuple[dict, Any]:
    ahora = datetime.now(timezone.utc)
    args = {
        "anio": request.args.get("anio", str(ahora.year)),
        "mes": request.args.get("mes", str(ahora.month)),
        "cliente": request.args.get("cliente", ""),
    }
    try:
        filtros = parse_filtros(args)
    except ApiError as exc:
        flash(exc.message, "error")
        args["anio"] = str(ahora.year)
        args["mes"] = str(ahora.month)
        filtros = parse_filtros(args)
    return args, filtros


@bp.get("/reportes")
def reportes():
    args, filtros = _filtros_reporte()
    viajes = query_aprobados(filtros).all()
    resumen = resumen_reporte(viajes)
    anio_actual = datetime.now(timezone.utc).year
    return render_template(
        "admin/reportes.html",
        args=args,
        filtros=filtros,
        resumen=resumen,
        anios=range(anio_actual - 4, anio_actual + 1),
        meses=[
            (1, "Enero"),
            (2, "Febrero"),
            (3, "Marzo"),
            (4, "Abril"),
            (5, "Mayo"),
            (6, "Junio"),
            (7, "Julio"),
            (8, "Agosto"),
            (9, "Septiembre"),
            (10, "Octubre"),
            (11, "Noviembre"),
            (12, "Diciembre"),
        ],
    )


@bp.get("/reportes.csv")
def reportes_csv():
    _args, filtros = _filtros_reporte()
    viajes = query_aprobados(filtros).all()
    response = current_app.response_class(
        csv_aprobados(viajes), mimetype="text/csv; charset=utf-8"
    )
    nombre = f"teqruta_reporte_{filtros.anio or 'todos'}_{filtros.mes or 'todos'}.csv"
    response.headers["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return response
