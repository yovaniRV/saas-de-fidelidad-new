export const environment = {
  production: false,
  // El backend local siempre corre en HTTP aunque el frontend use HTTPS (SSL en dev server).
  // Usamos http:// forzado para evitar mixed-content o ERR_SSL_PROTOCOL_ERROR.
  apiBaseUrl: `http://${typeof window !== 'undefined' ? window.location.hostname : 'localhost'}:8000`,
};