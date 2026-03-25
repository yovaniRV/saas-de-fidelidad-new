import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';

export interface RegistrarVisitaResponse {
  estado: 'exito' | 'recompensa';
  mensaje?: string;
  visitas: number;
  cliente: ClienteCuentaResponse;
}

export interface WalletLinks {
  apple: string | null;
  google: string | null;
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
}

export interface ComercioConfigUpdateRequest {
  nombre: string;
  logo_url: string | null;
  color_primario: string;
  color_secundario: string;
  visitas_objetivo: number;
  recompensa_nombre: string;
  descripcion: string | null;
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
  wallet_links: WalletLinks;
}

export interface ClienteMisComerciosResponse {
  telefono_mascarado: string;
  cuentas: ClienteCuentaResponse[];
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  comercio: ComercioBrandingResponse;
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

  constructor(private readonly http: HttpClient) {}

  login(comercioSlug: string, username: string, password: string): Observable<LoginResponse> {
    return this.http.post<LoginResponse>(this.loginUrl, {
      comercio_slug: comercioSlug,
      username,
      password
    });
  }

  guardarToken(token: string): void {
    localStorage.setItem(this.tokenKey, token);
  }

  guardarComercioSlug(slug: string): void {
    localStorage.setItem(this.comercioKey, slug);
  }

  limpiarToken(): void {
    localStorage.removeItem(this.tokenKey);
    localStorage.removeItem(this.comercioKey);
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

  registrarVisita(telefono: string): Observable<RegistrarVisitaResponse> {
    const token = this.obtenerToken();
    const headers = token
      ? new HttpHeaders({ Authorization: `Bearer ${token}` })
      : undefined;

    return this.http.post<RegistrarVisitaResponse>(this.apiUrl, { telefono }, { headers });
  }

  registrarVisitaPorQr(publicId: string): Observable<RegistrarVisitaResponse> {
    const token = this.obtenerToken();
    const headers = token
      ? new HttpHeaders({ Authorization: `Bearer ${token}` })
      : undefined;

    return this.http.post<RegistrarVisitaResponse>(this.qrUrl, { public_id: publicId }, { headers });
  }

  obtenerComercio(slug: string): Observable<ComercioBrandingResponse> {
    return this.http.get<ComercioBrandingResponse>(`${this.baseUrl}/comercios/${slug}`);
  }

  actualizarComercio(payload: ComercioConfigUpdateRequest): Observable<ComercioBrandingResponse> {
    const token = this.obtenerToken();
    const headers = token
      ? new HttpHeaders({ Authorization: `Bearer ${token}` })
      : undefined;

    return this.http.put<ComercioBrandingResponse>(`${this.baseUrl}/comercios/configuracion`, payload, { headers });
  }

  subirLogoComercio(file: File): Observable<ComercioBrandingResponse> {
    const token = this.obtenerToken();
    const headers = token
      ? new HttpHeaders({ Authorization: `Bearer ${token}` })
      : undefined;

    const formData = new FormData();
    formData.append('logo', file);

    return this.http.post<ComercioBrandingResponse>(`${this.baseUrl}/comercios/configuracion/logo`, formData, { headers });
  }

  obtenerCuentaCliente(comercioSlug: string, publicId: string): Observable<ClienteCuentaResponse> {
    return this.http.get<ClienteCuentaResponse>(`${this.baseUrl}/comercios/${comercioSlug}/clientes/${publicId}`);
  }

  accederCuentaCliente(comercioSlug: string, telefono: string): Observable<ClienteCuentaResponse> {
    return this.http.post<ClienteCuentaResponse>(`${this.baseUrl}/comercios/${comercioSlug}/acceso-cliente`, {
      telefono
    });
  }

  obtenerMisComercios(telefono: string): Observable<ClienteMisComerciosResponse> {
    return this.http.post<ClienteMisComerciosResponse>(`${this.baseUrl}/clientes/mis-comercios`, { telefono });
  }
}
