# Deploy en Railway (Backend + Frontend + Redis)

## 1) Estructura recomendada en Railway

Crea un proyecto en Railway con 3 servicios:

1. `saas-backend` (desde carpeta `backend`)
2. `saas-frontend` (desde carpeta `frontend`)
3. `redis` (plugin Redis de Railway)

Nota: Railway no usa `docker-compose.yml` directamente en produccion. Se despliega por servicio.

## 2) Backend (FastAPI)

### Servicio

- Root Directory: `backend`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

### Variables de entorno backend

Configura estas variables en `saas-backend`:

- `JWT_SECRET_KEY` = una clave larga y aleatoria
- `PUBLIC_BASE_URL` = URL publica del frontend (ej. `https://saas-frontend.up.railway.app`)
- `API_BASE_URL` = URL publica del backend (ej. `https://saas-backend.up.railway.app`)
- `REDIS_URL` = valor del servicio Redis en Railway
- `CORS_ALLOWED_ORIGINS` = URL del frontend (ej. `https://saas-frontend.up.railway.app`)
- `ALLOWED_HOSTS` = `localhost,127.0.0.1,*.up.railway.app`
- `UPLOADS_BASE_DIR` = ruta persistente para logos (ej. `/data/uploads`)

Persistencia de logos (recomendado):

- Crea un `Volume` en Railway y montalo en `/data`
- Define `UPLOADS_BASE_DIR=/data/uploads`
- Con esto, los archivos en `/data/uploads/logos` sobreviven a redeploys

Opcionales de rate limit:

- `RATE_LIMIT_LOGIN_IP`
- `RATE_LIMIT_LOGIN_IP_WINDOW`
- `RATE_LIMIT_LOGIN_SUBJECT`
- `RATE_LIMIT_LOGIN_SUBJECT_WINDOW`
- `RATE_LIMIT_SENSITIVE_IP`
- `RATE_LIMIT_SENSITIVE_IP_WINDOW`
- `RATE_LIMIT_SENSITIVE_SUBJECT`
- `RATE_LIMIT_SENSITIVE_SUBJECT_WINDOW`
- `INTERNAL_RATE_LIMIT_MULTIPLIER`
- `INTERNAL_NETWORKS`

### Verificacion

- Health: `GET https://tu-backend.up.railway.app/health`
- Debe responder algo como:
  - `{"status":"ok","rate_limit_backend":"redis"}`

Si responde `memory`, revisa `REDIS_URL`.

## 3) Frontend (Angular)

### Servicio

- Root Directory: `frontend`
- Build command:

```bash
sed -i "s|https://api.example.com|$API_BASE_URL|g" src/environments/environment.prod.ts
npm ci
npm run build
```

- Start command:

```bash
npx serve -s dist/saas-fidelidad-frontend -l $PORT
```

### Variable de entorno frontend

- `API_BASE_URL` = URL publica del backend (ej. `https://saas-backend.up.railway.app`)

## 4) Redis (Railway plugin)

- Agrega Redis desde `New > Database > Redis`
- Copia la variable de conexion y pegala en `REDIS_URL` del backend

## 5) Dominio y HTTPS

- Railway ya entrega HTTPS en `*.up.railway.app`
- Si luego usas dominio propio, actualiza:
  - `PUBLIC_BASE_URL`
  - `API_BASE_URL`
  - `CORS_ALLOWED_ORIGINS`

## 6) Checklist rapido

1. Backend desplegado y `/health` responde `ok`
2. Frontend desplegado y carga la UI
3. Login cajero funciona
4. Registro de visita funciona
5. `/health` muestra `rate_limit_backend = redis`
6. En tabla `auditoria_acciones` aparecen eventos `rate_limited` al forzar 429

## 7) Query SQL rapida de metricas (hero vs card vs wallet)

Si quieres auditar conversion por comercio sin pantalla, puedes usar esta query sobre `auditoria_acciones`:

```sql
SELECT
  comercio_id,
  SUM(CASE WHEN accion = 'analytics_evento' AND detalle LIKE '%evento=abrir_cuenta_cliente%' AND detalle LIKE '%origen=hero%' THEN 1 ELSE 0 END) AS hero_clicks,
  SUM(CASE WHEN accion = 'analytics_evento' AND detalle LIKE '%evento=abrir_cuenta_cliente%' AND detalle LIKE '%origen=card%' THEN 1 ELSE 0 END) AS card_clicks,
  SUM(CASE WHEN accion = 'analytics_evento' AND detalle LIKE '%evento=wallet_click%' AND detalle LIKE '%origen=apple_wallet%' THEN 1 ELSE 0 END) AS wallet_apple_clicks,
  SUM(CASE WHEN accion = 'analytics_evento' AND detalle LIKE '%evento=wallet_click%' AND detalle LIKE '%origen=google_wallet%' THEN 1 ELSE 0 END) AS wallet_google_clicks,
  SUM(CASE WHEN accion = 'analytics_evento' THEN 1 ELSE 0 END) AS total_clicks
FROM auditoria_acciones
GROUP BY comercio_id
ORDER BY total_clicks DESC;
```
