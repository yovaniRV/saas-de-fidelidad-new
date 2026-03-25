import os
import ipaddress
import secrets
from pathlib import Path
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from urllib.parse import urlparse

import jwt
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy.orm import Session

import models
import schemas
from database import SessionLocal, engine, ensure_sqlite_schema
from rate_limit import build_rate_limiter
from security_utils import verify_password

models.Base.metadata.create_all(bind=engine)
ensure_sqlite_schema()

app = FastAPI(title="SaaS Fidelidad API")

SECRET_KEY = os.getenv("JWT_SECRET_KEY") or secrets.token_urlsafe(48)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8
MAX_LOGIN_FAILED_ATTEMPTS = 5
LOGIN_LOCK_MINUTES = 5
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:4200")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
UPLOAD_DIR = Path(__file__).resolve().parent / "uploads" / "logos"
MAX_LOGO_SIZE_BYTES = 2 * 1024 * 1024
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver,*.up.railway.app").split(",")
    if host.strip()
]
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:4200,http://127.0.0.1:4200").split(",")
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
app.mount("/static", StaticFiles(directory=str(UPLOAD_DIR.parent)), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
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

    if path.startswith("/comercios/configuracion") or path.startswith("/clientes/"):
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
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), geolocation=(), microphone=()"
    response.headers["X-Permitted-Cross-Domain-Policies"] = "none"

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
        f"login:user:{payload.comercio_slug}:{payload.username.lower()}",
        "login_subject",
        request,
        db,
        f"login:{payload.comercio_slug}:{payload.username.lower()}",
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


def create_access_token(username: str, comercio_id: int, comercio_slug: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": username,
        "comercio_id": comercio_id,
        "comercio_slug": comercio_slug,
        "exp": expire,
    }
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
    logo_url = comercio.logo_url
    if logo_url and logo_url.startswith("/static/"):
        logo_url = f"{API_BASE_URL}{logo_url}"

    return schemas.ComercioBrandingResponse(
        slug=comercio.slug,
        nombre=comercio.nombre,
        logo_url=logo_url,
        color_primario=comercio.color_primario,
        color_secundario=comercio.color_secundario,
        visitas_objetivo=comercio.visitas_objetivo,
        recompensa_nombre=comercio.recompensa_nombre,
        descripcion=comercio.descripcion,
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


def build_wallet_links(comercio: models.Comercio, public_id: str) -> schemas.WalletLinks:
    account_url = f"{PUBLIC_BASE_URL}/comercio/{comercio.slug}/cliente/{public_id}"
    return schemas.WalletLinks(
        apple=f"{account_url}?wallet=apple",
        google=f"{account_url}?wallet=google",
    )


def build_cliente_response(cliente: models.Cliente, comercio: models.Comercio) -> schemas.ClienteCuentaResponse:
    account_url = f"{PUBLIC_BASE_URL}/comercio/{comercio.slug}/cliente/{cliente.public_id}"
    return schemas.ClienteCuentaResponse(
        comercio=build_comercio_response(comercio),
        public_id=cliente.public_id,
        telefono_mascarado=mask_phone(cliente.telefono),
        visitas_actuales=cliente.visitas,
        objetivo_visitas=comercio.visitas_objetivo,
        recompensas_total=cliente.recompensas_total,
        account_url=account_url,
        qr_value=account_url,
        wallet_links=build_wallet_links(comercio, cliente.public_id),
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


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict[str, str | int]:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        comercio_id = payload.get("comercio_id")
        comercio_slug = payload.get("comercio_slug")
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido o expirado",
        ) from exc

    if not username or not comercio_id or not comercio_slug:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido",
        )
    return {
        "username": username,
        "comercio_id": comercio_id,
        "comercio_slug": comercio_slug,
    }


def rate_limit_registrar_visita(
    request: Request,
    auth: dict[str, str | int] = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    enforce_subject_rate_limit(request, f"{auth['comercio_slug']}:{auth['username']}", db, str(auth["username"]), int(auth["comercio_id"]))


def rate_limit_registrar_visita_qr(
    request: Request,
    payload: schemas.RegistrarVisitaQrRequest,
    auth: dict[str, str | int] = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
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
    enforce_subject_rate_limit(request, f"config:{auth['comercio_slug']}:{auth['username']}", db, str(auth["username"]), int(auth["comercio_id"]))


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "rate_limit_backend": RATE_LIMIT_BACKEND,
    }


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
    comercio = get_comercio_by_slug(db, payload.comercio_slug)
    login_key = f"{payload.comercio_slug}:{payload.username}"
    estado = get_estado_login(db, login_key)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

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

    cajero = db.query(models.Cajero).filter(
        models.Cajero.comercio_id == comercio.id,
        models.Cajero.username == payload.username,
    ).first()

    if not cajero or not verify_password(cajero.password, payload.password):
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

    token = create_access_token(payload.username, comercio.id, comercio.slug)
    return schemas.LoginResponse(
        access_token=token,
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
    if previous_logo_url != comercio.logo_url and payload.logo_url != previous_logo_url:
        delete_managed_logo_file(previous_logo_url)
    log_auditoria(db, str(auth["username"]), "comercio_actualizado", "Branding y metas actualizadas", comercio.id)
    db.commit()
    db.refresh(comercio)
    return build_comercio_response(comercio)


@app.post("/comercios/configuracion/logo", response_model=schemas.ComercioBrandingResponse)
async def subir_logo_comercio(
    logo: UploadFile = File(...),
    db: Session = Depends(get_db),
    auth: dict[str, str | int] = Depends(get_current_user),
    _: None = Depends(rate_limit_configuracion),
):
    comercio = db.query(models.Comercio).filter(models.Comercio.id == auth["comercio_id"]).first()
    if not comercio:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Comercio invalido")

    filename = (logo.filename or "").lower()
    if not filename.endswith(".jpg") and not filename.endswith(".jpeg"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Solo se permiten logos en formato JPG")

    if logo.content_type not in {"image/jpeg", "image/jpg"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo debe ser image/jpeg")

    content = await logo.read()
    if len(content) > MAX_LOGO_SIZE_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El logo supera el limite de 2 MB")

    if len(content) < 4 or not content.startswith(b"\xff\xd8\xff"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo no es un JPG valido")

    file_suffix = ".jpg" if filename.endswith(".jpg") else ".jpeg"
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado")

    return build_cliente_response(cliente, comercio)


@app.post("/clientes/mis-comercios", response_model=schemas.ClienteMisComerciosResponse)
def obtener_mis_comercios(
    payload: schemas.AccesoClienteRequest,
    db: Session = Depends(get_db),
    _: None = Depends(rate_limit_mis_comercios),
):
    clientes = db.query(models.Cliente).filter(models.Cliente.telefono == payload.telefono).all()
    if not clientes:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado")

    comercios = db.query(models.Comercio).all()
    comercios_por_id = {comercio.id: comercio for comercio in comercios}

    cuentas: list[schemas.ClienteCuentaResponse] = []
    for cliente in clientes:
        comercio = comercios_por_id.get(cliente.comercio_id)
        if not comercio:
            continue
        cuentas.append(build_cliente_response(cliente, comercio))

    if not cuentas:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado")

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
