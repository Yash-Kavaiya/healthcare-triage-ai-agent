import { CommonModule } from '@angular/common';
import { Component, Input, output } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { IntakeResponse } from '../api.types.js';

@Component({
  selector: 'app-intake-panel',
  imports: [CommonModule, FormsModule],
  templateUrl: './intake-panel.html',
  styleUrl: './panel-shared.css',
})
export class IntakePanel {
  @Input({ required: true }) form!: {
    phone: string;
    age: number;
    sex: string;
    symptoms: string;
    auto_book_high_urgency: boolean;
    always_route_when_model_requests_human: boolean;
  };

  @Input() result: IntakeResponse | null = null;
  @Input() loading = false;

  readonly run = output<void>();

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
