import { CommonModule } from '@angular/common';
import { AfterViewChecked, Component, OnDestroy, OnInit } from '@angular/core';
import { RouterLink } from '@angular/router';

import { Html5Qrcode } from 'html5-qrcode';

import {
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
  comercioSlug = 'demo-cafe';
  comercio: ComercioBrandingResponse | null = null;
  username = '';
  password = '';
  telefono = '';
  mensaje = '';
  mensajeLogin = '';
  mensajeConfig = '';
  modoRegistro: 'telefono' | 'qr' = 'telefono';
  qrActivo = false;
  escanerError = '';
  autenticado = false;
  esRecompensa = false;
  cargando = false;
  cargandoLogin = false;
  guardandoConfig = false;
  configuracionAbierta = false;
  ultimoCliente: ClienteCuentaResponse | null = null;
  comercioForm: ComercioConfigUpdateRequest = {
    nombre: '',
    logo_url: null,
    color_primario: '#0f766e',
    color_secundario: '#f59e0b',
    visitas_objetivo: 5,
    recompensa_nombre: 'Bebida gratis',
    descripcion: null
  };
  logoErrores: Record<string, boolean> = {};

  private qrScanner: Html5Qrcode | null = null;
  private scannerMountPending = false;

  constructor(private readonly visitaService: VisitaService) {
    this.autenticado = this.visitaService.estaAutenticado();
    this.comercioSlug = this.visitaService.obtenerComercioSlug() ?? 'demo-cafe';
  }

  ngOnInit(): void {
    this.cargarComercio();
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

  onComercioSlugInput(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.comercioSlug = input.value.trim().toLowerCase();
  }

  onComercioSlugBlur(): void {
    if (this.comercioSlug) {
      this.cargarComercio();
    }
  }

  onPasswordInput(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.password = input.value;
  }

  iniciarSesion(): void {
    if (!this.comercioSlug || !this.username || !this.password) {
      this.mensajeLogin = 'Ingresa comercio, usuario y contrasena.';
      return;
    }

    this.cargandoLogin = true;
    this.mensajeLogin = '';

    this.visitaService.login(this.comercioSlug, this.username, this.password).subscribe({
      next: (response: LoginResponse) => {
        this.visitaService.guardarToken(response.access_token);
        this.visitaService.guardarComercioSlug(this.comercioSlug);
        this.comercio = response.comercio;
        this.sincronizarFormularioComercio(response.comercio);
        this.autenticado = true;
        this.cargandoLogin = false;
        this.mensaje = '';
      },
      error: (err) => {
        if (err?.status === 429) {
          this.mensajeLogin = err?.error?.detail ?? 'Cuenta bloqueada temporalmente.';
        } else if (err?.status === 404) {
          this.mensajeLogin = 'Ese comercio no existe.';
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
    this.mensaje = '';
    this.mensajeLogin = 'Sesion cerrada.';
    this.ultimoCliente = null;
    this.detenerEscanerQr();
  }

  cargarComercio(): void {
    this.visitaService.obtenerComercio(this.comercioSlug).subscribe({
      next: (response) => {
        this.comercio = response;
        this.sincronizarFormularioComercio(response);
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
      descripcion: comercio.descripcion
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

  alternarConfiguracion(): void {
    this.configuracionAbierta = !this.configuracionAbierta;
    this.mensajeConfig = '';
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
}
