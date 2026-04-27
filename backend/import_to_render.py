import os
from sqlalchemy import create_engine, text

# URL de Render proporcionada por el usuario
RENDER_DB_URL = "postgresql://saas_db_rew2_user:0kQZTuwwbvpBwmO559u8kGDXESULxnod@dpg-d7nr1pl7vvec739bn0s0-a/saas_db_rew2"

engine = create_engine(RENDER_DB_URL)

print("Conectando a Render DB...")

try:
    with engine.connect() as conn:
        print("Conexión exitosa. Importando datos...")

        # Leer el dump
        with open('../db_dump.sql', 'r') as f:
            sql_content = f.read()

        # Ejecutar el SQL
        conn.execute(text(sql_content))
        conn.commit()

        print("Datos importados exitosamente a Render!")

except Exception as e:
    print(f"Error importando datos: {e}")