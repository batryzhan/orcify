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

export interface ForecastPoint {
  month: string;
  income: number;
  expense: number;
  net: number;
  balance: number;
}

export interface CategoryChange {
  category: string;
  previous: number;
  current: number;
  change: number;
  change_pct: number | null;
}

export interface MonthComparison {
  previous_month: string;
  current_month: string;
  income_previous: number;
  income_current: number;
  expense_previous: number;
  expense_current: number;
  categories: CategoryChange[];
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
  forecast: ForecastPoint[];
  forecast_basis_months: number;
  month_over_month: MonthComparison | null;
  budget_month: string | null;
  last_month_by_category: CategoryTotal[];
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

export interface BudgetItem {
  category: string;
  limit: number;
}

export interface Budgets {
  items: BudgetItem[];
}

export interface BudgetCheck {
  category: string;
  limit: number;
  spent: number;
  remaining: number;
  ratio: number;
  over: boolean;
}

export interface ReportFile {
  report_id: string;
  filename: string;
  download_url: string;
  sha256: string;
  size_bytes: number;
}

export interface ReportRecord {
  file: ReportFile;
  created_at: string;
  period_start: string;
  period_end: string;
  rows: number;
  net: number;
  closing_balance: number;
  headline: string | null;
  issue_key: string | null;
}

export interface FinanceResult {
  metrics: FinanceMetrics;
  report: FinanceReport | null;
  report_error_code: string | null;
  report_file: ReportFile | null;
  budget_checks: BudgetCheck[];
  mcp_latency_ms: number;
}

// --- Orcify Jira (schemas/jira.py) ---

export type IssueStatus = "todo" | "in_progress" | "review" | "done";
export type IssueType = "task" | "story" | "bug" | "epic";
export type IssuePriority = "highest" | "high" | "medium" | "low";

export interface IssueAttachment {
  kind: "post" | "document" | "report";
  title: string;
  url: string;
}

export interface JiraIssue {
  key: string;
  summary: string;
  description: string;
  status: IssueStatus;
  type: IssueType;
  priority: IssuePriority;
  labels: string[];
  story_points: number | null;
  assignee: string | null;
  domain: Domain | null;
  task_id: string | null;
  parent_key: string | null;
  attachments: IssueAttachment[];
  created_at: string;
  updated_at: string;
}

export interface BoardColumn {
  status: IssueStatus;
  title: string;
}

export interface JiraBoard {
  project_key: string;
  project_name: string;
  columns: BoardColumn[];
  issues: JiraIssue[];
}

export interface IssueCreate {
  summary: string;
  description?: string;
  status?: IssueStatus;
  type?: IssueType;
  priority?: IssuePriority;
  labels?: string[];
  story_points?: number;
  assignee?: string;
}

export interface IssueUpdate {
  summary?: string;
  description?: string;
  status?: IssueStatus;
  type?: IssueType;
  priority?: IssuePriority;
  labels?: string[];
  story_points?: number;
  assignee?: string;
}

export interface ClearBoardResponse {
  removed: number;
}

// --- Awesome Posts (schemas/smm.py) ---

export type PostTemplate = "cosmos" | "neon" | "summit";

export interface PostCopy {
  template: PostTemplate;
  kicker: string | null;
  headline: string;
  headline_accent: string;
  subtitle: string;
  cta: string | null;
  handle: string;
  caption: string;
  hashtags: string[];
}

export interface RenderedPost {
  post_id: string;
  template: PostTemplate;
  image_url: string;
  width: number;
  height: number;
  sha256: string;
  size_bytes: number;
  render_ms: number;
  created_at: string;
}

export interface PostResult {
  content: PostCopy;
  post: RenderedPost;
  template_forced: boolean;
}

export interface PostRecord {
  post: RenderedPost;
  content: PostCopy;
  issue_key: string | null;
}

export interface TemplateInfo {
  id: PostTemplate;
  title: string;
  use_case: string;
  background_url: string;
  preview_url: string;
  credit: string;
}

// --- HR (schemas/hr.py) ---

export interface PlannedIssue {
  summary: string;
  description: string;
  type: IssueType;
  priority: IssuePriority;
  story_points: number;
  assignee_role: string;
}

export interface HrResult {
  plan: { epic: string; issues: PlannedIssue[] };
  issue_keys: string[];
}

// --- Telegram (schemas/telegram.py) ---

export interface TelegramStatus {
  configured: boolean;
  polling: boolean;
  bot_username: string | null;
  bot_name: string | null;
  linked_chats: number;
  handled_messages: number;
  completed_runs: number;
  last_error: string | null;
}

export interface SendPostResponse {
  sent: number;
  linked_chats: number;
}

export interface TaskResult {
  intent: IntentClassificationResult;
  low_confidence: boolean;
  issue_key?: string;
  legal?: LegalResult;
  finance?: FinanceResult;
  smm?: PostResult;
  hr?: HrResult;
}

export type TaskStatus =
  | "classifying_intent"
  | "creating_jira_issue"
  | "updating_jira"
  | "routing_smm"
  | "routing_finance"
  | "extracting_entities"
  | "rendering_docx"
  | "analyzing_csv"
  | "generating_report"
  | "rendering_pdf"
  | "writing_copy"
  | "rendering_post"
  | "planning_tasks"
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
  /** Снимок карточки Orcify Jira после создания/переноса — по нему анимируется рой агентов. */
  issue?: JiraIssue;
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
  post_template?: PostTemplate;
  /** Домен задаёт окно интерфейса; без него домен определяет Smart Router. */
  domain?: Domain;
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
  "creating_jira_issue",
  "updating_jira",
  "routing_smm",
  "routing_finance",
  "extracting_entities",
  "rendering_docx",
  "analyzing_csv",
  "generating_report",
  "rendering_pdf",
  "writing_copy",
  "rendering_post",
  "planning_tasks",
  "completed",
  "failed",
]);

export function isProgressEvent(value: unknown): value is ProgressEvent {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return typeof v.status === "string" && ALL_STATUSES.has(v.status) && typeof v.progress === "number";
}
