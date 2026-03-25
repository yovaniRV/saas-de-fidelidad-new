from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import main
import models
from database import Base
from security_utils import hash_password, is_password_hashed


def _build_test_client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "test_loyalty.db"
    test_engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    Base.metadata.create_all(bind=test_engine)
    main.app.state.testing_session_local = TestingSessionLocal
    main.rate_limiter.reset()

    db = TestingSessionLocal()
    try:
        comercio = models.Comercio(
            slug="demo-cafe",
            nombre="Demo Cafe",
            color_primario="#0f766e",
            color_secundario="#f59e0b",
            visitas_objetivo=5,
            recompensa_nombre="Bebida gratis",
            descripcion="Demo",
        )
        db.add(comercio)
        db.commit()
        db.refresh(comercio)

        db.add(
            models.Cajero(
                comercio_id=comercio.id,
                username="cajero",
                password=hash_password("1234"),
                nombre_mostrado="Caja principal",
            )
        )
        db.commit()
    finally:
        db.close()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[main.get_db] = override_get_db
    return TestClient(main.app)


def _override_rate_limit(profile_name: str, *, limit: int, window_seconds: int) -> dict[str, int]:
    previous = dict(main.RATE_LIMITS[profile_name])
    main.RATE_LIMITS[profile_name]["limit"] = limit
    main.RATE_LIMITS[profile_name]["window_seconds"] = window_seconds
    main.rate_limiter.reset()
    return previous


def _restore_rate_limit(profile_name: str, previous: dict[str, int]) -> None:
    main.RATE_LIMITS[profile_name].update(previous)
    main.rate_limiter.reset()


def _override_internal_multiplier(value: int) -> int:
    previous = main.INTERNAL_RATE_LIMIT_MULTIPLIER
    main.INTERNAL_RATE_LIMIT_MULTIPLIER = value
    main.rate_limiter.reset()
    return previous


def _restore_internal_multiplier(previous: int) -> None:
    main.INTERNAL_RATE_LIMIT_MULTIPLIER = previous
    main.rate_limiter.reset()


def _auth_headers(client: TestClient, comercio_slug: str = "demo-cafe") -> dict[str, str]:
    response = client.post(
        "/login",
        json={"comercio_slug": comercio_slug, "username": "cajero", "password": "1234"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _crear_comercio_y_cajero(slug: str) -> None:
    db = main.app.state.testing_session_local()
    try:
        comercio = models.Comercio(
            slug=slug,
            nombre=f"{slug} store",
            color_primario="#1d4ed8",
            color_secundario="#f97316",
            visitas_objetivo=7,
            recompensa_nombre="Postre gratis",
            descripcion="Sucursal secundaria",
        )
        db.add(comercio)
        db.commit()
        db.refresh(comercio)
        db.add(models.Cajero(comercio_id=comercio.id, username="cajero", password=hash_password("1234"), nombre_mostrado="Caja 2"))
        db.commit()
    finally:
        db.close()


def test_login_funciona_con_password_hasheado(tmp_path: Path):
    client = _build_test_client(tmp_path)

    db = main.app.state.testing_session_local()
    try:
        cajero = db.query(models.Cajero).filter(models.Cajero.username == "cajero").first()
        assert cajero is not None
        assert is_password_hashed(cajero.password)
    finally:
        db.close()

    response = client.post("/login", json={"comercio_slug": "demo-cafe", "username": "cajero", "password": "1234"})

    assert response.status_code == 200


def test_login_exitoso(tmp_path: Path):
    client = _build_test_client(tmp_path)

    response = client.post("/login", json={"comercio_slug": "demo-cafe", "username": "cajero", "password": "1234"})

    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert body["comercio"]["slug"] == "demo-cafe"


def test_login_fallido(tmp_path: Path):
    client = _build_test_client(tmp_path)

    response = client.post("/login", json={"comercio_slug": "demo-cafe", "username": "cajero", "password": "mala"})

    assert response.status_code == 401


def test_rate_limit_login_por_ip(tmp_path: Path):
    client = _build_test_client(tmp_path)
    previous = _override_rate_limit("login_ip", limit=2, window_seconds=60)

    try:
        for _ in range(2):
            response = client.post(
                "/login",
                json={"comercio_slug": "demo-cafe", "username": "cajero", "password": "mala"},
                headers={"x-forwarded-for": "198.51.100.10"},
            )
            assert response.status_code == 401

        blocked = client.post(
            "/login",
            json={"comercio_slug": "demo-cafe", "username": "otro", "password": "mala"},
            headers={"x-forwarded-for": "198.51.100.10"},
        )

        assert blocked.status_code == 429
        assert blocked.headers["retry-after"]
    finally:
        _restore_rate_limit("login_ip", previous)


def test_rate_limit_login_por_usuario(tmp_path: Path):
    client = _build_test_client(tmp_path)
    previous = _override_rate_limit("login_subject", limit=2, window_seconds=60)

    try:
        for _ in range(2):
            response = client.post(
                "/login",
                json={"comercio_slug": "demo-cafe", "username": "cajero", "password": "mala"},
                headers={"x-forwarded-for": "198.51.100.10"},
            )
            assert response.status_code == 401

        blocked = client.post(
            "/login",
            json={"comercio_slug": "demo-cafe", "username": "cajero", "password": "1234"},
            headers={"x-forwarded-for": "203.0.113.20"},
        )

        assert blocked.status_code == 429
        assert blocked.headers["retry-after"]
    finally:
        _restore_rate_limit("login_subject", previous)


def test_trafico_interno_recibe_limite_suavizado(tmp_path: Path):
    client = _build_test_client(tmp_path)
    previous_limit = _override_rate_limit("login_ip", limit=1, window_seconds=60)
    previous_multiplier = _override_internal_multiplier(3)

    try:
        first = client.post(
            "/login",
            json={"comercio_slug": "demo-cafe", "username": "uno", "password": "mala"},
            headers={"x-forwarded-for": "10.0.0.5"},
        )
        second = client.post(
            "/login",
            json={"comercio_slug": "demo-cafe", "username": "dos", "password": "mala"},
            headers={"x-forwarded-for": "10.0.0.5"},
        )
        third = client.post(
            "/login",
            json={"comercio_slug": "demo-cafe", "username": "tres", "password": "mala"},
            headers={"x-forwarded-for": "10.0.0.5"},
        )
        blocked = client.post(
            "/login",
            json={"comercio_slug": "demo-cafe", "username": "cuatro", "password": "mala"},
            headers={"x-forwarded-for": "10.0.0.5"},
        )

        assert first.status_code == 401
        assert second.status_code == 401
        assert third.status_code == 401
        assert blocked.status_code == 429
    finally:
        _restore_rate_limit("login_ip", previous_limit)
        _restore_internal_multiplier(previous_multiplier)


def test_rate_limit_endpoint_sensible_por_ip(tmp_path: Path):
    client = _build_test_client(tmp_path)
    headers = _auth_headers(client)
    previous = _override_rate_limit("sensitive_ip", limit=2, window_seconds=60)

    try:
        for telefono in ("1234567890", "1234567891"):
            response = client.post(
                "/registrar-visita",
                json={"telefono": telefono},
                headers={**headers, "x-forwarded-for": "198.51.100.30"},
            )
            assert response.status_code == 200

        blocked = client.post(
            "/registrar-visita",
            json={"telefono": "1234567892"},
            headers={**headers, "x-forwarded-for": "198.51.100.30"},
        )

        assert blocked.status_code == 429
        assert blocked.headers["retry-after"]
    finally:
        _restore_rate_limit("sensitive_ip", previous)


def test_rate_limit_endpoint_sensible_por_usuario(tmp_path: Path):
    client = _build_test_client(tmp_path)
    previous = _override_rate_limit("sensitive_subject", limit=2, window_seconds=60)

    try:
        for ip in ("198.51.100.40", "203.0.113.41"):
            response = client.post(
                "/comercios/demo-cafe/acceso-cliente",
                json={"telefono": "3012223344"},
                headers={"x-forwarded-for": ip},
            )
            assert response.status_code == 404

        blocked = client.post(
            "/comercios/demo-cafe/acceso-cliente",
            json={"telefono": "3012223344"},
            headers={"x-forwarded-for": "203.0.113.50"},
        )

        assert blocked.status_code == 429
        assert blocked.headers["retry-after"]
    finally:
        _restore_rate_limit("sensitive_subject", previous)


def test_audita_evento_rate_limited(tmp_path: Path):
    client = _build_test_client(tmp_path)
    previous = _override_rate_limit("login_ip", limit=1, window_seconds=60)

    try:
        first = client.post(
            "/login",
            json={"comercio_slug": "demo-cafe", "username": "cajero", "password": "mala"},
            headers={"x-forwarded-for": "198.51.100.91"},
        )
        blocked = client.post(
            "/login",
            json={"comercio_slug": "demo-cafe", "username": "otro", "password": "mala"},
            headers={"x-forwarded-for": "198.51.100.91"},
        )

        assert first.status_code == 401
        assert blocked.status_code == 429

        db = main.app.state.testing_session_local()
        try:
            eventos = db.query(models.AuditoriaAccion).filter(models.AuditoriaAccion.accion == "rate_limited").all()
        finally:
            db.close()

        assert len(eventos) >= 1
        assert "perfil=login_ip" in (eventos[-1].detalle or "")
        assert "ruta=/login" in (eventos[-1].detalle or "")
    finally:
        _restore_rate_limit("login_ip", previous)


def test_headers_de_seguridad_en_respuesta_publica(tmp_path: Path):
    client = _build_test_client(tmp_path)

    response = client.get("/comercios/demo-cafe")

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["permissions-policy"] == "camera=(), geolocation=(), microphone=()"
    assert "cache-control" not in response.headers


def test_health_sin_rate_limit(tmp_path: Path):
    client = _build_test_client(tmp_path)

    for _ in range(10):
        response = client.get("/health")
        assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert body["rate_limit_backend"] in {"memory", "redis"}


def test_login_marca_respuesta_como_no_cacheable(tmp_path: Path):
    client = _build_test_client(tmp_path)

    response = client.post("/login", json={"comercio_slug": "demo-cafe", "username": "cajero", "password": "1234"})

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["expires"] == "0"


def test_rechaza_host_no_permitido(tmp_path: Path):
    client = _build_test_client(tmp_path)

    response = client.get("/comercios/demo-cafe", headers={"host": "evil.example"})

    assert response.status_code == 400


def test_bloqueo_temporal_tras_multiples_intentos_fallidos(tmp_path: Path):
    client = _build_test_client(tmp_path)

    for _ in range(main.MAX_LOGIN_FAILED_ATTEMPTS):
        response = client.post("/login", json={"comercio_slug": "demo-cafe", "username": "cajero", "password": "mala"})

    assert response.status_code == 429

    bloqueado = client.post("/login", json={"comercio_slug": "demo-cafe", "username": "cajero", "password": "1234"})
    assert bloqueado.status_code == 429


def test_crea_cliente_y_registra_primera_visita(tmp_path: Path):
    client = _build_test_client(tmp_path)
    headers = _auth_headers(client)

    response = client.post("/registrar-visita", json={"telefono": "1234567890"}, headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["estado"] == "exito"
    assert body["mensaje"] == "Visita registrada correctamente"
    assert body["visitas"] == 1
    assert body["cliente"]["comercio"]["slug"] == "demo-cafe"
    assert body["cliente"]["visitas_actuales"] == 1
    assert body["cliente"]["objetivo_visitas"] == 5
    assert body["cliente"]["recompensas_total"] == 0
    assert body["cliente"]["public_id"]


def test_entrega_recompensa_en_quinta_visita_y_reinicia_contador(tmp_path: Path):
    client = _build_test_client(tmp_path)
    headers = _auth_headers(client)

    for _ in range(4):
        response = client.post("/registrar-visita", json={"telefono": "5555555555"}, headers=headers)
        assert response.status_code == 200
        assert response.json()["estado"] == "exito"

    recompensa = client.post("/registrar-visita", json={"telefono": "5555555555"}, headers=headers)

    assert recompensa.status_code == 200
    body = recompensa.json()
    assert body["estado"] == "recompensa"
    assert body["mensaje"] == "¡El cliente ganó su recompensa: Bebida gratis!"
    assert body["visitas"] == 0
    assert body["cliente"]["visitas_actuales"] == 0
    assert body["cliente"]["recompensas_total"] == 1


def test_valida_telefono_no_numerico(tmp_path: Path):
    client = _build_test_client(tmp_path)
    headers = _auth_headers(client)

    response = client.post("/registrar-visita", json={"telefono": "abc"}, headers=headers)

    assert response.status_code == 422


def test_valida_telefono_mayor_a_diez_digitos(tmp_path: Path):
    client = _build_test_client(tmp_path)
    headers = _auth_headers(client)

    response = client.post("/registrar-visita", json={"telefono": "12345678901"}, headers=headers)

    assert response.status_code == 422


def test_registrar_visita_sin_token_rechaza(tmp_path: Path):
    client = _build_test_client(tmp_path)

    response = client.post("/registrar-visita", json={"telefono": "1234567890"})

    assert response.status_code == 403


def test_auditoria_registra_login_y_visita(tmp_path: Path):
    client = _build_test_client(tmp_path)
    headers = _auth_headers(client)

    response = client.post("/registrar-visita", json={"telefono": "7777777777"}, headers=headers)
    assert response.status_code == 200

    db = main.app.state.testing_session_local()
    try:
        eventos = db.query(models.AuditoriaAccion).all()
    finally:
        db.close()

    acciones = {evento.accion for evento in eventos}
    assert "login_exitoso" in acciones
    assert "visita_registrada" in acciones


def test_obtener_cuenta_publica_cliente(tmp_path: Path):
    client = _build_test_client(tmp_path)
    headers = _auth_headers(client)

    registro = client.post("/registrar-visita", json={"telefono": "3001112233"}, headers=headers)
    public_id = registro.json()["cliente"]["public_id"]

    response = client.get(f"/comercios/demo-cafe/clientes/{public_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["public_id"] == public_id
    assert body["comercio"]["slug"] == "demo-cafe"
    assert body["telefono_mascarado"].endswith("2233")
    assert body["qr_value"].endswith(f"demo-cafe/cliente/{public_id}")
    assert body["wallet_links"]["apple"]
    assert body["wallet_links"]["google"]


def test_registrar_visita_por_qr(tmp_path: Path):
    client = _build_test_client(tmp_path)
    headers = _auth_headers(client)

    registro = client.post("/registrar-visita", json={"telefono": "3004445566"}, headers=headers)
    public_id = registro.json()["cliente"]["public_id"]

    response = client.post("/registrar-visita-qr", json={"public_id": public_id}, headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["estado"] == "exito"
    assert body["visitas"] == 2
    assert body["cliente"]["public_id"] == public_id


def test_acceso_cliente_por_comercio_y_telefono(tmp_path: Path):
    client = _build_test_client(tmp_path)
    headers = _auth_headers(client)
    client.post("/registrar-visita", json={"telefono": "3012223344"}, headers=headers)

    response = client.post("/comercios/demo-cafe/acceso-cliente", json={"telefono": "3012223344"})

    assert response.status_code == 200
    body = response.json()
    assert body["comercio"]["slug"] == "demo-cafe"
    assert body["telefono_mascarado"].endswith("3344")


def test_mismo_telefono_en_distintos_comercios_se_distingue(tmp_path: Path):
    client = _build_test_client(tmp_path)
    _crear_comercio_y_cajero("barrio-bakery")

    headers_demo = _auth_headers(client, "demo-cafe")
    headers_bakery = _auth_headers(client, "barrio-bakery")

    demo_response = client.post("/registrar-visita", json={"telefono": "3009990000"}, headers=headers_demo)
    bakery_response = client.post("/registrar-visita", json={"telefono": "3009990000"}, headers=headers_bakery)

    assert demo_response.status_code == 200
    assert bakery_response.status_code == 200
    assert demo_response.json()["cliente"]["public_id"] != bakery_response.json()["cliente"]["public_id"]
    assert demo_response.json()["cliente"]["comercio"]["slug"] == "demo-cafe"
    assert bakery_response.json()["cliente"]["comercio"]["slug"] == "barrio-bakery"


def test_actualizar_configuracion_comercio(tmp_path: Path):
    client = _build_test_client(tmp_path)
    headers = _auth_headers(client)

    response = client.put(
        "/comercios/configuracion",
        json={
            "nombre": "Cafe Aurora",
            "logo_url": "https://example.com/logo.png",
            "color_primario": "#111827",
            "color_secundario": "#f97316",
            "visitas_objetivo": 8,
            "recompensa_nombre": "Postre artesanal",
            "descripcion": "Especialidad de la casa"
        },
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["nombre"] == "Cafe Aurora"
    assert body["visitas_objetivo"] == 8
    assert body["recompensa_nombre"] == "Postre artesanal"


def test_subir_logo_jpg_comercio(tmp_path: Path):
    client = _build_test_client(tmp_path)
    headers = _auth_headers(client)

    response = client.post(
        "/comercios/configuracion/logo",
        files={"logo": ("logo.jpg", b"\xff\xd8\xff\xe0fake-jpg-content", "image/jpeg")},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["logo_url"] is not None
    assert "/static/logos/" in body["logo_url"]


def test_subir_logo_no_jpg_falla(tmp_path: Path):
    client = _build_test_client(tmp_path)
    headers = _auth_headers(client)

    response = client.post(
        "/comercios/configuracion/logo",
        files={"logo": ("logo.png", b"fake-png-content", "image/png")},
        headers=headers,
    )

    assert response.status_code == 400


def test_subir_logo_contenido_invalido_falla(tmp_path: Path):
    client = _build_test_client(tmp_path)
    headers = _auth_headers(client)

    response = client.post(
        "/comercios/configuracion/logo",
        files={"logo": ("logo.jpg", b"not-a-real-jpg", "image/jpeg")},
        headers=headers,
    )

    assert response.status_code == 400


def test_actualizar_configuracion_rechaza_logo_inseguro(tmp_path: Path):
    client = _build_test_client(tmp_path)
    headers = _auth_headers(client)

    response = client.put(
        "/comercios/configuracion",
        json={
            "nombre": "Cafe Aurora",
            "logo_url": "http://evil.example/logo.png",
            "color_primario": "#111827",
            "color_secundario": "#f97316",
            "visitas_objetivo": 8,
            "recompensa_nombre": "Postre artesanal",
            "descripcion": "Especialidad de la casa"
        },
        headers=headers,
    )

    assert response.status_code == 422


def test_cliente_puede_ver_todos_sus_comercios(tmp_path: Path):
    client = _build_test_client(tmp_path)
    _crear_comercio_y_cajero("barrio-bakery")

    headers_demo = _auth_headers(client, "demo-cafe")
    headers_bakery = _auth_headers(client, "barrio-bakery")

    client.post("/registrar-visita", json={"telefono": "3007778888"}, headers=headers_demo)
    client.post("/registrar-visita", json={"telefono": "3007778888"}, headers=headers_bakery)

    response = client.post("/clientes/mis-comercios", json={"telefono": "3007778888"})

    assert response.status_code == 200
    body = response.json()
    assert body["telefono_mascarado"].endswith("8888")
    assert len(body["cuentas"]) >= 2
    slugs = {item["comercio"]["slug"] for item in body["cuentas"]}
    assert "demo-cafe" in slugs
    assert "barrio-bakery" in slugs
