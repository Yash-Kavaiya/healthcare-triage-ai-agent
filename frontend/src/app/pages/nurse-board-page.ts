import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';

import { App } from '../app.js';

@Component({
  selector: 'app-nurse-board-page',
  imports: [CommonModule],
  template: `
    <section class="board-summary nurse">
      <div class="board-head">
        <p class="board-kicker">Nurse Board</p>
        <h2>Immediate Queue Operations</h2>
        <p>Prioritize pending cases, resolve high-risk patients, and document nurse actions.</p>
      </div>

      <div class="board-metrics">
        <article>
          <h3>Pending Queue</h3>
          <p>{{ app.metricNumber(app.metrics?.pending_queue) }}</p>
        </article>
        <article>
          <h3>Urgent Queue</h3>
          <p>{{ app.metricNumber(app.metrics?.pending_high_priority_queue) }}</p>
        </article>
        <article>
          <h3>Urgent+Emergency 24h</h3>
          <p>{{ app.metricNumber(app.metrics?.urgent_cases_24h) }}</p>
        </article>
      </div>

      <div class="board-actions">
        <button class="ghost" (click)="app.openBoardTab('queue')">Open Queue</button>
        <button class="ghost" (click)="app.openBoardTab('dashboard')">View Activity</button>
        <button class="ghost" (click)="app.openBoardTab('audit')">Audit Trail</button>
        <button class="primary" (click)="app.refreshBoardSummary()">Refresh Board</button>
      </div>
    </section>
  `,
  styleUrl: './board-page.css',
})
export class NurseBoardPage {
  constructor(public readonly app: App) {}
}
