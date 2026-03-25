import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { ComercioBrandingResponse, VisitaService } from '../services/visita.service';

@Component({
  selector: 'app-cliente-acceso',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './cliente-acceso.component.html',
  styleUrls: ['./cliente-acceso.component.css']
})
export class ClienteAccesoComponent implements OnInit {
  comercioSlug = '';
  comercio: ComercioBrandingResponse | null = null;
  telefono = '';
  mensaje = '';
  cargando = true;
  buscando = false;

  constructor(
    private readonly route: ActivatedRoute,
    private readonly router: Router,
    private readonly visitaService: VisitaService
  ) {}

  ngOnInit(): void {
    const comercioSlug = this.route.snapshot.paramMap.get('comercioSlug');
    if (!comercioSlug) {
      this.mensaje = 'No se encontro el comercio.';
      this.cargando = false;
      return;
    }

    this.comercioSlug = comercioSlug;
    this.visitaService.obtenerComercio(comercioSlug).subscribe({
      next: (response) => {
        this.comercio = response;
        this.cargando = false;
      },
      error: () => {
        this.mensaje = 'No fue posible cargar el comercio.';
        this.cargando = false;
      }
    });
  }

  onTelefonoInput(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.telefono = input.value.replace(/\D/g, '').slice(0, 10);
  }

  buscarCuenta(): void {
    if (!this.telefono) {
      this.mensaje = 'Ingresa tu telefono para encontrar tu cuenta.';
      return;
    }

    this.buscando = true;
    this.mensaje = '';
    this.visitaService.accederCuentaCliente(this.comercioSlug, this.telefono).subscribe({
      next: (response) => {
        this.router.navigate(['/comercio', this.comercioSlug, 'cliente', response.public_id]);
      },
      error: () => {
        this.mensaje = 'No encontramos una cuenta para ese telefono en este comercio.';
        this.buscando = false;
      }
    });
  }
}
