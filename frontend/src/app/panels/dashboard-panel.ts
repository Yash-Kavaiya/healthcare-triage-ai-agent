import { CommonModule } from '@angular/common';
import { Component, Input, output } from '@angular/core';

import { DashboardMetrics } from '../api.types.js';

@Component({
  selector: 'app-dashboard-panel',
  imports: [CommonModule],
  templateUrl: './dashboard-panel.html',
  styleUrl: './panel-shared.css',
})
export class DashboardPanel {
  @Input() metrics: DashboardMetrics | null = null;
  @Input() appointmentRows: Array<{
    appointmentId: string;
    bookedAt: string;
    patientId: string;
    phone: string;
    urgency: string;
    department: string;
    provider: string;
    slotWindow: string;
    note: string;
  }> = [];
  @Input() activityRows: Array<{
    id: string;
    appointmentId: string;
    activityType: string;
    createdAt: string;
    urgency: string;
    slotId: string;
    note: string;
    detailsSummary: string;
  }> = [];

  readonly refresh = output<void>();

  formatPercent(value: number): string {
    const normalized = value <= 1 ? value * 100 : value;
    return `${Math.max(0, Math.min(100, normalized)).toFixed(0)}%`;
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

  activityTone(value: string): 'critical' | 'high' | 'medium' | 'low' | 'neutral' {
    const activityType = value.trim().toUpperCase();
    if (activityType.includes('PREEMPTED')) {
      return 'high';
    }
    if (activityType.includes('ESCALATED')) {
      return 'critical';
    }
    if (activityType.includes('RESCHEDULED')) {
      return 'medium';
    }
    if (activityType.includes('BOOKED')) {
      return 'low';
    }
    return 'neutral';
  }
}
