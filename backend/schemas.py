from pydantic import BaseModel, Field, field_validator


class ComercioBrandingResponse(BaseModel):
    slug: str
    nombre: str
    logo_url: str | None = None
    color_primario: str
    color_secundario: str
    visitas_objetivo: int
    recompensa_nombre: str
    descripcion: str | None = None


class ComercioConfigUpdateRequest(BaseModel):
    nombre: str
    logo_url: str | None = None
    color_primario: str
    color_secundario: str
    visitas_objetivo: int = Field(..., ge=1, le=50)
    recompensa_nombre: str
    descripcion: str | None = None

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
        normalized = value.strip()
        if len(normalized) != 7 or not normalized.startswith("#"):
            raise ValueError("El color debe estar en formato hexadecimal #RRGGBB")
        int(normalized[1:], 16)
        return normalized.lower()


class RegistrarVisitaRequest(BaseModel):
    telefono: str = Field(
        ...,
        pattern=r"^\d{1,10}$",
        description="Numero de telefono de hasta 10 digitos",
    )


class RegistrarVisitaQrRequest(BaseModel):
    public_id: str


class WalletLinks(BaseModel):
    apple: str | None = None
    google: str | None = None


class ClienteCuentaResponse(BaseModel):
    comercio: ComercioBrandingResponse
    public_id: str
    telefono_mascarado: str
    visitas_actuales: int
    objetivo_visitas: int
    recompensas_total: int
    account_url: str
    qr_value: str
    wallet_links: WalletLinks


class RegistrarVisitaResponse(BaseModel):
    estado: str
    mensaje: str | None = None
    visitas: int
    cliente: ClienteCuentaResponse


class LoginRequest(BaseModel):
    comercio_slug: str
    username: str
    password: str

    @field_validator("comercio_slug", "username", "password")
    @classmethod
    def validar_login(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Campo obligatorio")
        return normalized


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    comercio: ComercioBrandingResponse


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
