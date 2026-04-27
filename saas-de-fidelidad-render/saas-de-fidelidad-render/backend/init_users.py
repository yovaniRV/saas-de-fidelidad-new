"""
Script de inicializacion de usuarios para el SaaS de Fidelidad.
Crea / actualiza:
  - admin/Admin123 (administrador del sistema)
  - jefe/Jefe123   (jefe de caja en demo-cafe)
  - cajero/Cajero123 (cajero en demo-cafe)
"""
import sys
sys.path.insert(0, '.')
from security_utils import hash_password, verify_password
from sqlalchemy import create_engine, text

DB_URL = 'postgresql://postgres:VrV180320@localhost:5432/saas_fidelidad'
engine = create_engine(DB_URL)

ADMIN_USER = 'admin'
ADMIN_PASS = 'Admin123'
JEFE_USER  = 'jefe'
JEFE_PASS  = 'Jefe123'
CAJERO_USER = 'cajero'
CAJERO_PASS = 'Cajero123'

with engine.begin() as conn:
    # ── Comercio demo ───────────────────────────────────────────────
    comercio_id = conn.execute(
        text("SELECT id FROM comercios WHERE slug = 'demo-cafe' LIMIT 1")
    ).scalar_one_or_none()

    if comercio_id is None:
        conn.execute(text(
            "INSERT INTO comercios (slug, nombre, color_primario, color_secundario, visitas_objetivo, recompensa_nombre) "
            "VALUES ('demo-cafe', 'Demo Cafe', '#0f766e', '#f59e0b', 5, 'Bebida gratis')"
        ))
        comercio_id = conn.execute(
            text("SELECT id FROM comercios WHERE slug = 'demo-cafe' LIMIT 1")
        ).scalar_one()
        print(f"Comercio 'demo-cafe' creado con id={comercio_id}")
    else:
        print(f"Comercio 'demo-cafe' ya existe id={comercio_id}")

    # ── Admin ───────────────────────────────────────────────────────
    existing = conn.execute(
        text("SELECT id, password FROM admin_usuarios WHERE username = :u"),
        {"u": ADMIN_USER}
    ).mappings().first()

    if existing is None:
        conn.execute(text(
            "INSERT INTO admin_usuarios (username, password, nombre_mostrado, activo) "
            "VALUES (:u, :p, 'Administrador', 1)"
        ), {"u": ADMIN_USER, "p": hash_password(ADMIN_PASS)})
        print(f"Admin '{ADMIN_USER}' CREADO con contraseña '{ADMIN_PASS}'")
    else:
        conn.execute(text(
            "UPDATE admin_usuarios SET password = :p, activo = 1 WHERE username = :u"
        ), {"u": ADMIN_USER, "p": hash_password(ADMIN_PASS)})
        print(f"Admin '{ADMIN_USER}' ACTUALIZADO con contraseña '{ADMIN_PASS}'")

    # ── Jefe ────────────────────────────────────────────────────────
    existing_jefe = conn.execute(
        text("SELECT id, password FROM cajeros WHERE username = :u"),
        {"u": JEFE_USER}
    ).mappings().first()

    if existing_jefe is None:
        conn.execute(text(
            "INSERT INTO cajeros (comercio_id, username, password, nombre_mostrado, rol, activo) "
            "VALUES (:cid, :u, :p, 'Jefe de caja', 'jefe', 1)"
        ), {"cid": comercio_id, "u": JEFE_USER, "p": hash_password(JEFE_PASS)})
        print(f"Jefe '{JEFE_USER}' CREADO con contraseña '{JEFE_PASS}'")
    else:
        conn.execute(text(
            "UPDATE cajeros SET password = :p, rol = 'jefe', activo = 1 WHERE username = :u"
        ), {"u": JEFE_USER, "p": hash_password(JEFE_PASS)})
        print(f"Jefe '{JEFE_USER}' ACTUALIZADO con contraseña '{JEFE_PASS}'")

    # Asegurar que el usuario 'cajero' (el viejo) sea solo cajero
    existing_cajero = conn.execute(
        text("SELECT id FROM cajeros WHERE username = :u"),
        {"u": CAJERO_USER}
    ).mappings().first()

    if existing_cajero is None:
        conn.execute(text(
            "INSERT INTO cajeros (comercio_id, username, password, nombre_mostrado, rol, activo) "
            "VALUES (:cid, :u, :p, 'Cajero principal', 'cajero', 1)"
        ), {"cid": comercio_id, "u": CAJERO_USER, "p": hash_password(CAJERO_PASS)})
        print(f"Cajero '{CAJERO_USER}' CREADO con contraseña '{CAJERO_PASS}'")
    else:
        conn.execute(text(
            "UPDATE cajeros SET password = :p, rol = 'cajero', activo = 1 WHERE username = :u"
        ), {"u": CAJERO_USER, "p": hash_password(CAJERO_PASS)})
        print(f"Cajero '{CAJERO_USER}' ACTUALIZADO con contraseña '{CAJERO_PASS}'")

    # ── Limpiar bloqueos ───────────────────────────────────────────
    conn.execute(text(
        "UPDATE estado_login_cajero SET intentos_fallidos = 0, bloqueado_hasta = NULL"
    ))
    print("Bloqueos limpiados para todos los usuarios")

print()
print("=" * 50)
print("USUARIOS DEL SISTEMA:")
print("=" * 50)
print(f"  ADMIN  -> usuario: {ADMIN_USER:10s}  contraseña: {ADMIN_PASS}")
print(f"  JEFE   -> usuario: {JEFE_USER:10s}  contraseña: {JEFE_PASS}")
print(f"  CAJERO -> usuario: {CAJERO_USER:10s}  contraseña: {CAJERO_PASS}")
print("=" * 50)
print("Entra en:  http://localhost:4200")
