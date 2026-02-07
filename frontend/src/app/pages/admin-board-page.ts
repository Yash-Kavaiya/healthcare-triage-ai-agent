import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';

import { App } from '../app.js';

@Component({
  selector: 'app-admin-board-page',
  imports: [CommonModule],
  template: `
    <section class="board-summary admin">
      <div class="board-head">
        <p class="board-kicker">Admin Board</p>
        <h2>System Health and Governance</h2>
        <p>Review platform-wide outcomes, monitor escalations, and validate process compliance.</p>
      </div>

      <div class="board-metrics">
        <article>
          <h3>Total Appointments</h3>
          <p>{{ app.metricNumber(app.metrics?.total_appointments) }}</p>
        </article>
        <article>
          <h3>Preempted</h3>
          <p>{{ app.metricNumber(app.metrics?.preempted_appointments) }}</p>
        </article>
        <article>
          <h3>Repeat Patients</h3>
          <p>{{ app.metricNumber(app.metrics?.repeat_patients_in_slots) }}</p>
        </article>
      </div>

      <div class="board-actions">
        <button class="ghost" (click)="app.openBoardTab('dashboard')">System Metrics</button>
        <button class="ghost" (click)="app.openBoardTab('queue')">Queue Supervision</button>
        <button class="ghost" (click)="app.openBoardTab('audit')">Audit Logs</button>
        <button class="secondary" (click)="app.navigateToUserManagement()">👥 User Management</button>
        <button class="primary" (click)="app.refreshBoardSummary()">Refresh Board</button>
      </div>
    </section>
  `,
  styleUrl: './board-page.css',
})
export class AdminBoardPage {
  constructor(public readonly app: App) {}
}
