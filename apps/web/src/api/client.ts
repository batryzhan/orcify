import createClient from "openapi-fetch";
import type { components, paths } from "./generated";

export type TenantAccess = components["schemas"]["TenantAccessResponse"];
export type Project = components["schemas"]["ProjectResponse"];
export type GraphResponse = components["schemas"]["GraphResponse"];
export type Graph = components["schemas"]["Graph"];
export type GraphNode = components["schemas"]["Node"];
export type DependencyEdge = components["schemas"]["DependencyEdge"];
export type ChangePlanRequest = components["schemas"]["ChangePlanRequest"];
export type Plan = components["schemas"]["Plan-Output"];
export type Artifact = components["schemas"]["ArtifactResponse"];
export type Approval = components["schemas"]["Approval"];
export type Eligibility = components["schemas"]["ArtifactEligibilityResult"];

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const apiBase = import.meta.env.VITE_API_BASE_URL?.trim() ?? "";

function errorMessage(value: unknown, fallback: string): string {
  if (
    typeof value === "object" &&
    value !== null &&
    "detail" in value &&
    typeof value.detail === "string"
  ) {
    return value.detail;
  }
  return fallback;
}

export function createApi(token: string) {
  const client = createClient<paths>({
    baseUrl: apiBase || window.location.origin,
  });
  client.use({
    onRequest({ request }) {
      request.headers.set("Authorization", `Bearer ${token}`);
      request.headers.set("Accept", "application/json");
      return request;
    },
  });

  async function unwrap<T>(
    response: Promise<{ data?: T; error?: unknown; response: Response }>,
  ): Promise<T> {
    const result = await response;
    if (!result.response.ok || result.data === undefined) {
      throw new ApiError(
        result.response.status,
        errorMessage(
          result.error,
          `API request failed (${result.response.status})`,
        ),
      );
    }
    return result.data;
  }

  return {
    tenants: () => unwrap(client.GET("/api/v1/tenants")),
    projects: (tenantId: string) =>
      unwrap(
        client.GET("/api/v1/tenants/{tenant_id}/projects", {
          params: { path: { tenant_id: tenantId } },
        }),
      ),
    graph: (tenantId: string, projectId: string) =>
      unwrap(
        client.GET("/api/v1/tenants/{tenant_id}/projects/{project_id}/graph", {
          params: { path: { tenant_id: tenantId, project_id: projectId } },
        }),
      ),
    artifacts: (tenantId: string, projectId: string) =>
      unwrap(
        client.GET(
          "/api/v1/tenants/{tenant_id}/projects/{project_id}/artifacts",
          {
            params: { path: { tenant_id: tenantId, project_id: projectId } },
          },
        ),
      ),
    approvals: (tenantId: string, projectId: string) =>
      unwrap(
        client.GET(
          "/api/v1/tenants/{tenant_id}/projects/{project_id}/approvals",
          {
            params: { path: { tenant_id: tenantId, project_id: projectId } },
          },
        ),
      ),
    plan: (tenantId: string, projectId: string, body: ChangePlanRequest) =>
      unwrap(
        client.POST("/api/v1/tenants/{tenant_id}/projects/{project_id}/plans", {
          params: { path: { tenant_id: tenantId, project_id: projectId } },
          body,
        }),
      ),
    eligibility: (tenantId: string, projectId: string, artifactId: string) =>
      unwrap(
        client.GET(
          "/api/v1/tenants/{tenant_id}/projects/{project_id}/artifacts/{artifact_version_id}/eligibility",
          {
            params: {
              path: {
                tenant_id: tenantId,
                project_id: projectId,
                artifact_version_id: artifactId,
              },
            },
          },
        ),
      ),
  };
}

export type Api = ReturnType<typeof createApi>;
