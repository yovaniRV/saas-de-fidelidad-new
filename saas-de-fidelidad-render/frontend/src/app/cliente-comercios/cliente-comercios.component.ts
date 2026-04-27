import { CommonModule } from '@angular/common';
import { AfterViewInit, Component, ElementRef, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import QRCode from 'qrcode';
import { Subscription } from 'rxjs';

import { ClienteCuentaResponse, ClienteMisComerciosResponse, VisitaService } from '../services/visita.service';

@Component({
  selector: 'app-cliente-comercios',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './cliente-comercios.component.html',
  styleUrls: ['./cliente-comercios.component.css']
})
export class ClienteComerciosComponent implements AfterViewInit, OnDestroy, OnInit {
  private static readonly telefonoSessionKey = 'saas_fidelidad_cliente_telefono';
  telefono = '';
  filtroComercio = '';
  orden: 'progreso' | 'nombre' | 'recompensas' = 'progreso';
  soloPendientes = false;
  readonly pasoCarga = 6;
  limiteVisible = this.pasoCarga;
  cargando = false;
  cargandoMas = false;
  mensaje = '';
  data: ClienteMisComerciosResponse | null = null;
  qrPorCuenta: Record<string, string> = {};
  logoErrores: Record<string, boolean> = {};
  cuentasAnimadas: Record<string, boolean> = {};
  private intersectionObserver: IntersectionObserver | null = null;
  private sentinelElemento: ElementRef<HTMLDivElement> | null = null;
  private readonly timeoutsAnimacion = new Map<string, number>();
  private queryParamsSub: Subscription | null = null;

  @ViewChild('loadMoreSentinel')
  set loadMoreSentinel(elemento: ElementRef<HTMLDivElement> | undefined) {
    this.sentinelElemento = elemento ?? null;
    this.conectarObserver();
  }

  constructor(
    private readonly visitaService: VisitaService,
    private readonly route: ActivatedRoute,
    private readonly router: Router
  ) {}

  ngOnInit(): void {
    this.telefono = sessionStorage.getItem(ClienteComerciosComponent.telefonoSessionKey) ?? '';

    this.queryParamsSub = this.route.queryParamMap.subscribe((params) => {
      const filtro = params.get('filtro') ?? '';
      const orden = params.get('orden');
      const soloPendientes = params.get('pendientes') === '1';
      const visible = params.get('visible');

      this.filtroComercio = filtro;
      this.orden = this.esOrdenValido(orden) ? orden : 'progreso';
      this.soloPendientes = soloPendientes;
      this.limiteVisible = this.parsearLimiteVisible(visible);

      if (this.data) {
        void this.generarQrsVisibles();
      }
    });

    if (this.telefono.length === 10) {
      this.buscarComercios();
    }
  }

  ngAfterViewInit(): void {
    this.conectarObserver();
  }

  ngOnDestroy(): void {
    this.intersectionObserver?.disconnect();
    this.intersectionObserver = null;
    this.queryParamsSub?.unsubscribe();
    for (const timeoutId of this.timeoutsAnimacion.values()) {
      window.clearTimeout(timeoutId);
    }
    this.timeoutsAnimacion.clear();
  }

  onTelefonoInput(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.telefono = input.value.replace(/\D/g, '').slice(0, 10);
    if (!this.telefono) {
      sessionStorage.removeItem(ClienteComerciosComponent.telefonoSessionKey);
    }
  }

  buscarComercios(): void {
    if (this.telefono.length !== 10) {
      this.mensaje = 'Ingresa un telefono de 10 digitos.';
      return;
    }

    this.cargando = true;
    this.mensaje = '';
    this.data = null;

    this.visitaService.obtenerMisComercios(this.telefono).subscribe({
      next: async (response) => {
        this.data = response;
        sessionStorage.setItem(ClienteComerciosComponent.telefonoSessionKey, this.telefono);
        this.limiteVisible = Math.max(this.limiteVisible, this.pasoCarga);
        this.qrPorCuenta = {};
        this.logoErrores = {};
        this.cuentasAnimadas = {};
        await this.generarQrsVisibles();
        this.cargando = false;
      },
      error: () => {
        this.mensaje = 'No encontramos cuentas para ese telefono.';
        this.cargando = false;
      }
    });
  }

  progreso(visitasActuales: number, objetivo: number): number {
    if (!objetivo) {
      return 0;
    }
    return Math.min(100, (visitasActuales / objetivo) * 100);
  }

  get totalVisitas(): number {
    return this.data?.cuentas.reduce((total, cuenta) => total + cuenta.visitas_actuales, 0) ?? 0;
  }

  get totalRecompensas(): number {
    return this.data?.cuentas.reduce((total, cuenta) => total + cuenta.recompensas_total, 0) ?? 0;
  }

  get cuentasFiltradas(): ClienteCuentaResponse[] {
    const cuentas = this.data?.cuentas ?? [];
    const termino = this.normalizarTexto(this.filtroComercio.trim());

    const filtradas = cuentas.filter((cuenta) => {
      const coincideNombre =
        !termino || this.normalizarTexto(cuenta.comercio.nombre).includes(termino) || this.normalizarTexto(cuenta.comercio.slug).includes(termino);
      const pendiente = cuenta.visitas_actuales < cuenta.objetivo_visitas;
      return coincideNombre && (!this.soloPendientes || pendiente);
    });

    return filtradas.sort((a, b) => {
      if (this.orden === 'nombre') {
        return a.comercio.nombre.localeCompare(b.comercio.nombre, 'es', { sensitivity: 'base' });
      }

      if (this.orden === 'recompensas') {
        return b.recompensas_total - a.recompensas_total;
      }

      const progresoA = this.progreso(a.visitas_actuales, a.objetivo_visitas);
      const progresoB = this.progreso(b.visitas_actuales, b.objetivo_visitas);
      return progresoB - progresoA;
    });
  }

  get cuentasPrioritarias(): ClienteCuentaResponse[] {
    return this.cuentasFiltradas
      .filter((cuenta) => this.visitasRestantes(cuenta) > 0)
      .sort((a, b) => {
        const restantesA = this.visitasRestantes(a);
        const restantesB = this.visitasRestantes(b);
        if (restantesA === restantesB) {
          return this.progreso(b.visitas_actuales, b.objetivo_visitas) - this.progreso(a.visitas_actuales, a.objetivo_visitas);
        }
        return restantesA - restantesB;
      })
      .slice(0, 3);
  }

  get cuentaHero(): ClienteCuentaResponse | null {
    return this.cuentasPrioritarias[0] ?? null;
  }

  get cuentasPrioritariasSecundarias(): ClienteCuentaResponse[] {
    return this.cuentasPrioritarias.slice(1);
  }

  get cuentasPaginadas(): ClienteCuentaResponse[] {
    return this.cuentasListado.slice(0, this.limiteVisible);
  }

  get cuentasListado(): ClienteCuentaResponse[] {
    if (!this.cuentaHero) {
      return this.cuentasFiltradas;
    }

    return this.cuentasFiltradas.filter((cuenta) => cuenta.public_id !== this.cuentaHero?.public_id);
  }

  get quedanPorMostrar(): number {
    return Math.max(this.cuentasListado.length - this.cuentasPaginadas.length, 0);
  }

  get resumenVisible(): string {
    if (!this.cuentasListado.length) {
      return '0 de 0';
    }
    return `${this.cuentasPaginadas.length} de ${this.cuentasListado.length}`;
  }

  actualizarFiltro(valor: string): void {
    this.filtroComercio = valor;
    this.limiteVisible = this.pasoCarga;
    this.sincronizarQueryParams();
    void this.generarQrsVisibles();
  }

  actualizarOrden(valor: 'progreso' | 'nombre' | 'recompensas'): void {
    this.orden = valor;
    this.limiteVisible = this.pasoCarga;
    this.sincronizarQueryParams();
    void this.generarQrsVisibles();
  }

  actualizarSoloPendientes(valor: boolean): void {
    this.soloPendientes = valor;
    this.limiteVisible = this.pasoCarga;
    this.sincronizarQueryParams();
    void this.generarQrsVisibles();
  }

  async cargarMas(): Promise<void> {
    const cuentasAntes = this.cuentasPaginadas.map((cuenta) => cuenta.public_id);
    this.limiteVisible += this.pasoCarga;
    this.marcarNuevasCuentas(cuentasAntes);
    this.sincronizarQueryParams();
    await this.generarQrsVisibles();
  }

  mostrarMenos(): void {
    this.limiteVisible = this.pasoCarga;
    this.sincronizarQueryParams();
  }

  visitasRestantes(cuenta: ClienteCuentaResponse): number {
    return Math.max(cuenta.objetivo_visitas - cuenta.visitas_actuales, 0);
  }

  estadoMeta(cuenta: ClienteCuentaResponse): string {
    const restantes = this.visitasRestantes(cuenta);
    if (restantes === 0) {
      return 'Recompensa lista para canjear';
    }
    return `Te faltan ${restantes} visita${restantes === 1 ? '' : 's'}`;
  }

  badgePrioridad(cuenta: ClienteCuentaResponse): string {
    const restantes = this.visitasRestantes(cuenta);
    if (restantes === 1) {
      return 'A 1 visita de premio';
    }
    if (restantes <= 3) {
      return `A ${restantes} visitas de premio`;
    }
    return `Meta en ${restantes} visitas`;
  }

  ctaHero(cuenta: ClienteCuentaResponse): string {
    const restantes = this.visitasRestantes(cuenta);
    if (restantes === 1) {
      return 'Te falta 1 visita, vuelve hoy';
    }
    if (restantes <= 3) {
      return `Estas a ${restantes} visitas de tu recompensa`;
    }
    return 'Sigue acumulando para desbloquear tu premio';
  }

  recomendacionHero(cuenta: ClienteCuentaResponse): string {
    const mensajeContextual = cuenta.comercio.mensaje_contextual?.trim();
    if (mensajeContextual) {
      return mensajeContextual;
    }

    const momento = cuenta.comercio.momento_recomendado ?? this.obtenerMomentoActual();
    switch (momento) {
      case 'desayuno':
        return 'Ideal para pasar hoy en la manana y sumar una visita temprano.';
      case 'almuerzo':
        return 'Ideal para pasar hoy al almuerzo y acercarte a tu recompensa.';
      case 'merienda':
        return 'Buen momento para una pausa de tarde y seguir acumulando.';
      case 'cena':
        return 'Buen plan para cerrar el dia con una visita mas.';
      default:
        return 'Aprovecha tu siguiente visita para empujar esta meta cuanto antes.';
    }
  }

  registrarClickHero(cuenta: ClienteCuentaResponse): void {
    this.registrarEventoAnalitico('hero', cuenta);
  }

  registrarClickCard(cuenta: ClienteCuentaResponse): void {
    this.registrarEventoAnalitico('card', cuenta);
  }

  tieneQr(publicId: string): boolean {
    return !!this.qrPorCuenta[publicId];
  }

  esCuentaNueva(publicId: string): boolean {
    return !!this.cuentasAnimadas[publicId];
  }

  claseBadgePrioridad(cuenta: ClienteCuentaResponse): 'urgente' | 'cercana' | 'normal' {
    const restantes = this.visitasRestantes(cuenta);
    if (restantes === 1) {
      return 'urgente';
    }
    if (restantes <= 3) {
      return 'cercana';
    }
    return 'normal';
  }

  trackByCuenta(_: number, cuenta: ClienteCuentaResponse): string {
    return cuenta.public_id;
  }

  mostrarLogo(publicId: string, logoUrl: string | null | undefined): boolean {
    return !!logoUrl && !this.logoErrores[publicId];
  }

  marcarLogoError(publicId: string): void {
    this.logoErrores[publicId] = true;
  }

  inicialesComercio(nombre: string): string {
    return nombre
      .split(' ')
      .filter(Boolean)
      .slice(0, 2)
      .map((segmento) => segmento[0]?.toUpperCase() ?? '')
      .join('') || 'LC';
  }

  private normalizarTexto(texto: string): string {
    return texto
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '');
  }

  private esOrdenValido(valor: string | null): valor is 'progreso' | 'nombre' | 'recompensas' {
    return valor === 'progreso' || valor === 'nombre' || valor === 'recompensas';
  }

  private sincronizarQueryParams(): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      replaceUrl: true,
      queryParams: {
        filtro: this.filtroComercio || null,
        orden: this.orden !== 'progreso' ? this.orden : null,
        pendientes: this.soloPendientes ? '1' : null,
        visible: this.limiteVisible > this.pasoCarga ? String(this.limiteVisible) : null
      }
    });
  }

  private parsearLimiteVisible(valor: string | null): number {
    const parsed = Number(valor);
    if (!Number.isFinite(parsed) || parsed < this.pasoCarga) {
      return this.pasoCarga;
    }

    return Math.floor(parsed);
  }

  private obtenerMomentoActual(): 'desayuno' | 'almuerzo' | 'merienda' | 'cena' {
    const hora = new Date().getHours();
    if (hora < 11) {
      return 'desayuno';
    }
    if (hora < 16) {
      return 'almuerzo';
    }
    if (hora < 20) {
      return 'merienda';
    }
    return 'cena';
  }

  private registrarEventoAnalitico(
    origen: 'hero' | 'card',
    cuenta: ClienteCuentaResponse,
    evento: 'abrir_cuenta_cliente' = 'abrir_cuenta_cliente'
  ): void {
    this.visitaService.registrarEventoAnalitico({
      comercio_slug: cuenta.comercio.slug,
      public_id: cuenta.public_id,
      evento,
      origen,
    }).subscribe({
      error: () => {
        // La telemetria no debe afectar la navegacion del usuario.
      }
    });
  }

  private async generarQrsVisibles(): Promise<void> {
    const cuentasSinQr = this.cuentasPaginadas.filter((cuenta) => !this.qrPorCuenta[cuenta.public_id]);
    if (!cuentasSinQr.length) {
      return;
    }

    const qrs = await Promise.all(
      cuentasSinQr.map(async (cuenta) => ({
        publicId: cuenta.public_id,
        dataUrl: await QRCode.toDataURL(cuenta.qr_value, {
          margin: 1,
          width: 220,
          color: {
            dark: '#10233d',
            light: '#ffffff'
          }
        })
      }))
    );

    for (const qr of qrs) {
      this.qrPorCuenta[qr.publicId] = qr.dataUrl;
    }
  }

  private marcarNuevasCuentas(idsPrevias: string[]): void {
    const idsPreviasSet = new Set(idsPrevias);
    const idsNuevas = this.cuentasPaginadas
      .map((cuenta) => cuenta.public_id)
      .filter((publicId) => !idsPreviasSet.has(publicId));

    for (const publicId of idsNuevas) {
      this.cuentasAnimadas[publicId] = true;
      const timeoutPrevio = this.timeoutsAnimacion.get(publicId);
      if (timeoutPrevio) {
        window.clearTimeout(timeoutPrevio);
      }

      const timeoutId = window.setTimeout(() => {
        delete this.cuentasAnimadas[publicId];
        this.timeoutsAnimacion.delete(publicId);
      }, 850);

      this.timeoutsAnimacion.set(publicId, timeoutId);
    }
  }

  private conectarObserver(): void {
    this.intersectionObserver?.disconnect();

    if (!this.sentinelElemento) {
      this.intersectionObserver = null;
      return;
    }

    this.intersectionObserver = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (!entry?.isIntersecting || this.cargandoMas || this.quedanPorMostrar === 0) {
          return;
        }

        void this.cargarMasAutomaticamente();
      },
      {
        rootMargin: '240px 0px 240px 0px',
        threshold: 0.1
      }
    );

    this.intersectionObserver.observe(this.sentinelElemento.nativeElement);
  }

  private async cargarMasAutomaticamente(): Promise<void> {
    this.cargandoMas = true;
    try {
      await this.cargarMas();
    } finally {
      this.cargandoMas = false;
    }
  }
}
