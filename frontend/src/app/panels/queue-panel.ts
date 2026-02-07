import { CommonModule } from '@angular/common';
import { Component, Input, output } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { QueueItem } from '../api.types.js';

@Component({
  selector: 'app-queue-panel',
  imports: [CommonModule, FormsModule],
  templateUrl: './queue-panel.html',
  styleUrl: './panel-shared.css',
})
export class QueuePanel {
  @Input({ required: true }) items!: QueueItem[];
  @Input() selectedQueueId: number | null = null;
  @Input() loading = false;
  @Input({ required: true }) bookForm!: {
    nurse_name: string;
    department_override: string;
    urgency_override: string;
    note: string;
  };

  readonly refresh = output<void>();
  readonly book = output<void>();
  readonly selectedQueueIdChange = output<number | null>();

  onSelectQueue(id: number): void {
    this.selectedQueueIdChange.emit(id);
  }

  selectedQueue(): QueueItem | null {
    if (!this.selectedQueueId) {
      return null;
    }
    return this.items.find((item) => item.id === this.selectedQueueId) || null;
  }
}
