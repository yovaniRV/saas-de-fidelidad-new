import re

from pydantic import BaseModel, Field, field_validator


USERNAME_REGEX = re.compile(r"^[a-z0-9][a-z0-9._-]{2,49}$")


def normalize_required(value: str, message: str = "Campo obligatorio") -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(message)
    return normalized


def validate_username(value: str) -> str:
    normalized = normalize_required(value).lower()
    if not USERNAME_REGEX.match(normalized):
        raise ValueError("Usuario invalido: usa 3-50 caracteres [a-z0-9._-]")
    return normalized


def validate_password_strength(value: str) -> str:
    normalized = normalize_required(value)
    if len(normalized) < 6:
        raise ValueError("La contrasena debe tener al menos 6 caracteres")
    if len(normalized) > 72:
        raise ValueError("La contrasena no debe superar 72 caracteres")
    if not any(ch.isalpha() for ch in normalized) or not any(ch.isdigit() for ch in normalized):
        raise ValueError("La contrasena debe incluir letras y numeros")
    return normalized


def validate_hex_color(value: str) -> str:
    normalized = value.strip()
    if len(normalized) != 7 or not normalized.startswith("#"):
        raise ValueError("El color debe estar en formato hexadecimal #RRGGBB")
    int(normalized[1:], 16)
    return normalized.lower()


class ComercioBrandingResponse(BaseModel):
    slug: str
    nombre: str
    logo_url: str | None = None
    color_primario: str
    color_secundario: str
    visitas_objetivo: int
    recompensa_nombre: str
    descripcion: str | None = None
    momento_recomendado: str | None = None
    mensaje_contextual: str | None = None
    suscripcion: "SuscripcionComercioResponse"


class SuscripcionComercioResponse(BaseModel):
    plan: str
    estado: str
    monto_mxn: int
    proximo_cobro: str | None = None
    notas: str | None = None


class AnalyticsEventRequest(BaseModel):
    comercio_slug: str
    public_id: str | None = None
    evento: str
    origen: str

    @field_validator("comercio_slug", "evento", "origen")
    @classmethod
    def validar_textos_evento(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("Campo obligatorio")
        return normalized


class AnalyticsEventResponse(BaseModel):
    status: str


class AnalyticsSummaryResponse(BaseModel):
    hero_clicks: int
    card_clicks: int
    wallet_apple_clicks: int
    wallet_google_clicks: int
    total_clicks: int


class CajeroCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=72)
    nombre_mostrado: str | None = Field(default=None, max_length=120)

    @field_validator("username", "password")
    @classmethod
    def validar_username(cls, value: str) -> str:
        return validate_username(value)

    @field_validator("password")
    @classmethod
    def validar_password_seguro(cls, value: str) -> str:
        return validate_password_strength(value)

    @field_validator("nombre_mostrado")
    @classmethod
    def normalizar_nombre_mostrado(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class CajeroResponse(BaseModel):
    id: int
    username: str
    nombre_mostrado: str | None = None
    rol: str = "cajero"
    activo: bool = True


class ComercioCreateRequest(BaseModel):
    slug: str = Field(..., min_length=3, max_length=80)
    nombre: str = Field(..., min_length=2, max_length=120)
    jefe_username: str = Field(..., min_length=3, max_length=50)
    jefe_password: str = Field(..., min_length=6, max_length=72)
    jefe_nombre_mostrado: str | None = Field(default=None, max_length=120)
    color_primario: str = "#0f766e"
    color_secundario: str = "#f59e0b"
    visitas_objetivo: int = Field(default=5, ge=1, le=50)
    recompensa_nombre: str = Field(default="Bebida gratis", min_length=2, max_length=120)
    descripcion: str | None = Field(default=None, max_length=255)

    @field_validator("slug")
    @classmethod
    def validar_slug(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("Campo obligatorio")
        if len(normalized) > 80:
            raise ValueError("Slug demasiado largo")

        allowed_chars = set("abcdefghijklmnopqrstuvwxyz0123456789-")
        if any(ch not in allowed_chars for ch in normalized):
            raise ValueError("Slug invalido: usa solo minusculas, numeros y guion")
        return normalized

    @field_validator("nombre", "recompensa_nombre")
    @classmethod
    def validar_textos_creacion(cls, value: str) -> str:
        return normalize_required(value)

    @field_validator("jefe_username")
    @classmethod
    def validar_jefe_username(cls, value: str) -> str:
        return validate_username(value)

    @field_validator("jefe_password")
    @classmethod
    def validar_jefe_password_seguro(cls, value: str) -> str:
        return validate_password_strength(value)

    @field_validator("jefe_nombre_mostrado", "descripcion")
    @classmethod
    def normalizar_opcionales(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("color_primario", "color_secundario")
    @classmethod
    def validar_colores_hex_creacion(cls, value: str) -> str:
        return validate_hex_color(value)


class ComercioCreateResponse(BaseModel):
    comercio: ComercioBrandingResponse
    jefe: CajeroResponse


class AdminComercioResumenResponse(BaseModel):
    slug: str
    nombre: str
    suscripcion: SuscripcionComercioResponse


class AdminSuscripcionUpdateRequest(BaseModel):
    plan: str = Field(..., min_length=2, max_length=40)
    estado: str = Field(..., min_length=3, max_length=20)
    monto_mxn: int = Field(..., ge=0, le=1000000)
    proximo_cobro: str | None = None
    notas: str | None = Field(default=None, max_length=255)

    @field_validator("plan")
    @classmethod
    def validar_plan(cls, value: str) -> str:
        normalized = normalize_required(value).lower()
        allowed = {"mensual", "trimestral", "anual", "personalizado"}
        if normalized not in allowed:
            raise ValueError("plan debe ser mensual, trimestral, anual o personalizado")
        return normalized

    @field_validator("estado")
    @classmethod
    def validar_estado(cls, value: str) -> str:
        normalized = normalize_required(value).lower()
        allowed = {"prueba", "activa", "vencida", "suspendida", "cancelada"}
        if normalized not in allowed:
            raise ValueError("estado debe ser prueba, activa, vencida, suspendida o cancelada")
        return normalized

    @field_validator("proximo_cobro")
    @classmethod
    def validar_proximo_cobro(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        # formato YYYY-MM-DD
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", normalized):
            raise ValueError("proximo_cobro debe tener formato YYYY-MM-DD")
        return normalized

    @field_validator("notas")
    @classmethod
    def normalizar_notas(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class AdminPersonalComercioResponse(BaseModel):
    comercio: AdminComercioResumenResponse
    personal: list[CajeroResponse]


class AdminJefeCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=72)
    nombre_mostrado: str | None = Field(default=None, max_length=120)

    @field_validator("username")
    @classmethod
    def validar_username(cls, value: str) -> str:
        return validate_username(value)

    @field_validator("password")
    @classmethod
    def validar_password_seguro(cls, value: str) -> str:
        return validate_password_strength(value)

    @field_validator("nombre_mostrado")
    @classmethod
    def normalizar_nombre_mostrado(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class AdminCambiarRolRequest(BaseModel):
    rol: str

    @field_validator("rol")
    @classmethod
    def validar_rol(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"jefe", "cajero"}:
            raise ValueError("rol debe ser jefe o cajero")
        return normalized


class AdminCambiarEstadoRequest(BaseModel):
    activo: bool


class AdminDesbloqueoLoginResponse(BaseModel):
    username: str
    desbloqueado: bool


class AdminDesbloqueoMasivoResponse(BaseModel):
    desbloqueados: int


class ComercioConfigUpdateRequest(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=120)
    logo_url: str | None = None
    color_primario: str
    color_secundario: str
    visitas_objetivo: int = Field(..., ge=1, le=50)
    recompensa_nombre: str = Field(..., min_length=2, max_length=120)
    descripcion: str | None = Field(default=None, max_length=255)
    momento_recomendado: str | None = None
    mensaje_contextual: str | None = Field(default=None, max_length=160)

    @field_validator("nombre", "recompensa_nombre")
    @classmethod
    def validar_textos_requeridos(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Este campo es obligatorio")
        return normalized

    @field_validator("descripcion")
    @classmethod
    def normalizar_descripcion(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("momento_recomendado")
    @classmethod
    def validar_momento_recomendado(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip().lower()
        if not normalized:
            return None

        allowed = {"desayuno", "almuerzo", "merienda", "cena"}
        if normalized not in allowed:
            raise ValueError("momento_recomendado debe ser desayuno, almuerzo, merienda o cena")
        return normalized

    @field_validator("mensaje_contextual")
    @classmethod
    def normalizar_mensaje_contextual(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("logo_url")
    @classmethod
    def validar_logo_url(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        if not normalized:
            return None

        allowed_prefixes = (
            "https://",
            "http://localhost:8000/static/",
            "http://127.0.0.1:8000/static/",
            "/static/",
        )
        if not normalized.startswith(allowed_prefixes):
            raise ValueError("El logo debe usar HTTPS o un archivo subido al servidor")
        return normalized

    @field_validator("color_primario", "color_secundario")
    @classmethod
    def validar_colores_hex(cls, value: str) -> str:
        return validate_hex_color(value)


class RegistrarVisitaRequest(BaseModel):
    telefono: str = Field(
        ...,
        pattern=r"^\d{1,10}$",
        description="Numero de telefono de hasta 10 digitos",
    )


class RegistrarVisitaQrRequest(BaseModel):
    public_id: str


class ClienteCuentaResponse(BaseModel):
    comercio: ComercioBrandingResponse
    public_id: str
    telefono_mascarado: str
    visitas_actuales: int
    objetivo_visitas: int
    recompensas_total: int
    account_url: str
    qr_value: str


class RegistrarVisitaResponse(BaseModel):
    estado: str
    mensaje: str | None = None
    visitas: int
    cliente: ClienteCuentaResponse


class LoginRequest(BaseModel):
    username: str
    password: str

    @field_validator("username", "password")
    @classmethod
    def validar_login(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Campo obligatorio")
        return normalized


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    rol: str
    comercio: ComercioBrandingResponse | None = None


class ErrorResponse(BaseModel):
    detail: str


class AccesoClienteRequest(BaseModel):
    telefono: str = Field(
        ...,
        pattern=r"^\d{1,10}$",
        description="Numero de telefono de hasta 10 digitos",
    )


class ClienteMisComerciosResponse(BaseModel):
    telefono_mascarado: str
    cuentas: list[ClienteCuentaResponse]

class CambiarPasswordRequest(BaseModel):
    password: str = Field(..., min_length=6, max_length=72)

    @field_validator("password")
    @classmethod
    def validar_password_seguro(cls, value: str) -> str:
        return validate_password_strength(value)
