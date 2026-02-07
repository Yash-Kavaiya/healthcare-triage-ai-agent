import { TestBed } from '@angular/core/testing';

import { DashboardPanel } from './dashboard-panel.js';

describe('DashboardPanel', () => {
  it('emits refresh when refresh button is clicked', () => {
    TestBed.configureTestingModule({
      imports: [DashboardPanel],
    });
    const fixture = TestBed.createComponent(DashboardPanel);
    const component = fixture.componentInstance;
    component.metrics = {
      repeat_patients_in_slots: 1,
      total_slots: 10,
      available_slots: 5,
      booked_slots: 5,
      slot_utilization_percent: 50,
      pending_queue: 2,
      pending_high_priority_queue: 1,
      total_appointments: 5,
      auto_booked_appointments: 3,
      preempted_appointments: 0,
      triage_events_24h: 12,
      urgent_cases_24h: 4,
      avg_confidence_24h: 0.78,
    };
    component.appointmentRows = [];
    component.activityRows = [];

    let emitted = 0;
    const sub = component.refresh.subscribe(() => {
      emitted += 1;
    });

    fixture.detectChanges();
    (
      (fixture.nativeElement as HTMLElement).querySelector(
        'button.ghost',
      ) as HTMLButtonElement | null
    )?.click();

    expect(emitted).toBe(1);
    sub.unsubscribe();
  });
});
