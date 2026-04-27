# Migración a Render (Backend Gratuito)

## Pasos para migrar el backend a Render

### 1. Crear cuenta en Render
- Ve a [render.com](https://render.com) y regístrate gratis.

### 2. Crear PostgreSQL Database
- En dashboard: "New" → "PostgreSQL"
- Elige "Free" tier
- Nombre: `saas-db`
- Crea la DB (espera a que esté listo)
- Copia la `DATABASE_URL` (ej: `postgresql://user:pass@host:5432/db`)

### 3. Migrar datos de SQLite a PostgreSQL
- Los datos ya están exportados a `db_dump.sql`.
- Importa manualmente desde tu terminal:
  ```
  psql "postgresql://saas_db_rew2_user:0kQZTuwwbvpBwmO559u8kGDXESULxnod@dpg-d7nr1pl7vvec739bn0s0-a/saas_db_rew2" < db_dump.sql
  ```
- O sube `db_dump.sql` al dashboard de Render y usa su herramienta de importación.

### 4. Crear Web Service
- En dashboard: "New" → "Web Service"
- Conecta tu repo GitHub `vani875/saas-de-fidelidad-vani875`
- Elige branch `main`
- Build settings:
  - Runtime: `Docker`
  - Dockerfile path: `backend/Dockerfile` (Render detectará automáticamente)
- Environment: `Production`
- Variables de entorno:
  - `DATABASE_URL`: `postgresql://saas_db_rew2_user:0kQZTuwwbvpBwmO559u8kGDXESULxnod@dpg-d7nr1pl7vvec739bn0s0-a/saas_db_rew2`
  - `JWT_SECRET_KEY`: `CMKU4GtUyaWrKvrTqm92NkFlbVH-ZoX-Nu5ubms-11E`
  - `CORS_ALLOWED_ORIGINS`: `https://browser-mu-dusky.vercel.app`
  - `UPLOADS_BASE_DIR`: `/tmp/uploads` (logos temporales)
  - `PUBLIC_BASE_URL`: `https://tu-frontend.vercel.app`
  - `API_BASE_URL`: `https://tu-backend.onrender.com` (se asignará después)
- Deploy

### 5. Actualizar Frontend
- Una vez desplegado, obtén la URL de Render (ej: `https://saas-backend.onrender.com`)
- Edita `frontend/src/environments/environment.prod.ts`:
  ```ts
  export const environment = {
    production: true,
    apiBaseUrl: 'https://tu-backend.onrender.com',
  };
  ```
- Redeploy en Vercel.

### 6. Verificar
- Backend: `https://tu-backend.onrender.com/health`
- Frontend: debería funcionar sin CORS errors.

## Notas
- Render gratuito duerme después de 15 min inactivo.
- Logos se pierden al redeploy; considera Cloudinary gratis para producción.
- Si hay errores, revisa logs en Render dashboard.