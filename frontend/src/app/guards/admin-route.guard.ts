import { inject } from '@angular/core';
import { CanActivateFn, Router, UrlTree } from '@angular/router';

import { VisitaService } from '../services/visita.service';

export const adminRouteGuard: CanActivateFn = (): true | UrlTree => {
  const visitaService = inject(VisitaService);
  const router = inject(Router);
  const rol = visitaService.obtenerRol();

  if (visitaService.estaAutenticado() && rol && rol !== 'admin') {
    return router.parseUrl('/caja');
  }

  return true;
};