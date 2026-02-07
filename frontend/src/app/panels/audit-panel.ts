import { CommonModule } from '@angular/common';
import { Component, Input, output } from '@angular/core';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-audit-panel',
  imports: [CommonModule, FormsModule],
  templateUrl: './audit-panel.html',
  styleUrl: './panel-shared.css',
})
export class AuditPanel {
  @Input({ required: true }) roleLabel!: string;
  @Input() auditRows = 80;
  @Input() auditLoaded = false;
  @Input() triageRows: Array<{
    triageEventId: string;
    createdAt: string;
    urgency: string;
    confidenceLabel: string;
    suggestedDepartment: string;
    routingAction: string;
    routingReason: string;
  }> = [];
  @Input() auditLogRows: Array<{
    id: string;
    entityType: string;
    entityId: string;
    action: string;
    createdAt: string;
    payloadSummary: string;
  }> = [];

  readonly refresh = output<void>();
  readonly auditRowsChange = output<number>();

  onAuditRowsChange(value: string | number): void {
    const parsed = Number(value);
    if (Number.isNaN(parsed)) {
      return;
    }
    this.auditRowsChange.emit(parsed);
  }

  urgencyTone(value: string): 'critical' | 'high' | 'medium' | 'low' | 'neutral' {
    const urgency = value.trim().toUpperCase();
    if (urgency === 'EMERGENCY') {
      return 'critical';
    }
    if (urgency === 'URGENT') {
      return 'high';
    }
    if (urgency === 'SOON') {
      return 'medium';
    }
    if (urgency === 'ROUTINE') {
      return 'low';
    }
    return 'neutral';
  }

  routingTone(value: string): 'critical' | 'high' | 'medium' | 'low' | 'neutral' {
    const action = value.trim().toUpperCase();
    if (action === 'ESCALATE') {
      return 'critical';
    }
    if (action === 'QUEUE_REVIEW') {
      return 'medium';
    }
    if (action === 'AUTO_BOOK') {
      return 'low';
    }
    return 'neutral';
  }

  trackByIndex(index: number): number {
    return index;
  }
}
