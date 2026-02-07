import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { of } from 'rxjs';

import { App } from './app.js';
import { ApiService } from './api.service.js';
import { routes } from './app.routes.js';

class ApiServiceMock {
  login = jasmine.createSpy().and.returnValue(
    of({
      access_token: 'token',
      refresh_token: 'refresh',
      token_type: 'bearer',
      expires_in: 3600,
      refresh_expires_in: 7200,
      user: {
        username: 'ops',
        role: 'operations',
        password_change_required: false,
        onboarding_completed: false,
      },
    }),
  );
  me = jasmine.createSpy().and.returnValue(
    of({
      username: 'ops',
      role: 'operations',
      password_change_required: false,
      onboarding_completed: false,
    }),
  );
  refreshSession = jasmine.createSpy().and.returnValue(
    of({
      access_token: 'token',
      refresh_token: 'refresh',
      token_type: 'bearer',
      expires_in: 3600,
      refresh_expires_in: 7200,
      user: {
        username: 'ops',
        role: 'operations',
        password_change_required: false,
        onboarding_completed: false,
      },
    }),
  );
  changePassword = jasmine.createSpy().and.returnValue(
    of({
      access_token: 'token',
      refresh_token: 'refresh',
      token_type: 'bearer',
      expires_in: 3600,
      refresh_expires_in: 7200,
      user: {
        username: 'ops',
        role: 'operations',
        password_change_required: false,
        onboarding_completed: false,
      },
    }),
  );
  completeOnboarding = jasmine.createSpy().and.returnValue(
    of({
      username: 'ops',
      role: 'operations',
      password_change_required: false,
      onboarding_completed: true,
    }),
  );
  resetOnboarding = jasmine.createSpy().and.returnValue(
    of({
      username: 'ops',
      role: 'operations',
      password_change_required: false,
      onboarding_completed: false,
    }),
  );
  logout = jasmine.createSpy();
  hasSession = jasmine.createSpy().and.returnValue(false);
  currentUser = jasmine.createSpy().and.returnValue(null);
  runIntake = jasmine.createSpy().and.returnValue(of(null));
  listQueue = jasmine.createSpy().and.returnValue(of({ items: [] }));
  bookQueueItem = jasmine.createSpy().and.returnValue(of({ queue_id: 1, appointment_result: { status: 'BOOKED', note: '' } }));
  getMetrics = jasmine.createSpy().and.returnValue(
    of({
      repeat_patients_in_slots: 0,
      total_slots: 0,
      available_slots: 0,
      booked_slots: 0,
      slot_utilization_percent: 0,
      pending_queue: 0,
      pending_high_priority_queue: 0,
      total_appointments: 0,
      auto_booked_appointments: 0,
      preempted_appointments: 0,
      triage_events_24h: 0,
      urgent_cases_24h: 0,
      avg_confidence_24h: 0,
    }),
  );
  getAppointments = jasmine.createSpy().and.returnValue(of({ items: [] }));
  getActivity = jasmine.createSpy().and.returnValue(of({ items: [] }));
  getAudit = jasmine.createSpy().and.returnValue(of({ role: 'operations', triage: [], audit_log: [] }));
}

describe('App', () => {
  beforeEach(async () => {
    localStorage.clear();
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [provideRouter(routes), { provide: ApiService, useClass: ApiServiceMock }],
    }).compileComponents();
  });

  it('should create the app', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    expect(app).toBeTruthy();
  });

  it('should render title', () => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('h1')?.textContent).toContain('Patient Triage Control Center');
  });

  it('should send first login to role onboarding', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    const router = TestBed.inject(Router);
    const navSpy = spyOn(router, 'navigateByUrl').and.resolveTo(true);

    app.login();

    expect(navSpy).toHaveBeenCalledWith('/onboarding/ops', { replaceUrl: true });
    expect(app.message).toContain('Complete onboarding');
  });

  it('should complete onboarding and open board route', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    const router = TestBed.inject(Router);
    const navSpy = spyOn(router, 'navigateByUrl').and.resolveTo(true);

    app.currentUser = {
      username: 'ops',
      role: 'operations',
      password_change_required: false,
      onboarding_completed: false,
    };
    app.completeOnboarding('operations');

    expect(navSpy).toHaveBeenCalledWith('/ops', { replaceUrl: true });
  });
});
