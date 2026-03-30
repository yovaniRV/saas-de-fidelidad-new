import { Routes } from '@angular/router';

import { AdminPanelComponent } from './admin-panel/admin-panel.component';
import { ClienteAccesoComponent } from './cliente-acceso/cliente-acceso.component';
import { ClienteComerciosComponent } from './cliente-comercios/cliente-comercios.component';
import { ClienteCuentaComponent } from './cliente-cuenta/cliente-cuenta.component';
import { adminRouteGuard } from './guards/admin-route.guard';
import { bloquearClienteConSesionCajaGuard } from './guards/bloquear-cliente-con-sesion-caja.guard';
import { cajaRouteGuard } from './guards/caja-route.guard';
import { RegistroVisitaComponent } from './registro-visita/registro-visita.component';

export const appRoutes: Routes = [
  {
    path: '',
    redirectTo: 'mi-cuenta',
    pathMatch: 'full'
  },
  {
    path: 'caja',
    component: RegistroVisitaComponent,
    canActivate: [cajaRouteGuard]
  },
  {
    path: 'admin',
    component: AdminPanelComponent,
    canActivate: [adminRouteGuard]
  },
  {
    path: 'comercio/:comercioSlug/mi-cuenta',
    component: ClienteAccesoComponent,
    canActivate: [bloquearClienteConSesionCajaGuard]
  },
  {
    path: 'mi-cuenta',
    component: ClienteComerciosComponent,
    canActivate: [bloquearClienteConSesionCajaGuard]
  },
  {
    path: 'comercio/:comercioSlug/cliente/:publicId',
    component: ClienteCuentaComponent,
    canActivate: [bloquearClienteConSesionCajaGuard]
  },
  {
    path: '**',
    redirectTo: 'mi-cuenta'
  }
];
