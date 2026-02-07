import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';

import { App } from '../app.js';

@Component({
  selector: 'app-ops-board-page',
  imports: [CommonModule],
  template: `
    <section class="board-summary operations">
      <div class="board-head">
        <p class="board-kicker">Ops Board</p>
        <h2>Operational Throughput Snapshot</h2>
        <p>Manage intake quality and monitor appointment flow across departments.</p>
      </div>

      <div class="board-metrics">
        <article>
          <h3>Triage Events 24h</h3>
          <p>{{ app.metricNumber(app.metrics?.triage_events_24h) }}</p>
        </article>
        <article>
          <h3>Utilization</h3>
          <p>{{ app.metricPercent(app.metrics?.slot_utilization_percent) }}</p>
        </article>
        <article>
          <h3>Avg Confidence 24h</h3>
          <p>{{ app.metricPercent(app.metrics?.avg_confidence_24h) }}</p>
        </article>
      </div>

      <div class="board-actions">
        <button class="ghost" (click)="app.openBoardTab('intake')">New Intake</button>
        <button class="ghost" (click)="app.openBoardTab('dashboard')">Throughput</button>
        <button class="ghost" (click)="app.openBoardTab('audit')">Compliance</button>
        <button class="primary" (click)="app.refreshBoardSummary()">Refresh Board</button>
      </div>
    </section>
  `,
  styleUrl: './board-page.css',
})
export class OpsBoardPage {
  constructor(public readonly app: App) {}
}
