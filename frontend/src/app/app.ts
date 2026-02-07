// Healthcare Triage AI Agent - Main App Component
import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { NavigationEnd, Router, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';

import { ApiService } from './api.service.js';
import {
  AuditResponse,
  AuthTokenResponse,
  AuthUser,
  DashboardActivityResponse,
  DashboardAppointmentsResponse,
  DashboardMetrics,
  IntakeResponse,
  QueueBookResponse,
  QueueItem,
  QueueListResponse,
} from './api.types.js';
import { AuditPanel } from './panels/audit-panel.js';
import { DashboardPanel } from './panels/dashboard-panel.js';
import { IntakePanel } from './panels/intake-panel.js';
import { QueuePanel } from './panels/queue-panel.js';

type TabKey = 'intake' | 'queue' | 'dashboard' | 'audit';
type BoardKey = 'nurse' | 'operations' | 'admin';
type UrgencyTone = 'critical' | 'high' | 'medium' | 'low' | 'neutral';

interface AuditTriageRow {
  triageEventId: string;
  createdAt: string;
  urgency: string;
  confidenceLabel: string;
  suggestedDepartment: string;
  routingAction: string;
  routingReason: string;
}

interface AuditLogRow {
  id: string;
  entityType: string;
  entityId: string;
  action: string;
  createdAt: string;
  payloadSummary: string;
}

interface AppointmentViewRow {
  appointmentId: string;
  bookedAt: string;
  patientId: string;
  phone: string;
  urgency: string;
  department: string;
  provider: string;
  slotWindow: string;
  note: string;
}

interface ActivityViewRow {
  id: string;
  appointmentId: string;
  activityType: string;
  createdAt: string;
  urgency: string;
  slotId: string;
  note: string;
  detailsSummary: string;
}

@Component({
  selector: 'app-root',
  imports: [
    CommonModule,
    FormsModule,
    RouterOutlet,
    IntakePanel,
    QueuePanel,
    DashboardPanel,
    AuditPanel,
  ],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App implements OnInit {
  activeBoard: BoardKey = 'operations';
  activeTab: TabKey = 'intake';
  loading = false;
  message = '';
  error = '';

  loginForm = {
    username: 'ops',
    password: 'ops123',
  };
  currentUser: AuthUser | null = null;
  mustChangePassword = false;
  passwordForm = {
    current_password: '',
    new_password: '',
    confirm_password: '',
  };

  intakeForm = {
    phone: '',
    age: 30,
    sex: 'Male',
    symptoms: '',
    auto_book_high_urgency: true,
    always_route_when_model_requests_human: true,
  };
  intakeResult: IntakeResponse | null = null;

  queueItems: QueueItem[] = [];
  selectedQueueId: number | null = null;
  queueBookForm = {
    nurse_name: 'triage-nurse',
    department_override: '',
    urgency_override: '',
    note: '',
  };

  metrics: DashboardMetrics | null = null;
  appointments: DashboardAppointmentsResponse['items'] = [];
  activity: DashboardActivityResponse['items'] = [];
  appointmentRows: AppointmentViewRow[] = [];
  activityRows: ActivityViewRow[] = [];

  auditRows = 80;
  audit: AuditResponse | null = null;
  auditTriageRows: AuditTriageRow[] = [];
  auditLogRows: AuditLogRow[] = [];

  constructor(
    private readonly api: ApiService,
    private readonly router: Router,
  ) {}

  ngOnInit(): void {
    this.syncBoardFromUrl(this.router.url);
    this.router.events
      .pipe(filter((event) => event instanceof NavigationEnd))
      .subscribe((event) =>
        this.syncBoardFromUrl((event as NavigationEnd).urlAfterRedirects),
      );

    if (this.api.hasSession()) {
      this.restoreSession();
    }
  }

  setTab(tab: TabKey): void {
    if (!this.currentUser) {
      this.error = 'Log in first.';
      return;
    }
    if (this.mustChangePassword) {
      this.error = 'Change your password before accessing protected modules.';
      return;
    }
    if (!this.isTabVisible(tab)) {
      this.error = 'This tab is not available for the selected board.';
      return;
    }
    this.activeTab = tab;
    this.clearStatus();
  }

  setBoard(board: BoardKey): void {
    if (!this.currentUser) {
      this.error = 'Log in first.';
      return;
    }
    if (this.mustChangePassword) {
      this.error = 'Change your password before accessing protected modules.';
      return;
    }
    if (!this.canAccessBoard(board)) {
      this.error = 'You do not have access to this board.';
      return;
    }
    this.activeBoard = board;
    this.navigateToBoard(board);
    if (!this.isTabVisible(this.activeTab)) {
      this.activeTab = this.defaultTabForBoard(this.activeBoard);
    }
    this.clearStatus();
  }

  login(): void {
    this.loading = true;
    this.clearStatus();
    this.api.login(this.loginForm).subscribe({
      next: (result: AuthTokenResponse) => {
        this.currentUser = result.user;
        this.mustChangePassword = !!result.user.password_change_required;
        this.activeBoard = this.defaultBoardForUser(result.user.role);
        this.activeTab = this.defaultTabForBoard(this.activeBoard);
        if (this.mustChangePassword) {
          this.message = 'Password change required before continuing.';
          this.passwordForm.current_password = this.loginForm.password;
          this.navigateToBoard(this.activeBoard, true);
        } else if (this.requiresOnboarding(result.user)) {
          this.navigateToOnboarding(result.user.role, true);
          this.message = `Welcome ${result.user.username}. Complete onboarding to unlock ${result.user.role} workflows.`;
        } else {
          this.navigateToBoard(this.activeBoard, true);
          this.message = `Logged in as ${result.user.username} (${result.user.role}).`;
          this.bootstrapData();
        }
        this.loading = false;
      },
      error: (err: unknown) => {
        this.error = this.extractError(err, 'Login failed.');
        this.loading = false;
      },
    });
  }

  changePassword(): void {
    if (!this.currentUser) {
      this.error = 'Log in first.';
      return;
    }
    if (!this.passwordForm.current_password || !this.passwordForm.new_password) {
      this.error = 'Current and new password are required.';
      return;
    }
    if (this.passwordForm.new_password !== this.passwordForm.confirm_password) {
      this.error = 'New password and confirmation do not match.';
      return;
    }
    this.loading = true;
    this.clearStatus();
    this.api
      .changePassword({
        current_password: this.passwordForm.current_password,
        new_password: this.passwordForm.new_password,
      })
      .subscribe({
        next: (tokenResponse: AuthTokenResponse) => {
          this.currentUser = tokenResponse.user;
          this.mustChangePassword = !!tokenResponse.user.password_change_required;
          this.activeBoard = this.defaultBoardForUser(tokenResponse.user.role);
          this.activeTab = this.defaultTabForBoard(this.activeBoard);
          this.passwordForm = {
            current_password: '',
            new_password: '',
            confirm_password: '',
          };
          if (this.mustChangePassword) {
            this.message = 'Password change required before continuing.';
            this.navigateToBoard(this.activeBoard, true);
          } else if (this.requiresOnboarding(tokenResponse.user)) {
            this.navigateToOnboarding(tokenResponse.user.role, true);
            this.message = 'Password updated. Complete onboarding to continue.';
          } else {
            this.message = 'Password updated. Access granted.';
            this.bootstrapData();
          }
          this.loading = false;
        },
        error: (err: unknown) => {
          this.error = this.extractError(err, 'Unable to change password.');
          this.loading = false;
        },
      });
  }

  logout(): void {
    this.api.logout();
    this.currentUser = null;
    this.mustChangePassword = false;
    this.passwordForm = {
      current_password: '',
      new_password: '',
      confirm_password: '',
    };
    this.intakeResult = null;
    this.queueItems = [];
    this.metrics = null;
    this.appointments = [];
    this.activity = [];
    this.appointmentRows = [];
    this.activityRows = [];
    this.audit = null;
    this.auditTriageRows = [];
    this.auditLogRows = [];
    this.activeBoard = 'operations';
    this.activeTab = 'intake';
    this.navigateToBoard(this.activeBoard, true);
    this.message = 'Logged out.';
    this.error = '';
  }

  runIntake(): void {
    if (!this.currentUser) {
      this.error = 'Log in first.';
      return;
    }
    if (this.mustChangePassword) {
      this.error = 'Change password first.';
      return;
    }
    if (!this.intakeForm.symptoms.trim()) {
      this.error = 'Symptoms are required.';
      return;
    }
    this.loading = true;
    this.clearStatus();
    this.api
      .runIntake({
        phone: this.intakeForm.phone || null,
        age: Number(this.intakeForm.age),
        sex: this.intakeForm.sex,
        symptoms: this.intakeForm.symptoms.trim(),
        auto_book_high_urgency: this.intakeForm.auto_book_high_urgency,
        always_route_when_model_requests_human:
          this.intakeForm.always_route_when_model_requests_human,
      })
      .subscribe({
        next: (result: IntakeResponse) => {
          this.intakeResult = result;
          this.message = 'Triage completed.';
          this.refreshQueue();
          this.refreshDashboard();
          this.refreshAudit();
          this.loading = false;
        },
        error: (err: unknown) => {
          this.error = this.extractError(err, 'Unable to complete triage.');
          this.loading = false;
        },
      });
  }

  refreshQueue(): void {
    if (!this.currentUser || !this.canManageQueue() || this.mustChangePassword) {
      this.queueItems = [];
      this.selectedQueueId = null;
      return;
    }
    this.api.listQueue().subscribe({
      next: (result: QueueListResponse) => {
        this.queueItems = result.items;
        if (!this.queueItems.length) {
          this.selectedQueueId = null;
          return;
        }
        if (
          !this.selectedQueueId ||
          !this.queueItems.find((it) => it.id === this.selectedQueueId)
        ) {
          this.selectedQueueId = this.queueItems[0].id;
        }
      },
      error: (err: unknown) => {
        this.error = this.extractError(err, 'Unable to load queue.');
      },
    });
  }

  bookQueueItem(): void {
    if (!this.currentUser || !this.canManageQueue()) {
      this.error = 'Queue management requires nurse or admin role.';
      return;
    }
    if (this.mustChangePassword) {
      this.error = 'Change password first.';
      return;
    }
    if (!this.selectedQueueId) {
      this.error = 'Select a queue item first.';
      return;
    }
    this.loading = true;
    this.clearStatus();
    this.api
      .bookQueueItem(this.selectedQueueId, {
        nurse_name: this.queueBookForm.nurse_name,
        department_override: this.queueBookForm.department_override || null,
        urgency_override:
          (this.queueBookForm.urgency_override as
            | 'EMERGENCY'
            | 'URGENT'
            | 'SOON'
            | 'ROUTINE') || null,
        note: this.queueBookForm.note,
      })
      .subscribe({
        next: (result: QueueBookResponse) => {
          this.message = `Queue #${result.queue_id} resolved: ${result.appointment_result.status}`;
          this.refreshQueue();
          this.refreshDashboard();
          this.refreshAudit();
          this.loading = false;
        },
        error: (err: unknown) => {
          this.error = this.extractError(err, 'Unable to book queue item.');
          this.loading = false;
        },
      });
  }

  refreshDashboard(): void {
    if (!this.currentUser || this.mustChangePassword) {
      return;
    }
    this.api.getMetrics().subscribe({
      next: (metrics: DashboardMetrics) => (this.metrics = metrics),
      error: (err: unknown) => (this.error = this.extractError(err, 'Unable to load metrics.')),
    });
    this.api.getAppointments().subscribe({
      next: (data: DashboardAppointmentsResponse) => {
        this.appointments = data.items;
        this.appointmentRows = this.buildAppointmentRows(data.items);
      },
      error: (err: unknown) => (this.error = this.extractError(err, 'Unable to load appointments.')),
    });
    this.api.getActivity().subscribe({
      next: (data: DashboardActivityResponse) => {
        this.activity = data.items;
        this.activityRows = this.buildActivityRows(data.items);
      },
      error: (err: unknown) => (this.error = this.extractError(err, 'Unable to load activity.')),
    });
  }

  refreshAudit(): void {
    if (!this.currentUser || this.mustChangePassword) {
      return;
    }
    this.api.getAudit(this.auditRows).subscribe({
      next: (data: AuditResponse) => {
        this.audit = data;
        this.auditTriageRows = this.buildAuditTriageRows(data.triage);
        this.auditLogRows = this.buildAuditLogRows(data.audit_log);
      },
      error: (err: unknown) => (this.error = this.extractError(err, 'Unable to load audit data.')),
    });
  }

  selectedQueue(): QueueItem | null {
    if (!this.selectedQueueId) {
      return null;
    }
    return this.queueItems.find((item) => item.id === this.selectedQueueId) || null;
  }

  canManageQueue(): boolean {
    return this.currentUser?.role === 'nurse' || this.currentUser?.role === 'admin';
  }

  availableBoards(): BoardKey[] {
    if (!this.currentUser) {
      return [];
    }
    if (this.currentUser.role === 'admin') {
      return ['admin', 'nurse', 'operations'];
    }
    if (this.currentUser.role === 'nurse') {
      return ['nurse'];
    }
    return ['operations'];
  }

  boardLabel(board: BoardKey): string {
    if (board === 'admin') {
      return 'Admin Board';
    }
    if (board === 'nurse') {
      return 'Nurse Board';
    }
    return 'Ops Board';
  }

  pageTitle(): string {
    if (!this.currentUser) {
      return 'Patient Triage Control Center';
    }
    if (this.isOnboardingRoute()) {
      return 'Role Onboarding';
    }
    if (this.activeBoard === 'admin') {
      return 'Admin Governance Workspace';
    }
    if (this.activeBoard === 'nurse') {
      return 'Nurse Triage Workspace';
    }
    return 'Operations Control Workspace';
  }

  pageSubtitle(): string {
    if (!this.currentUser) {
      return 'FastAPI backend + Angular frontend with JWT auth and role-enforced actions.';
    }
    if (this.isOnboardingRoute()) {
      return 'Complete setup checklist before accessing protected triage modules.';
    }
    if (this.activeBoard === 'admin') {
      return 'Policy oversight, routing safety, and cross-role supervision.';
    }
    if (this.activeBoard === 'nurse') {
      return 'Queue-first triage resolution with rapid booking and escalation.';
    }
    return 'Intake throughput, utilization tracking, and workflow monitoring.';
  }

  openBoardTab(tab: TabKey): void {
    this.setTab(tab);
  }

  isOnboardingRoute(): boolean {
    return this.onboardingRoleFromUrl(this.router.url) !== null;
  }

  completeOnboarding(role: BoardKey): void {
    if (!this.currentUser) {
      this.error = 'Log in first.';
      return;
    }
    const userBoard = this.defaultBoardForUser(this.currentUser.role);
    if (role !== userBoard) {
      this.error = 'Role mismatch for onboarding completion.';
      return;
    }
    this.loading = true;
    this.clearStatus();
    this.api.completeOnboarding().subscribe({
      next: (updatedUser: AuthUser) => {
        this.currentUser = updatedUser;
        this.activeBoard = userBoard;
        this.activeTab = this.defaultTabForBoard(this.activeBoard);
        this.message = `${this.boardLabel(userBoard)} onboarding completed.`;
        this.navigateToBoard(this.activeBoard, true);
        this.bootstrapData();
        this.loading = false;
      },
      error: (err: unknown) => {
        this.error = this.extractError(err, 'Unable to complete onboarding.');
        this.loading = false;
      },
    });
  }

  refreshBoardSummary(): void {
    this.refreshDashboard();
    if (this.activeBoard === 'nurse' || this.activeBoard === 'admin') {
      this.refreshQueue();
    }
    this.refreshAudit();
  }

  navigateToUserManagement(): void {
    void this.router.navigate(['/admin/users']);
  }

  metricNumber(value: number | null | undefined): string {
    if (value === null || value === undefined) {
      return '-';
    }
    return String(value);
  }

  metricPercent(value: number | null | undefined): string {
    if (value === null || value === undefined) {
      return '-';
    }
    return this.formatPercent(value);
  }

  isTabVisible(tab: TabKey): boolean {
    return this.visibleTabs().includes(tab);
  }

  asJson(value: unknown): string {
    return JSON.stringify(value, null, 2);
  }

  formatPercent(value: number): string {
    const percent = this.toPercent(value);
    return `${percent.toFixed(0)}%`;
  }

  urgencyTone(value: string): UrgencyTone {
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

  routingTone(value: string): UrgencyTone {
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

  activityTone(value: string): UrgencyTone {
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

  trackByIndex(index: number): number {
    return index;
  }

  clearStatus(): void {
    this.message = '';
    this.error = '';
  }

  private restoreSession(): void {
    this.api.me().subscribe({
      next: (user: AuthUser) => {
        this.currentUser = user;
        this.mustChangePassword = !!user.password_change_required;
        this.activeBoard = this.defaultBoardForUser(user.role);
        this.activeTab = this.defaultTabForBoard(this.activeBoard);
        if (this.mustChangePassword) {
          this.navigateToBoard(this.activeBoard, true);
          this.message = 'Password change required before continuing.';
        } else if (this.requiresOnboarding(user)) {
          this.navigateToOnboarding(user.role, true);
          this.message = 'Complete onboarding to unlock your role workspace.';
        } else {
          this.navigateToBoard(this.activeBoard, true);
          this.bootstrapData();
        }
      },
      error: () => {
        this.api.logout();
        this.currentUser = null;
        this.mustChangePassword = false;
      },
    });
  }

  private bootstrapData(): void {
    if (this.mustChangePassword) {
      return;
    }
    if (this.currentUser && this.requiresOnboarding(this.currentUser)) {
      this.navigateToOnboarding(this.currentUser.role, true);
      return;
    }
    if (!this.canAccessBoard(this.activeBoard)) {
      this.activeBoard = this.defaultBoardForUser(this.currentUser?.role);
    }
    if (!this.isTabVisible(this.activeTab)) {
      this.activeTab = this.defaultTabForBoard(this.activeBoard);
    }
    this.navigateToBoard(this.activeBoard, true);
    this.refreshDashboard();
    this.refreshAudit();
    this.refreshQueue();
  }

  private canAccessBoard(board: BoardKey): boolean {
    if (!this.currentUser) {
      return false;
    }
    if (this.currentUser.role === 'admin') {
      return true;
    }
    if (this.currentUser.role === 'nurse') {
      return board === 'nurse';
    }
    return board === 'operations';
  }

  private visibleTabs(): TabKey[] {
    if (this.activeBoard === 'admin') {
      return ['intake', 'queue', 'dashboard', 'audit'];
    }
    if (this.activeBoard === 'nurse') {
      return ['queue', 'intake', 'dashboard', 'audit'];
    }
    return ['intake', 'dashboard', 'audit'];
  }

  private defaultBoardForUser(role: AuthUser['role'] | undefined): BoardKey {
    if (role === 'admin') {
      return 'admin';
    }
    if (role === 'nurse') {
      return 'nurse';
    }
    return 'operations';
  }

  private defaultTabForBoard(board: BoardKey): TabKey {
    if (board === 'nurse') {
      return 'queue';
    }
    if (board === 'admin') {
      return 'dashboard';
    }
    return 'intake';
  }

  private syncBoardFromUrl(url: string): void {
    const onboardingRole = this.onboardingRoleFromUrl(url);
    if (onboardingRole) {
      this.activeBoard = onboardingRole;
      if (!this.isTabVisible(this.activeTab)) {
        this.activeTab = this.defaultTabForBoard(onboardingRole);
      }
      return;
    }

    const board = this.boardFromUrl(url);
    if (!board) {
      return;
    }
    if (!this.currentUser) {
      this.activeBoard = board;
      if (!this.isTabVisible(this.activeTab)) {
        this.activeTab = this.defaultTabForBoard(board);
      }
      return;
    }
    if (this.canAccessBoard(board)) {
      this.activeBoard = board;
    } else {
      this.activeBoard = this.defaultBoardForUser(this.currentUser.role);
    }
    if (!this.isTabVisible(this.activeTab)) {
      this.activeTab = this.defaultTabForBoard(this.activeBoard);
    }
    if (this.currentUser && !this.mustChangePassword && this.requiresOnboarding(this.currentUser)) {
      this.navigateToOnboarding(this.currentUser.role, true);
    }
  }

  private boardFromUrl(url: string): BoardKey | null {
    const cleanPath = url.split('?')[0].split('#')[0];
    const segment = cleanPath.replace(/^\//, '').split('/')[0];
    if (segment === 'nurse') {
      return 'nurse';
    }
    if (segment === 'admin') {
      return 'admin';
    }
    if (segment === 'ops') {
      return 'operations';
    }
    return null;
  }

  private boardPath(board: BoardKey): string {
    if (board === 'nurse') {
      return 'nurse';
    }
    if (board === 'admin') {
      return 'admin';
    }
    return 'ops';
  }

  private navigateToBoard(board: BoardKey, replaceUrl = false): void {
    const target = `/${this.boardPath(board)}`;
    const current = this.router.url.split('?')[0].split('#')[0];
    if (current === target) {
      return;
    }
    void this.router.navigateByUrl(target, { replaceUrl });
  }

  private onboardingPathForRole(role: AuthUser['role']): string {
    const board = this.defaultBoardForUser(role);
    return `/onboarding/${this.boardPath(board)}`;
  }

  private onboardingRoleFromUrl(url: string): BoardKey | null {
    const cleanPath = url.split('?')[0].split('#')[0];
    const segments = cleanPath.replace(/^\//, '').split('/');
    if (segments.length < 2 || segments[0] !== 'onboarding') {
      return null;
    }
    if (segments[1] === 'nurse') {
      return 'nurse';
    }
    if (segments[1] === 'admin') {
      return 'admin';
    }
    if (segments[1] === 'ops') {
      return 'operations';
    }
    return null;
  }

  private navigateToOnboarding(role: AuthUser['role'], replaceUrl = false): void {
    const target = this.onboardingPathForRole(role);
    const current = this.router.url.split('?')[0].split('#')[0];
    if (current === target) {
      return;
    }
    void this.router.navigateByUrl(target, { replaceUrl });
  }

  private requiresOnboarding(user: AuthUser | null | undefined): boolean {
    if (!user) {
      return false;
    }
    return !user.onboarding_completed;
  }

  private extractError(err: unknown, fallback: string): string {
    const response = err as HttpErrorResponse;
    const detail = response?.error?.detail;
    if (typeof detail === 'string' && detail.trim()) {
      return detail;
    }
    if (Array.isArray(detail) && detail.length) {
      return detail
        .map((item) => (typeof item === 'string' ? item : JSON.stringify(item)))
        .join('; ');
    }
    if (detail && typeof detail === 'object') {
      return JSON.stringify(detail);
    }
    if (response?.status === 0) {
      return 'Cannot reach backend API. Start FastAPI on http://localhost:8000.';
    }
    if (response?.message) {
      return response.message;
    }
    return fallback;
  }

  private buildAuditTriageRows(rows: Array<Record<string, unknown>>): AuditTriageRow[] {
    return rows.map((row) => ({
      triageEventId: this.valueLabel(row['triage_event_id']),
      createdAt: this.timestampLabel(row['created_at']),
      urgency: this.valueLabel(row['urgency']),
      confidenceLabel: this.formatConfidence(row['confidence']),
      suggestedDepartment: this.valueLabel(row['suggested_department']),
      routingAction: this.valueLabel(row['routing_action']),
      routingReason: this.valueLabel(row['routing_reason']),
    }));
  }

  private buildAuditLogRows(rows: Array<Record<string, unknown>>): AuditLogRow[] {
    return rows.map((row) => ({
      id: this.valueLabel(row['id']),
      entityType: this.valueLabel(row['entity_type']),
      entityId: this.valueLabel(row['entity_id']),
      action: this.valueLabel(row['action']),
      createdAt: this.timestampLabel(row['created_at']),
      payloadSummary: this.payloadSummary(row['payload']),
    }));
  }

  private buildAppointmentRows(rows: Array<Record<string, unknown>>): AppointmentViewRow[] {
    return rows.map((row) => {
      const slotStart = this.timestampLabel(row['slot_start']);
      const slotEnd = this.timestampLabel(row['slot_end']);
      let slotWindow = '-';
      if (slotStart !== '-' && slotEnd !== '-') {
        slotWindow = `${slotStart} -> ${slotEnd}`;
      } else if (slotStart !== '-') {
        slotWindow = slotStart;
      } else if (slotEnd !== '-') {
        slotWindow = slotEnd;
      }

      return {
        appointmentId: this.valueLabel(row['appointment_id']),
        bookedAt: this.timestampLabel(row['booked_at']),
        patientId: this.valueLabel(row['patient_id']),
        phone: this.valueLabel(row['phone']),
        urgency: this.valueLabel(row['urgency']),
        department: this.valueLabel(row['department']),
        provider: this.valueLabel(row['provider']),
        slotWindow,
        note: this.valueLabel(row['note']),
      };
    });
  }

  private buildActivityRows(rows: Array<Record<string, unknown>>): ActivityViewRow[] {
    return rows.map((row) => {
      const details = this.asRecord(row['details']);
      const slotId = details ? details['slot_id'] ?? details['new_slot_id'] ?? details['old_slot_id'] : null;
      const note = details ? details['note'] : null;
      const urgency = details ? details['urgency'] : null;

      return {
        id: this.valueLabel(row['id']),
        appointmentId: this.valueLabel(row['appointment_id']),
        activityType: this.valueLabel(row['activity_type']),
        createdAt: this.timestampLabel(row['created_at']),
        urgency: this.valueLabel(urgency),
        slotId: this.valueLabel(slotId),
        note: this.valueLabel(note),
        detailsSummary: this.payloadSummary(details),
      };
    });
  }

  private valueLabel(value: unknown): string {
    if (value === null || value === undefined) {
      return '-';
    }
    if (typeof value === 'string') {
      const trimmed = value.trim();
      return trimmed || '-';
    }
    if (typeof value === 'number' || typeof value === 'boolean') {
      return String(value);
    }
    return JSON.stringify(value);
  }

  private timestampLabel(value: unknown): string {
    if (typeof value !== 'string') {
      return this.valueLabel(value);
    }
    const trimmed = value.trim();
    return trimmed.replace('T', ' ').replace('Z', '');
  }

  private formatConfidence(value: unknown): string {
    if (typeof value === 'number') {
      return this.formatPercent(value);
    }
    if (typeof value === 'string') {
      const parsed = Number(value);
      if (!Number.isNaN(parsed)) {
        return this.formatPercent(parsed);
      }
      return value;
    }
    return '-';
  }

  private toPercent(value: number): number {
    const normalized = value <= 1 ? value * 100 : value;
    return Math.max(0, Math.min(100, normalized));
  }

  private payloadSummary(payload: unknown): string {
    if (payload === null || payload === undefined) {
      return '-';
    }
    if (typeof payload === 'string') {
      return payload;
    }
    if (typeof payload !== 'object') {
      return String(payload);
    }
    if (Array.isArray(payload)) {
      return `${payload.length} items`;
    }
    const entries = Object.entries(payload as Record<string, unknown>)
      .slice(0, 3)
      .map(([key, value]) => `${key}: ${this.valueLabel(value)}`);
    return entries.length ? entries.join(' | ') : '-';
  }

  private asRecord(value: unknown): Record<string, unknown> | null {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      return null;
    }
    return value as Record<string, unknown>;
  }
}
