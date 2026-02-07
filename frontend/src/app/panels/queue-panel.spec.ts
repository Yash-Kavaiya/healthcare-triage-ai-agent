import { TestBed } from '@angular/core/testing';

import { QueuePanel } from './queue-panel.js';

describe('QueuePanel', () => {
  it('emits selectedQueueIdChange, refresh, and book events', () => {
    TestBed.configureTestingModule({
      imports: [QueuePanel],
    });
    const fixture = TestBed.createComponent(QueuePanel);
    const component = fixture.componentInstance;
    component.items = [
      {
        id: 101,
        status: 'PENDING',
        priority: 'URGENT',
        reason: 'Model requested human routing',
        created_at: '2026-02-07 10:00:00',
        triage_event_id: 55,
        urgency: 'URGENT',
        confidence: 0.72,
        suggested_department: 'General Medicine',
        rationale: 'Needs review',
        patient_id: 88,
        phone: '5551234567',
        age: 43,
        sex: 'Male',
        symptoms: 'Persistent fever',
      },
    ];
    component.selectedQueueId = 101;
    component.loading = false;
    component.bookForm = {
      nurse_name: 'triage-nurse',
      department_override: '',
      urgency_override: '',
      note: '',
    };

    const selectedValues: Array<number | null> = [];
    let refreshCount = 0;
    let bookCount = 0;
    const subSelect = component.selectedQueueIdChange.subscribe((value) => {
      selectedValues.push(value);
    });
    const subRefresh = component.refresh.subscribe(() => {
      refreshCount += 1;
    });
    const subBook = component.book.subscribe(() => {
      bookCount += 1;
    });

    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;
    (root.querySelector('button.ghost') as HTMLButtonElement | null)?.click();
    (root.querySelector('button.queue-item') as HTMLButtonElement | null)?.click();
    (root.querySelector('button.primary') as HTMLButtonElement | null)?.click();

    expect(refreshCount).toBe(1);
    expect(selectedValues[0]).toBe(101);
    expect(bookCount).toBe(1);

    subSelect.unsubscribe();
    subRefresh.unsubscribe();
    subBook.unsubscribe();
  });
});
