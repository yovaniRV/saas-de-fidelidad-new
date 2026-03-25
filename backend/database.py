import os
import uuid

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from security_utils import hash_password, is_password_hashed

SQLALCHEMY_DATABASE_URL = "sqlite:///./loyalty.db"
DEFAULT_COMERCIO_SLUG = "demo-cafe"
DEFAULT_COMERCIO_NOMBRE = "Demo Cafe"
DEFAULT_CAJERO_USERNAME = os.getenv("CASHIER_USERNAME", "cajero")
DEFAULT_CAJERO_PASSWORD = os.getenv("CASHIER_PASSWORD", "cambiar-esta-contrasena")

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def ensure_sqlite_schema() -> None:
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    with engine.begin() as connection:
        if "comercios" in table_names:
            connection.execute(
                text(
                    """
                    INSERT INTO comercios (slug, nombre, color_primario, color_secundario, visitas_objetivo, recompensa_nombre, descripcion)
                    SELECT :slug, :nombre, '#0f766e', '#f59e0b', 5, 'Bebida gratis', 'Comercio demo para el MVP'
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
            connection.execute(
                text(
                    """
                    INSERT INTO cajeros (comercio_id, username, password, nombre_mostrado)
                    SELECT :comercio_id, :username, :password, 'Caja principal'
                    WHERE NOT EXISTS (
                        SELECT 1 FROM cajeros WHERE comercio_id = :comercio_id AND username = :username
                    )
                    """
                ),
                {
                    "comercio_id": default_comercio,
                    "username": DEFAULT_CAJERO_USERNAME,
                    "password": hash_password(DEFAULT_CAJERO_PASSWORD),
                },
            )
            connection.execute(
                text("CREATE UNIQUE INDEX IF NOT EXISTS ix_cajeros_comercio_username ON cajeros (comercio_id, username)")
            )
            cajeros = connection.execute(text("SELECT id, password FROM cajeros")).mappings().all()
            for cajero in cajeros:
                if not is_password_hashed(cajero["password"]):
                    connection.execute(
                        text("UPDATE cajeros SET password = :password WHERE id = :id"),
                        {"id": cajero["id"], "password": hash_password(cajero["password"])},
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
