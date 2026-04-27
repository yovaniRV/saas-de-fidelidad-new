import os
from sqlalchemy import create_engine, MetaData, Table
from sqlalchemy.orm import sessionmaker

# Configuración de origen (SQLite local)
SOURCE_DB_URL = "sqlite:///./loyalty.db"  # Ajusta si es otro path

# Configuración de destino (PostgreSQL en Render)
TARGET_DB_URL = os.getenv("TARGET_DATABASE_URL")  # Pasa esto como env var

if not TARGET_DB_URL:
    print("Error: Establece TARGET_DATABASE_URL con la URL de PostgreSQL de Render")
    exit(1)

# Engines
source_engine = create_engine(SOURCE_DB_URL)
target_engine = create_engine(TARGET_DB_URL)

# Metadata
metadata = MetaData()

# Tablas a migrar (en orden por dependencias)
tables_to_migrate = [
    'comercios',
    'admin_usuarios',
    'cajeros',
    'estado_login_cajero',
    'clientes',
    'auditoria_acciones'
]

def migrate_table(table_name):
    print(f"Migrando tabla: {table_name}")

    # Reflejar tabla de origen
    source_table = Table(table_name, metadata, autoload_with=source_engine)

    # Crear tabla en destino si no existe
    metadata.create_all(target_engine, tables=[source_table])

    # Copiar datos
    with source_engine.connect() as source_conn:
        result = source_conn.execute(source_table.select())
        rows = result.fetchall()

    if rows:
        with target_engine.connect() as target_conn:
            target_conn.execute(source_table.insert(), [dict(row._mapping) for row in rows])
            target_conn.commit()

    print(f"Tabla {table_name}: {len(rows)} filas migradas")

def main():
    print("Iniciando migración de SQLite a PostgreSQL...")

    for table in tables_to_migrate:
        try:
            migrate_table(table)
        except Exception as e:
            print(f"Error migrando {table}: {e}")
            continue

    print("Migración completada!")

if __name__ == "__main__":
    main()