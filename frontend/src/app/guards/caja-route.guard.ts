import { inject } from '@angular/core';
import { CanActivateFn, Router, UrlTree } from '@angular/router';

import { VisitaService } from '../services/visita.service';

export const cajaRouteGuard: CanActivateFn = (): true | UrlTree => {
  const visitaService = inject(VisitaService);
  const router = inject(Router);

  if (visitaService.estaAutenticado() && visitaService.obtenerRol() === 'admin') {
    return router.parseUrl('/admin');
  }

  return true;
};