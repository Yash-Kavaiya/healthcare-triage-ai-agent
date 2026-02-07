import { TestBed } from '@angular/core/testing';

import { AuditPanel } from './audit-panel.js';

describe('AuditPanel', () => {
  it('emits refresh and auditRowsChange events', () => {
    TestBed.configureTestingModule({
      imports: [AuditPanel],
    });
    const fixture = TestBed.createComponent(AuditPanel);
    const component = fixture.componentInstance;
    component.roleLabel = 'operations';
    component.auditRows = 80;
    component.auditLoaded = true;
    component.triageRows = [
      {
        triageEventId: '1',
        createdAt: '2026-02-07 10:00:00',
        urgency: 'URGENT',
        confidenceLabel: '80%',
        suggestedDepartment: 'General Medicine',
        routingAction: 'QUEUE_REVIEW',
        routingReason: 'Model requested human review',
      },
    ];
    component.auditLogRows = [
      {
        id: '11',
        entityType: 'nurse_queue',
        entityId: '1',
        action: 'ENQUEUED',
        createdAt: '2026-02-07 10:01:00',
        payloadSummary: 'priority: URGENT',
      },
    ];

    let refreshCount = 0;
    let rowsValue = 0;
    const subRefresh = component.refresh.subscribe(() => {
      refreshCount += 1;
    });
    const subRows = component.auditRowsChange.subscribe((value) => {
      rowsValue = value;
    });

    fixture.detectChanges();
    component.onAuditRowsChange('120');
    (
      (fixture.nativeElement as HTMLElement).querySelector(
        'button.primary',
      ) as HTMLButtonElement | null
    )?.click();

    expect(rowsValue).toBe(120);
    expect(refreshCount).toBe(1);
    subRefresh.unsubscribe();
    subRows.unsubscribe();
  });
});
