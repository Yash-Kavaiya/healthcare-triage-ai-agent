import { inject } from '@angular/core';
import { CanActivateFn, Router, Routes } from '@angular/router';
import { AuthUser } from './api.types.js';
import { AdminOnboardingPage } from './pages/admin-onboarding-page.js';
import { AdminBoardPage } from './pages/admin-board-page.js';
import { NurseOnboardingPage } from './pages/nurse-onboarding-page.js';
import { NurseBoardPage } from './pages/nurse-board-page.js';
import { OpsOnboardingPage } from './pages/ops-onboarding-page.js';
import { OpsBoardPage } from './pages/ops-board-page.js';
import { UserManagementPage } from './pages/user-management-page.js';

type Role = AuthUser['role'];

const USER_KEY = 'triage_user';
const ROLE_PATHS: Record<Role, string> = {
  operations: '/ops',
  nurse: '/nurse',
  admin: '/admin',
};

function userRoleFromStorage(): Role | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as Partial<AuthUser>;
    if (parsed.role === 'operations' || parsed.role === 'nurse' || parsed.role === 'admin') {
      return parsed.role;
    }
    return null;
  } catch {
    return null;
  }
}

function boardAccessGuard(target: Role, options?: { allowAdmin?: boolean }): CanActivateFn {
  const allowAdmin = options?.allowAdmin ?? true;
  return () => {
    const role = userRoleFromStorage();
    if (!role) {
      return true;
    }
    if (role === target) {
      return true;
    }
    if (allowAdmin && role === 'admin') {
      return true;
    }
    const router = inject(Router);
    return router.parseUrl(ROLE_PATHS[role]);
  };
}

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'ops' },
  {
    path: 'onboarding/ops',
    component: OpsOnboardingPage,
    canActivate: [boardAccessGuard('operations', { allowAdmin: false })],
  },
  {
    path: 'onboarding/nurse',
    component: NurseOnboardingPage,
    canActivate: [boardAccessGuard('nurse', { allowAdmin: false })],
  },
  {
    path: 'onboarding/admin',
    component: AdminOnboardingPage,
    canActivate: [boardAccessGuard('admin', { allowAdmin: false })],
  },
  {
    path: 'ops',
    component: OpsBoardPage,
    canActivate: [boardAccessGuard('operations')],
  },
  {
    path: 'nurse',
    component: NurseBoardPage,
    canActivate: [boardAccessGuard('nurse')],
  },
  {
    path: 'admin',
    component: AdminBoardPage,
    canActivate: [boardAccessGuard('admin')],
  },
  {
    path: 'admin/users',
    component: UserManagementPage,
    canActivate: [boardAccessGuard('admin')],
  },
  { path: '**', redirectTo: 'ops' },
];
