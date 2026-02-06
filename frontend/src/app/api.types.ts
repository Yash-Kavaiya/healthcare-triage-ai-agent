export interface DepartmentScore {
  department: string;
  score: number;
}

export interface AuthLoginRequest {
  username: string;
  password: string;
}

export interface AuthUser {
  username: string;
  role: 'operations' | 'nurse' | 'admin';
  full_name?: string | null;
  password_change_required: boolean;
}

export interface AuthTokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: 'bearer';
  expires_in: number;
  refresh_expires_in: number;
  user: AuthUser;
}

export interface AuthChangePasswordRequest {
  current_password: string;
  new_password: string;
}

export interface TriageResult {
  redacted_symptoms: string;
  urgency: 'EMERGENCY' | 'URGENT' | 'SOON' | 'ROUTINE';
  confidence: number;
  red_flags: string[];
  department_candidates: DepartmentScore[];
  suggested_department: string;
  rationale: string;
  recommended_timeframe_minutes: number;
  human_routing_flag: boolean;
}

export interface RoutingDecision {
  action: 'AUTO_BOOK' | 'QUEUE_REVIEW' | 'ESCALATE';
  reason: string;
  confidence_threshold: number;
  department_threshold: number;
}

export interface AppointmentResult {
  status: string;
  appointment_id?: number | null;
  slot_id?: number | null;
  slot_start?: string | null;
  note: string;
  preempted_appointment_id?: number | null;
}

export interface IntakeRequest {
  phone?: string | null;
  age: number;
  sex: string;
  symptoms: string;
  auto_book_high_urgency: boolean;
  always_route_when_model_requests_human: boolean;
}

export interface IntakeResponse {
  patient_id: number;
  triage_event_id: number;
  triage_result: TriageResult;
  routing_decision: RoutingDecision;
  appointment_result?: AppointmentResult | null;
  queue_id?: number | null;
}

export interface QueueItem {
  id: number;
  status: string;
  priority: string;
  reason: string;
  created_at: string;
  triage_event_id: number;
  urgency: string;
  confidence: number;
  suggested_department: string;
  rationale: string;
  patient_id: number;
  phone?: string | null;
  age: number;
  sex: string;
  symptoms: string;
}

export interface QueueListResponse {
  items: QueueItem[];
}

export interface QueueBookRequest {
  nurse_name: string;
  department_override?: string | null;
  urgency_override?: 'EMERGENCY' | 'URGENT' | 'SOON' | 'ROUTINE' | null;
  note: string;
}

export interface QueueBookResponse {
  queue_id: number;
  appointment_result: AppointmentResult;
}

export interface DashboardMetrics {
  repeat_patients_in_slots: number;
  total_slots: number;
  available_slots: number;
  booked_slots: number;
  slot_utilization_percent: number;
  pending_queue: number;
  pending_high_priority_queue: number;
  total_appointments: number;
  auto_booked_appointments: number;
  preempted_appointments: number;
  triage_events_24h: number;
  urgent_cases_24h: number;
  avg_confidence_24h: number;
}

export interface DashboardAppointmentsResponse {
  items: Array<Record<string, unknown>>;
}

export interface DashboardActivityResponse {
  items: Array<Record<string, unknown>>;
}

export interface AuditResponse {
  role: 'operations' | 'nurse' | 'admin';
  triage: Array<Record<string, unknown>>;
  audit_log: Array<Record<string, unknown>>;
}
