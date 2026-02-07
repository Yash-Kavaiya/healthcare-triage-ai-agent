import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';

import { App } from '../app.js';

@Component({
  selector: 'app-nurse-onboarding-page',
  imports: [CommonModule],
  template: `
    <section class="board-summary onboarding nurse">
      <div class="board-head">
        <p class="board-kicker">Nurse Onboarding</p>
        <h2>Nurse Queue Readiness</h2>
        <p>Standardize escalation and booking behavior for high-risk patients.</p>
      </div>

      <div class="onboarding-grid">
        <article>
          <h3>Queue Triage</h3>
          <p>Work top-down by urgency, then age and symptom complexity.</p>
        </article>
        <article>
          <h3>Escalation Protocol</h3>
          <p>Escalate emergency signs immediately and capture rationale in note field.</p>
        </article>
        <article>
          <h3>Booking Discipline</h3>
          <p>Use department/urgency overrides only when chart evidence supports it.</p>
        </article>
      </div>

      <div class="board-actions">
        <button class="ghost" (click)="app.openBoardTab('queue')">Preview Queue</button>
        <button class="ghost" (click)="app.openBoardTab('audit')">Preview Audit</button>
        <button class="primary" (click)="app.completeOnboarding('nurse')">
          Complete Nurse Onboarding
        </button>
      </div>
    </section>
  `,
  styleUrl: './board-page.css',
})
export class NurseOnboardingPage {
  constructor(public readonly app: App) {}
}
