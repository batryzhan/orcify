import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowDownRight,
  ArrowRight,
  Check,
  ChevronDown,
  CircleHelp,
  Clock3,
  Command,
  FileCheck2,
  Fingerprint,
  GitBranch,
  KeyRound,
  Layers3,
  LoaderCircle,
  LogOut,
  RefreshCw,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  ApiError,
  createApi,
  type Approval,
  type Artifact,
  type GraphNode,
  type Plan,
  type TenantAccess,
} from "../api/client";
import { Badge, Button, SectionLabel } from "../components/ui";
import { GraphCanvas } from "../graph/GraphCanvas";
import { nodeKind, nodeTitle } from "../graph/model";

function Login({ onLogin }: { onLogin: (token: string) => void }) {
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const tryLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const candidate = token.trim();
    if (!candidate) return;
    setBusy(true);
    setError("");
    try {
      const api = createApi(candidate);
      await api.tenants();
      onLogin(candidate);
      setToken("");
    } catch (cause) {
      setError(
        cause instanceof ApiError && cause.status === 401
          ? "That credential is invalid, expired, or revoked."
          : cause instanceof Error
            ? cause.message
            : "The API could not be reached.",
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <main className="login-page">
      <div className="login-decoration" />
      <section className="login-card">
        <div className="brand-lockup">
          <div className="brand-mark">
            <Command size={21} />
          </div>
          <span>
            orcify<span className="brand-period">.</span>
          </span>
        </div>
        <div className="login-eyebrow">OPTIONAL LOCAL API CONNECTION</div>
        <h1>Explore a stored project.</h1>
        <p className="login-copy">
          Connect to the existing research API to inspect an authorized
          PostgreSQL snapshot. The presentation demo does not require this
          connection.
        </p>
        <form onSubmit={tryLogin} className="login-form">
          <label htmlFor="access-token">Development access token</label>
          <div className="token-input">
            <KeyRound size={16} />
            <input
              id="access-token"
              type="password"
              autoComplete="off"
              spellCheck={false}
              value={token}
              onChange={(event) => setToken(event.target.value)}
              placeholder="Paste a server-provisioned bearer token"
              required
            />
          </div>
          {error && (
            <div className="form-error" role="alert">
              <AlertCircle size={15} />
              {error}
            </div>
          )}
          <Button type="submit" disabled={busy}>
            {busy ? (
              <>
                <LoaderCircle className="spin" size={16} /> Verifying access…
              </>
            ) : (
              <>
                Continue securely <ArrowRight size={16} />
              </>
            )}
          </Button>
        </form>
        <div className="token-note">
          <ShieldCheck size={15} />
          <span>
            Credential stays in this tab’s memory and is cleared when you sign
            out.
          </span>
        </div>
        <div className="login-footer">
          <span>Orcify 2.0</span>
          <span>Read-only workspace</span>
          <span>API-backed access</span>
        </div>
      </section>
      <div className="login-side-note">
        <span>GAMO-CA</span> Change-aware orchestration with human authority.
      </div>
    </main>
  );
}

function apiError(error: unknown): string {
  if (error instanceof ApiError && error.status === 401)
    return "Your credential expired or was revoked. Sign in again.";
  if (error instanceof ApiError && error.status === 404)
    return "This resource is no longer available to your account.";
  if (error instanceof ApiError && error.status === 409)
    return "The project changed while this view was open. Refresh the authoritative snapshot.";
  if (error instanceof ApiError && error.status === 422)
    return "The proposed change does not satisfy the planner’s current preconditions.";
  if (error instanceof Error) return error.message;
  return "The API request failed. Try again.";
}

function Loading({ label }: { label: string }) {
  return (
    <div className="state-panel">
      <LoaderCircle className="spin" size={20} />
      <span>{label}</span>
    </div>
  );
}

function Failure({ error, retry }: { error: unknown; retry: () => void }) {
  return (
    <div className="state-panel error-panel">
      <div className="state-icon">
        <AlertCircle size={18} />
      </div>
      <div>
        <strong>Couldn’t load authoritative data</strong>
        <p>{apiError(error)}</p>
        <Button variant="secondary" onClick={retry}>
          <RefreshCw size={14} /> Retry
        </Button>
      </div>
    </div>
  );
}

function initialTenant(tenants: TenantAccess[]): string {
  return tenants[0]?.tenant_id ?? "";
}

function sha256Text(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(JSON.stringify(text));
  return crypto.subtle
    .digest("SHA-256", bytes)
    .then((digest) =>
      Array.from(new Uint8Array(digest), (byte) =>
        byte.toString(16).padStart(2, "0"),
      ).join(""),
    );
}

function latestApproval(
  approvals: Approval[],
  artifact: Artifact,
): Approval | undefined {
  return [...approvals]
    .filter(
      (approval) =>
        approval.asset_version_id === artifact.node_id &&
        approval.asset_version === artifact.node_version,
    )
    .sort(
      (left, right) =>
        Date.parse(right.created_at) - Date.parse(left.created_at),
    )[0];
}

function AppWorkspace({
  token,
  onSignOut,
}: {
  token: string;
  onSignOut: () => void;
}) {
  const queryClient = useQueryClient();
  const api = useMemo(() => createApi(token), [token]);
  const [tenantId, setTenantId] = useState("");
  const [projectId, setProjectId] = useState("");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [targetId, setTargetId] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [proposedText, setProposedText] = useState("");
  const [plan, setPlan] = useState<Plan | null>(null);
  const tenants = useQuery({ queryKey: ["tenants"], queryFn: api.tenants });
  const projects = useQuery({
    queryKey: ["projects", tenantId],
    queryFn: () => api.projects(tenantId),
    enabled: Boolean(tenantId),
  });
  const project = projects.data?.find((item) => item.project_id === projectId);
  const graphQuery = useQuery({
    queryKey: ["graph", tenantId, projectId],
    queryFn: () => api.graph(tenantId, projectId),
    enabled: Boolean(project),
  });
  const artifactsQuery = useQuery({
    queryKey: ["artifacts", tenantId, projectId],
    queryFn: () => api.artifacts(tenantId, projectId),
    enabled: Boolean(project),
  });
  const approvalsQuery = useQuery({
    queryKey: ["approvals", tenantId, projectId],
    queryFn: () => api.approvals(tenantId, projectId),
    enabled: Boolean(project),
  });
  const graph = graphQuery.data?.graph;
  const artifacts = artifactsQuery.data ?? [];
  const approvals = approvalsQuery.data?.approvals ?? [];
  const eligibilityQueries = useQueries({
    queries: artifacts.map((artifact) => ({
      queryKey: [
        "eligibility",
        tenantId,
        projectId,
        artifact.artifact_version_id,
      ],
      queryFn: () =>
        api.eligibility(tenantId, projectId, artifact.artifact_version_id),
      enabled: Boolean(project),
    })),
  });
  const requirements =
    graph?.nodes.filter(
      (node) => "status" in node && node.status === "CONFIRMED",
    ) ?? [];
  const confirmedEvidence =
    graph?.nodes.filter(
      (node) => "extracted_span" in node && Boolean(node.confirmed_by),
    ) ?? [];
  const selectedNode =
    graph?.nodes.find((node) => node.id === selectedNodeId) ?? null;

  useEffect(() => {
    if (!tenantId && tenants.data?.length)
      setTenantId(initialTenant(tenants.data));
  }, [tenantId, tenants.data]);
  useEffect(() => {
    if (
      projects.data?.length &&
      !projects.data.some((item) => item.project_id === projectId)
    ) {
      setProjectId(projects.data[0]?.project_id ?? "");
    }
  }, [projectId, projects.data]);
  useEffect(() => {
    if (graph && !graph.nodes.some((node) => node.id === selectedNodeId))
      setSelectedNodeId(graph.nodes[0]?.id ?? null);
  }, [graph, selectedNodeId]);
  const planMutation = useMutation({
    onMutate: () => setPlan(null),
    mutationFn: async () => {
      const graphState = graphQuery.data;
      const target = graphState?.graph.nodes.find(
        (node) => node.id === targetId,
      );
      if (!graphState || !target || !sourceId || !proposedText.trim())
        throw new Error(
          "Choose a confirmed target and evidence, then enter a proposed value.",
        );
      const source = graphState.graph.nodes.find(
        (node) => node.id === sourceId,
      );
      if (!source || !("confirmed_by" in source) || !source.confirmed_by)
        throw new Error(
          "Planning requires confirmed evidence from the current graph.",
        );
      const [oldHash, newHash] = await Promise.all([
        sha256Text(target.content),
        sha256Text(proposedText),
      ]);
      return api.plan(tenantId, projectId, {
        event_id: crypto.randomUUID(),
        target_id: target.id,
        source_id: sourceId,
        change_type: "CONTENT_REVISION",
        old_version: target.version,
        new_version: target.version + 1,
        old_hash: oldHash,
        new_hash: newHash,
        changed_fields: ["content"],
      });
    },
    onSuccess: (result) => setPlan(result),
  });

  const signOut = () => {
    queryClient.clear();
    onSignOut();
  };
  const allErrors = [
    tenants.error,
    projects.error,
    graphQuery.error,
    artifactsQuery.error,
    approvalsQuery.error,
    ...eligibilityQueries.map((query) => query.error),
  ].filter(Boolean);
  if (
    allErrors.some((error) => error instanceof ApiError && error.status === 401)
  ) {
    return (
      <main className="session-expired">
        <div>
          <ShieldCheck size={24} />
          <h2>Access needs to be renewed</h2>
          <p>
            Your credential expired or was revoked. Sign in with a newly
            provisioned token.
          </p>
          <Button onClick={signOut}>Return to secure sign in</Button>
        </div>
      </main>
    );
  }

  return (
    <div className="workspace">
      <header className="topbar">
        <div className="brand-lockup compact">
          <div className="brand-mark">
            <Command size={18} />
          </div>
          <span>
            orcify<span className="brand-period">.</span>
          </span>
        </div>
        <div className="top-divider" />
        <div className="crumb">
          <span>Workspace</span>
          <ChevronDown size={13} />
          <strong>Graph & impact</strong>
        </div>
        <div className="top-actions">
          <Badge className="read-only-badge">
            <span className="status-dot" /> Read only
          </Badge>
          <button className="user-chip" onClick={signOut} title="Sign out">
            <span className="avatar">O</span>
            <span>Sign out</span>
            <LogOut size={14} />
          </button>
        </div>
      </header>
      <div className="workspace-body">
        <aside className="sidebar">
          <div className="sidebar-section">
            <SectionLabel>Workspace</SectionLabel>
            <button className="sidebar-link active">
              <GitBranch size={16} /> Graph explorer{" "}
              <span className="sidebar-active-mark" />
            </button>
          </div>
          <div className="scope-card">
            <SectionLabel>Authorized scope</SectionLabel>
            {tenants.isPending ? (
              <Loading label="Checking membership…" />
            ) : tenants.isError ? (
              <Failure
                error={tenants.error}
                retry={() => void tenants.refetch()}
              />
            ) : tenants.data?.length ? (
              <>
                <label className="field-label" htmlFor="tenant-choice">
                  Tenant
                </label>
                <div className="select-wrap">
                  <select
                    id="tenant-choice"
                    value={tenantId}
                    onChange={(event) => {
                      setTenantId(event.target.value);
                      setProjectId("");
                      setPlan(null);
                    }}
                    aria-label="Tenant"
                  >
                    {tenants.data.map((tenant) => (
                      <option key={tenant.tenant_id} value={tenant.tenant_id}>
                        {tenant.tenant_id}
                      </option>
                    ))}
                  </select>
                  <ChevronDown size={15} />
                </div>
                <div className="tenant-role">
                  <ShieldCheck size={13} />{" "}
                  {tenants.data
                    .find((item) => item.tenant_id === tenantId)
                    ?.role.replaceAll("_", " ")}
                </div>
                <label
                  className="field-label project-label"
                  htmlFor="project-choice"
                >
                  Project
                </label>
                {projects.isPending ? (
                  <div className="select-placeholder">
                    <LoaderCircle className="spin" size={14} /> Loading
                    projects…
                  </div>
                ) : projects.isError ? (
                  <Failure
                    error={projects.error}
                    retry={() => void projects.refetch()}
                  />
                ) : projects.data?.length ? (
                  <div className="select-wrap">
                    <select
                      id="project-choice"
                      value={projectId}
                      onChange={(event) => {
                        setProjectId(event.target.value);
                        setPlan(null);
                      }}
                      aria-label="Project"
                    >
                      {projects.data.map((item) => (
                        <option key={item.project_id} value={item.project_id}>
                          {item.project_id}
                        </option>
                      ))}
                    </select>
                    <ChevronDown size={15} />
                  </div>
                ) : (
                  <div className="empty-scope">
                    No projects are available to this membership.
                  </div>
                )}
              </>
            ) : (
              <div className="empty-scope">
                No active tenant memberships were found for this credential.
              </div>
            )}
          </div>
          <div className="sidebar-spacer" />
          <div className="sidebar-foot">
            <div className="connection-row">
              <span className="status-dot" />{" "}
              {allErrors.length
                ? "API needs attention"
                : tenants.isPending
                  ? "Checking API…"
                  : "API authenticated"}
            </div>
            <span className="sidebar-version">
              Orcify 2.0 · Explorer preview
            </span>
          </div>
        </aside>

        <main className="main-content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">PROJECT INTELLIGENCE</div>
              <h1>Graph & impact</h1>
              <p>Understand dependencies before making a change.</p>
            </div>
            {project && (
              <div className="revision-card">
                <div className="revision-icon">
                  <Fingerprint size={17} />
                </div>
                <div>
                  <span>Authoritative revision</span>
                  <strong>r{project.revision}</strong>
                </div>
                <span className="revision-separator" />
                <div>
                  <span>Snapshot</span>
                  <strong className="hash-short">
                    {project.current_snapshot_hash.slice(0, 10)}
                  </strong>
                </div>
              </div>
            )}
          </div>
          {!tenantId || !projectId ? (
            <div className="welcome-panel">
              <div className="welcome-icon">
                <Layers3 />
              </div>
              <h2>Select an authorized project</h2>
              <p>
                Choose a tenant and project from your active server-side
                memberships.
              </p>
            </div>
          ) : graphQuery.isPending ? (
            <Loading label="Loading PostgreSQL snapshot…" />
          ) : graphQuery.isError ? (
            <Failure
              error={graphQuery.error}
              retry={() => void graphQuery.refetch()}
            />
          ) : graph ? (
            <>
              <div className="explorer-grid">
                <section className="canvas-column">
                  <div className="canvas-toolbar">
                    <div className="canvas-title">
                      <span className="live-indicator" />
                      <strong>{projectId}</strong>
                      <span className="toolbar-divider" />
                      <span>{graph.nodes.length} nodes</span>
                      <span className="toolbar-dot">·</span>
                      <span>
                        {
                          graph.edges.filter((edge) => edge.valid_to === null)
                            .length
                        }{" "}
                        dependencies
                      </span>
                    </div>
                    <div
                      className={`snapshot-pill ${graphQuery.isStale ? "snapshot-stale" : ""}`}
                    >
                      <Clock3 size={13} /> Snapshot {graphQuery.data.revision}
                      {graphQuery.isStale ? " · refresh to confirm" : ""}{" "}
                      <span className="fresh-dot" />
                    </div>
                  </div>
                  <GraphCanvas
                    graph={graph}
                    selectedId={selectedNodeId}
                    onSelect={(node) => setSelectedNodeId(node.id)}
                  />
                  <section className="impact-card">
                    <div className="impact-heading">
                      <div className="impact-title-icon">
                        <Sparkles size={16} />
                      </div>
                      <div>
                        <h2>Impact preview</h2>
                        <p>
                          Ask GAMO-CA how a proposed change could affect this
                          graph.
                        </p>
                      </div>
                      <Badge className="preview-badge">Preview only</Badge>
                    </div>
                    <form
                      className="impact-form"
                      onSubmit={(event) => {
                        event.preventDefault();
                        planMutation.mutate();
                      }}
                    >
                      <div className="impact-selects">
                        <label>
                          <span>Proposed target</span>
                          <div className="select-wrap">
                            <select
                              value={targetId}
                              onChange={(event) =>
                                setTargetId(event.target.value)
                              }
                              aria-label="Proposed target"
                            >
                              <option value="">
                                Choose a confirmed requirement
                              </option>
                              {requirements.map((node) => (
                                <option key={node.id} value={node.id}>
                                  {nodeTitle(node)}
                                </option>
                              ))}
                            </select>
                            <ChevronDown size={14} />
                          </div>
                        </label>
                        <label>
                          <span>Confirmed evidence</span>
                          <div className="select-wrap">
                            <select
                              value={sourceId}
                              onChange={(event) =>
                                setSourceId(event.target.value)
                              }
                              aria-label="Confirmed evidence"
                            >
                              <option value="">Choose evidence source</option>
                              {confirmedEvidence.map((node) => (
                                <option key={node.id} value={node.id}>
                                  {node.id}
                                </option>
                              ))}
                            </select>
                            <ChevronDown size={14} />
                          </div>
                        </label>
                      </div>
                      <label
                        className="proposal-label"
                        htmlFor="proposed-change"
                      >
                        <span>Proposed value</span>
                        <textarea
                          id="proposed-change"
                          value={proposedText}
                          onChange={(event) =>
                            setProposedText(event.target.value)
                          }
                          placeholder="Describe the proposed requirement text…"
                          rows={2}
                        />
                      </label>
                      <div className="impact-actions">
                        <span>
                          <ShieldCheck size={14} /> Planning does not change
                          project data.
                        </span>
                        <Button
                          type="submit"
                          disabled={
                            planMutation.isPending ||
                            !targetId ||
                            !sourceId ||
                            !proposedText.trim()
                          }
                        >
                          {planMutation.isPending ? (
                            <>
                              <LoaderCircle className="spin" size={15} />{" "}
                              Analyzing…
                            </>
                          ) : (
                            <>
                              Analyze impact <ArrowDownRight size={15} />
                            </>
                          )}
                        </Button>
                      </div>
                    </form>
                    {planMutation.isError && (
                      <div className="plan-error" role="alert">
                        <AlertCircle size={14} />
                        {apiError(planMutation.error)}
                      </div>
                    )}
                    {plan && <PlanResults plan={plan} />}
                  </section>
                </section>
                <aside className="inspector">
                  <div className="inspector-header">
                    <div>
                      <SectionLabel>Inspector</SectionLabel>
                      <h2>
                        {selectedNode
                          ? nodeKind(selectedNode)
                          : "Project details"}
                      </h2>
                    </div>
                    <button
                      className="icon-button"
                      title="Refresh authoritative project data"
                      aria-label="Refresh authoritative project data"
                      onClick={() => {
                        setPlan(null);
                        void Promise.all([
                          graphQuery.refetch(),
                          artifactsQuery.refetch(),
                          approvalsQuery.refetch(),
                        ]);
                        void queryClient.invalidateQueries({
                          queryKey: ["eligibility", tenantId, projectId],
                        });
                      }}
                    >
                      <RefreshCw size={15} />
                    </button>
                  </div>
                  {selectedNode ? (
                    <NodeInspector node={selectedNode} graph={graph} />
                  ) : (
                    <p className="muted-copy">
                      Select a node to inspect its authoritative version and
                      provenance.
                    </p>
                  )}
                  <div className="inspector-divider" />
                  <div className="artifact-section">
                    <div className="artifact-section-heading">
                      <SectionLabel>Artifact eligibility</SectionLabel>
                      <span className="artifact-count">{artifacts.length}</span>
                    </div>
                    {artifactsQuery.isPending ? (
                      <div className="inline-state">
                        <LoaderCircle className="spin" size={14} /> Loading
                        artifact records…
                      </div>
                    ) : artifactsQuery.isError ? (
                      <div className="inline-error">
                        {apiError(artifactsQuery.error)}
                      </div>
                    ) : artifacts.length ? (
                      <div className="artifact-list">
                        {artifacts.map((artifact, index) => {
                          const approval = latestApproval(approvals, artifact);
                          return (
                            <ArtifactRow
                              key={artifact.artifact_version_id}
                              artifact={artifact}
                              {...(approval ? { approval } : {})}
                              approvalLoading={approvalsQuery.isPending}
                              approvalError={approvalsQuery.isError}
                              eligibility={
                                eligibilityQueries[index]?.data ?? null
                              }
                              eligibilityError={
                                eligibilityQueries[index]?.isError ?? false
                              }
                              loading={
                                eligibilityQueries[index]?.isPending ?? false
                              }
                            />
                          );
                        })}
                      </div>
                    ) : (
                      <p className="muted-copy small">
                        No immutable artifact versions have been recorded.
                      </p>
                    )}
                    {approvalsQuery.isError && (
                      <div className="inline-error">
                        Approval history unavailable:{" "}
                        {apiError(approvalsQuery.error)}
                      </div>
                    )}
                  </div>
                  <div className="inspector-foot">
                    <ShieldCheck size={14} />
                    <span>
                      Eligibility comes from current PostgreSQL state. Graph
                      projection is not consulted.
                    </span>
                  </div>
                </aside>
              </div>
            </>
          ) : null}
        </main>
      </div>
    </div>
  );
}

export function NodeInspector({
  node,
  graph,
}: {
  node: GraphNode;
  graph: import("../api/client").Graph;
}) {
  const kind = nodeKind(node);
  const upstream = graph.edges.filter(
    (edge) => edge.dependent_id === node.id && edge.valid_to === null,
  );
  const downstream = graph.edges.filter(
    (edge) => edge.upstream_id === node.id && edge.valid_to === null,
  );
  return (
    <div className="node-inspector">
      <div className="inspected-title">
        <h3>{nodeTitle(node)}</h3>
        <Badge>v{node.version}</Badge>
      </div>
      <div className="inspected-id">{node.id}</div>
      <div className="metadata-grid">
        <div>
          <span>Type</span>
          <strong>{kind}</strong>
        </div>
        <div>
          <span>Version</span>
          <strong>v{node.version}</strong>
        </div>
        <div>
          <span>Valid from</span>
          <strong>{new Date(node.valid_from).toLocaleString()}</strong>
        </div>
        <div>
          <span>Provider</span>
          <strong>
            {"provider" in node ? node.provider : "Human / source"}
          </strong>
        </div>
      </div>
      {"status" in node && (
        <div className="requirement-state">
          <div className="detail-label">Requirement state</div>
          <Badge
            className={
              node.status === "CONFIRMED"
                ? "state-confirmed"
                : "state-unconfirmed"
            }
          >
            <span className="status-dot" />
            {node.status}
          </Badge>
          {node.confirmed_by && (
            <span className="confirmed-by">
              Confirmed by {node.confirmed_by}
            </span>
          )}
        </div>
      )}
      {"confirmed_by" in node && (
        <div className="requirement-state">
          <div className="detail-label">Evidence provenance</div>
          <Badge
            className={
              node.confirmed_by ? "state-confirmed" : "state-unconfirmed"
            }
          >
            <span className="status-dot" />
            {node.confirmed_by ? "Confirmed" : "Unconfirmed"}
          </Badge>
          {node.confirmed_by && (
            <span className="confirmed-by">{node.confirmed_by}</span>
          )}
        </div>
      )}
      {"source_id" in node && (
        <div className="detail-block">
          <div className="detail-label">Source record</div>
          <div className="evidence-link">
            <FileCheck2 size={13} />
            {node.source_id}
          </div>
        </div>
      )}
      {"extracted_span" in node && (
        <div className="detail-block">
          <div className="detail-label">Extracted evidence span</div>
          <div className="content-preview">{node.extracted_span}</div>
        </div>
      )}
      <div className="detail-block">
        <div className="detail-label">Content</div>
        <div className="content-preview">{node.content}</div>
      </div>
      {"model_version" in node &&
        (node.provider !== "none" ||
          node.model_version !== "none" ||
          node.prompt_version !== "none") && (
          <div className="detail-block">
            <div className="detail-label">Generation provenance</div>
            <div className="provenance-lines">
              <span>
                Provider <strong>{node.provider}</strong>
              </span>
              <span>
                Model <strong>{node.model_version}</strong>
              </span>
              <span>
                Prompt <strong>{node.prompt_version}</strong>
              </span>
              <span>
                Policy <strong>{node.policy_version}</strong>
              </span>
            </div>
          </div>
        )}
      <div className="detail-block">
        <div className="detail-label">
          Dependencies <span>{upstream.length}</span>
        </div>
        {upstream.length ? (
          upstream.map((edge) => (
            <div className="dependency-row" key={edge.id}>
              <span className={`edge-mark ${edge.strength.toLowerCase()}`} />
              <span>{edge.upstream_id}</span>
              <Badge>{edge.strength}</Badge>
            </div>
          ))
        ) : (
          <div className="muted-copy small">No upstream dependencies.</div>
        )}
      </div>
      <div className="detail-block">
        <div className="detail-label">
          Downstream <span>{downstream.length}</span>
        </div>
        {downstream.length ? (
          downstream.map((edge) => (
            <div className="dependency-row" key={edge.id}>
              <ArrowRight size={13} />
              <span>{edge.dependent_id}</span>
              <Badge>{edge.strength}</Badge>
            </div>
          ))
        ) : (
          <div className="muted-copy small">No downstream dependencies.</div>
        )}
      </div>
      {"evidence_ids" in node && node.evidence_ids.length > 0 && (
        <div className="detail-block">
          <div className="detail-label">Evidence links</div>
          {node.evidence_ids.map((id) => (
            <div className="evidence-link" key={id}>
              <FileCheck2 size={13} />
              {id}
            </div>
          ))}
        </div>
      )}
      {"inputs" in node && node.inputs.length > 0 && (
        <div className="detail-block">
          <div className="detail-label">Consumed input versions</div>
          {node.inputs.map((input) => (
            <div className="input-version" key={input.source_id}>
              <span>
                {input.source_id} · v{input.version}
              </span>
              <code>{input.content_hash.slice(0, 12)}</code>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function ArtifactRow({
  artifact,
  approval,
  approvalLoading,
  approvalError,
  eligibility,
  eligibilityError,
  loading,
}: {
  artifact: Artifact;
  approval?: Approval;
  approvalLoading: boolean;
  approvalError: boolean;
  eligibility: {
    artifact_version_id: string;
    eligible: boolean;
    reasons: string[];
  } | null;
  eligibilityError: boolean;
  loading: boolean;
}) {
  const state =
    approval?.decision ??
    (approvalError
      ? "UNAVAILABLE"
      : approvalLoading
        ? "CHECKING APPROVAL"
        : "NO APPROVAL");
  return (
    <div className="artifact-row">
      <div className="artifact-icon">
        <FileCheck2 size={15} />
      </div>
      <div className="artifact-main">
        <div className="artifact-name">
          {artifact.artifact_id}
          <span>v{artifact.version}</span>
        </div>
        <div className="artifact-sub">
          Node {artifact.node_id} · v{artifact.node_version} ·{" "}
          {artifact.content_hash.slice(0, 10)}
        </div>
        {approval && (
          <div
            className="approval-binding"
            title={`Requirement snapshot ${approval.requirement_fingerprint}`}
          >
            <span>
              Exact v{approval.asset_version} · {approval.actor_id}
            </span>
            <code>
              req {approval.requirement_fingerprint.slice(0, 10)} ·{" "}
              {approval.policy_version}
            </code>
          </div>
        )}
        <div className="artifact-statuses">
          <Badge
            className={`approval-${state.toLowerCase().replaceAll(" ", "-")}`}
          >
            {state}
          </Badge>
          {loading ? (
            <Badge className="eligibility-pending">
              <LoaderCircle className="spin" size={11} />
              Checking
            </Badge>
          ) : eligibilityError || !eligibility ? (
            <Badge className="eligibility-pending">Unavailable</Badge>
          ) : (
            <Badge className={eligibility.eligible ? "eligible" : "ineligible"}>
              {eligibility.eligible ? "Eligible" : "Blocked"}
            </Badge>
          )}
        </div>
        {eligibility && !eligibility.eligible && (
          <div className="eligibility-reasons">
            {eligibility.reasons.map((reason) => (
              <span key={reason}>{reason}</span>
            ))}
          </div>
        )}
        {eligibilityError && (
          <div className="eligibility-reasons">
            Eligibility could not be verified from the API.
          </div>
        )}
      </div>
    </div>
  );
}

export function PlanResults({ plan }: { plan: Plan }) {
  const decisions = [...plan.decisions].sort(
    (a, b) =>
      ["BLOCK", "REVIEW", "RECOMPUTE", "KEEP"].indexOf(a.action) -
      ["BLOCK", "REVIEW", "RECOMPUTE", "KEEP"].indexOf(b.action),
  );
  return (
    <div className="plan-results">
      <div className="plan-results-heading">
        <div>
          <div className="detail-label">GAMO-CA plan</div>
          <span className="plan-hash">{plan.plan_hash.slice(0, 12)}</span>
        </div>
        <Badge className="simulated-badge">Deterministic preview</Badge>
      </div>
      <div className="decision-summary">
        {["RECOMPUTE", "REVIEW", "KEEP", "BLOCK"].map((action) => (
          <div
            className={`decision-count count-${action.toLowerCase()}`}
            key={action}
          >
            <span>{action}</span>
            <strong>
              {plan.decisions.filter((item) => item.action === action).length}
            </strong>
          </div>
        ))}
      </div>
      <div className="decision-list">
        {decisions.map((decision) => (
          <div className="decision-row" key={decision.node_id}>
            <span
              className={`decision-symbol decision-${decision.action.toLowerCase()}`}
            >
              {decision.action === "KEEP" ? (
                <Check size={12} />
              ) : decision.action === "RECOMPUTE" ? (
                <RefreshCw size={12} />
              ) : decision.action === "REVIEW" ? (
                <CircleHelp size={12} />
              ) : (
                <AlertCircle size={12} />
              )}
            </span>
            <div className="decision-copy">
              <div>
                <strong>{decision.node_id}</strong>
                <Badge className={`action-${decision.action.toLowerCase()}`}>
                  {decision.action}
                </Badge>
              </div>
              <p>{decision.reasons.join(" · ")}</p>
            </div>
          </div>
        ))}
      </div>
      <div className="plan-footnote">
        <ShieldCheck size={14} />
        <span>
          KEEP is a reuse decision only; it does not grant approval or
          publication eligibility.
        </span>
      </div>
    </div>
  );
}

export function App() {
  const [token, setToken] = useState<string | null>(null);
  if (!token) return <Login onLogin={setToken} />;
  return <AppWorkspace token={token} onSignOut={() => setToken(null)} />;
}
