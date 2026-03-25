import { Routes } from '@angular/router';

import { ClienteAccesoComponent } from './cliente-acceso/cliente-acceso.component';
import { ClienteComerciosComponent } from './cliente-comercios/cliente-comercios.component';
import { ClienteCuentaComponent } from './cliente-cuenta/cliente-cuenta.component';
import { RegistroVisitaComponent } from './registro-visita/registro-visita.component';

export const appRoutes: Routes = [
  {
    path: '',
    redirectTo: 'mi-cuenta',
    pathMatch: 'full'
  },
  {
    path: 'caja',
    component: RegistroVisitaComponent
  },
  {
    path: 'comercio/:comercioSlug/mi-cuenta',
    component: ClienteAccesoComponent
  },
  {
    path: 'mi-cuenta',
    component: ClienteComerciosComponent
  },
  {
    path: 'comercio/:comercioSlug/cliente/:publicId',
    component: ClienteCuentaComponent
  },
  {
    path: '**',
    redirectTo: 'mi-cuenta'
  }
];
