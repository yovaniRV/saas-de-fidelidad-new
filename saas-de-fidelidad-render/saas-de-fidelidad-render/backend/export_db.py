import os
from sqlalchemy import create_engine, MetaData, Table, text

# Conectar a PostgreSQL local
engine = create_engine('postgresql://postgres:VrV180320@localhost:5432/saas_fidelidad')

metadata = MetaData()
metadata.reflect(bind=engine)

# Tablas a exportar
tables_to_export = [
    'comercios',
    'admin_usuarios',
    'cajeros',
    'estado_login_cajero',
    'clientes',
    'auditoria_acciones'
]

with open('../db_dump.sql', 'w') as f:
    f.write('-- Dump de datos para Render\n')
    f.write('BEGIN;\n')

    for table_name in tables_to_export:
        table = Table(table_name, metadata, autoload_with=engine)
        with engine.connect() as conn:
            result = conn.execute(table.select())
            rows = result.fetchall()

        if rows:
            f.write(f'-- Datos para {table_name}\n')
            for row in rows:
                # Generar INSERT
                columns = ', '.join(f'"{col}"' for col in table.columns.keys())
                values = ', '.join(repr(getattr(row, col)) for col in table.columns.keys())
                insert = f'INSERT INTO {table_name} ({columns}) VALUES ({values});\n'
                f.write(insert)
            f.write('\n')

    f.write('COMMIT;\n')

print('Dump creado en ../db_dump.sql')