import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';

import { App } from '../app.js';

@Component({
  selector: 'app-admin-onboarding-page',
  imports: [CommonModule],
  template: `
    <section class="board-summary onboarding admin">
      <div class="board-head">
        <p class="board-kicker">Admin Onboarding</p>
        <h2>Governance Activation Checklist</h2>
        <p>Validate policy guardrails before supervising cross-role activity.</p>
      </div>

      <div class="onboarding-grid">
        <article>
          <h3>Auth Controls</h3>
          <p>Confirm default-password reset policy and lockout settings are active.</p>
        </article>
        <article>
          <h3>Operational Oversight</h3>
          <p>Monitor queue pressure, preemption rate, and high-urgency trends daily.</p>
        </article>
        <article>
          <h3>Audit Governance</h3>
          <p>Review sampled triage decisions and audit log payloads for compliance.</p>
        </article>
      </div>

      <div class="board-actions">
        <button class="ghost" (click)="app.openBoardTab('dashboard')">Preview Dashboard</button>
        <button class="ghost" (click)="app.openBoardTab('audit')">Preview Audit</button>
        <button class="primary" (click)="app.completeOnboarding('admin')">
          Complete Admin Onboarding
        </button>
      </div>
    </section>
  `,
  styleUrl: './board-page.css',
})
export class AdminOnboardingPage {
  constructor(public readonly app: App) {}
}
