import { TestBed } from '@angular/core/testing';

import { IntakePanel } from './intake-panel.js';

describe('IntakePanel', () => {
  it('emits run when run button is clicked', () => {
    TestBed.configureTestingModule({
      imports: [IntakePanel],
    });
    const fixture = TestBed.createComponent(IntakePanel);
    const component = fixture.componentInstance;
    component.form = {
      phone: '',
      age: 30,
      sex: 'Male',
      symptoms: 'cough',
      auto_book_high_urgency: true,
      always_route_when_model_requests_human: true,
    };
    component.loading = false;
    component.result = null;

    let emitted = 0;
    const sub = component.run.subscribe(() => {
      emitted += 1;
    });

    fixture.detectChanges();
    (
      (fixture.nativeElement as HTMLElement).querySelector(
        'button.primary',
      ) as HTMLButtonElement | null
    )?.click();

    expect(emitted).toBe(1);
    sub.unsubscribe();
  });
});
