import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Observable, map } from 'rxjs';

import { environment } from '../../environments/environment';

export interface RegistrarVisitaResponse {
  estado: 'exito' | 'recompensa';
  mensaje?: string;
  visitas: number;
  cliente: ClienteCuentaResponse;
}

export interface SuscripcionComercio {
  plan: 'mensual' | 'trimestral' | 'anual' | 'personalizado';
  estado: 'prueba' | 'activa' | 'vencida' | 'suspendida' | 'cancelada';
  monto_mxn: number;
  proximo_cobro: string | null;
  notas: string | null;
}

export interface ComercioBrandingResponse {
  slug: string;
  nombre: string;
  logo_url: string | null;
  color_primario: string;
  color_secundario: string;
  visitas_objetivo: number;
  recompensa_nombre: string;
  descripcion: string | null;
  momento_recomendado?: string | null;
  mensaje_contextual?: string | null;
  suscripcion: SuscripcionComercio;
}

export interface AnalyticsEventRequest {
  comercio_slug: string;
  public_id: string | null;
  evento: string;
  origen: string;
}

export interface AnalyticsEventResponse {
  status: string;
}

export interface AnalyticsSummaryResponse {
  hero_clicks: number;
  card_clicks: number;
  wallet_apple_clicks: number;
  wallet_google_clicks: number;
  total_clicks: number;
}

export interface CajeroCreateRequest {
  username: string;
  password: string;
  nombre_mostrado: string | null;
}

export interface CajeroResponse {
  id: number;
  username: string;
  nombre_mostrado: string | null;
  rol: 'cajero' | 'jefe';
  activo: boolean;
}

export interface ComercioCreateRequest {
  slug: string;
  nombre: string;
  jefe_username: string;
  jefe_password: string;
  jefe_nombre_mostrado: string | null;
  color_primario: string;
  color_secundario: string;
  visitas_objetivo: number;
  recompensa_nombre: string;
  descripcion: string | null;
}

export interface ComercioCreateResponse {
  comercio: ComercioBrandingResponse;
  jefe: CajeroResponse;
}

export interface AdminComercioResumenResponse {
  slug: string;
  nombre: string;
  suscripcion: SuscripcionComercio;
}

export interface AdminSuscripcionUpdateRequest {
  plan: SuscripcionComercio['plan'];
  estado: SuscripcionComercio['estado'];
  monto_mxn: number;
  proximo_cobro: string | null;
  notas: string | null;
}

export interface AdminPersonalComercioResponse {
  comercio: AdminComercioResumenResponse;
  personal: CajeroResponse[];
}

export interface AdminJefeCreateRequest {
  username: string;
  password: string;
  nombre_mostrado: string | null;
}

export interface AdminCambiarRolRequest {
  rol: 'jefe' | 'cajero';
}

export interface AdminCambiarEstadoRequest {
  activo: boolean;
}

export interface ComercioConfigUpdateRequest {
  nombre: string;
  logo_url: string | null;
  color_primario: string;
  color_secundario: string;
  visitas_objetivo: number;
  recompensa_nombre: string;
  descripcion: string | null;
  momento_recomendado: string | null;
  mensaje_contextual: string | null;
}

export interface ClienteCuentaResponse {
  comercio: ComercioBrandingResponse;
  public_id: string;
  telefono_mascarado: string;
  visitas_actuales: number;
  objetivo_visitas: number;
  recompensas_total: number;
  account_url: string;
  qr_value: string;
}

export interface ClienteMisComerciosResponse {
  telefono_mascarado: string;
  cuentas: ClienteCuentaResponse[];
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  rol: 'admin' | 'jefe' | 'cajero';
  comercio: ComercioBrandingResponse | null;
}

@Injectable({
  providedIn: 'root'
})
export class VisitaService {
  private readonly baseUrl = environment.apiBaseUrl.replace(/\/$/, '');
  private readonly loginUrl = `${this.baseUrl}/login`;
  private readonly apiUrl = `${this.baseUrl}/registrar-visita`;
  private readonly qrUrl = `${this.baseUrl}/registrar-visita-qr`;
  private readonly tokenKey = 'saas_fidelidad_token';
  private readonly comercioKey = 'saas_fidelidad_comercio_slug';
  private readonly roleKey = 'saas_fidelidad_rol';

  constructor(private readonly http: HttpClient) {}

  private normalizarLogoUrl(logoUrl: string | null): string | null {
    if (!logoUrl) {
      return null;
    }

    if (/^https?:\/\//i.test(logoUrl)) {
      return logoUrl;
    }

    if (logoUrl.startsWith('/')) {
      return `${this.baseUrl}${logoUrl}`;
    }

    return logoUrl;
  }

  private normalizarComercio(comercio: ComercioBrandingResponse): ComercioBrandingResponse {
    return {
      ...comercio,
      logo_url: this.normalizarLogoUrl(comercio.logo_url),
    };
  }

  private normalizarClienteCuenta(cuenta: ClienteCuentaResponse): ClienteCuentaResponse {
    const comercio = this.normalizarComercio(cuenta.comercio);
    return {
      ...cuenta,
      comercio,
      objetivo_visitas: comercio.visitas_objetivo,
    };
  }

  private normalizarRegistrarVisitaResponse(response: RegistrarVisitaResponse): RegistrarVisitaResponse {
    return {
      ...response,
      cliente: this.normalizarClienteCuenta(response.cliente),
    };
  }

  private authHeaders(): HttpHeaders | undefined {
    const token = this.obtenerToken();
    return token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : undefined;
  }

  login(username: string, password: string): Observable<LoginResponse> {
    // Enviar el objeto directamente para que Angular lo serialice como JSON
    return this.http.post<LoginResponse>(
      this.loginUrl,
      { username: username?.trim(), password: password?.trim() },
      {
        headers: { 'Content-Type': 'application/json' }
      }
    ).pipe(
      map((response) => ({
        ...response,
        comercio: response.comercio ? this.normalizarComercio(response.comercio) : null,
      }))
    );
  }

  guardarToken(token: string): void {
    localStorage.setItem(this.tokenKey, token);
  }

  guardarComercioSlug(slug: string): void {
    localStorage.setItem(this.comercioKey, slug);
  }

  guardarRol(rol: LoginResponse['rol']): void {
    localStorage.setItem(this.roleKey, rol);
  }

  limpiarToken(): void {
    localStorage.removeItem(this.tokenKey);
    localStorage.removeItem(this.comercioKey);
    localStorage.removeItem(this.roleKey);
  }

  estaAutenticado(): boolean {
    return !!this.obtenerToken();
  }

  obtenerToken(): string | null {
    return localStorage.getItem(this.tokenKey);
  }

  obtenerComercioSlug(): string | null {
    return localStorage.getItem(this.comercioKey);
  }

  obtenerRol(): LoginResponse['rol'] | null {
    const rol = localStorage.getItem(this.roleKey);
    if (rol === 'admin' || rol === 'jefe' || rol === 'cajero') {
      return rol;
    }
    return null;
  }

  registrarVisita(telefono: string): Observable<RegistrarVisitaResponse> {
    const headers = this.authHeaders();
    return this.http.post<RegistrarVisitaResponse>(this.apiUrl, { telefono }, { headers }).pipe(
      map((response) => this.normalizarRegistrarVisitaResponse(response))
    );
  }

  registrarVisitaPorQr(publicId: string): Observable<RegistrarVisitaResponse> {
    const headers = this.authHeaders();
    return this.http.post<RegistrarVisitaResponse>(this.qrUrl, { public_id: publicId }, { headers }).pipe(
      map((response) => this.normalizarRegistrarVisitaResponse(response))
    );
  }

  obtenerComercio(slug: string): Observable<ComercioBrandingResponse> {
    return this.http.get<ComercioBrandingResponse>(`${this.baseUrl}/comercios/${slug}`).pipe(
      map((response) => this.normalizarComercio(response))
    );
  }

  actualizarComercio(payload: ComercioConfigUpdateRequest): Observable<ComercioBrandingResponse> {
    const headers = this.authHeaders();
    return this.http.put<ComercioBrandingResponse>(`${this.baseUrl}/comercios/configuracion`, payload, { headers }).pipe(
      map((response) => this.normalizarComercio(response))
    );
  }

  subirLogoComercio(file: File): Observable<ComercioBrandingResponse> {
    const headers = this.authHeaders();

    const formData = new FormData();
    formData.append('logo', file);

    return this.http.post<ComercioBrandingResponse>(`${this.baseUrl}/comercios/configuracion/logo`, formData, { headers }).pipe(
      map((response) => this.normalizarComercio(response))
    );
  }

  obtenerCuentaCliente(comercioSlug: string, publicId: string): Observable<ClienteCuentaResponse> {
    return this.http.get<ClienteCuentaResponse>(`${this.baseUrl}/comercios/${comercioSlug}/clientes/${publicId}`).pipe(
      map((response) => this.normalizarClienteCuenta(response))
    );
  }

  obtenerCuentaClientePorId(publicId: string): Observable<ClienteCuentaResponse> {
    return this.http.get<ClienteCuentaResponse>(`${this.baseUrl}/clientes/${publicId}`).pipe(
      map((response) => this.normalizarClienteCuenta(response))
    );
  }

  accederCuentaCliente(comercioSlug: string, telefono: string): Observable<ClienteCuentaResponse> {
    return this.http.post<ClienteCuentaResponse>(`${this.baseUrl}/comercios/${comercioSlug}/acceso-cliente`, {
      telefono
    }).pipe(
      map((response) => this.normalizarClienteCuenta(response))
    );
  }

  obtenerMisComercios(telefono: string): Observable<ClienteMisComerciosResponse> {
    return this.http.post<ClienteMisComerciosResponse>(`${this.baseUrl}/clientes/mis-comercios`, { telefono }).pipe(
      map((response) => ({
        ...response,
        cuentas: response.cuentas.map((cuenta) => this.normalizarClienteCuenta(cuenta)),
      }))
    );
  }

  registrarEventoAnalitico(payload: AnalyticsEventRequest): Observable<AnalyticsEventResponse> {
    return this.http.post<AnalyticsEventResponse>(`${this.baseUrl}/analytics/eventos`, payload);
  }

  obtenerResumenAnalyticsComercio(desde?: string | null, hasta?: string | null): Observable<AnalyticsSummaryResponse> {
    const headers = this.authHeaders();

    let params = new HttpParams();
    if (desde) {
      params = params.set('desde', desde);
    }
    if (hasta) {
      params = params.set('hasta', hasta);
    }

    return this.http.get<AnalyticsSummaryResponse>(`${this.baseUrl}/analytics/resumen/comercio`, { headers, params });
  }

  listarCajeros(): Observable<CajeroResponse[]> {
    const headers = this.authHeaders();

    return this.http.get<CajeroResponse[]>(`${this.baseUrl}/cajeros`, { headers });
  }

  crearCajero(payload: CajeroCreateRequest): Observable<CajeroResponse> {
    const headers = this.authHeaders();

    return this.http.post<CajeroResponse>(`${this.baseUrl}/cajeros`, payload, { headers });
  }

  crearComercio(payload: ComercioCreateRequest): Observable<ComercioCreateResponse> {
    const headers = this.authHeaders();

    return this.http.post<ComercioCreateResponse>(`${this.baseUrl}/comercios`, payload, { headers });
  }

  listarComerciosAdmin(): Observable<AdminComercioResumenResponse[]> {
    const headers = this.authHeaders();

    return this.http.get<AdminComercioResumenResponse[]>(`${this.baseUrl}/admin/comercios`, { headers });
  }

  crearJefeAdmin(comercioSlug: string, payload: AdminJefeCreateRequest): Observable<CajeroResponse> {
    const headers = this.authHeaders();

    return this.http.post<CajeroResponse>(`${this.baseUrl}/admin/comercios/${comercioSlug}/jefes`, payload, { headers });
  }

  listarPersonalAdmin(comercioSlug: string): Observable<AdminPersonalComercioResponse> {
    const headers = this.authHeaders();

    return this.http.get<AdminPersonalComercioResponse>(`${this.baseUrl}/admin/comercios/${comercioSlug}/personal`, { headers });
  }

  cambiarRolAdmin(cajeroId: number, payload: AdminCambiarRolRequest): Observable<CajeroResponse> {
    const headers = this.authHeaders();

    return this.http.patch<CajeroResponse>(`${this.baseUrl}/admin/cajeros/${cajeroId}/rol`, payload, { headers });
  }

  cambiarEstadoAdmin(cajeroId: number, payload: AdminCambiarEstadoRequest): Observable<CajeroResponse> {
    const headers = this.authHeaders();

    return this.http.patch<CajeroResponse>(`${this.baseUrl}/admin/cajeros/${cajeroId}/estado`, payload, { headers });
  }

  actualizarSuscripcionAdmin(comercioSlug: string, payload: AdminSuscripcionUpdateRequest): Observable<AdminComercioResumenResponse> {
    const headers = this.authHeaders();

    return this.http.patch<AdminComercioResumenResponse>(`${this.baseUrl}/admin/comercios/${comercioSlug}/suscripcion`, payload, { headers });
  }

}
