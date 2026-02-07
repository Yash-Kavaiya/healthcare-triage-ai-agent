import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';

import { App } from '../app.js';

@Component({
  selector: 'app-ops-onboarding-page',
  imports: [CommonModule],
  template: `
    <section class="board-summary onboarding operations">
      <div class="board-head">
        <p class="board-kicker">Ops Onboarding</p>
        <h2>Operations Start Checklist</h2>
        <p>Confirm intake quality controls before routing live triage events.</p>
      </div>

      <div class="onboarding-grid">
        <article>
          <h3>Intake Standards</h3>
          <p>Verify symptom capture format, age/sex validation, and contact policy.</p>
        </article>
        <article>
          <h3>Routing Safety</h3>
          <p>Keep human routing enabled for uncertainty and low-confidence outcomes.</p>
        </article>
        <article>
          <h3>Daily Monitoring</h3>
          <p>Review throughput, utilization, and urgent-case drift at shift start.</p>
        </article>
      </div>

      <div class="board-actions">
        <button class="ghost" (click)="app.openBoardTab('intake')">Preview Intake</button>
        <button class="ghost" (click)="app.openBoardTab('dashboard')">Preview Dashboard</button>
        <button class="primary" (click)="app.completeOnboarding('operations')">
          Complete Ops Onboarding
        </button>
      </div>
    </section>
  `,
  styleUrl: './board-page.css',
})
export class OpsOnboardingPage {
  constructor(public readonly app: App) {}
}
