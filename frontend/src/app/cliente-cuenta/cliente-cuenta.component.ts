import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import QRCode from 'qrcode';

import { ClienteCuentaResponse, VisitaService } from '../services/visita.service';

@Component({
  selector: 'app-cliente-cuenta',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './cliente-cuenta.component.html',
  styleUrls: ['./cliente-cuenta.component.css']
})
export class ClienteCuentaComponent implements OnInit {
  cuenta: ClienteCuentaResponse | null = null;
  cargando = true;
  error = '';
  qrDataUrl = '';
  comercioSlug = '';
  logoFallido = false;

  constructor(
    private readonly route: ActivatedRoute,
    private readonly visitaService: VisitaService
  ) {}

  ngOnInit(): void {
    const publicId = this.route.snapshot.paramMap.get('publicId');
    const comercioSlug = this.route.snapshot.paramMap.get('comercioSlug');
    if (!publicId || !comercioSlug) {
      this.error = 'No se encontro la cuenta del cliente.';
      this.cargando = false;
      return;
    }

    this.comercioSlug = comercioSlug;
    this.visitaService.obtenerCuentaCliente(comercioSlug, publicId).subscribe({
      next: async (response) => {
        this.cuenta = response;
        this.logoFallido = false;
        this.qrDataUrl = await QRCode.toDataURL(response.qr_value, {
          margin: 1,
          width: 320,
          color: {
            dark: '#10233d',
            light: '#ffffff'
          }
        });
        this.cargando = false;
      },
      error: () => {
        this.error = 'No fue posible cargar la cuenta del cliente.';
        this.cargando = false;
      }
    });
  }

  get progreso(): number {
    if (!this.cuenta) {
      return 0;
    }
    return (this.cuenta.visitas_actuales / this.cuenta.objetivo_visitas) * 100;
  }

  get mostrarLogo(): boolean {
    return !!this.cuenta?.comercio.logo_url && !this.logoFallido;
  }

  marcarLogoFallido(): void {
    this.logoFallido = true;
  }

  get inicialesComercio(): string {
    return (this.cuenta?.comercio.nombre ?? '')
      .split(' ')
      .filter(Boolean)
      .slice(0, 2)
      .map((segmento) => segmento[0]?.toUpperCase() ?? '')
      .join('') || 'LC';
  }

  registrarClickWalletApple(): void {
    if (!this.cuenta) {
      return;
    }

    this.visitaService.registrarEventoAnalitico({
      comercio_slug: this.cuenta.comercio.slug,
      public_id: this.cuenta.public_id,
      evento: 'wallet_click',
      origen: 'apple_wallet',
    }).subscribe({
      error: () => {
        // La navegacion no depende del evento analitico.
      }
    });
  }

  registrarClickWalletGoogle(): void {
    if (!this.cuenta) {
      return;
    }

    this.visitaService.registrarEventoAnalitico({
      comercio_slug: this.cuenta.comercio.slug,
      public_id: this.cuenta.public_id,
      evento: 'wallet_click',
      origen: 'google_wallet',
    }).subscribe({
      error: () => {
        // La navegacion no depende del evento analitico.
      }
    });
  }
}
