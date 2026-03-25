import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import QRCode from 'qrcode';

import { ClienteMisComerciosResponse, VisitaService } from '../services/visita.service';

@Component({
  selector: 'app-cliente-comercios',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './cliente-comercios.component.html',
  styleUrls: ['./cliente-comercios.component.css']
})
export class ClienteComerciosComponent {
  telefono = '';
  cargando = false;
  mensaje = '';
  data: ClienteMisComerciosResponse | null = null;
  qrPorCuenta: Record<string, string> = {};
  logoErrores: Record<string, boolean> = {};

  constructor(private readonly visitaService: VisitaService) {}

  onTelefonoInput(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.telefono = input.value.replace(/\D/g, '').slice(0, 10);
  }

  buscarComercios(): void {
    if (!this.telefono) {
      this.mensaje = 'Ingresa tu telefono.';
      return;
    }

    this.cargando = true;
    this.mensaje = '';
    this.data = null;

    this.visitaService.obtenerMisComercios(this.telefono).subscribe({
      next: async (response) => {
        this.data = response;
        this.qrPorCuenta = {};
        this.logoErrores = {};
        for (const cuenta of response.cuentas) {
          this.qrPorCuenta[cuenta.public_id] = await QRCode.toDataURL(cuenta.qr_value, {
            margin: 1,
            width: 220,
            color: {
              dark: '#10233d',
              light: '#ffffff'
            }
          });
        }
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
    return (visitasActuales / objetivo) * 100;
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
}
