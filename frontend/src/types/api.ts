// Зеркало Pydantic-схем backend/app/schemas/*. Меняются только вместе.

export type Domain = "Legal" | "SMM" | "Finance" | "HR";

export interface IntentClassificationResult {
  domain: Domain;
  confidence: number;
  reasoning: string;
}

export type Currency = "KZT" | "USD" | "EUR" | "RUB";

/** ContractEntitiesSchema: null = значение не найдено в тексте. Decimal приходит строкой. */
export interface ContractEntities {
  client_name: string | null;
  bin_iin: string | null;
  contract_amount: string | null;
  currency: Currency | null;
  deadline_date: string | null;
  scope_of_work: string | null;
}

export type ContractField = keyof ContractEntities;

/** ContractData: тело POST /api/legal/contracts. */
export interface ContractData {
  client_name: string;
  bin_iin: string;
  contract_amount: string;
  currency: Currency;
  deadline_date: string;
  scope_of_work: string;
}

export interface DocumentInfo {
  document_id: string;
  filename: string;
  download_url: string;
  sha256: string;
  size_bytes: number;
}

export type LegalOutcome = "rendered" | "needs_input";

export interface LegalResult {
  outcome: LegalOutcome;
  entities: ContractEntities;
  missing_fields: ContractField[];
  invalid_fields: ContractField[];
  document?: DocumentInfo;
}

// --- Privacy (schemas/privacy.py) ---

export type PiiCategory = "PERSON" | "COMPANY" | "ADDRESS" | "IIN" | "BIN" | "PHONE" | "EMAIL" | "IBAN" | "CARD";

export interface AnonymizationReport {
  entities_total: number;
  by_category: Partial<Record<PiiCategory, number>>;
  llm_detection_used: boolean;
  leaked_count: number;
}

// --- Finance (schemas/finance.py) ---

export interface MonthlyFlow {
  month: string;
  income: number;
  expense: number;
  net: number;
}

export interface CategoryTotal {
  category: string;
  amount: number;
  share: number;
}

export interface CounterpartyTotal {
  name: string;
  amount: number;
  count: number;
}

export interface CashGap {
  start: string;
  end: string;
  days: number;
  min_balance: number;
}

export interface Anomaly {
  date: string;
  amount: number;
  counterparty: string | null;
  category: string | null;
  score: number;
}

export interface FinanceMetrics {
  rows: number;
  period_start: string;
  period_end: string;
  currency: string | null;
  total_income: number;
  total_expense: number;
  net: number;
  opening_balance: number;
  closing_balance: number;
  monthly: MonthlyFlow[];
  expense_by_category: CategoryTotal[];
  top_income_counterparties: CounterpartyTotal[];
  top_expense_counterparties: CounterpartyTotal[];
  cash_gaps: CashGap[];
  anomalies: Anomaly[];
  columns_detected: Record<string, string>;
  warnings: string[];
}

export type RiskLevel = "low" | "medium" | "high";

export interface FinanceRisk {
  title: string;
  level: RiskLevel;
  detail: string;
}

export interface FinanceReport {
  headline: string;
  key_findings: string[];
  risks: FinanceRisk[];
  recommendations: string[];
}

export interface FinanceResult {
  metrics: FinanceMetrics;
  report: FinanceReport | null;
  report_error_code: string | null;
  document: DocumentInfo | null;
  mcp_latency_ms: number;
}

// --- SMM (schemas/smm.py) ---

export interface Scene {
  scene_no: number;
  duration_s: number;
  visual: string;
  voiceover: string;
  on_screen_text: string;
}

export interface VideoScript {
  title: string;
  goal: string;
  target_audience: string;
  aspect_ratio: "9:16" | "16:9" | "1:1";
  duration_s: number;
  scenes: Scene[];
  video_prompt: string;
  hashtags: string[];
}

export interface VideoOutcome {
  status: "generated" | "storyboard";
  url?: string | null;
  error_code?: string | null;
  latency_ms: number;
}

export interface TrackerOutcome {
  status: "created" | "queued";
  issue_key?: string | null;
  queued_id?: string | null;
  error_code?: string | null;
}

export interface SmmResult {
  script: VideoScript;
  external_prompt: string;
  anonymization: AnonymizationReport;
  video: VideoOutcome;
  tracker: TrackerOutcome;
  storyboard: DocumentInfo;
}

export interface TaskResult {
  intent: IntentClassificationResult;
  low_confidence: boolean;
  legal?: LegalResult;
  finance?: FinanceResult;
  smm?: SmmResult;
}

export type TaskStatus =
  | "classifying_intent"
  | "routing_smm"
  | "routing_finance"
  | "anonymizing_pii"
  | "analyzing"
  | "extracting_entities"
  | "rendering_docx"
  | "analyzing_csv"
  | "generating_report"
  | "generating_video"
  | "creating_jira_issue"
  | "completed"
  | "failed";

export interface ErrorInfo {
  code: string;
  message: string;
}

export interface ProgressEvent {
  status: TaskStatus;
  progress: number;
  /** Домен известен после Этапа 1 Smart Routing и приходит во всех следующих событиях. */
  domain?: Domain;
  message?: string;
  anonymization?: AnonymizationReport;
  result?: TaskResult;
  error?: ErrorInfo;
}

export interface TaskAttachment {
  filename: string;
  media_type: "text/csv";
  content: string;
}

export interface TaskCreateRequest {
  text: string;
  attachment?: TaskAttachment;
  opening_balance?: number;
}

export interface McpServerHealth {
  name: string;
  domains: Domain[];
  is_external: boolean;
  enabled: boolean;
  reachable: boolean;
  tools: string[];
  error_code: string | null;
}

export interface TaskCreatedResponse {
  task_id: string;
  events_url: string;
}

export interface LLMHealth {
  reachable: boolean;
  model?: string | null;
  loaded?: boolean | null;
  context_length?: number | null;
  latency_ms: number;
  error_code?: string | null;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  llm: LLMHealth;
}

/** Ошибка валидации FastAPI (422). */
export interface ValidationErrorItem {
  loc: (string | number)[];
  msg: string;
  type: string;
}

export interface ValidationErrorResponse {
  detail: ValidationErrorItem[];
}

export const TERMINAL_STATUSES: ReadonlySet<TaskStatus> = new Set<TaskStatus>(["completed", "failed"]);

const ALL_STATUSES: ReadonlySet<string> = new Set<TaskStatus>([
  "classifying_intent",
  "routing_smm",
  "routing_finance",
  "anonymizing_pii",
  "analyzing",
  "extracting_entities",
  "rendering_docx",
  "analyzing_csv",
  "generating_report",
  "generating_video",
  "creating_jira_issue",
  "completed",
  "failed",
]);

export function isProgressEvent(value: unknown): value is ProgressEvent {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return typeof v.status === "string" && ALL_STATUSES.has(v.status) && typeof v.progress === "number";
}
