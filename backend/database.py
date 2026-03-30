import os
import uuid

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from security_utils import hash_password, is_password_hashed, verify_password

# Soporta PostgreSQL (producción) y SQLite (tests/fallback)
# Variable de entorno DATABASE_URL para producción.
# Por defecto usa PostgreSQL local con usuario postgres.
DEFAULT_DB_URL = "postgresql://postgres:VrV180320@localhost:5432/saas_fidelidad"
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DB_URL)
DEFAULT_COMERCIO_SLUG = "demo-cafe"
DEFAULT_COMERCIO_NOMBRE = "Demo Cafe"
DEFAULT_CAJERO_USERNAME = os.getenv("CASHIER_USERNAME", "cajero")
DEFAULT_CAJERO_PASSWORD = os.getenv("CASHIER_PASSWORD", "Cajero123")
DEFAULT_ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin123")
_ADMIN_PASSWORD_EXPLICITLY_SET = "ADMIN_PASSWORD" in os.environ
_CAJERO_PASSWORD_EXPLICITLY_SET = "CASHIER_PASSWORD" in os.environ

_is_sqlite = SQLALCHEMY_DATABASE_URL.startswith("sqlite")
_engine_kwargs: dict = {"connect_args": {"check_same_thread": False}} if _is_sqlite else {}
engine = create_engine(SQLALCHEMY_DATABASE_URL, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def ensure_sqlite_schema() -> None:
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    with engine.begin() as connection:
        if "comercios" in table_names:
            comercio_columns = {column["name"] for column in inspect(engine).get_columns("comercios")}
            if "momento_recomendado" not in comercio_columns:
                connection.execute(text("ALTER TABLE comercios ADD COLUMN momento_recomendado VARCHAR(20)"))
            if "mensaje_contextual" not in comercio_columns:
                connection.execute(text("ALTER TABLE comercios ADD COLUMN mensaje_contextual VARCHAR(160)"))
            if "suscripcion_plan" not in comercio_columns:
                connection.execute(text("ALTER TABLE comercios ADD COLUMN suscripcion_plan VARCHAR(40) DEFAULT 'mensual'"))
                connection.execute(text("UPDATE comercios SET suscripcion_plan = 'mensual' WHERE suscripcion_plan IS NULL OR suscripcion_plan = ''"))
            if "suscripcion_estado" not in comercio_columns:
                connection.execute(text("ALTER TABLE comercios ADD COLUMN suscripcion_estado VARCHAR(20) DEFAULT 'activa'"))
                connection.execute(text("UPDATE comercios SET suscripcion_estado = 'activa' WHERE suscripcion_estado IS NULL OR suscripcion_estado = ''"))
            if "suscripcion_monto_mxn" not in comercio_columns:
                connection.execute(text("ALTER TABLE comercios ADD COLUMN suscripcion_monto_mxn INTEGER DEFAULT 299"))
                connection.execute(text("UPDATE comercios SET suscripcion_monto_mxn = 299 WHERE suscripcion_monto_mxn IS NULL"))
            if "suscripcion_proximo_cobro" not in comercio_columns:
                connection.execute(text("ALTER TABLE comercios ADD COLUMN suscripcion_proximo_cobro DATE"))
            if "suscripcion_notas" not in comercio_columns:
                connection.execute(text("ALTER TABLE comercios ADD COLUMN suscripcion_notas VARCHAR(255)"))

            connection.execute(
                text(
                    """
                    INSERT INTO comercios (
                        slug,
                        nombre,
                        color_primario,
                        color_secundario,
                        visitas_objetivo,
                        recompensa_nombre,
                        descripcion,
                        suscripcion_plan,
                        suscripcion_estado,
                        suscripcion_monto_mxn
                    )
                    SELECT :slug, :nombre, '#0f766e', '#f59e0b', 5, 'Bebida gratis', 'Comercio demo para el MVP', 'mensual', 'activa', 299
                    WHERE NOT EXISTS (SELECT 1 FROM comercios WHERE slug = :slug)
                    """
                ),
                {"slug": DEFAULT_COMERCIO_SLUG, "nombre": DEFAULT_COMERCIO_NOMBRE},
            )

        default_comercio = connection.execute(
            text("SELECT id FROM comercios WHERE slug = :slug LIMIT 1"),
            {"slug": DEFAULT_COMERCIO_SLUG},
        ).scalar_one_or_none()

        if "cajeros" in table_names and default_comercio is not None:
            cajero_columns = {column["name"] for column in inspect(engine).get_columns("cajeros")}
            if "rol" not in cajero_columns:
                connection.execute(text("ALTER TABLE cajeros ADD COLUMN rol VARCHAR(20) DEFAULT 'cajero'"))
                connection.execute(text("UPDATE cajeros SET rol = 'cajero' WHERE rol IS NULL OR rol = ''"))
            if "activo" not in cajero_columns:
                connection.execute(text("ALTER TABLE cajeros ADD COLUMN activo INTEGER DEFAULT 1"))
                connection.execute(text("UPDATE cajeros SET activo = 1 WHERE activo IS NULL"))

            connection.execute(
                text(
                    """
                    INSERT INTO cajeros (comercio_id, username, password, nombre_mostrado, rol, activo)
                    SELECT :comercio_id, :username, :password, 'Caja principal', 'jefe', 1
                    WHERE NOT EXISTS (
                        SELECT 1 FROM cajeros WHERE username = :username
                    )
                    """
                ),
                {
                    "comercio_id": default_comercio,
                    "username": DEFAULT_CAJERO_USERNAME,
                    "password": hash_password(DEFAULT_CAJERO_PASSWORD),
                },
            )

            # Promueve al primer usuario de cada comercio a jefe si aun no existe uno.
            comercios_ids = connection.execute(text("SELECT id FROM comercios")).scalars().all()
            for comercio_id in comercios_ids:
                tiene_jefe = connection.execute(
                    text("SELECT 1 FROM cajeros WHERE comercio_id = :comercio_id AND rol = 'jefe' LIMIT 1"),
                    {"comercio_id": comercio_id},
                ).scalar_one_or_none()
                if tiene_jefe:
                    continue

                primer_cajero_id = connection.execute(
                    text("SELECT id FROM cajeros WHERE comercio_id = :comercio_id ORDER BY id ASC LIMIT 1"),
                    {"comercio_id": comercio_id},
                ).scalar_one_or_none()
                if primer_cajero_id:
                    connection.execute(
                        text("UPDATE cajeros SET rol = 'jefe' WHERE id = :id"),
                        {"id": primer_cajero_id},
                    )

            duplicados = connection.execute(
                text("SELECT username FROM cajeros GROUP BY username HAVING COUNT(*) > 1")
            ).scalars().all()
            for username in duplicados:
                filas = connection.execute(
                    text("SELECT id FROM cajeros WHERE username = :username ORDER BY id ASC"),
                    {"username": username},
                ).scalars().all()
                for duplicate_id in filas[1:]:
                    connection.execute(
                        text("UPDATE cajeros SET username = :nuevo WHERE id = :id"),
                        {"id": duplicate_id, "nuevo": f"{username}-{duplicate_id}"},
                    )

            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_cajeros_username ON cajeros (username)"))
            cajeros = connection.execute(text("SELECT id, username, password FROM cajeros")).mappings().all()
            for cajero in cajeros:
                if not is_password_hashed(cajero["password"]):
                    connection.execute(
                        text("UPDATE cajeros SET password = :password WHERE id = :id"),
                        {"id": cajero["id"], "password": hash_password(cajero["password"])},
                    )
                elif (
                    _CAJERO_PASSWORD_EXPLICITLY_SET
                    and cajero["username"] == DEFAULT_CAJERO_USERNAME
                    and not verify_password(cajero["password"], DEFAULT_CAJERO_PASSWORD)
                ):
                    connection.execute(
                        text("UPDATE cajeros SET password = :password WHERE id = :id"),
                        {"id": cajero["id"], "password": hash_password(DEFAULT_CAJERO_PASSWORD)},
                    )

        if "clientes" in table_names:
            columns = {column["name"] for column in inspect(engine).get_columns("clientes")}
            if "comercio_id" not in columns:
                existing_rows = connection.execute(text("SELECT * FROM clientes")).mappings().all()
                connection.execute(text("DROP TABLE clientes"))
                connection.execute(
                    text(
                        """
                        CREATE TABLE clientes (
                            id INTEGER NOT NULL PRIMARY KEY,
                            comercio_id INTEGER NOT NULL,
                            telefono VARCHAR(20) NOT NULL,
                            public_id VARCHAR(36) NOT NULL,
                            visitas INTEGER NOT NULL DEFAULT 0,
                            recompensas_total INTEGER NOT NULL DEFAULT 0,
                            FOREIGN KEY(comercio_id) REFERENCES comercios (id)
                        )
                        """
                    )
                )

                for row in existing_rows:
                    connection.execute(
                        text(
                            """
                            INSERT INTO clientes (id, comercio_id, telefono, public_id, visitas, recompensas_total)
                            VALUES (:id, :comercio_id, :telefono, :public_id, :visitas, :recompensas_total)
                            """
                        ),
                        {
                            "id": row["id"],
                            "comercio_id": default_comercio,
                            "telefono": row["telefono"],
                            "public_id": row.get("public_id") or str(uuid.uuid4()),
                            "visitas": row.get("visitas") or 0,
                            "recompensas_total": row.get("recompensas_total") or 0,
                        },
                    )

            refreshed_columns = {column["name"] for column in inspect(engine).get_columns("clientes")}
            if "public_id" not in refreshed_columns:
                connection.execute(text("ALTER TABLE clientes ADD COLUMN public_id VARCHAR(36)"))
                existing_rows = connection.execute(text("SELECT id FROM clientes")).mappings().all()
                for row in existing_rows:
                    connection.execute(
                        text("UPDATE clientes SET public_id = :public_id WHERE id = :id"),
                        {"public_id": str(uuid.uuid4()), "id": row["id"]},
                    )

            if "recompensas_total" not in refreshed_columns:
                connection.execute(text("ALTER TABLE clientes ADD COLUMN recompensas_total INTEGER DEFAULT 0"))
                connection.execute(text("UPDATE clientes SET recompensas_total = 0 WHERE recompensas_total IS NULL"))

            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_clientes_public_id ON clientes (public_id)"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_clientes_comercio_telefono ON clientes (comercio_id, telefono)"))

        if "auditoria_acciones" in table_names:
            audit_columns = {column["name"] for column in inspector.get_columns("auditoria_acciones")}
            if "comercio_id" not in audit_columns:
                connection.execute(text("ALTER TABLE auditoria_acciones ADD COLUMN comercio_id INTEGER"))
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_auditoria_acciones_comercio_id ON auditoria_acciones (comercio_id)")
            )

        if "admin_usuarios" in table_names:
            admin_columns = {column["name"] for column in inspect(engine).get_columns("admin_usuarios")}
            if "activo" not in admin_columns:
                connection.execute(text("ALTER TABLE admin_usuarios ADD COLUMN activo INTEGER DEFAULT 1"))
                connection.execute(text("UPDATE admin_usuarios SET activo = 1 WHERE activo IS NULL"))

            connection.execute(
                text(
                    """
                    INSERT INTO admin_usuarios (username, password, nombre_mostrado, activo)
                    SELECT :username, :password, 'Administrador principal', 1
                    WHERE NOT EXISTS (SELECT 1 FROM admin_usuarios WHERE username = :username)
                    """
                ),
                {
                    "username": DEFAULT_ADMIN_USERNAME,
                    "password": hash_password(DEFAULT_ADMIN_PASSWORD),
                },
            )

            admins = connection.execute(text("SELECT id, password FROM admin_usuarios")).mappings().all()
            for admin in admins:
                if not is_password_hashed(admin["password"]):
                    connection.execute(
                        text("UPDATE admin_usuarios SET password = :password WHERE id = :id"),
                        {"id": admin["id"], "password": hash_password(admin["password"])},
                    )
                  elif _ADMIN_PASSWORD_EXPLICITLY_SET and admin["username"] == DEFAULT_ADMIN_USERNAME and not verify_password(admin["password"], DEFAULT_ADMIN_PASSWORD):
                      # Si ADMIN_PASSWORD está configurado explícitamente en el entorno,
                      # actualizar el hash del admin por defecto para que coincida.
                    connection.execute(
                        text("UPDATE admin_usuarios SET password = :password WHERE id = :id"),
                        {"id": admin["id"], "password": hash_password(DEFAULT_ADMIN_PASSWORD)},
                    )
