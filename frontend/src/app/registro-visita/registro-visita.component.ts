import { CommonModule } from '@angular/common';
import { AfterViewChecked, Component, OnDestroy, OnInit } from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { Html5Qrcode } from 'html5-qrcode';

import {
  AnalyticsSummaryResponse,
  CajeroResponse,
  ClienteCuentaResponse,
  ComercioConfigUpdateRequest,
  ComercioBrandingResponse,
  LoginResponse,
  RegistrarVisitaResponse,
  VisitaService
} from '../services/visita.service';

@Component({
  selector: 'app-registro-visita',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './registro-visita.component.html',
  styleUrls: ['./registro-visita.component.css']
})
export class RegistroVisitaComponent implements AfterViewChecked, OnDestroy, OnInit {
  comercioSlug = '';
  comercio: ComercioBrandingResponse | null = null;
  username = '';
  password = '';
  telefono = '';
  mensaje = '';
  mensajeLogin = '';
  mensajeConfig = '';
  mensajeComercioNuevo = '';
  modoRegistro: 'telefono' | 'qr' = 'telefono';
  qrActivo = false;
  escanerError = '';
  autenticado = false;
  rolUsuario: 'admin' | 'jefe' | 'cajero' | null = null;
  esRecompensa = false;
  cargando = false;
  cargandoLogin = false;
  guardandoConfig = false;
  cargandoMetricas = false;
  seccionActiva: 'registro' | 'metricas' | 'cajeros' | 'configuracion' = 'registro';
  ultimoCliente: ClienteCuentaResponse | null = null;
  resumenAnalytics: AnalyticsSummaryResponse | null = null;
  cajeros: CajeroResponse[] = [];
  cargandoCajeros = false;
  guardandoCajero = false;
  mensajeCajero = '';
  nuevoCajero = {
    username: '',
    password: '',
    nombre_mostrado: ''
  };
  analyticsDesde = '';
  analyticsHasta = '';
  presetRango: '7d' | '30d' | '90d' = '30d';
  comercioForm: ComercioConfigUpdateRequest = {
    nombre: '',
    logo_url: null,
    color_primario: '#0f766e',
    color_secundario: '#f59e0b',
    visitas_objetivo: 5,
    recompensa_nombre: 'Bebida gratis',
    descripcion: null,
    momento_recomendado: null,
    mensaje_contextual: null
  };
  logoErrores: Record<string, boolean> = {};

  private qrScanner: Html5Qrcode | null = null;
  private scannerMountPending = false;

  constructor(
    private readonly visitaService: VisitaService,
    private readonly router: Router,
  ) {
    this.autenticado = this.visitaService.estaAutenticado();
    this.comercioSlug = this.visitaService.obtenerComercioSlug() ?? '';
    this.rolUsuario = this.visitaService.obtenerRol();
    this.inicializarRangoMetricas();
  }

  ngOnInit(): void {
    if (this.autenticado && this.rolUsuario === 'admin') {
      void this.router.navigate(['/admin']);
      return;
    }

    if (this.comercioSlug) {
      this.cargarComercio();
    }
  }

  ngAfterViewChecked(): void {
    if (this.scannerMountPending) {
      this.scannerMountPending = false;
      this.iniciarEscanerQr();
    }
  }

  ngOnDestroy(): void {
    this.detenerEscanerQr();
  }

  onUsernameInput(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.username = input.value;
  }

  onPasswordInput(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.password = input.value;
  }

  iniciarSesion(): void {
    if (!this.username || !this.password) {
      this.mensajeLogin = 'Ingresa usuario y contrasena.';
      return;
    }

    this.cargandoLogin = true;
    this.mensajeLogin = '';

    this.visitaService.login(this.username, this.password).subscribe({
      next: (response: LoginResponse) => {
        this.visitaService.guardarToken(response.access_token);
        this.rolUsuario = response.rol;
        this.visitaService.guardarRol(response.rol);
        this.autenticado = true;
        if (response.rol === 'admin') {
          this.cargandoLogin = false;
          void this.router.navigate(['/admin']);
          return;
        } else {
          this.comercioSlug = response.comercio?.slug ?? '';
          this.visitaService.guardarComercioSlug(this.comercioSlug);
          this.comercio = response.comercio;
          if (response.comercio) {
            this.sincronizarFormularioComercio(response.comercio);
          }
          this.seccionActiva = 'registro';
          this.cargarResumenAnalytics();
          if (this.puedeGestionarCajeros) {
            this.cargarCajeros();
          }
        }
        this.cargandoLogin = false;
        this.mensaje = '';
      },
      error: (err) => {
        if (err?.status === 429) {
          this.mensajeLogin = err?.error?.detail ?? 'Cuenta bloqueada temporalmente.';
        } else if (err?.status === 409) {
          this.mensajeLogin = err?.error?.detail ?? 'Usuario ambiguo. Contacta al administrador.';
        } else {
          this.mensajeLogin = 'Credenciales invalidas.';
        }
        this.cargandoLogin = false;
      }
    });
  }

  cerrarSesion(): void {
    this.visitaService.limpiarToken();
    this.autenticado = false;
    this.rolUsuario = null;
    this.mensaje = '';
    this.mensajeLogin = 'Sesion cerrada.';
    this.ultimoCliente = null;
    this.resumenAnalytics = null;
    this.seccionActiva = 'registro';
    this.cajeros = [];
    this.nuevoCajero = { username: '', password: '', nombre_mostrado: '' };
    this.mensajeCajero = '';
    this.detenerEscanerQr();
  }

  cargarComercio(): void {
    if (!this.comercioSlug) {
      return;
    }

    this.visitaService.obtenerComercio(this.comercioSlug).subscribe({
      next: (response) => {
        this.comercio = response;
        this.sincronizarFormularioComercio(response);
        if (this.autenticado) {
          this.cargarResumenAnalytics();
          if (this.puedeGestionarCajeros) {
            this.cargarCajeros();
          }
        }
      },
      error: () => {
        this.comercio = null;
      }
    });
  }

  sincronizarFormularioComercio(comercio: ComercioBrandingResponse): void {
    this.logoErrores = {};
    this.comercioForm = {
      nombre: comercio.nombre,
      logo_url: comercio.logo_url,
      color_primario: comercio.color_primario,
      color_secundario: comercio.color_secundario,
      visitas_objetivo: comercio.visitas_objetivo,
      recompensa_nombre: comercio.recompensa_nombre,
      descripcion: comercio.descripcion,
      momento_recomendado: comercio.momento_recomendado ?? null,
      mensaje_contextual: comercio.mensaje_contextual ?? null
    };
  }

  mostrarLogo(url: string | null | undefined, key: string): boolean {
    return !!url && !this.logoErrores[key];
  }

  marcarLogoError(key: string): void {
    this.logoErrores[key] = true;
  }

  inicialesComercio(nombre: string | null | undefined): string {
    return (nombre ?? '')
      .split(' ')
      .filter(Boolean)
      .slice(0, 2)
      .map((segmento) => segmento[0]?.toUpperCase() ?? '')
      .join('') || 'LC';
  }

  cambiarSeccion(seccion: 'registro' | 'metricas' | 'cajeros' | 'configuracion'): void {
    this.seccionActiva = seccion;
  }

  get esAdmin(): boolean {
    return this.rolUsuario === 'admin';
  }

  get esJefe(): boolean {
    return this.rolUsuario === 'jefe';
  }

  get puedeGestionarCajeros(): boolean {
    return this.esAdmin || this.esJefe;
  }

  get puedePersonalizarComercio(): boolean {
    return this.esJefe;
  }

  onConfigInput(field: keyof ComercioConfigUpdateRequest, event: Event): void {
    const input = event.target as HTMLInputElement | HTMLTextAreaElement;
    const value = input.value;

    if (field === 'visitas_objetivo') {
      this.comercioForm.visitas_objetivo = Number(value) || 1;
      return;
    }

    this.comercioForm = {
      ...this.comercioForm,
      [field]: value || null
    };
  }

  guardarConfiguracionComercio(): void {
    this.guardandoConfig = true;
    this.mensajeConfig = '';

    this.visitaService.actualizarComercio(this.comercioForm).subscribe({
      next: (response) => {
        this.comercio = response;
        this.sincronizarFormularioComercio(response);
        this.cargarResumenAnalytics();
        this.cargarCajeros();
        this.guardandoConfig = false;
        this.mensajeConfig = 'Configuracion guardada.';
      },
      error: () => {
        this.guardandoConfig = false;
        this.mensajeConfig = 'No fue posible guardar la configuracion del comercio.';
      }
    });
  }

  onLogoFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) {
      return;
    }

    const isJpg = file.type === 'image/jpeg' || /\.jpe?g$/i.test(file.name);
    if (!isJpg) {
      this.mensajeConfig = 'Solo se permiten logos en formato JPG.';
      input.value = '';
      return;
    }

    this.guardandoConfig = true;
    this.mensajeConfig = '';
    this.visitaService.subirLogoComercio(file).subscribe({
      next: (response) => {
        this.comercio = response;
        this.sincronizarFormularioComercio(response);
        this.cargarResumenAnalytics();
        this.cargarCajeros();
        this.guardandoConfig = false;
        this.mensajeConfig = 'Logo actualizado correctamente.';
        input.value = '';
      },
      error: (err) => {
        this.guardandoConfig = false;
        this.mensajeConfig = err?.error?.detail ?? 'No fue posible subir el logo.';
        input.value = '';
      }
    });
  }

  onTelefonoInput(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.telefono = input.value.replace(/\D/g, '').slice(0, 10);
  }

  cambiarModo(modo: 'telefono' | 'qr'): void {
    this.modoRegistro = modo;
    this.mensaje = '';
    this.esRecompensa = false;
    this.escanerError = '';

    if (modo === 'qr') {
      this.scannerMountPending = true;
      return;
    }

    this.detenerEscanerQr();
  }

  iniciarEscanerQr(): void {
    if (!this.autenticado || this.qrActivo) {
      return;
    }

    const regionId = 'qr-reader';
    this.qrScanner = new Html5Qrcode(regionId);
    this.qrScanner.start(
      { facingMode: 'environment' },
      { fps: 10, qrbox: 220 },
      (decodedText) => {
        const publicId = this.extraerPublicId(decodedText);
        if (!publicId) {
          this.escanerError = 'QR invalido para este sistema.';
          return;
        }
        this.detenerEscanerQr();
        this.registrarVisitaDesdeQr(publicId);
      },
      () => undefined
    ).then(() => {
      this.qrActivo = true;
    }).catch(() => {
      this.escanerError = 'No se pudo acceder a la camara. Revisa permisos del navegador.';
      this.qrActivo = false;
    });
  }

  detenerEscanerQr(): void {
    if (!this.qrScanner) {
      this.qrActivo = false;
      return;
    }

    void this.qrScanner.stop().catch(() => undefined).finally(() => {
      if (this.qrScanner) {
        this.qrScanner.clear();
      }
      this.qrScanner = null;
      this.qrActivo = false;
    });
  }

  extraerPublicId(rawValue: string): string | null {
    try {
      const url = new URL(rawValue);
      const segments = url.pathname.split('/').filter(Boolean);
      if (segments.length >= 4 && segments[0] === 'comercio' && segments[2] === 'cliente') {
        return segments[3];
      }
      if (segments.length >= 2 && segments[0] === 'cliente') {
        return segments[1];
      }
      return null;
    } catch {
      return rawValue.trim() || null;
    }
  }

  registrarVisitaDesdeQr(publicId: string): void {
    this.cargando = true;
    this.mensaje = '';
    this.esRecompensa = false;

    this.visitaService.registrarVisitaPorQr(publicId).subscribe({
      next: (response: RegistrarVisitaResponse) => {
        this.aplicarRespuestaRegistro(response);
        this.cambiarModo('qr');
      },
      error: () => {
        this.cargando = false;
        this.escanerError = 'No fue posible registrar la visita desde QR.';
        this.scannerMountPending = true;
      }
    });
  }

  aplicarRespuestaRegistro(response: RegistrarVisitaResponse): void {
    this.ultimoCliente = response.cliente;
    this.esRecompensa = response.estado === 'recompensa';
    this.mensaje = response.mensaje ?? (this.esRecompensa
      ? '¡El cliente ganó su recompensa!'
      : 'Visita registrada correctamente.');
    if (this.esRecompensa) {
      alert('¡El cliente ganó su recompensa!');
    }
    this.telefono = '';
    this.cargando = false;
  }

  registrarVisita(): void {
    if (!this.autenticado) {
      this.esRecompensa = false;
      this.mensaje = 'Primero debes iniciar sesion como cajero.';
      return;
    }

    if (!this.telefono || this.telefono.length > 10) {
      this.esRecompensa = false;
      this.mensaje = 'Ingresa un telefono valido de hasta 10 digitos.';
      return;
    }

    this.cargando = true;
    this.mensaje = '';
    this.esRecompensa = false;

    this.visitaService.registrarVisita(this.telefono).subscribe({
      next: (response: RegistrarVisitaResponse) => {
        this.aplicarRespuestaRegistro(response);
        this.cargarResumenAnalytics();
      },
      error: (err) => {
        this.esRecompensa = false;
        if (err?.status === 401 || err?.status === 403) {
          this.mensaje = 'Sesion expirada o invalida. Inicia sesion nuevamente.';
          this.autenticado = false;
          this.visitaService.limpiarToken();
        } else {
          this.mensaje = 'No fue posible registrar la visita. Intenta nuevamente.';
        }
        this.cargando = false;
      }
    });
  }

  cargarResumenAnalytics(): void {
    if (!this.autenticado) {
      this.resumenAnalytics = null;
      return;
    }

    this.cargandoMetricas = true;
    this.visitaService.obtenerResumenAnalyticsComercio(this.analyticsDesde || null, this.analyticsHasta || null).subscribe({
      next: (resumen) => {
        this.resumenAnalytics = resumen;
        this.cargandoMetricas = false;
      },
      error: () => {
        this.cargandoMetricas = false;
      }
    });
  }

  onAnalyticsDesdeInput(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.analyticsDesde = input.value;
  }

  onAnalyticsHastaInput(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.analyticsHasta = input.value;
  }

  aplicarFiltroMetricas(): void {
    if (this.analyticsDesde && this.analyticsHasta && this.analyticsDesde > this.analyticsHasta) {
      this.mensajeConfig = 'Rango de metricas invalido: la fecha desde no puede ser mayor que hasta.';
      return;
    }

    this.mensajeConfig = '';
    this.cargarResumenAnalytics();
  }

  limpiarFiltroMetricas(): void {
    this.presetRango = '30d';
    this.inicializarRangoMetricas();
    this.mensajeConfig = '';
    this.cargarResumenAnalytics();
  }

  aplicarPresetRango(preset: '7d' | '30d' | '90d'): void {
    this.presetRango = preset;

    const hoy = new Date();
    const desde = new Date(hoy);
    const dias = preset === '7d' ? 7 : preset === '30d' ? 30 : 90;
    desde.setDate(desde.getDate() - dias);

    this.analyticsHasta = this.formatearFechaInput(hoy);
    this.analyticsDesde = this.formatearFechaInput(desde);
    this.mensajeConfig = '';
    this.cargarResumenAnalytics();
  }

  get porcentajeHero(): number {
    if (!this.resumenAnalytics?.total_clicks) {
      return 0;
    }
    return Math.round((this.resumenAnalytics.hero_clicks / this.resumenAnalytics.total_clicks) * 100);
  }

  get porcentajeCard(): number {
    if (!this.resumenAnalytics?.total_clicks) {
      return 0;
    }
    return Math.round((this.resumenAnalytics.card_clicks / this.resumenAnalytics.total_clicks) * 100);
  }

  get porcentajeWallet(): number {
    if (!this.resumenAnalytics?.total_clicks) {
      return 0;
    }
    const walletTotal = this.resumenAnalytics.wallet_apple_clicks + this.resumenAnalytics.wallet_google_clicks;
    return Math.round((walletTotal / this.resumenAnalytics.total_clicks) * 100);
  }

  get insightPrincipalMetricas(): string {
    if (!this.resumenAnalytics || this.resumenAnalytics.total_clicks === 0) {
      return 'Todavia no hay clics suficientes. Prueba destacar una oferta en la hero y revisar en unas horas.';
    }

    const canales = [
      { nombre: 'Hero principal', valor: this.resumenAnalytics.hero_clicks },
      { nombre: 'Cards del listado', valor: this.resumenAnalytics.card_clicks },
      { nombre: 'Wallets', valor: this.resumenAnalytics.wallet_apple_clicks + this.resumenAnalytics.wallet_google_clicks },
    ].sort((a, b) => b.valor - a.valor);

    return `${canales[0].nombre} lidera con ${canales[0].valor} clics en este rango.`;
  }

  private inicializarRangoMetricas(): void {
    const hoy = new Date();
    const hace30 = new Date(hoy);
    hace30.setDate(hace30.getDate() - 30);

    this.analyticsHasta = this.formatearFechaInput(hoy);
    this.analyticsDesde = this.formatearFechaInput(hace30);
  }

  private formatearFechaInput(fecha: Date): string {
    const year = fecha.getFullYear();
    const month = String(fecha.getMonth() + 1).padStart(2, '0');
    const day = String(fecha.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  onNuevoCajeroInput(field: 'username' | 'password' | 'nombre_mostrado', event: Event): void {
    const input = event.target as HTMLInputElement;
    this.nuevoCajero = {
      ...this.nuevoCajero,
      [field]: input.value,
    };
  }

  cargarCajeros(): void {
    if (!this.autenticado || !this.esJefe) {
      this.cajeros = [];
      return;
    }

    this.cargandoCajeros = true;
    this.visitaService.listarCajeros().subscribe({
      next: (listado) => {
        this.cajeros = listado;
        this.cargandoCajeros = false;
      },
      error: () => {
        this.cargandoCajeros = false;
      }
    });
  }

  crearNuevoCajero(): void {
    if (!this.esJefe) {
      this.mensajeCajero = 'Solo el jefe del comercio puede crear cajeros.';
      return;
    }

    const username = this.nuevoCajero.username.trim();
    const password = this.nuevoCajero.password.trim();
    const nombreMostrado = this.nuevoCajero.nombre_mostrado.trim();

    if (!username || !password) {
      this.mensajeCajero = 'Usuario y contrasena son obligatorios.';
      return;
    }

    this.guardandoCajero = true;
    this.mensajeCajero = '';
    this.visitaService.crearCajero({
      username,
      password,
      nombre_mostrado: nombreMostrado || null,
    }).subscribe({
      next: () => {
        this.guardandoCajero = false;
        this.mensajeCajero = 'Cajero creado correctamente.';
        this.nuevoCajero = { username: '', password: '', nombre_mostrado: '' };
        this.cargarCajeros();
      },
      error: (err) => {
        this.guardandoCajero = false;
        this.mensajeCajero = err?.error?.detail ?? 'No fue posible crear el cajero.';
      }
    });
  }

}
