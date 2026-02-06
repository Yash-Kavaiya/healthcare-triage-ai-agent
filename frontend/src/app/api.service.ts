import { Injectable } from '@angular/core';
import { HttpClient, HttpErrorResponse, HttpHeaders, HttpParams } from '@angular/common/http';
import { Observable, catchError, switchMap, tap, throwError } from 'rxjs';

import {
  AuditResponse,
  AuthChangePasswordRequest,
  AuthLoginRequest,
  AuthTokenResponse,
  AuthUser,
  DashboardActivityResponse,
  DashboardAppointmentsResponse,
  DashboardMetrics,
  IntakeRequest,
  IntakeResponse,
  QueueBookRequest,
  QueueBookResponse,
  QueueListResponse,
} from './api.types.js';

@Injectable({
  providedIn: 'root',
})
export class ApiService {
  private readonly baseUrl = '/api/v1';
  private readonly tokenKey = 'triage_access_token';
  private readonly refreshTokenKey = 'triage_refresh_token';
  private readonly userKey = 'triage_user';

  constructor(private readonly http: HttpClient) {}

  login(payload: AuthLoginRequest): Observable<AuthTokenResponse> {
    return this.http
      .post<AuthTokenResponse>(`${this.baseUrl}/auth/login`, payload)
      .pipe(tap((token) => this.setSession(token)));
  }

  me(): Observable<AuthUser> {
    return this.withAutoRefresh(() =>
      this.http.get<AuthUser>(`${this.baseUrl}/auth/me`, this.authOptions()),
    );
  }

  refreshSession(): Observable<AuthTokenResponse> {
    const refreshToken = this.getRefreshToken();
    if (!refreshToken) {
      return throwError(() => new Error('No refresh token available.'));
    }
    return this.http
      .post<AuthTokenResponse>(`${this.baseUrl}/auth/refresh`, {
        refresh_token: refreshToken,
      })
      .pipe(tap((token) => this.setSession(token)));
  }

  changePassword(payload: AuthChangePasswordRequest): Observable<AuthTokenResponse> {
    return this.withAutoRefresh(() =>
      this.http
        .post<AuthTokenResponse>(`${this.baseUrl}/auth/change-password`, payload, this.authOptions())
        .pipe(tap((token) => this.setSession(token))),
    );
  }

  logout(): void {
    const refreshToken = this.getRefreshToken();
    if (refreshToken) {
      this.http
        .post<{ status: string }>(`${this.baseUrl}/auth/logout`, { refresh_token: refreshToken })
        .subscribe({
          next: () => undefined,
          error: () => undefined,
        });
    }
    this.clearLocalSession();
  }

  hasSession(): boolean {
    return !!this.getAccessToken() || !!this.getRefreshToken();
  }

  currentUser(): AuthUser | null {
    const raw = localStorage.getItem(this.userKey);
    if (!raw) {
      return null;
    }
    try {
      return JSON.parse(raw) as AuthUser;
    } catch {
      return null;
    }
  }

  runIntake(payload: IntakeRequest): Observable<IntakeResponse> {
    return this.withAutoRefresh(() =>
      this.http.post<IntakeResponse>(`${this.baseUrl}/triage/intake`, payload, this.authOptions()),
    );
  }

  listQueue(status = 'PENDING'): Observable<QueueListResponse> {
    return this.withAutoRefresh(() =>
      this.http.get<QueueListResponse>(`${this.baseUrl}/queue`, this.authOptions({ status })),
    );
  }

  bookQueueItem(queueId: number, payload: QueueBookRequest): Observable<QueueBookResponse> {
    return this.withAutoRefresh(() =>
      this.http.post<QueueBookResponse>(
        `${this.baseUrl}/queue/${queueId}/book`,
        payload,
        this.authOptions(),
      ),
    );
  }

  getMetrics(): Observable<DashboardMetrics> {
    return this.withAutoRefresh(() =>
      this.http.get<DashboardMetrics>(`${this.baseUrl}/dashboard/metrics`, this.authOptions()),
    );
  }

  getAppointments(limit = 30): Observable<DashboardAppointmentsResponse> {
    return this.withAutoRefresh(() =>
      this.http.get<DashboardAppointmentsResponse>(
        `${this.baseUrl}/dashboard/appointments`,
        this.authOptions({ limit }),
      ),
    );
  }

  getActivity(limit = 30): Observable<DashboardActivityResponse> {
    return this.withAutoRefresh(() =>
      this.http.get<DashboardActivityResponse>(
        `${this.baseUrl}/dashboard/activity`,
        this.authOptions({ limit }),
      ),
    );
  }

  getAudit(limit = 100): Observable<AuditResponse> {
    return this.withAutoRefresh(() =>
      this.http.get<AuditResponse>(`${this.baseUrl}/audit`, this.authOptions({ limit })),
    );
  }

  private withAutoRefresh<T>(requestFactory: () => Observable<T>): Observable<T> {
    return requestFactory().pipe(
      catchError((err) => {
        const response = err as HttpErrorResponse;
        if (!this.shouldRefresh(response)) {
          return throwError(() => err);
        }
        return this.refreshSession().pipe(
          switchMap(() => requestFactory()),
          catchError((refreshErr) => {
            this.clearLocalSession();
            return throwError(() => refreshErr);
          }),
        );
      }),
    );
  }

  private shouldRefresh(err: HttpErrorResponse): boolean {
    return err.status === 401 && !!this.getRefreshToken();
  }

  private setSession(tokenResponse: AuthTokenResponse): void {
    localStorage.setItem(this.tokenKey, tokenResponse.access_token);
    localStorage.setItem(this.refreshTokenKey, tokenResponse.refresh_token);
    localStorage.setItem(this.userKey, JSON.stringify(tokenResponse.user));
  }

  private clearLocalSession(): void {
    localStorage.removeItem(this.tokenKey);
    localStorage.removeItem(this.refreshTokenKey);
    localStorage.removeItem(this.userKey);
  }

  private getAccessToken(): string {
    return localStorage.getItem(this.tokenKey) || '';
  }

  private getRefreshToken(): string {
    return localStorage.getItem(this.refreshTokenKey) || '';
  }

  private authOptions(params?: Record<string, string | number>): {
    headers: HttpHeaders;
    params?: HttpParams;
  } {
    const token = this.getAccessToken();
    const headers = new HttpHeaders(token ? { Authorization: `Bearer ${token}` } : {});
    if (!params) {
      return { headers };
    }
    let httpParams = new HttpParams();
    Object.entries(params).forEach(([key, value]) => {
      httpParams = httpParams.set(key, String(value));
    });
    return { headers, params: httpParams };
  }
}
