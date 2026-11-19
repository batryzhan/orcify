import type {
  Budgets,
  ClearBoardResponse,
  ReportRecord,
  ContractData,
  DocumentInfo,
  HealthResponse,
  IssueCreate,
  IssueUpdate,
  JiraBoard,
  JiraIssue,
  McpServerHealth,
  PostRecord,
  SendPostResponse,
  TaskCreatedResponse,
  TaskCreateRequest,
  TelegramStatus,
  TemplateInfo,
  ValidationErrorResponse,
} from "../types/api";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly validation: ValidationErrorResponse | null,
  ) {
    super(`HTTP ${status}`);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    let validation: ValidationErrorResponse | null = null;
    if (response.status === 422) {
      validation = (await response.json()) as ValidationErrorResponse;
    }
    throw new ApiError(response.status, validation);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) });

export const api = {
  health: () => request<HealthResponse>("/api/health"),
  mcpHealth: () => request<McpServerHealth[]>("/api/health/mcp"),
  createTask: (body: TaskCreateRequest) => request<TaskCreatedResponse>("/api/tasks", json("POST", body)),
  renderContract: (body: ContractData) => request<DocumentInfo>("/api/legal/contracts", json("POST", body)),

  board: () => request<JiraBoard>("/api/jira/board"),
  createIssue: (body: IssueCreate) => request<JiraIssue>("/api/jira/issues", json("POST", body)),
  updateIssue: (key: string, body: IssueUpdate) => request<JiraIssue>(`/api/jira/issues/${key}`, json("PATCH", body)),
  deleteIssue: (key: string) => request<void>(`/api/jira/issues/${key}`, { method: "DELETE" }),

  postTemplates: () => request<TemplateInfo[]>("/api/posts/templates"),
  posts: () => request<PostRecord[]>("/api/posts"),
  sendPostToTelegram: (postId: string) => request<SendPostResponse>(`/api/posts/${postId}/telegram`, { method: "POST" }),
  telegramStatus: () => request<TelegramStatus>("/api/telegram/status"),
  clearBoard: (scope: "done" | "all") => request<ClearBoardResponse>("/api/jira/clear", json("POST", { scope })),

  budgets: () => request<Budgets>("/api/finance/budgets"),
  saveBudgets: (body: Budgets) => request<Budgets>("/api/finance/budgets", json("PUT", body)),
  reports: () => request<ReportRecord[]>("/api/finance/reports"),
  deleteReport: (id: string) => request<void>(`/api/finance/reports/${id}`, { method: "DELETE" }),
  sendReportToTelegram: (id: string) =>
    request<SendPostResponse>(`/api/finance/reports/${id}/telegram`, { method: "POST" }),
};
