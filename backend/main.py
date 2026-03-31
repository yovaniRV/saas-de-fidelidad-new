import os
import ipaddress
import secrets
import socket
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
from urllib.parse import urlparse

import jwt
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy.orm import Session

import models
import schemas
from database import SessionLocal, engine, ensure_sqlite_schema
from rate_limit import build_rate_limiter
from security_utils import hash_password, verify_password

models.Base.metadata.create_all(bind=engine)
ensure_sqlite_schema()

app = FastAPI(title="SaaS Fidelidad API")

def _load_or_create_secret_key() -> str:
    env_key = os.getenv("JWT_SECRET_KEY")
    if env_key:
        return env_key
    secret_file = Path(__file__).resolve().parent / ".secret_key"
    if secret_file.exists():
        return secret_file.read_text().strip()
    new_key = secrets.token_urlsafe(48)
    secret_file.write_text(new_key)
    return new_key

SECRET_KEY = _load_or_create_secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8
MAX_LOGIN_FAILED_ATTEMPTS = 5
LOGIN_LOCK_MINUTES = 5
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:4200")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
UPLOADS_BASE_DIR = Path(os.getenv("UPLOADS_BASE_DIR", str(Path(__file__).resolve().parent / "uploads")))
UPLOAD_DIR = UPLOADS_BASE_DIR / "logos"
_MAGIC_RESET_REQUESTED = os.getenv("MAGIC_RESET_ENABLED", "false").strip().lower() == "true"
_ALLOW_MAGIC_RESET_ON_RAILWAY = os.getenv("ALLOW_MAGIC_RESET_ON_RAILWAY", "false").strip().lower() == "true"
_IS_RAILWAY_DEPLOYMENT = bool(os.getenv("RAILWAY_ENVIRONMENT"))
MAGIC_RESET_ENABLED = _MAGIC_RESET_REQUESTED and (not _IS_RAILWAY_DEPLOYMENT or _ALLOW_MAGIC_RESET_ON_RAILWAY)
MAGIC_RESET_TOKEN = os.getenv("MAGIC_RESET_TOKEN", "").strip()
MAX_LOGO_SIZE_BYTES = 2 * 1024 * 1024
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver,*.up.railway.app").split(",")
    if host.strip()
]
# Añadir la IP local automáticamente para permitir acceso desde la red local
def _get_local_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as _s:
            _s.connect(("8.8.8.8", 80))
            return _s.getsockname()[0]
    except Exception:
        return None

_local_ip = _get_local_ip()
if _local_ip and _local_ip not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(_local_ip)
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:4200,http://127.0.0.1:4200,https://localhost:4200,https://127.0.0.1:4200",
    ).split(",")
    if origin.strip()
]
REDIS_URL = os.getenv("REDIS_URL")
INTERNAL_RATE_LIMIT_MULTIPLIER = max(1, int(os.getenv("INTERNAL_RATE_LIMIT_MULTIPLIER", "5")))
INTERNAL_NETWORKS = [
    ipaddress.ip_network(value.strip())
    for value in os.getenv("INTERNAL_NETWORKS", "127.0.0.0/8,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16").split(",")
    if value.strip()
]
RATE_LIMITS = {
    "login_ip": {
        "limit": int(os.getenv("RATE_LIMIT_LOGIN_IP", "12")),
        "window_seconds": int(os.getenv("RATE_LIMIT_LOGIN_IP_WINDOW", "60")),
    },
    "login_subject": {
        "limit": int(os.getenv("RATE_LIMIT_LOGIN_SUBJECT", "6")),
        "window_seconds": int(os.getenv("RATE_LIMIT_LOGIN_SUBJECT_WINDOW", "60")),
    },
    "sensitive_ip": {
        "limit": int(os.getenv("RATE_LIMIT_SENSITIVE_IP", "60")),
        "window_seconds": int(os.getenv("RATE_LIMIT_SENSITIVE_IP_WINDOW", "60")),
    },
    "sensitive_subject": {
        "limit": int(os.getenv("RATE_LIMIT_SENSITIVE_SUBJECT", "30")),
        "window_seconds": int(os.getenv("RATE_LIMIT_SENSITIVE_SUBJECT_WINDOW", "60")),
    },
}
security = HTTPBearer()
rate_limiter, RATE_LIMIT_BACKEND = build_rate_limiter(REDIS_URL)

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(UPLOADS_BASE_DIR)), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_origin_regex=(
        r"https://.*\.vercel\.app"
        r"|https?://(192\.168|10\.|172\.(1[6-9]|2\d|3[01]))\.\d+\.\d+:\d+"
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)


def is_sensitive_path(path: str) -> bool:
    if path == "/health":
        return False

    if path in {"/login", "/registrar-visita", "/registrar-visita-qr", "/clientes/mis-comercios"}:
        return True

    if path.startswith("/comercios/configuracion") or path.startswith("/clientes/") or path.startswith("/analytics/"):
        return True

    if path.startswith("/static/") or path.startswith("/docs") or path.startswith("/openapi") or path.startswith("/redoc"):
        return False

    if path.startswith("/comercios/") and ("/clientes/" in path or path.endswith("/acceso-cliente")):
        return True

    if path.startswith("/comercios/"):
        return False

    return False


@app.middleware("http")
async def apply_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Request-Id"] = uuid4().hex
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
    response.headers["Origin-Agent-Cluster"] = "?1"
    response.headers["Permissions-Policy"] = "camera=(), geolocation=(), microphone=()"
    response.headers["X-Permitted-Cross-Domain-Policies"] = "none"

    if not request.url.path.startswith("/docs") and not request.url.path.startswith("/redoc") and not request.url.path.startswith("/openapi"):
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"

    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=86400, immutable"
    elif is_sensitive_path(request.url.path):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

    return response


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/magic-reset-180320")
def wipe_and_reset_users(
    token: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    if not MAGIC_RESET_ENABLED:
        # Evita que un endpoint destructivo quede activo en producción por defecto.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    if not MAGIC_RESET_TOKEN or token != MAGIC_RESET_TOKEN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso denegado")

    db.query(models.Cajero).delete()
    db.query(models.AdminUsuario).delete()
    db.commit()

    comercio = db.query(models.Comercio).first()
    if not comercio:
        comercio = models.Comercio(slug="demo", nombre="Demo")
        db.add(comercio)
        db.commit()
        db.refresh(comercio)

    admin = models.AdminUsuario(
        username="vani",
        password=hash_password("VrV180320"),
        nombre_mostrado="Vani",
        activo=1
    )
    db.add(admin)

    cajero = models.Cajero(
        comercio_id=comercio.id,
        username="cajero",
        password=hash_password("VrV180320"),
        nombre_mostrado="Cajero Default",
        rol="cajero",
        activo=1
    )
    db.add(cajero)
    db.commit()
    return {"message": "Base de datos reseteada. Usuario admin 'vani' creado."}


def is_internal_request(request: Request) -> bool:
    client_ip = get_client_ip(request)
    try:
        parsed_ip = ipaddress.ip_address(client_ip)
    except ValueError:
        return False

    return any(parsed_ip in network for network in INTERNAL_NETWORKS)


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if forwarded_for:
        return forwarded_for
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def audit_rate_limit(
    db: Session,
    request: Request,
    profile_name: str,
    subject: str,
    retry_after: int,
    username: str,
    comercio_id: int | None = None,
) -> None:
    log_auditoria(
        db,
        username,
        "rate_limited",
        f"perfil={profile_name} ruta={request.url.path} ip={get_client_ip(request)} sujeto={subject} retry_after={retry_after}s",
        comercio_id,
    )
    db.commit()


def apply_rate_limit(
    key: str,
    profile_name: str,
    request: Request,
    db: Session,
    subject: str,
    username: str,
    comercio_id: int | None = None,
) -> None:
    profile = RATE_LIMITS[profile_name]
    limit = profile["limit"]
    if is_internal_request(request):
        limit *= INTERNAL_RATE_LIMIT_MULTIPLIER

    allowed, retry_after = rate_limiter.hit(key, limit, profile["window_seconds"])
    if allowed:
        return

    audit_rate_limit(db, request, profile_name, subject, retry_after, username, comercio_id)

    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Demasiadas solicitudes. Intenta nuevamente en unos segundos.",
        headers={"Retry-After": str(retry_after)},
    )


def enforce_login_rate_limit(request: Request, payload: schemas.LoginRequest, db: Session) -> None:
    client_ip = get_client_ip(request)
    apply_rate_limit(f"login:ip:{client_ip}", "login_ip", request, db, f"ip:{client_ip}", payload.username)
    apply_rate_limit(
        f"login:user:{payload.username.lower()}",
        "login_subject",
        request,
        db,
        f"login:{payload.username.lower()}",
        payload.username,
    )


def enforce_subject_rate_limit(
    request: Request,
    subject: str,
    db: Session,
    username: str,
    comercio_id: int | None = None,
) -> None:
    client_ip = get_client_ip(request)
    normalized_subject = subject.strip().lower()
    apply_rate_limit(f"sensitive:ip:{client_ip}", "sensitive_ip", request, db, f"ip:{client_ip}", username, comercio_id)
    apply_rate_limit(
        f"sensitive:subject:{normalized_subject}",
        "sensitive_subject",
        request,
        db,
        normalized_subject,
        username,
        comercio_id,
    )


def rate_limit_login(request: Request, payload: schemas.LoginRequest, db: Session = Depends(get_db)) -> None:
    enforce_login_rate_limit(request, payload, db)


def rate_limit_acceso_cliente(
    request: Request,
    slug: str,
    payload: schemas.AccesoClienteRequest,
    db: Session = Depends(get_db),
) -> None:
    enforce_subject_rate_limit(request, f"cliente:{slug}:{payload.telefono}", db, "cliente-publico")


def rate_limit_mis_comercios(
    request: Request,
    payload: schemas.AccesoClienteRequest,
    db: Session = Depends(get_db),
) -> None:
    enforce_subject_rate_limit(request, f"mis-comercios:{payload.telefono}", db, "cliente-global")


def rate_limit_cuenta_cliente_comercio(
    request: Request,
    slug: str,
    public_id: str,
    db: Session = Depends(get_db),
) -> None:
    enforce_subject_rate_limit(request, f"cuenta:{slug}:{public_id}", db, "cliente-cuenta")


def rate_limit_cuenta_cliente_global(
    request: Request,
    public_id: str,
    db: Session = Depends(get_db),
) -> None:
    enforce_subject_rate_limit(request, f"cuenta-global:{public_id}", db, "cliente-cuenta-global")


def create_access_token(
    username: str,
    role: str,
    comercio_id: int | None = None,
    comercio_slug: str | None = None,
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": username,
        "role": role,
        "exp": expire,
    }
    if comercio_id is not None:
        payload["comercio_id"] = comercio_id
    if comercio_slug is not None:
        payload["comercio_slug"] = comercio_slug
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def log_auditoria(
    db: Session,
    username: str,
    accion: str,
    detalle: str | None = None,
    comercio_id: int | None = None,
) -> None:
    evento = models.AuditoriaAccion(
        comercio_id=comercio_id,
        username=username,
        accion=accion,
        detalle=detalle,
    )
    db.add(evento)


def build_cajero_response(cajero: models.Cajero) -> schemas.CajeroResponse:
    return schemas.CajeroResponse(
        id=cajero.id,
        username=cajero.username,
        nombre_mostrado=cajero.nombre_mostrado,
        rol=cajero.rol,
        activo=bool(cajero.activo),
    )


def contar_jefes_activos(db: Session, comercio_id: int, excluding_id: int | None = None) -> int:
    query = db.query(models.Cajero).filter(
        models.Cajero.comercio_id == comercio_id,
        models.Cajero.rol == "jefe",
        models.Cajero.activo == 1,
    )
    if excluding_id is not None:
        query = query.filter(models.Cajero.id != excluding_id)
    return query.count()


def get_estado_login(db: Session, login_key: str) -> models.EstadoLoginCajero:
    estado = db.query(models.EstadoLoginCajero).filter(models.EstadoLoginCajero.username == login_key).first()
    if estado:
        return estado

    estado = models.EstadoLoginCajero(username=login_key, intentos_fallidos=0, bloqueado_hasta=None)
    db.add(estado)
    db.flush()
    return estado


def get_comercio_by_slug(db: Session, slug: str) -> models.Comercio:
    comercio = db.query(models.Comercio).filter(models.Comercio.slug == slug).first()
    if not comercio:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comercio no encontrado")
    return comercio


def build_comercio_response(comercio: models.Comercio) -> schemas.ComercioBrandingResponse:
    return schemas.ComercioBrandingResponse(
        slug=comercio.slug,
        nombre=comercio.nombre,
        logo_url=comercio.logo_url,
        color_primario=comercio.color_primario,
        color_secundario=comercio.color_secundario,
        visitas_objetivo=comercio.visitas_objetivo,
        recompensa_nombre=comercio.recompensa_nombre,
        descripcion=comercio.descripcion,
        momento_recomendado=comercio.momento_recomendado,
        mensaje_contextual=comercio.mensaje_contextual,
        suscripcion=build_suscripcion_response(comercio),
    )


def build_suscripcion_response(comercio: models.Comercio) -> schemas.SuscripcionComercioResponse:
    return schemas.SuscripcionComercioResponse(
        plan=comercio.suscripcion_plan or "mensual",
        estado=comercio.suscripcion_estado or "activa",
        monto_mxn=comercio.suscripcion_monto_mxn or 0,
        proximo_cobro=comercio.suscripcion_proximo_cobro.isoformat() if comercio.suscripcion_proximo_cobro else None,
        notas=comercio.suscripcion_notas,
    )


def delete_managed_logo_file(logo_url: str | None) -> None:
    if not logo_url:
        return

    parsed = urlparse(logo_url)
    path = parsed.path if parsed.scheme else logo_url
    if not path.startswith("/static/logos/"):
        return

    file_name = Path(path).name
    file_path = UPLOAD_DIR / file_name
    if file_path.exists():
        file_path.unlink(missing_ok=True)


def mask_phone(phone: str) -> str:
    visible_suffix = phone[-4:] if len(phone) >= 4 else phone
    hidden_prefix = "*" * max(0, len(phone) - len(visible_suffix))
    return f"{hidden_prefix}{visible_suffix}"


def build_cliente_response(cliente: models.Cliente, comercio: models.Comercio) -> schemas.ClienteCuentaResponse:
    account_url = f"{PUBLIC_BASE_URL}/c/{cliente.public_id}"
    return schemas.ClienteCuentaResponse(
        comercio=build_comercio_response(comercio),
        public_id=cliente.public_id,
        telefono_mascarado=mask_phone(cliente.telefono),
        visitas_actuales=cliente.visitas,
        objetivo_visitas=comercio.visitas_objetivo,
        recompensas_total=cliente.recompensas_total,
        account_url=account_url,
        qr_value=account_url,
    )


def registrar_visita_a_cliente(
    db: Session,
    comercio: models.Comercio,
    cliente: models.Cliente,
    username: str,
) -> schemas.RegistrarVisitaResponse:
    cliente.visitas += 1

    if cliente.visitas >= comercio.visitas_objetivo:
        cliente.visitas = 0
        cliente.recompensas_total += 1
        log_auditoria(
            db,
            username,
            "recompensa_entregada",
            f"Telefono {cliente.telefono} | recompensa {comercio.recompensa_nombre}",
            comercio.id,
        )
        db.commit()
        db.refresh(cliente)
        return schemas.RegistrarVisitaResponse(
            estado="recompensa",
            mensaje=f"¡El cliente ganó su recompensa: {comercio.recompensa_nombre}!",
            visitas=cliente.visitas,
            cliente=build_cliente_response(cliente, comercio),
        )

    log_auditoria(
        db,
        username,
        "visita_registrada",
        f"Telefono {cliente.telefono} | visitas {cliente.visitas}",
        comercio.id,
    )
    db.commit()
    db.refresh(cliente)
    return schemas.RegistrarVisitaResponse(
        estado="exito",
        mensaje="Visita registrada correctamente",
        visitas=cliente.visitas,
        cliente=build_cliente_response(cliente, comercio),
    )


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict[str, str | int | None]:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        role = payload.get("role", "cajero")
        comercio_id = payload.get("comercio_id")
        comercio_slug = payload.get("comercio_slug")
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido o expirado",
        ) from exc

    if not username or role not in {"admin", "jefe", "cajero"}:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido",
        )

    if role != "admin" and (not comercio_id or not comercio_slug):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido",
        )

    return {
        "username": username,
        "role": role,
        "comercio_id": comercio_id,
        "comercio_slug": comercio_slug,
    }


def ensure_admin(auth: dict[str, str | int | None]) -> None:
    if auth.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo administrador")


def ensure_jefe_or_admin(auth: dict[str, str | int | None]) -> None:
    if auth.get("role") not in {"jefe", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso solo para jefe o administrador")


def rate_limit_registrar_visita(
    request: Request,
    auth: dict[str, str | int] = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    if auth.get("role") == "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="El administrador no registra visitas")
    enforce_subject_rate_limit(request, f"{auth['comercio_slug']}:{auth['username']}", db, str(auth["username"]), int(auth["comercio_id"]))


def rate_limit_registrar_visita_qr(
    request: Request,
    payload: schemas.RegistrarVisitaQrRequest,
    auth: dict[str, str | int] = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    if auth.get("role") == "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="El administrador no registra visitas")
    enforce_subject_rate_limit(
        request,
        f"{auth['comercio_slug']}:{auth['username']}:{payload.public_id}",
        db,
        str(auth["username"]),
        int(auth["comercio_id"]),
    )


def rate_limit_configuracion(
    request: Request,
    auth: dict[str, str | int] = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    if auth.get("role") == "admin":
        return
    enforce_subject_rate_limit(request, f"config:{auth['comercio_slug']}:{auth['username']}", db, str(auth["username"]), int(auth["comercio_id"]))


def rate_limit_admin_actions(
    request: Request,
    auth: dict[str, str | int | None] = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    ensure_admin(auth)
    enforce_subject_rate_limit(request, f"admin:{auth['username']}:{request.url.path}", db, str(auth["username"]))


@app.get("/health")
def health() -> dict:
    import os as _os
    logos_dir = UPLOAD_DIR
    logos_files = []
    try:
        logos_files = [f.name for f in logos_dir.iterdir() if f.is_file()]
    except Exception:
        logos_files = []
    return {
        "status": "ok",
        "rate_limit_backend": RATE_LIMIT_BACKEND,
        "uploads_base_dir": str(UPLOADS_BASE_DIR),
        "upload_dir": str(UPLOAD_DIR),
        "upload_dir_exists": UPLOAD_DIR.exists(),
        "logos_count": len(logos_files),
        "logos": logos_files[:5],
    }


@app.post("/analytics/eventos", response_model=schemas.AnalyticsEventResponse)
def registrar_evento_analitico(
    payload: schemas.AnalyticsEventRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    comercio = get_comercio_by_slug(db, payload.comercio_slug)
    detalle = (
        f"evento={payload.evento} origen={payload.origen} public_id={payload.public_id or '-'} "
        f"ruta={request.url.path} ip={get_client_ip(request)}"
    )
    log_auditoria(db, "cliente-analytics", "analytics_evento", detalle, comercio.id)
    db.commit()
    return schemas.AnalyticsEventResponse(status="ok")


@app.get("/analytics/resumen/comercio", response_model=schemas.AnalyticsSummaryResponse)
def obtener_resumen_analitico_comercio(
    desde: date | None = Query(default=None),
    hasta: date | None = Query(default=None),
    db: Session = Depends(get_db),
    auth: dict[str, str | int] = Depends(get_current_user),
):
    if auth.get("role") == "admin":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usa panel admin para metricas globales")

    if desde and hasta and desde > hasta:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Rango de fechas invalido")

    comercio_id = int(auth["comercio_id"])
    base_query = db.query(models.AuditoriaAccion).filter(
        models.AuditoriaAccion.comercio_id == comercio_id,
        models.AuditoriaAccion.accion == "analytics_evento",
    )

    if desde:
        desde_dt = datetime(desde.year, desde.month, desde.day)
        base_query = base_query.filter(models.AuditoriaAccion.creado_en >= desde_dt)
    if hasta:
        hasta_dt_exclusive = datetime(hasta.year, hasta.month, hasta.day) + timedelta(days=1)
        base_query = base_query.filter(models.AuditoriaAccion.creado_en < hasta_dt_exclusive)

    hero_clicks = base_query.filter(
        models.AuditoriaAccion.detalle.contains("evento=abrir_cuenta_cliente"),
        models.AuditoriaAccion.detalle.contains("origen=hero"),
    ).count()
    card_clicks = base_query.filter(
        models.AuditoriaAccion.detalle.contains("evento=abrir_cuenta_cliente"),
        models.AuditoriaAccion.detalle.contains("origen=card"),
    ).count()
    return schemas.AnalyticsSummaryResponse(
        hero_clicks=hero_clicks,
        card_clicks=card_clicks,
        wallet_apple_clicks=0,
        wallet_google_clicks=0,
        total_clicks=hero_clicks + card_clicks,
    )


@app.post("/comercios", response_model=schemas.ComercioCreateResponse)
def crear_comercio(
    payload: schemas.ComercioCreateRequest,
    db: Session = Depends(get_db),
    auth: dict[str, str | int | None] = Depends(get_current_user),
    _: None = Depends(rate_limit_admin_actions),
):
    ensure_admin(auth)

    existente = db.query(models.Comercio).filter(models.Comercio.slug == payload.slug).first()
    if existente:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ese slug de comercio ya existe")

    usuario_existente = db.query(models.Cajero).filter(models.Cajero.username == payload.jefe_username).first()
    if usuario_existente:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ese usuario de jefe ya existe. Usa uno unico")

    comercio = models.Comercio(
        slug=payload.slug,
        nombre=payload.nombre,
        color_primario=payload.color_primario,
        color_secundario=payload.color_secundario,
        visitas_objetivo=payload.visitas_objetivo,
        recompensa_nombre=payload.recompensa_nombre,
        descripcion=payload.descripcion,
    )
    db.add(comercio)
    db.flush()

    cajero = models.Cajero(
        comercio_id=comercio.id,
        username=payload.jefe_username,
        password=hash_password(payload.jefe_password),
        nombre_mostrado=payload.jefe_nombre_mostrado,
        rol="jefe",
        activo=1,
    )
    db.add(cajero)
    log_auditoria(db, str(auth["username"]), "comercio_creado", f"Nuevo comercio {payload.slug}", comercio.id)
    db.commit()
    db.refresh(comercio)
    db.refresh(cajero)

    return schemas.ComercioCreateResponse(
        comercio=build_comercio_response(comercio),
        jefe=build_cajero_response(cajero),
    )


@app.post(
    "/login",
    response_model=schemas.LoginResponse,
    responses={429: {"model": schemas.ErrorResponse}},
)
def login(
    payload: schemas.LoginRequest,
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit_login),
):
    login_key = payload.username.lower()
    estado = get_estado_login(db, login_key)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    admin = db.query(models.AdminUsuario).filter(models.AdminUsuario.username == payload.username).first()
    if admin:
        if not admin.activo:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario desactivado")

        if estado.bloqueado_hasta and estado.bloqueado_hasta > now:
            log_auditoria(
                db,
                payload.username,
                "login_bloqueado",
                f"Bloqueado hasta {estado.bloqueado_hasta.isoformat()}",
            )
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Cuenta bloqueada temporalmente. Intenta nuevamente en unos minutos.",
            )

        if not verify_password(admin.password, payload.password):
            estado.intentos_fallidos += 1
            detalle = f"Intento fallido {estado.intentos_fallidos}/{MAX_LOGIN_FAILED_ATTEMPTS}"
            log_auditoria(db, payload.username, "login_fallido", detalle)

            if estado.intentos_fallidos >= MAX_LOGIN_FAILED_ATTEMPTS:
                estado.bloqueado_hasta = now + timedelta(minutes=LOGIN_LOCK_MINUTES)
                log_auditoria(
                    db,
                    payload.username,
                    "login_bloqueado_activado",
                    f"Bloqueado hasta {estado.bloqueado_hasta.isoformat()}",
                )
                db.commit()
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Demasiados intentos fallidos. Cuenta bloqueada temporalmente.",
                )

            db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales invalidas")

        estado.intentos_fallidos = 0
        estado.bloqueado_hasta = None
        log_auditoria(db, payload.username, "login_exitoso", "Inicio de sesion admin correcto")
        db.commit()

        token = create_access_token(payload.username, "admin")
        return schemas.LoginResponse(
            access_token=token,
            rol="admin",
            comercio=None,
        )

    cajeros = db.query(models.Cajero).filter(models.Cajero.username == payload.username).all()
    if not cajeros:
        estado.intentos_fallidos += 1
        detalle = f"Intento fallido {estado.intentos_fallidos}/{MAX_LOGIN_FAILED_ATTEMPTS}"
        log_auditoria(db, payload.username, "login_fallido", detalle)

        if estado.intentos_fallidos >= MAX_LOGIN_FAILED_ATTEMPTS:
            estado.bloqueado_hasta = now + timedelta(minutes=LOGIN_LOCK_MINUTES)
            log_auditoria(
                db,
                payload.username,
                "login_bloqueado_activado",
                f"Bloqueado hasta {estado.bloqueado_hasta.isoformat()}",
            )
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Demasiados intentos fallidos. Cuenta bloqueada temporalmente.",
            )

        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales invalidas",
        )

    if len(cajeros) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Usuario ambiguo. Pide al administrador un usuario unico.",
        )

    cajero = cajeros[0]
    if not cajero.activo:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario desactivado")

    comercio = db.query(models.Comercio).filter(models.Comercio.id == cajero.comercio_id).first()
    if not comercio:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Comercio invalido")

    if (comercio.suscripcion_estado or "activa") in {"suspendida", "cancelada"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La suscripcion del comercio esta inactiva. Contacta al administrador.",
        )

    if estado.bloqueado_hasta and estado.bloqueado_hasta > now:
        log_auditoria(
            db,
            payload.username,
            "login_bloqueado",
            f"Bloqueado hasta {estado.bloqueado_hasta.isoformat()}",
            comercio.id,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Cuenta bloqueada temporalmente. Intenta nuevamente en unos minutos.",
        )

    if not verify_password(cajero.password, payload.password):
        estado.intentos_fallidos += 1
        detalle = f"Intento fallido {estado.intentos_fallidos}/{MAX_LOGIN_FAILED_ATTEMPTS}"
        log_auditoria(db, payload.username, "login_fallido", detalle, comercio.id)

        if estado.intentos_fallidos >= MAX_LOGIN_FAILED_ATTEMPTS:
            estado.bloqueado_hasta = now + timedelta(minutes=LOGIN_LOCK_MINUTES)
            log_auditoria(
                db,
                payload.username,
                "login_bloqueado_activado",
                f"Bloqueado hasta {estado.bloqueado_hasta.isoformat()}",
                comercio.id,
            )
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Demasiados intentos fallidos. Cuenta bloqueada temporalmente.",
            )

        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales invalidas",
        )

    estado.intentos_fallidos = 0
    estado.bloqueado_hasta = None
    log_auditoria(db, payload.username, "login_exitoso", "Inicio de sesion correcto", comercio.id)
    db.commit()

    token = create_access_token(payload.username, cajero.rol, comercio.id, comercio.slug)
    return schemas.LoginResponse(
        access_token=token,
        rol=cajero.rol,
        comercio=build_comercio_response(comercio),
    )


@app.post("/registrar-visita", response_model=schemas.RegistrarVisitaResponse)
def registrar_visita(
    payload: schemas.RegistrarVisitaRequest,
    db: Session = Depends(get_db),
    auth: dict[str, str | int] = Depends(get_current_user),
    _: None = Depends(rate_limit_registrar_visita),
):
    comercio = db.query(models.Comercio).filter(models.Comercio.id == auth["comercio_id"]).first()
    if not comercio:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Comercio invalido")

    cliente = db.query(models.Cliente).filter(
        models.Cliente.comercio_id == comercio.id,
        models.Cliente.telefono == payload.telefono,
    ).first()

    if not cliente:
        cliente = models.Cliente(comercio_id=comercio.id, telefono=payload.telefono, visitas=1)
        db.add(cliente)
        log_auditoria(db, str(auth["username"]), "visita_registrada", f"Telefono {payload.telefono} | visitas 1", comercio.id)
        db.commit()
        db.refresh(cliente)
        return schemas.RegistrarVisitaResponse(
            estado="exito",
            mensaje="Visita registrada correctamente",
            visitas=cliente.visitas,
            cliente=build_cliente_response(cliente, comercio),
        )

    return registrar_visita_a_cliente(db, comercio, cliente, str(auth["username"]))


@app.post("/registrar-visita-qr", response_model=schemas.RegistrarVisitaResponse)
def registrar_visita_qr(
    payload: schemas.RegistrarVisitaQrRequest,
    db: Session = Depends(get_db),
    auth: dict[str, str | int] = Depends(get_current_user),
    _: None = Depends(rate_limit_registrar_visita_qr),
):
    comercio = db.query(models.Comercio).filter(models.Comercio.id == auth["comercio_id"]).first()
    if not comercio:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Comercio invalido")

    cliente = db.query(models.Cliente).filter(
        models.Cliente.public_id == payload.public_id,
        models.Cliente.comercio_id == comercio.id,
    ).first()
    if not cliente:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado")

    log_auditoria(db, str(auth["username"]), "visita_qr_escaneada", f"Cliente {payload.public_id}", comercio.id)
    return registrar_visita_a_cliente(db, comercio, cliente, str(auth["username"]))


@app.put("/comercios/configuracion", response_model=schemas.ComercioBrandingResponse)
def actualizar_comercio_configuracion(
    payload: schemas.ComercioConfigUpdateRequest,
    db: Session = Depends(get_db),
    auth: dict[str, str | int] = Depends(get_current_user),
    _: None = Depends(rate_limit_configuracion),
):
    ensure_jefe_or_admin(auth)

    if auth.get("role") == "admin":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Un administrador debe gestionar configuracion desde panel admin")

    comercio = db.query(models.Comercio).filter(models.Comercio.id == auth["comercio_id"]).first()
    if not comercio:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Comercio invalido")

    comercio.nombre = payload.nombre
    previous_logo_url = comercio.logo_url
    comercio.logo_url = payload.logo_url
    comercio.color_primario = payload.color_primario
    comercio.color_secundario = payload.color_secundario
    comercio.visitas_objetivo = payload.visitas_objetivo
    comercio.recompensa_nombre = payload.recompensa_nombre
    comercio.descripcion = payload.descripcion
    comercio.momento_recomendado = payload.momento_recomendado
    comercio.mensaje_contextual = payload.mensaje_contextual
    if previous_logo_url != comercio.logo_url and payload.logo_url != previous_logo_url:
        delete_managed_logo_file(previous_logo_url)
    log_auditoria(db, str(auth["username"]), "comercio_actualizado", "Branding y metas actualizadas", comercio.id)
    db.commit()
    db.refresh(comercio)
    return build_comercio_response(comercio)


@app.get("/cajeros", response_model=list[schemas.CajeroResponse])
def listar_cajeros(
    db: Session = Depends(get_db),
    auth: dict[str, str | int | None] = Depends(get_current_user),
):
    ensure_jefe_or_admin(auth)
    if auth.get("role") == "admin":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usa el panel admin para ver cajeros por comercio")

    comercio_id = int(auth["comercio_id"])
    cajeros = db.query(models.Cajero).filter(models.Cajero.comercio_id == comercio_id).order_by(models.Cajero.id.desc()).all()
    return [build_cajero_response(cajero) for cajero in cajeros]


@app.get("/admin/comercios", response_model=list[schemas.AdminComercioResumenResponse])
def listar_comercios_admin(
    db: Session = Depends(get_db),
    auth: dict[str, str | int | None] = Depends(get_current_user),
    _: None = Depends(rate_limit_admin_actions),
):
    ensure_admin(auth)
    comercios = db.query(models.Comercio).order_by(models.Comercio.nombre.asc()).all()
    return [
        schemas.AdminComercioResumenResponse(
            slug=item.slug,
            nombre=item.nombre,
            suscripcion=build_suscripcion_response(item),
        )
        for item in comercios
    ]


@app.patch("/admin/comercios/{slug}/suscripcion", response_model=schemas.AdminComercioResumenResponse)
def actualizar_suscripcion_comercio_admin(
    slug: str,
    payload: schemas.AdminSuscripcionUpdateRequest,
    db: Session = Depends(get_db),
    auth: dict[str, str | int | None] = Depends(get_current_user),
    _: None = Depends(rate_limit_admin_actions),
):
    ensure_admin(auth)
    comercio = get_comercio_by_slug(db, slug)

    comercio.suscripcion_plan = payload.plan
    comercio.suscripcion_estado = payload.estado
    comercio.suscripcion_monto_mxn = payload.monto_mxn
    comercio.suscripcion_proximo_cobro = date.fromisoformat(payload.proximo_cobro) if payload.proximo_cobro else None
    comercio.suscripcion_notas = payload.notas

    log_auditoria(
        db,
        str(auth["username"]),
        "suscripcion_actualizada",
        f"Comercio {slug} estado={payload.estado} plan={payload.plan} monto={payload.monto_mxn}",
        comercio.id,
    )
    db.commit()
    db.refresh(comercio)
    return schemas.AdminComercioResumenResponse(
        slug=comercio.slug,
        nombre=comercio.nombre,
        suscripcion=build_suscripcion_response(comercio),
    )


@app.post("/admin/comercios/{slug}/jefes", response_model=schemas.CajeroResponse)
def crear_jefe_para_comercio(
    slug: str,
    payload: schemas.AdminJefeCreateRequest,
    db: Session = Depends(get_db),
    auth: dict[str, str | int | None] = Depends(get_current_user),
    _: None = Depends(rate_limit_admin_actions),
):
    ensure_admin(auth)
    comercio = get_comercio_by_slug(db, slug)

    existe = db.query(models.Cajero).filter(models.Cajero.username == payload.username).first()
    if existe:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ese usuario ya existe. Usa un nombre de usuario unico")

    jefe = models.Cajero(
        comercio_id=comercio.id,
        username=payload.username,
        password=hash_password(payload.password),
        nombre_mostrado=payload.nombre_mostrado,
        rol="jefe",
        activo=1,
    )
    db.add(jefe)
    log_auditoria(db, str(auth["username"]), "jefe_creado", f"Nuevo jefe {payload.username} para {slug}", comercio.id)
    db.commit()
    db.refresh(jefe)
    return build_cajero_response(jefe)


@app.get("/admin/comercios/{slug}/personal", response_model=schemas.AdminPersonalComercioResponse)
def listar_personal_por_comercio_admin(
    slug: str,
    db: Session = Depends(get_db),
    auth: dict[str, str | int | None] = Depends(get_current_user),
    _: None = Depends(rate_limit_admin_actions),
):
    ensure_admin(auth)
    comercio = get_comercio_by_slug(db, slug)
    personal = db.query(models.Cajero).filter(models.Cajero.comercio_id == comercio.id).order_by(models.Cajero.rol.desc(), models.Cajero.id.asc()).all()
    return schemas.AdminPersonalComercioResponse(
        comercio=schemas.AdminComercioResumenResponse(
            slug=comercio.slug,
            nombre=comercio.nombre,
            suscripcion=build_suscripcion_response(comercio),
        ),
        personal=[build_cajero_response(item) for item in personal],
    )


@app.patch("/admin/cajeros/{cajero_id}/rol", response_model=schemas.CajeroResponse)
def cambiar_rol_cajero_admin(
    cajero_id: int,
    payload: schemas.AdminCambiarRolRequest,
    db: Session = Depends(get_db),
    auth: dict[str, str | int | None] = Depends(get_current_user),
    _: None = Depends(rate_limit_admin_actions),
):
    ensure_admin(auth)
    cajero = db.query(models.Cajero).filter(models.Cajero.id == cajero_id).first()
    if not cajero:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    if cajero.rol == payload.rol:
        return build_cajero_response(cajero)

    if cajero.rol == "jefe" and payload.rol == "cajero" and contar_jefes_activos(db, cajero.comercio_id, cajero.id) == 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El comercio debe mantener al menos un jefe activo")

    cajero.rol = payload.rol
    log_auditoria(db, str(auth["username"]), "rol_actualizado", f"Usuario {cajero.username} ahora es {payload.rol}", cajero.comercio_id)
    db.commit()
    db.refresh(cajero)
    return build_cajero_response(cajero)


@app.patch("/admin/cajeros/{cajero_id}/estado", response_model=schemas.CajeroResponse)
def cambiar_estado_cajero_admin(
    cajero_id: int,
    payload: schemas.AdminCambiarEstadoRequest,
    db: Session = Depends(get_db),
    auth: dict[str, str | int | None] = Depends(get_current_user),
    _: None = Depends(rate_limit_admin_actions),
):
    ensure_admin(auth)
    cajero = db.query(models.Cajero).filter(models.Cajero.id == cajero_id).first()
    if not cajero:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    if not payload.activo and cajero.rol == "jefe" and contar_jefes_activos(db, cajero.comercio_id, cajero.id) == 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El comercio debe mantener al menos un jefe activo")

    cajero.activo = 1 if payload.activo else 0
    accion = "usuario_activado" if payload.activo else "usuario_desactivado"
    detalle = f"Usuario {cajero.username} {'activado' if payload.activo else 'desactivado'}"
    log_auditoria(db, str(auth["username"]), accion, detalle, cajero.comercio_id)
    db.commit()
    db.refresh(cajero)
    return build_cajero_response(cajero)


@app.post("/cajeros", response_model=schemas.CajeroResponse)
def crear_cajero(
    payload: schemas.CajeroCreateRequest,
    db: Session = Depends(get_db),
    auth: dict[str, str | int | None] = Depends(get_current_user),
    _: None = Depends(rate_limit_configuracion),
):
    ensure_jefe_or_admin(auth)
    if auth.get("role") == "admin":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usa /admin/comercios/{slug}/jefes para administrar jerarquia")

    comercio_id = int(auth["comercio_id"])
    existe = db.query(models.Cajero).filter(models.Cajero.username == payload.username).first()
    if existe:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ese usuario ya existe. Usa un nombre de usuario unico")

    cajero = models.Cajero(
        comercio_id=comercio_id,
        username=payload.username,
        password=hash_password(payload.password),
        nombre_mostrado=payload.nombre_mostrado,
        rol="cajero",
        activo=1,
    )
    db.add(cajero)
    log_auditoria(db, str(auth["username"]), "cajero_creado", f"Nuevo cajero {payload.username}", comercio_id)
    db.commit()
    db.refresh(cajero)
    return build_cajero_response(cajero)


@app.post("/comercios/configuracion/logo", response_model=schemas.ComercioBrandingResponse)
async def subir_logo_comercio(
    logo: UploadFile = File(...),
    db: Session = Depends(get_db),
    auth: dict[str, str | int] = Depends(get_current_user),
    _: None = Depends(rate_limit_configuracion),
):
    ensure_jefe_or_admin(auth)
    if auth.get("role") == "admin":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Un administrador debe gestionar configuracion desde panel admin")

    comercio = db.query(models.Comercio).filter(models.Comercio.id == auth["comercio_id"]).first()
    if not comercio:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Comercio invalido")

    filename = (logo.filename or "").lower()
    allowed_extensions = (".jpg", ".jpeg", ".png")
    if not filename.endswith(allowed_extensions):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Solo se permiten logos en formato JPG o PNG")

    if logo.content_type not in {"image/jpeg", "image/jpg", "image/png"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo debe ser image/jpeg o image/png")

    content = await logo.read()
    if len(content) > MAX_LOGO_SIZE_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El logo supera el limite de 2 MB")

    is_jpeg = len(content) >= 4 and content.startswith(b"\xff\xd8\xff")
    is_png = len(content) >= 8 and content.startswith(b"\x89PNG\r\n\x1a\n")
    if not (is_jpeg or is_png):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo no es una imagen JPG/PNG valida")

    if filename.endswith(".png"):
        file_suffix = ".png"
    elif filename.endswith(".jpeg"):
        file_suffix = ".jpeg"
    else:
        file_suffix = ".jpg"
    safe_filename = f"{comercio.slug}-{uuid4().hex}{file_suffix}"
    destination = UPLOAD_DIR / safe_filename

    previous_logo_url = comercio.logo_url
    destination.write_bytes(content)

    comercio.logo_url = f"/static/logos/{safe_filename}"
    delete_managed_logo_file(previous_logo_url)
    log_auditoria(db, str(auth["username"]), "logo_actualizado", f"Logo {safe_filename}", comercio.id)
    db.commit()
    db.refresh(comercio)
    return build_comercio_response(comercio)


@app.get("/comercios/{slug}", response_model=schemas.ComercioBrandingResponse)
def obtener_comercio(slug: str, db: Session = Depends(get_db)):
    comercio = get_comercio_by_slug(db, slug)
    return build_comercio_response(comercio)


@app.post("/comercios/{slug}/acceso-cliente", response_model=schemas.ClienteCuentaResponse)
def acceso_cliente(
    slug: str,
    payload: schemas.AccesoClienteRequest,
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit_acceso_cliente),
):
    comercio = get_comercio_by_slug(db, slug)
    cliente = db.query(models.Cliente).filter(
        models.Cliente.comercio_id == comercio.id,
        models.Cliente.telefono == payload.telefono,
    ).first()
    if not cliente:
        cliente = models.Cliente(comercio_id=comercio.id, telefono=payload.telefono, visitas=0)
        db.add(cliente)
        log_auditoria(db, "cliente-publico", "cliente_creado_desde_acceso", f"Telefono {payload.telefono}", comercio.id)
        db.commit()
        db.refresh(cliente)

    return build_cliente_response(cliente, comercio)


@app.post("/clientes/mis-comercios", response_model=schemas.ClienteMisComerciosResponse)
def obtener_mis_comercios(
    payload: schemas.AccesoClienteRequest,
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit_mis_comercios),
):
    clientes = db.query(models.Cliente).filter(models.Cliente.telefono == payload.telefono).all()
    if not clientes:
        return schemas.ClienteMisComerciosResponse(
            telefono_mascarado=mask_phone(payload.telefono),
            cuentas=[],
        )

    comercios = db.query(models.Comercio).all()
    comercios_por_id = {comercio.id: comercio for comercio in comercios}

    cuentas: list[schemas.ClienteCuentaResponse] = []
    for cliente in clientes:
        comercio = comercios_por_id.get(cliente.comercio_id)
        if not comercio:
            continue
        cuentas.append(build_cliente_response(cliente, comercio))

    if not cuentas:
        return schemas.ClienteMisComerciosResponse(
            telefono_mascarado=mask_phone(payload.telefono),
            cuentas=[],
        )

    cuentas.sort(key=lambda item: item.comercio.nombre.lower())
    return schemas.ClienteMisComerciosResponse(
        telefono_mascarado=mask_phone(payload.telefono),
        cuentas=cuentas,
    )


@app.get("/comercios/{slug}/clientes/{public_id}", response_model=schemas.ClienteCuentaResponse)
def obtener_cuenta_cliente_comercio(
    slug: str,
    public_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit_cuenta_cliente_comercio),
):
    comercio = get_comercio_by_slug(db, slug)
    cliente = db.query(models.Cliente).filter(
        models.Cliente.comercio_id == comercio.id,
        models.Cliente.public_id == public_id,
    ).first()
    if not cliente:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado")

    return build_cliente_response(cliente, comercio)


@app.get("/clientes/{public_id}", response_model=schemas.ClienteCuentaResponse)
def obtener_cuenta_cliente(
    public_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit_cuenta_cliente_global),
):
    cliente = db.query(models.Cliente).filter(models.Cliente.public_id == public_id).first()
    if not cliente:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado")

    comercio = db.query(models.Comercio).filter(models.Comercio.id == cliente.comercio_id).first()
    if not comercio:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comercio no encontrado")

    return build_cliente_response(cliente, comercio)

@app.put("/cajeros/me/password", response_model=schemas.CajeroResponse)
def cambiar_mi_password(
    payload: schemas.CambiarPasswordRequest,
    db: Session = Depends(get_db),
    auth: dict[str, str | int | None] = Depends(get_current_active_user),
):
    ensure_jefe_or_admin(auth)
    if auth.get("role") != "jefe":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo los jefes pueden cambiar su contrase�a directamente"
        )
    
    cajero = db.query(models.Cajero).filter(models.Cajero.id == auth["user_id"]).first()
    if not cajero:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cajero no encontrado")
    
    from security_utils import hash_password
    cajero.password_hash = hash_password(payload.password)
    
    log_auditoria(db, str(auth["username"]), "password_actualizado", "El jefe ha actualizado su contrase�a", int(auth["comercio_id"]))
    db.commit()
    db.refresh(cajero)
    
    return build_cajero_response(cajero)
