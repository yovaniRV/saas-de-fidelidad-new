from sqlalchemy import create_engine

engine = create_engine('postgresql://postgres:VrV180320@localhost:5432/saas_fidelidad')
try:
    conn = engine.connect()
    print('PostgreSQL local conectado')
    conn.close()
except Exception as e:
    print('No hay PostgreSQL local:', e)