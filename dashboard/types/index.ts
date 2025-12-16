/**
 * IT-Friends Handwerk Dashboard - TypeScript Types
 * Matches the backend phone-agent API models
 */

// ============================================================================
// Enums (matching backend workflows.py)
// ============================================================================

export type UrgencyLevel = "notfall" | "dringend" | "normal" | "routine";
export type TaskType =
  | "repairs"
  | "quotes"
  | "complaints"
  | "billing"
  | "appointment"
  | "general"
  | "spam"
  | "parts"
  | "callback";
export type TaskStatus = "new" | "assigned" | "in_progress" | "completed" | "cancelled";
export type SourceType = "phone" | "email" | "form" | "chat" | "whatsapp";
export type TradeCategory = "shk" | "elektro" | "sanitaer" | "general";

// ============================================================================
// Core Models
// ============================================================================

export interface Company {
  id: string;
  name: string;
  legal_name?: string;
  industry: string;
  trade_category?: TradeCategory;
  phone?: string;
  email?: string;
  website?: string;
  address_street?: string;
  address_zip?: string;
  address_city?: string;
  latitude?: number;
  longitude?: number;
  service_radius_km: number;
  plan: "starter" | "professional" | "enterprise";
  max_users: number;
  max_calls_per_month: number;
  settings_json?: CompanySettings;
  status: "active" | "suspended" | "inactive";
  created_at: string;
  updated_at: string;
}

export interface CompanySettings {
  branding?: {
    primary_color?: string;
    logo_url?: string;
  };
  email_intake?: {
    enabled: boolean;
    imap_host?: string;
    imap_port?: number;
    imap_user?: string;
    poll_interval_minutes?: number;
  };
  notifications?: {
    sms_enabled: boolean;
    email_enabled: boolean;
  };
}

export interface Department {
  id: string;
  tenant_id: string;
  name: string;
  description?: string;
  handles_task_types: TaskType[];
  handles_urgency_levels: UrgencyLevel[];
  phone?: string;
  email?: string;
  working_hours?: WorkingHours;
  is_active: boolean;
  created_at: string;
  // Computed fields
  worker_count?: number;
  open_tasks_count?: number;
}

export interface Worker {
  id: string;
  tenant_id: string;
  department_id?: string;
  first_name: string;
  last_name: string;
  role: "owner" | "admin" | "worker";
  phone?: string;
  email?: string;
  trade_categories: TradeCategory[];
  certifications?: string[];
  working_hours?: WorkingHours;
  max_tasks_per_day: number;
  is_active: boolean;
  created_at: string;
  // Computed fields
  department_name?: string;
  current_tasks_count?: number;
  full_name?: string;
}

export interface Task {
  id: string;
  tenant_id: string;
  job_number?: string;
  source_type: SourceType;
  source_id?: string;
  task_type: TaskType;
  urgency: UrgencyLevel;
  trade_category?: TradeCategory;
  customer_name?: string;
  customer_phone?: string;
  customer_email?: string;
  customer_address?: string;
  customer_plz?: string;
  title: string;
  description?: string;
  ai_summary?: string;
  attachments_json?: TaskAttachment[];
  latitude?: number;
  longitude?: number;
  distance_from_hq_km?: number;
  assigned_department_id?: string;
  assigned_worker_id?: string;
  routing_priority: number;
  routing_reason?: string;
  status: TaskStatus;
  due_date?: string;
  completed_at?: string;
  created_at: string;
  updated_at: string;
  // Computed/joined fields
  assigned_department_name?: string;
  assigned_worker_name?: string;
  history?: TaskHistoryEntry[];
}

export interface TaskAttachment {
  filename: string;
  content_type: string;
  size: number;
  url?: string;
}

export interface TaskHistoryEntry {
  id: string;
  task_id: string;
  action: string;
  actor_id?: string;
  actor_name?: string;
  details?: Record<string, unknown>;
  created_at: string;
}

export interface RoutingRule {
  id: string;
  tenant_id: string;
  name: string;
  priority: number;
  conditions: RoutingCondition;
  route_to_department_id?: string;
  route_to_worker_id?: string;
  escalate_after_minutes?: number;
  send_notification: boolean;
  is_active: boolean;
  created_at: string;
  // Computed fields
  route_to_department_name?: string;
  route_to_worker_name?: string;
}

export interface RoutingCondition {
  task_type?: TaskType | TaskType[];
  urgency?: UrgencyLevel | UrgencyLevel[];
  trade_category?: TradeCategory | TradeCategory[];
  customer_plz_starts_with?: string;
  time_of_day?: { start: string; end: string };
}

export interface WorkingHours {
  monday?: string;
  tuesday?: string;
  wednesday?: string;
  thursday?: string;
  friday?: string;
  saturday?: string;
  sunday?: string;
}

// ============================================================================
// Dashboard Statistics
// ============================================================================

export interface DashboardStats {
  total_tasks_today: number;
  open_tasks: number;
  open_emergencies: number;
  in_progress_tasks: number;
  completed_today: number;
  completion_rate: number;
  average_response_time_minutes: number;
  tasks_by_type: Record<TaskType, number>;
  tasks_by_urgency: Record<UrgencyLevel, number>;
  tasks_by_status: Record<TaskStatus, number>;
  tasks_by_source: Record<SourceType, number>;
  tasks_trend_7_days: { date: string; count: number }[];
}

export interface WorkerStats {
  worker_id: string;
  worker_name: string;
  tasks_assigned: number;
  tasks_completed: number;
  tasks_in_progress: number;
  average_completion_time_minutes: number;
  completion_rate: number;
}

// ============================================================================
// API Request/Response Types
// ============================================================================

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface TaskFilters {
  status?: TaskStatus[];
  urgency?: UrgencyLevel[];
  task_type?: TaskType[];
  trade_category?: TradeCategory[];
  source_type?: SourceType[];
  assigned_department_id?: string;
  assigned_worker_id?: string;
  search?: string;
  date_from?: string;
  date_to?: string;
}

export interface CreateTaskRequest {
  task_type: TaskType;
  urgency: UrgencyLevel;
  trade_category?: TradeCategory;
  customer_name?: string;
  customer_phone?: string;
  customer_email?: string;
  customer_address?: string;
  customer_plz?: string;
  title: string;
  description?: string;
  source_type: SourceType;
}

export interface UpdateTaskRequest {
  status?: TaskStatus;
  assigned_department_id?: string;
  assigned_worker_id?: string;
  urgency?: UrgencyLevel;
  due_date?: string;
  notes?: string;
}

export interface CreateDepartmentRequest {
  name: string;
  description?: string;
  handles_task_types: TaskType[];
  handles_urgency_levels: UrgencyLevel[];
  phone?: string;
  email?: string;
  working_hours?: WorkingHours;
}

export interface CreateWorkerRequest {
  first_name: string;
  last_name: string;
  department_id?: string;
  role: "owner" | "admin" | "worker";
  phone?: string;
  email?: string;
  trade_categories: TradeCategory[];
  certifications?: string[];
  working_hours?: WorkingHours;
  max_tasks_per_day?: number;
}

export interface CreateRoutingRuleRequest {
  name: string;
  priority: number;
  conditions: RoutingCondition;
  route_to_department_id?: string;
  route_to_worker_id?: string;
  escalate_after_minutes?: number;
  send_notification?: boolean;
}

// ============================================================================
// UI Helper Types
// ============================================================================

export interface SelectOption<T = string> {
  value: T;
  label: string;
}

export interface TableColumn<T> {
  key: keyof T | string;
  header: string;
  sortable?: boolean;
  width?: string;
  render?: (item: T) => React.ReactNode;
}

// German labels for UI
export const URGENCY_LABELS: Record<UrgencyLevel, string> = {
  notfall: "Notfall",
  dringend: "Dringend",
  normal: "Normal",
  routine: "Routine",
};

export const TASK_TYPE_LABELS: Record<TaskType, string> = {
  repairs: "Reparatur",
  quotes: "Angebot",
  complaints: "Reklamation",
  billing: "Rechnung",
  appointment: "Termin",
  general: "Allgemein",
  spam: "Spam",
  parts: "Materialanfrage",
  callback: "Rückruf",
};

export const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  new: "Neu",
  assigned: "Zugewiesen",
  in_progress: "In Bearbeitung",
  completed: "Erledigt",
  cancelled: "Storniert",
};

export const SOURCE_TYPE_LABELS: Record<SourceType, string> = {
  phone: "Telefon",
  email: "E-Mail",
  form: "Formular",
  chat: "Chat",
  whatsapp: "WhatsApp",
};

export const TRADE_CATEGORY_LABELS: Record<TradeCategory, string> = {
  shk: "SHK (Heizung/Sanitär/Klima)",
  elektro: "Elektro",
  sanitaer: "Sanitär",
  general: "Allgemein",
};

// ============================================================================
// Job Creation Types (for Handwerk dashboard)
// ============================================================================

export interface CreateHandwerkJobRequest {
  title: string;
  description?: string;
  trade_category: TradeCategory;
  urgency: UrgencyLevel;
  customer_name?: string;
  customer_phone?: string;
  customer_email?: string;
  address_street?: string;
  address_number?: string;
  address_zip?: string;
  address_city?: string;
  property_type?: "residential" | "commercial" | "industrial";
  access_notes?: string;
  preferred_date?: string;
  preferred_time_window?: "morning" | "afternoon" | "evening" | "any";
  customer_notes?: string;
}

// ============================================================================
// Triage Assessment Types
// ============================================================================

export interface TriageRequest {
  free_text?: string;
  issues?: TriageIssue[];
  customer_context?: TriageCustomerContext;
}

export interface TriageIssue {
  description: string;
  category: string;
  severity: number;
  is_recurring: boolean;
  affects_safety: boolean;
}

export interface TriageCustomerContext {
  is_commercial: boolean;
  is_elderly: boolean;
  has_children: boolean;
  property_type: string;
  has_maintenance_contract: boolean;
}

export interface TriageResponse {
  urgency: UrgencyLevel;
  urgency_display: string;
  risk_score: number;
  primary_concern: string;
  recommended_action: string;
  trade_category: TradeCategory;
  is_emergency: boolean;
  max_wait_hours: number | null;
  requires_specialist: boolean;
  requires_permit: boolean;
  assessment_notes: string[];
  extracted_issues: TriageIssue[];
}

// ============================================================================
// Technician Matching Types
// ============================================================================

export interface TechnicianSearchRequest {
  trade_category: TradeCategory;
  urgency?: UrgencyLevel;
  certifications?: string[];
  location_zip?: string;
}

export interface TechnicianMatch {
  id: string;
  name: string;
  first_name: string;
  last_name: string;
  qualification: string;
  trade_categories: TradeCategory[];
  certifications: string[];
  current_workload: number;
  max_workload: number;
  availability_today: boolean;
  next_available_slot?: string;
  distance_km?: number;
  match_score: number;
  phone?: string;
  email?: string;
}

// ============================================================================
// Scheduling Types
// ============================================================================

export interface TimeSlotSearchRequest {
  job_type?: string;
  trade_category?: TradeCategory;
  urgency_max_wait_hours?: number;
  preferred_days?: number[];
  preferred_time_of_day?: "morning" | "afternoon" | "evening";
  technician_id?: string;
}

export interface TimeSlot {
  id: string;
  date: string;
  time_start: string;
  time_end: string;
  technician_id?: string;
  technician_name?: string;
  is_preferred: boolean;
  is_emergency_slot: boolean;
}

export interface BookAppointmentRequest {
  slot_id: string;
  job_id: string;
  customer_notes?: string;
  send_confirmation_sms?: boolean;
  send_confirmation_email?: boolean;
}

// ============================================================================
// Job History & Notes Types
// ============================================================================

export interface JobNote {
  id: string;
  job_id: string;
  author_id?: string;
  author_name?: string;
  content: string;
  note_type: "internal" | "customer" | "technician" | "system";
  created_at: string;
}

export interface AddJobNoteRequest {
  content: string;
  note_type?: "internal" | "customer" | "technician";
}

// ============================================================================
// Additional German Labels
// ============================================================================

export const PROPERTY_TYPE_LABELS: Record<string, string> = {
  residential: "Wohngebäude",
  commercial: "Gewerbe",
  industrial: "Industrie",
};

export const TIME_WINDOW_LABELS: Record<string, string> = {
  morning: "Vormittags (8-12 Uhr)",
  afternoon: "Nachmittags (12-17 Uhr)",
  evening: "Abends (17-20 Uhr)",
  any: "Flexibel",
};

export const NOTE_TYPE_LABELS: Record<string, string> = {
  internal: "Intern",
  customer: "Kunde",
  technician: "Techniker",
  system: "System",
};
