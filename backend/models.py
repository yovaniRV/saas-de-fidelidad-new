import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from database import Base


class Comercio(Base):
    __tablename__ = "comercios"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(80), unique=True, index=True, nullable=False)
    nombre = Column(String(120), nullable=False)
    logo_url = Column(String(255), nullable=True)
    color_primario = Column(String(20), nullable=False, default="#0f766e")
    color_secundario = Column(String(20), nullable=False, default="#f59e0b")
    visitas_objetivo = Column(Integer, default=5, nullable=False)
    recompensa_nombre = Column(String(120), nullable=False, default="Bebida gratis")
    descripcion = Column(String(255), nullable=True)
    momento_recomendado = Column(String(20), nullable=True)
    mensaje_contextual = Column(String(160), nullable=True)
    suscripcion_plan = Column(String(40), nullable=False, default="mensual")
    suscripcion_estado = Column(String(20), nullable=False, default="activa")
    suscripcion_monto_mxn = Column(Integer, nullable=False, default=299)
    suscripcion_proximo_cobro = Column(Date, nullable=True)
    suscripcion_notas = Column(String(255), nullable=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Cajero(Base):
    __tablename__ = "cajeros"

    id = Column(Integer, primary_key=True, index=True)
    comercio_id = Column(Integer, ForeignKey("comercios.id"), index=True, nullable=False)
    username = Column(String(100), nullable=False)
    password = Column(String(255), nullable=False)
    nombre_mostrado = Column(String(120), nullable=True)
    rol = Column(String(20), nullable=False, default="cajero")
    activo = Column(Integer, nullable=False, default=1)
    creado_en = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AdminUsuario(Base):
    __tablename__ = "admin_usuarios"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)
    nombre_mostrado = Column(String(120), nullable=True)
    activo = Column(Integer, nullable=False, default=1)
    creado_en = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Cliente(Base):
    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True, index=True)
    comercio_id = Column(Integer, ForeignKey("comercios.id"), index=True, nullable=False)
    telefono = Column(String(20), index=True, nullable=False)
    public_id = Column(String(36), unique=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    visitas = Column(Integer, default=0, nullable=False)
    recompensas_total = Column(Integer, default=0, nullable=False)


class EstadoLoginCajero(Base):
    __tablename__ = "estado_login_cajero"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    intentos_fallidos = Column(Integer, default=0, nullable=False)
    bloqueado_hasta = Column(DateTime(timezone=True), nullable=True)
    actualizado_en = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AuditoriaAccion(Base):
    __tablename__ = "auditoria_acciones"

    id = Column(Integer, primary_key=True, index=True)
    comercio_id = Column(Integer, ForeignKey("comercios.id"), index=True, nullable=True)
    username = Column(String(100), nullable=False)
    accion = Column(String(80), nullable=False)
    detalle = Column(String(255), nullable=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
