export const environment = {
  production: false,
  // Usa el mismo protocolo y host con el que se abrió la página (funciona desde HTTPS en red local)
  apiBaseUrl: `${typeof window !== 'undefined' ? window.location.protocol : 'https:'}//${typeof window !== 'undefined' ? window.location.hostname : 'localhost'}:8000`,
};