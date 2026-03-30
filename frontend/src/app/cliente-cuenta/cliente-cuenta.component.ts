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
  mensajeQr = '';

  constructor(
    private readonly route: ActivatedRoute,
    private readonly visitaService: VisitaService
  ) {}

  ngOnInit(): void {
    const publicId = this.route.snapshot.paramMap.get('publicId');
    const comercioSlug = this.route.snapshot.paramMap.get('comercioSlug');
    if (!publicId) {
      this.error = 'No se encontro la cuenta del cliente.';
      this.cargando = false;
      return;
    }

    const cuenta$ = comercioSlug
      ? this.visitaService.obtenerCuentaCliente(comercioSlug, publicId)
      : this.visitaService.obtenerCuentaClientePorId(publicId);

    cuenta$.subscribe({
      next: async (response) => {
        this.logoFallido = false;
        const slug = response.comercio.slug;
        this.comercioSlug = slug;
        this.visitaService.obtenerComercio(slug).subscribe({
          next: (comercio) => {
            this.cuenta = {
              ...response,
              comercio,
              objetivo_visitas: comercio.visitas_objetivo,
            };
          },
          error: () => {
            this.cuenta = response;
          }
        });

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

  descargarQr(): void {
    if (!this.qrDataUrl || !this.cuenta) {
      return;
    }

    const enlace = document.createElement('a');
    enlace.href = this.qrDataUrl;
    enlace.download = `qr-${this.cuenta.comercio.slug}-${this.cuenta.public_id}.png`;
    enlace.click();
    this.mensajeQr = 'QR descargado correctamente.';
  }

  async compartirQr(): Promise<void> {
    if (!this.qrDataUrl || !this.cuenta) {
      return;
    }

    try {
      const blob = await (await fetch(this.qrDataUrl)).blob();
      const file = new File([blob], `qr-${this.cuenta.comercio.slug}-${this.cuenta.public_id}.png`, { type: 'image/png' });

      if (navigator.share && (navigator as Navigator & { canShare?: (data: ShareData) => boolean }).canShare?.({ files: [file] })) {
        await navigator.share({
          title: 'Mi QR de fidelidad',
          text: 'Comparte este QR para registrar visitas en caja.',
          files: [file],
        });
        this.mensajeQr = 'QR compartido correctamente.';
        return;
      }

      this.descargarQr();
    } catch {
      this.mensajeQr = 'No se pudo compartir el QR desde este navegador.';
    }
  }
}
