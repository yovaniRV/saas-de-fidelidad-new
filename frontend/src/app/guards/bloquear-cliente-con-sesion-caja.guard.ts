import { inject } from '@angular/core';
import { CanActivateFn, Router, UrlTree } from '@angular/router';

import { VisitaService } from '../services/visita.service';

export const bloquearClienteConSesionCajaGuard: CanActivateFn = (): true | UrlTree => {
  const visitaService = inject(VisitaService);
  const router = inject(Router);

  if (visitaService.estaAutenticado()) {
    return router.parseUrl(visitaService.obtenerRol() === 'admin' ? '/admin' : '/caja');
  }

  return true;
};
