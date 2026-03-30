import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { Router } from '@angular/router';

import {
  AdminComercioResumenResponse,
  AdminPersonalComercioResponse,
  CajeroResponse,
  ComercioCreateRequest,
  LoginResponse,
  VisitaService,
} from '../services/visita.service';

@Component({
  selector: 'app-admin-panel',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './admin-panel.component.html',
  styleUrls: ['./admin-panel.component.css']
})
export class AdminPanelComponent implements OnInit {
  username = '';
  password = '';
  autenticado = false;
  cargandoLogin = false;
  creandoComercio = false;
  cargandoPersonalAdmin = false;
  mensajeLogin = '';
  mensajeAdmin = '';
  mensajeAdminTipo: 'success' | 'error' = 'success';
  mensajeComercioNuevo = '';
  mensajeComercioTipo: 'success' | 'error' = 'success';
  comerciosAdmin: AdminComercioResumenResponse[] = [];
  personalAdmin: CajeroResponse[] = [];
  comercioJefeSlug = '';
  comercioPersonalNombre = '';
  nuevoJefe = {
    username: '',
    password: '',
    nombre_mostrado: ''
  };
  nuevoComercio: ComercioCreateRequest = {
    slug: '',
    nombre: '',
    jefe_username: '',
    jefe_password: '',
    jefe_nombre_mostrado: null,
    color_primario: '#0f766e',
    color_secundario: '#f59e0b',
    visitas_objetivo: 5,
    recompensa_nombre: 'Bebida gratis',
    descripcion: null,
  };

  constructor(
    private readonly visitaService: VisitaService,
    private readonly router: Router,
  ) {}

  ngOnInit(): void {
    this.autenticado = this.visitaService.estaAutenticado() && this.visitaService.obtenerRol() === 'admin';
    if (this.autenticado) {
      this.cargarComerciosAdmin();
    }
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
        if (response.rol !== 'admin') {
          this.visitaService.guardarToken(response.access_token);
          this.visitaService.guardarRol(response.rol);
          if (response.comercio?.slug) {
            this.visitaService.guardarComercioSlug(response.comercio.slug);
          }
          void this.router.navigate(['/caja']);
          return;
        }

        this.visitaService.guardarToken(response.access_token);
        this.visitaService.guardarRol(response.rol);
        this.autenticado = true;
        this.cargandoLogin = false;
        this.cargarComerciosAdmin();
      },
      error: (err) => {
        this.cargandoLogin = false;
        // Manejo robusto de errores para FastAPI: muestra errores de validación legibles
        let mensaje = 'No fue posible iniciar sesion como administrador.';
        const error = err?.error;
        if (error?.detail) {
          mensaje = error.detail;
        } else if (typeof error === 'string') {
          mensaje = error;
        } else if (Array.isArray(error) && error.length > 0) {
          // FastAPI: error de validación (422)
          const primer = error[0];
          if (primer?.msg) {
            mensaje = primer.msg;
          } else if (typeof primer === 'string') {
            mensaje = primer;
          } else if (primer?.detail) {
            mensaje = primer.detail;
          } else {
            mensaje = JSON.stringify(primer);
          }
        } else if (err?.status === 0) {
          mensaje = 'No se pudo conectar con el servidor. Verifica que el backend esté en línea.';
        } else if (error) {
          try {
            mensaje = JSON.stringify(error);
          } catch {
            mensaje = 'Error inesperado: ' + String(error);
          }
        }
        this.mensajeLogin = mensaje;
      }
    });
  }

  cerrarSesion(): void {
    this.visitaService.limpiarToken();
    this.autenticado = false;
    this.resetAdminState();
    this.mensajeLogin = 'Sesion cerrada.';
  }

  forzarReinicioSesion(): void {
    this.visitaService.limpiarToken();
    this.autenticado = false;
    this.resetAdminState();
    this.mensajeLogin = 'Sesion expirada. Por favor ingresa nuevamente.';
  }

  onNuevoComercioInput(field: keyof ComercioCreateRequest, event: Event): void {
    const input = event.target as HTMLInputElement | HTMLTextAreaElement;
    const value = input.value;

    if (field === 'visitas_objetivo') {
      this.nuevoComercio.visitas_objetivo = Number(value) || 1;
      return;
    }

    if (field === 'jefe_nombre_mostrado' || field === 'descripcion') {
      this.nuevoComercio = {
        ...this.nuevoComercio,
        [field]: value.trim() || null,
      };
      return;
    }

    this.nuevoComercio = {
      ...this.nuevoComercio,
      [field]: value,
    };
  }

  crearComercioDesdePanel(): void {
    const slug = (this.nuevoComercio.slug ?? '').trim().toLowerCase();
    const nombre = (this.nuevoComercio.nombre ?? '').trim();
    const jefeUsername = (this.nuevoComercio.jefe_username ?? '').trim();
    const jefePassword = (this.nuevoComercio.jefe_password ?? '').trim();

    if (!slug || !nombre || !jefeUsername || !jefePassword) {
      this.mensajeComercioNuevo = 'Completa slug, nombre, usuario jefe y contrasena.';
      this.mensajeComercioTipo = 'error';
      return;
    }

    if (!/^[a-z0-9][a-z0-9-]{2,79}$/.test(slug)) {
      this.mensajeComercioNuevo = 'Slug invalido. Usa 3-80 caracteres [a-z0-9-].';
      this.mensajeComercioTipo = 'error';
      return;
    }

    if (!this.esPasswordSegura(jefePassword)) {
      this.mensajeComercioNuevo = 'La contrasena del jefe debe tener minimo 6 caracteres con letras y numeros.';
      this.mensajeComercioTipo = 'error';
      return;
    }

    if (!this.esColorHexValido(this.nuevoComercio.color_primario) || !this.esColorHexValido(this.nuevoComercio.color_secundario)) {
      this.mensajeComercioNuevo = 'Los colores deben estar en formato #RRGGBB.';
      this.mensajeComercioTipo = 'error';
      return;
    }

    if (this.nuevoComercio.visitas_objetivo < 1 || this.nuevoComercio.visitas_objetivo > 50) {
      this.mensajeComercioNuevo = 'La meta de visitas debe estar entre 1 y 50.';
      this.mensajeComercioTipo = 'error';
      return;
    }

    this.creandoComercio = true;
    this.mensajeComercioNuevo = '';
    this.visitaService.crearComercio({
      ...this.nuevoComercio,
      slug,
      nombre,
      jefe_username: jefeUsername,
      jefe_password: jefePassword,
      jefe_nombre_mostrado: this.nuevoComercio.jefe_nombre_mostrado?.trim() || null,
      descripcion: this.nuevoComercio.descripcion?.trim() || null,
    }).subscribe({
      next: (response) => {
        this.creandoComercio = false;
        this.mensajeComercioNuevo = `✓ Comercio creado con jefe ${response.jefe.username}.`;
        this.mensajeComercioTipo = 'success';
        this.comercioJefeSlug = response.comercio.slug;
        this.nuevoComercio = {
          slug: '',
          nombre: '',
          jefe_username: '',
          jefe_password: '',
          jefe_nombre_mostrado: null,
          color_primario: '#0f766e',
          color_secundario: '#f59e0b',
          visitas_objetivo: 5,
          recompensa_nombre: 'Bebida gratis',
          descripcion: null,
        };
        this.cargarComerciosAdmin();
        this.cargarPersonalAdmin(response.comercio.slug);
      },
      error: (err) => {
        this.creandoComercio = false;
        if (err?.status === 401) {
          this.forzarReinicioSesion();
          return;
        }
        this.mensajeComercioNuevo = this.extraerMensajeError(err, 'No fue posible crear el comercio.');
        this.mensajeComercioTipo = 'error';
      }
    });
  }

  cargarComerciosAdmin(): void {
    this.visitaService.listarComerciosAdmin().subscribe({
      next: (comercios) => {
        this.comerciosAdmin = comercios;
        if (!this.comercioJefeSlug && comercios.length) {
          this.comercioJefeSlug = comercios[0].slug;
        }
        if (this.comercioJefeSlug) {
          this.cargarPersonalAdmin(this.comercioJefeSlug);
        }
      },
      error: (err) => {
        if (err?.status === 401) {
          this.forzarReinicioSesion();
          return;
        }
        this.mensajeAdmin = 'No fue posible cargar comercios para el panel admin.';
        this.mensajeAdminTipo = 'error';
      }
    });
  }

  onComercioJefeChange(event: Event): void {
    const input = event.target as HTMLSelectElement;
    this.comercioJefeSlug = input.value;
    this.cargarPersonalAdmin(this.comercioJefeSlug);
  }

  onNuevoJefeInput(field: 'username' | 'password' | 'nombre_mostrado', event: Event): void {
    const input = event.target as HTMLInputElement;
    this.nuevoJefe = {
      ...this.nuevoJefe,
      [field]: input.value,
    };
  }

  crearJefeDesdeAdmin(): void {
    const username = (this.nuevoJefe.username ?? '').trim();
    const password = (this.nuevoJefe.password ?? '').trim();
    const nombreMostrado = (this.nuevoJefe.nombre_mostrado ?? '').trim();

    if (!this.comercioJefeSlug || !username || !password) {
      this.mensajeAdmin = 'Selecciona comercio y completa usuario/contrasena del jefe.';
      this.mensajeAdminTipo = 'error';
      return;
    }

    this.visitaService.crearJefeAdmin(this.comercioJefeSlug, {
      username,
      password,
      nombre_mostrado: nombreMostrado || null,
    }).subscribe({
      next: (jefe) => {
        this.mensajeAdmin = `✓ Jefe ${jefe.username} creado para ${this.comercioJefeSlug}.`;
        this.mensajeAdminTipo = 'success';
        this.nuevoJefe = { username: '', password: '', nombre_mostrado: '' };
        this.cargarPersonalAdmin(this.comercioJefeSlug);
      },
      error: (err) => {
        if (err?.status === 401) {
          this.forzarReinicioSesion();
          return;
        }
        const detail = err?.error?.detail;
        if (Array.isArray(detail) && detail.length > 0) {
          const primer = detail[0];
          this.mensajeAdmin = typeof primer?.msg === 'string' ? primer.msg.replace('Value error, ', '') : 'Datos invalidos.';
        } else {
          this.mensajeAdmin = typeof detail === 'string' ? detail : 'No fue posible crear el jefe.';
        }
        this.mensajeAdminTipo = 'error';
      }
    });
  }

  cargarPersonalAdmin(slug: string): void {
    if (!slug) {
      this.personalAdmin = [];
      this.comercioPersonalNombre = '';
      return;
    }

    this.cargandoPersonalAdmin = true;
    this.visitaService.listarPersonalAdmin(slug).subscribe({
      next: (response: AdminPersonalComercioResponse) => {
        this.personalAdmin = response.personal;
        this.comercioPersonalNombre = response.comercio.nombre;
        this.cargandoPersonalAdmin = false;
      },
      error: (err) => {
        if (err?.status === 401) {
          this.forzarReinicioSesion();
          return;
        }
        this.cargandoPersonalAdmin = false;
        this.mensajeAdmin = this.extraerMensajeError(err, 'No fue posible cargar el personal del comercio.');
        this.mensajeAdminTipo = 'error';
      }
    });
  }

  promoverODegradar(personal: CajeroResponse): void {
    const nuevoRol: 'jefe' | 'cajero' = personal.rol === 'jefe' ? 'cajero' : 'jefe';
    this.visitaService.cambiarRolAdmin(personal.id, { rol: nuevoRol }).subscribe({
      next: (actualizado) => {
        this.actualizarPersonalAdminLocal(actualizado);
        this.mensajeAdmin = `✓ ${actualizado.username} ahora tiene rol ${actualizado.rol}.`;
        this.mensajeAdminTipo = 'success';
      },
      error: (err) => {
        if (err?.status === 401) {
          this.forzarReinicioSesion();
          return;
        }
        this.mensajeAdmin = this.extraerMensajeError(err, 'No fue posible actualizar el rol.');
        this.mensajeAdminTipo = 'error';
      }
    });
  }

  toggleActivo(personal: CajeroResponse): void {
    this.visitaService.cambiarEstadoAdmin(personal.id, { activo: !personal.activo }).subscribe({
      next: (actualizado) => {
        this.actualizarPersonalAdminLocal(actualizado);
        this.mensajeAdmin = `✓ ${actualizado.username} ahora esta ${actualizado.activo ? 'activo' : 'desactivado'}.`;
        this.mensajeAdminTipo = 'success';
      },
      error: (err) => {
        if (err?.status === 401) {
          this.forzarReinicioSesion();
          return;
        }
        this.mensajeAdmin = this.extraerMensajeError(err, 'No fue posible actualizar el estado.');
        this.mensajeAdminTipo = 'error';
      }
    });
  }

  etiquetaEstado(personal: CajeroResponse): string {
    return personal.activo ? 'Activo' : 'Desactivado';
  }

  claseEstado(personal: CajeroResponse): 'activo' | 'inactivo' {
    return personal.activo ? 'activo' : 'inactivo';
  }

  private actualizarPersonalAdminLocal(actualizado: CajeroResponse): void {
    this.personalAdmin = this.personalAdmin.map((item) => item.id === actualizado.id ? actualizado : item);
  }

  private esPasswordSegura(value: string): boolean {
    if (value.length < 6 || value.length > 72) {
      return false;
    }
    const hasLetter = /[a-zA-Z]/.test(value);
    const hasNumber = /\d/.test(value);
    return hasLetter && hasNumber;
  }

  private esColorHexValido(value: string | null | undefined): boolean {
    return /^#[0-9a-fA-F]{6}$/.test((value ?? '').trim());
  }

  private extraerMensajeError(err: any, fallback: string): string {
    if (err?.status === 0) {
      return 'No se pudo conectar con el servidor. Verifica que el backend este en linea.';
    }
    const detail = err?.error?.detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const primer = detail[0];
      if (typeof primer?.msg === 'string') {
        return primer.msg.replace('Value error, ', '');
      }
      return 'Datos invalidos.';
    }
    if (typeof detail === 'string') {
      return detail;
    }
    return fallback;
  }

  private resetAdminState(): void {
    this.comerciosAdmin = [];
    this.personalAdmin = [];
    this.comercioJefeSlug = '';
    this.comercioPersonalNombre = '';
    this.mensajeAdmin = '';
    this.mensajeAdminTipo = 'success';
    this.mensajeComercioNuevo = '';
    this.mensajeComercioTipo = 'success';
  }
}