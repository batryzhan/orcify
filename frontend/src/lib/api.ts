import type {
  ContractData,
  DocumentInfo,
  HealthResponse,
  McpServerHealth,
  TaskCreatedResponse,
  TaskCreateRequest,
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
  return (await response.json()) as T;
}

export const api = {
  health: () => request<HealthResponse>("/api/health"),
  mcpHealth: () => request<McpServerHealth[]>("/api/health/mcp"),
  createTask: (body: TaskCreateRequest) =>
    request<TaskCreatedResponse>("/api/tasks", { method: "POST", body: JSON.stringify(body) }),
  renderContract: (body: ContractData) =>
    request<DocumentInfo>("/api/legal/contracts", { method: "POST", body: JSON.stringify(body) }),
};
