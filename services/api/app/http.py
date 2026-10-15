"""Authenticated, tenant-scoped FastAPI v1 boundary."""

# ruff: noqa: B008 -- FastAPI dependency defaults are its declared injection mechanism.

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from gamo_ca.approvals import ApprovalError, ReviewerIdentity
from gamo_ca.events import EventReplayState, GraphChangeIdentity, GraphChangePayload
from gamo_ca.fingerprints import canonical, fingerprint
from gamo_ca.graph import Graph
from gamo_ca.models import Approval, ApprovalDecision, ChangeEvent
from gamo_ca.planner import Plan, PlanningError, Policy, plan_change
from pydantic import TypeAdapter
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from services.api.app.artifact_schemas import (
    DependencyVersion,
    ExecutionAttemptStartRequest,
    ExecutionTransitionRequest,
)
from services.api.app.artifact_store import (
    ArtifactConflict,
    ArtifactStoreError,
    ExecutionTransitionConflict,
    StaleArtifactSource,
    check_artifact_eligibility,
    create_artifact_version,
    create_execution_run,
    record_execution_transition,
    start_execution_attempt,
)
from services.api.app.auth import Principal, authenticate, get_session, require_membership
from services.api.app.event_store import (
    EventConflict,
    ProjectNotFound,
    StaleProjectRevision,
    append_approval,
    append_graph_change,
    create_project,
    load_current_graph,
    load_project,
)
from services.api.app.http_schemas import (
    ApprovalHistoryResponse,
    ApprovalRequest,
    ApprovalResponse,
    ArtifactCreateHttpRequest,
    ArtifactCreateResponse,
    ArtifactEligibilityResult,
    ArtifactResponse,
    ChangePlanRequest,
    ExecutionAttemptView,
    ExecutionEventView,
    ExecutionRunCreateHttpRequest,
    ExecutionRunView,
    ExecutionWriteResponse,
    GraphChangeRequest,
    GraphChangeResponse,
    GraphResponse,
    ProjectCreateRequest,
    ProjectResponse,
    RunHistoryResponse,
    TenantAccessResponse,
)
from services.api.app.models import (
    ApprovalRecord,
    ArtifactVersionRecord,
    ExecutionAttemptRecord,
    ExecutionEventRecord,
    ExecutionRunRecord,
    ProjectRecord,
    TenantMembershipRecord,
)

ALL_ROLES = {"tenant_admin", "producer", "editor", "reviewer", "researcher"}
WRITE_ROLES = {"tenant_admin", "producer", "editor"}
GRAPH_ROLES = {"producer", "editor", "reviewer"}


def _change_event(
    request: ChangePlanRequest, *, tenant_id: str, project_id: str, actor_id: str, graph: Any
) -> ChangeEvent:
    return ChangeEvent(
        id=request.event_id,
        tenant_id=tenant_id,
        project_id=project_id,
        created_at=graph.as_of,
        target_id=request.target_id,
        source_id=request.source_id,
        actor_id=actor_id,
        change_type=request.change_type,
        old_version=request.old_version,
        new_version=request.new_version,
        old_hash=request.old_hash,
        new_hash=request.new_hash,
        changed_fields=request.changed_fields,
        occurred_at=graph.as_of,
        expected_snapshot_hash=graph.snapshot_hash,
    )


def _plan(
    request: ChangePlanRequest, *, tenant_id: str, project_id: str, actor_id: str, graph: Any
) -> Plan:
    return plan_change(
        graph,
        _change_event(
            request, tenant_id=tenant_id, project_id=project_id, actor_id=actor_id, graph=graph
        ),
        Policy(),
    )


def _project_response(record: ProjectRecord) -> ProjectResponse:
    return ProjectResponse(
        tenant_id=record.tenant_id,
        project_id=record.project_id,
        revision=record.revision,
        current_graph_hash=record.current_graph_hash,
        current_snapshot_hash=record.current_snapshot_hash,
    )


def _artifact_response(record: ArtifactVersionRecord) -> ArtifactResponse:
    return ArtifactResponse(
        artifact_version_id=record.artifact_version_id,
        artifact_id=record.artifact_id,
        version=record.version,
        node_id=record.node_id,
        node_version=record.node_version,
        graph_revision=record.graph_revision,
        graph_snapshot_hash=record.graph_snapshot_hash,
        dependencies=tuple(DependencyVersion.model_validate(item) for item in record.dependencies),
        content=record.content,
        content_hash=record.content_hash,
        planner_decision=TypeAdapter(Plan).validate_python(record.planner_decision),
    )


def _authorize(
    session: Session, principal: Principal, tenant_id: str, roles: set[str]
) -> TenantMembershipRecord:
    return require_membership(session, principal=principal, tenant_id=tenant_id, roles=roles)


def create_app(engine: Engine | None = None) -> FastAPI:
    """Create an API app; tests may provide an isolated engine, deployments use DATABASE_URL."""
    db_engine = engine or create_engine(
        os.environ.get(
            "DATABASE_URL", "postgresql+psycopg://orcify:orcify-local-dev@localhost:5432/orcify"
        ),
        pool_pre_ping=True,
    )
    factory: Callable[[], Session] = sessionmaker(db_engine, expire_on_commit=False)
    app = FastAPI(
        title="Orcify API", version="1.0.0", description="Authenticated, tenant-scoped research API"
    )
    web_origins = [
        origin.strip()
        for origin in os.environ.get(
            "ORCIFY_WEB_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
        ).split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=web_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept"],
    )
    app.state.session_factory = factory

    @app.exception_handler(StaleProjectRevision)
    async def stale_revision_handler(request: Request, exc: Exception) -> JSONResponse:
        return _http_error(409, "project revision is stale")

    @app.exception_handler(EventConflict)
    @app.exception_handler(ArtifactConflict)
    @app.exception_handler(ExecutionTransitionConflict)
    @app.exception_handler(ArtifactStoreError)
    async def conflict_handler(request: Request, exc: Exception) -> JSONResponse:
        return _http_error(409, "request conflicts with current project state")

    @app.exception_handler(StaleArtifactSource)
    async def stale_artifact_handler(request: Request, exc: Exception) -> JSONResponse:
        return _http_error(409, "artifact source is stale")

    @app.exception_handler(ApprovalError)
    async def approval_handler(request: Request, exc: Exception) -> JSONResponse:
        return _http_error(409, "approval transition is invalid or stale")

    @app.exception_handler(PlanningError)
    async def planning_handler(request: Request, exc: Exception) -> JSONResponse:
        return _http_error(422, "change cannot be planned against current state")

    @app.exception_handler(ValueError)
    async def validation_domain_handler(request: Request, exc: Exception) -> JSONResponse:
        return _http_error(422, "request violates domain constraints")

    @app.get("/api/v1/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/tenants", response_model=list[TenantAccessResponse])
    def list_tenants_route(
        principal: Principal = Depends(authenticate),
        session: Session = Depends(get_session),
    ) -> list[TenantAccessResponse]:
        memberships = session.scalars(
            select(TenantMembershipRecord)
            .where(
                TenantMembershipRecord.actor_id == principal.actor_id,
                TenantMembershipRecord.revoked_at.is_(None),
            )
            .order_by(TenantMembershipRecord.tenant_id)
        ).all()
        return [TenantAccessResponse(tenant_id=row.tenant_id, role=row.role) for row in memberships]

    @app.post(
        "/api/v1/tenants/{tenant_id}/projects", response_model=ProjectResponse, status_code=201
    )
    def create_project_route(
        tenant_id: str,
        body: ProjectCreateRequest,
        principal: Principal = Depends(authenticate),
        session: Session = Depends(get_session),
    ) -> ProjectResponse:
        _authorize(session, principal, tenant_id, {"tenant_admin"})
        initial_graph = TypeAdapter(Graph).validate_python(body.initial_graph)
        if (initial_graph.tenant_id, initial_graph.project_id) != (
            tenant_id,
            body.project_id,
        ):
            raise HTTPException(422, "initial graph scope must match the requested project")
        state = EventReplayState.from_graph(initial_graph)
        session.rollback()
        record = create_project(
            session, tenant_id, body.project_id, state, initial_graph=initial_graph
        )
        return _project_response(record)

    @app.get("/api/v1/tenants/{tenant_id}/projects", response_model=list[ProjectResponse])
    def list_projects_route(
        tenant_id: str,
        principal: Principal = Depends(authenticate),
        session: Session = Depends(get_session),
    ) -> list[ProjectResponse]:
        _authorize(session, principal, tenant_id, ALL_ROLES)
        rows = session.scalars(
            select(ProjectRecord)
            .where(ProjectRecord.tenant_id == tenant_id)
            .order_by(ProjectRecord.project_id)
        ).all()
        return [_project_response(row) for row in rows]

    @app.get("/api/v1/tenants/{tenant_id}/projects/{project_id}", response_model=ProjectResponse)
    def get_project_route(
        tenant_id: str,
        project_id: str,
        principal: Principal = Depends(authenticate),
        session: Session = Depends(get_session),
    ) -> ProjectResponse:
        _authorize(session, principal, tenant_id, ALL_ROLES)
        return _project_response(_load_project_or_404(session, tenant_id, project_id))

    @app.get(
        "/api/v1/tenants/{tenant_id}/projects/{project_id}/graph", response_model=GraphResponse
    )
    def graph_route(
        tenant_id: str,
        project_id: str,
        principal: Principal = Depends(authenticate),
        session: Session = Depends(get_session),
    ) -> GraphResponse:
        _authorize(session, principal, tenant_id, ALL_ROLES)
        project = _load_project_or_404(session, tenant_id, project_id)
        return GraphResponse(
            revision=project.revision,
            snapshot_hash=project.current_graph_hash,
            graph=load_current_graph(session, tenant_id, project_id),
        )

    @app.post(
        "/api/v1/tenants/{tenant_id}/projects/{project_id}/graph-changes",
        response_model=GraphChangeResponse,
    )
    def graph_change_route(
        tenant_id: str,
        project_id: str,
        body: GraphChangeRequest,
        principal: Principal = Depends(authenticate),
        session: Session = Depends(get_session),
    ) -> GraphChangeResponse:
        membership = _project_access(session, principal, tenant_id, project_id, GRAPH_ROLES)
        snapshot = TypeAdapter(Graph).validate_python(body.snapshot)
        payload = GraphChangePayload(
            event_id=body.event_id,
            tenant_id=tenant_id,
            project_id=project_id,
            actor_id=principal.actor_id,
            occurred_at=snapshot.as_of,
            expected_revision=body.expected_revision,
            expected_snapshot_hash=body.expected_snapshot_hash,
            snapshot=snapshot,
        )
        identity = GraphChangeIdentity(
            principal.actor_id, tenant_id, project_id, membership.role, True
        )
        session.rollback()
        result = append_graph_change(
            session, change=payload, identity=identity, idempotency_key=body.idempotency_key
        )
        return GraphChangeResponse(
            event_id=result.receipt.event_id,
            revision=result.revision,
            snapshot_hash=result.snapshot_hash,
            replayed=result.replayed,
        )

    @app.post("/api/v1/tenants/{tenant_id}/projects/{project_id}/plans", response_model=Plan)
    def plan_route(
        tenant_id: str,
        project_id: str,
        body: ChangePlanRequest,
        principal: Principal = Depends(authenticate),
        session: Session = Depends(get_session),
    ) -> Plan:
        _project_access(session, principal, tenant_id, project_id, ALL_ROLES)
        graph = load_current_graph(session, tenant_id, project_id)
        return _plan(
            body,
            tenant_id=tenant_id,
            project_id=project_id,
            actor_id=principal.actor_id,
            graph=graph,
        )

    @app.post(
        "/api/v1/tenants/{tenant_id}/projects/{project_id}/approvals",
        status_code=201,
        response_model=ApprovalResponse,
    )
    def approval_route(
        tenant_id: str,
        project_id: str,
        body: ApprovalRequest,
        principal: Principal = Depends(authenticate),
        session: Session = Depends(get_session),
    ) -> ApprovalResponse:
        roles = (
            {"producer", "editor", "reviewer"}
            if body.decision == ApprovalDecision.SUBMITTED
            else {"reviewer"}
        )
        membership = _project_access(session, principal, tenant_id, project_id, roles)
        command = Approval(
            id=body.approval_id,
            tenant_id=tenant_id,
            project_id=project_id,
            created_at=datetime.now(UTC),
            asset_version_id=body.asset_version_id,
            asset_version=body.asset_version,
            requirement_fingerprint=body.requirement_fingerprint,
            actor_id=principal.actor_id,
            decision=body.decision,
            policy_version=body.policy_version,
            idempotency_key=body.idempotency_key,
            expected_revision=body.expected_revision,
            reason=body.reason,
            supersedes_id=body.supersedes_id,
        )
        prior = session.scalar(
            select(ApprovalRecord).where(
                ApprovalRecord.tenant_id == tenant_id,
                ApprovalRecord.project_id == project_id,
                ApprovalRecord.idempotency_key == body.idempotency_key,
            )
        )
        if prior is not None:
            payload = canonical(command)
            if not isinstance(payload, dict):
                raise TypeError("approval payload must serialize to an object")
            semantic_hash = fingerprint(
                {key: value for key, value in payload.items() if key != "created_at"}
            )
            if prior.payload_hash != semantic_hash:
                raise EventConflict("approval idempotency key has conflicting payload")
            approval = TypeAdapter(Approval).validate_python(prior.payload)
            return ApprovalResponse(approval=approval, replayed=True)
        graph = load_current_graph(session, tenant_id, project_id)
        plan = _plan(
            body.planning_event,
            tenant_id=tenant_id,
            project_id=project_id,
            actor_id=principal.actor_id,
            graph=graph,
        )
        identity = ReviewerIdentity(
            principal.actor_id, tenant_id, project_id, membership.role, True
        )
        session.rollback()
        result = append_approval(
            session, command=command, identity=identity, graph=graph, plan=plan
        )
        return ApprovalResponse(approval=result.latest, replayed=result.replayed)

    @app.get(
        "/api/v1/tenants/{tenant_id}/projects/{project_id}/approvals",
        response_model=ApprovalHistoryResponse,
    )
    def approval_history_route(
        tenant_id: str,
        project_id: str,
        principal: Principal = Depends(authenticate),
        session: Session = Depends(get_session),
    ) -> ApprovalHistoryResponse:
        _project_access(session, principal, tenant_id, project_id, ALL_ROLES)
        records = session.scalars(
            select(ApprovalRecord)
            .where(
                ApprovalRecord.tenant_id == tenant_id,
                ApprovalRecord.project_id == project_id,
            )
            .order_by(ApprovalRecord.revision, ApprovalRecord.id)
        ).all()
        return ApprovalHistoryResponse(
            approvals=tuple(TypeAdapter(Approval).validate_python(row.payload) for row in records)
        )

    @app.post(
        "/api/v1/tenants/{tenant_id}/projects/{project_id}/artifacts",
        status_code=201,
        response_model=ArtifactCreateResponse,
    )
    def create_artifact_route(
        tenant_id: str,
        project_id: str,
        body: ArtifactCreateHttpRequest,
        principal: Principal = Depends(authenticate),
        session: Session = Depends(get_session),
    ) -> ArtifactCreateResponse:
        _project_access(session, principal, tenant_id, project_id, WRITE_ROLES)
        graph = load_current_graph(session, tenant_id, project_id)
        computed = _plan(
            body.planning_event,
            tenant_id=tenant_id,
            project_id=project_id,
            actor_id=principal.actor_id,
            graph=graph,
        )
        if body.artifact.planner_decision != computed:
            raise HTTPException(409, "planner decision does not match authoritative plan")
        session.rollback()
        result = create_artifact_version(
            session, tenant_id=tenant_id, project_id=project_id, command=body.artifact
        )
        row = session.scalar(
            select(ArtifactVersionRecord).where(
                ArtifactVersionRecord.tenant_id == tenant_id,
                ArtifactVersionRecord.project_id == project_id,
                ArtifactVersionRecord.artifact_version_id == result.artifact_version_id,
            )
        )
        assert row is not None
        return ArtifactCreateResponse(artifact=_artifact_response(row), replayed=result.replayed)

    @app.get(
        "/api/v1/tenants/{tenant_id}/projects/{project_id}/artifacts",
        response_model=list[ArtifactResponse],
    )
    def list_artifacts_route(
        tenant_id: str,
        project_id: str,
        principal: Principal = Depends(authenticate),
        session: Session = Depends(get_session),
    ) -> list[ArtifactResponse]:
        _project_access(session, principal, tenant_id, project_id, ALL_ROLES)
        rows = session.scalars(
            select(ArtifactVersionRecord)
            .where(
                ArtifactVersionRecord.tenant_id == tenant_id,
                ArtifactVersionRecord.project_id == project_id,
            )
            .order_by(ArtifactVersionRecord.artifact_id, ArtifactVersionRecord.version)
        ).all()
        return [_artifact_response(row) for row in rows]

    @app.get(
        "/api/v1/tenants/{tenant_id}/projects/{project_id}/artifacts/{artifact_version_id}",
        response_model=ArtifactResponse,
    )
    def get_artifact_route(
        tenant_id: str,
        project_id: str,
        artifact_version_id: str,
        principal: Principal = Depends(authenticate),
        session: Session = Depends(get_session),
    ) -> ArtifactResponse:
        _project_access(session, principal, tenant_id, project_id, ALL_ROLES)
        row = session.scalar(
            select(ArtifactVersionRecord).where(
                ArtifactVersionRecord.tenant_id == tenant_id,
                ArtifactVersionRecord.project_id == project_id,
                ArtifactVersionRecord.artifact_version_id == artifact_version_id,
            )
        )
        if row is None:
            raise HTTPException(404, "resource not found")
        return _artifact_response(row)

    @app.get(
        "/api/v1/tenants/{tenant_id}/projects/{project_id}/artifacts/{artifact_version_id}/eligibility",
        response_model=ArtifactEligibilityResult,
    )
    def eligibility_route(
        tenant_id: str,
        project_id: str,
        artifact_version_id: str,
        principal: Principal = Depends(authenticate),
        session: Session = Depends(get_session),
    ) -> ArtifactEligibilityResult:
        _project_access(session, principal, tenant_id, project_id, ALL_ROLES)
        artifact = session.scalar(
            select(ArtifactVersionRecord).where(
                ArtifactVersionRecord.tenant_id == tenant_id,
                ArtifactVersionRecord.project_id == project_id,
                ArtifactVersionRecord.artifact_version_id == artifact_version_id,
            )
        )
        if artifact is None:
            raise HTTPException(404, "resource not found")
        session.rollback()
        return check_artifact_eligibility(
            session,
            tenant_id=tenant_id,
            project_id=project_id,
            artifact_version_id=artifact_version_id,
        )

    @app.post(
        "/api/v1/tenants/{tenant_id}/projects/{project_id}/runs",
        status_code=201,
        response_model=ExecutionWriteResponse,
    )
    def create_run_route(
        tenant_id: str,
        project_id: str,
        body: ExecutionRunCreateHttpRequest,
        principal: Principal = Depends(authenticate),
        session: Session = Depends(get_session),
    ) -> ExecutionWriteResponse:
        _project_access(session, principal, tenant_id, project_id, WRITE_ROLES)
        graph = load_current_graph(session, tenant_id, project_id)
        computed = _plan(
            body.planning_event,
            tenant_id=tenant_id,
            project_id=project_id,
            actor_id=principal.actor_id,
            graph=graph,
        )
        if body.run.planner_decision != computed:
            raise HTTPException(409, "planner decision does not match authoritative plan")
        session.rollback()
        result = create_execution_run(
            session, tenant_id=tenant_id, project_id=project_id, command=body.run
        )
        return ExecutionWriteResponse(
            run_id=result.run_id, status=result.status, replayed=result.replayed
        )

    @app.post(
        "/api/v1/tenants/{tenant_id}/projects/{project_id}/runs/{run_id}/attempts",
        status_code=201,
        response_model=ExecutionWriteResponse,
    )
    def start_attempt_route(
        tenant_id: str,
        project_id: str,
        run_id: str,
        body: ExecutionAttemptStartRequest,
        principal: Principal = Depends(authenticate),
        session: Session = Depends(get_session),
    ) -> ExecutionWriteResponse:
        _project_access(session, principal, tenant_id, project_id, WRITE_ROLES)
        if (
            session.scalar(
                select(ExecutionRunRecord.run_id).where(
                    ExecutionRunRecord.tenant_id == tenant_id,
                    ExecutionRunRecord.project_id == project_id,
                    ExecutionRunRecord.run_id == run_id,
                )
            )
            is None
        ):
            raise HTTPException(404, "resource not found")
        session.rollback()
        result = start_execution_attempt(
            session, tenant_id=tenant_id, project_id=project_id, run_id=run_id, command=body
        )
        return ExecutionWriteResponse(
            run_id=result.run_id, status=result.status, replayed=result.replayed
        )

    @app.post(
        "/api/v1/tenants/{tenant_id}/projects/{project_id}/runs/{run_id}/attempts/{attempt_id}/transitions",
        response_model=ExecutionWriteResponse,
    )
    def transition_route(
        tenant_id: str,
        project_id: str,
        run_id: str,
        attempt_id: str,
        body: ExecutionTransitionRequest,
        principal: Principal = Depends(authenticate),
        session: Session = Depends(get_session),
    ) -> ExecutionWriteResponse:
        _project_access(session, principal, tenant_id, project_id, WRITE_ROLES)
        if (
            session.scalar(
                select(ExecutionAttemptRecord.attempt_id).where(
                    ExecutionAttemptRecord.tenant_id == tenant_id,
                    ExecutionAttemptRecord.project_id == project_id,
                    ExecutionAttemptRecord.run_id == run_id,
                    ExecutionAttemptRecord.attempt_id == attempt_id,
                )
            )
            is None
        ):
            raise HTTPException(404, "resource not found")
        session.rollback()
        result = record_execution_transition(
            session,
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            attempt_id=attempt_id,
            command=body,
        )
        return ExecutionWriteResponse(
            run_id=result.run_id, status=result.status, replayed=result.replayed
        )

    @app.get(
        "/api/v1/tenants/{tenant_id}/projects/{project_id}/runs/{run_id}",
        response_model=RunHistoryResponse,
    )
    def run_history_route(
        tenant_id: str,
        project_id: str,
        run_id: str,
        principal: Principal = Depends(authenticate),
        session: Session = Depends(get_session),
    ) -> RunHistoryResponse:
        _project_access(session, principal, tenant_id, project_id, ALL_ROLES)
        run = session.scalar(
            select(ExecutionRunRecord).where(
                ExecutionRunRecord.tenant_id == tenant_id,
                ExecutionRunRecord.project_id == project_id,
                ExecutionRunRecord.run_id == run_id,
            )
        )
        if run is None:
            raise HTTPException(404, "resource not found")
        attempts = session.scalars(
            select(ExecutionAttemptRecord)
            .where(
                ExecutionAttemptRecord.tenant_id == tenant_id,
                ExecutionAttemptRecord.project_id == project_id,
                ExecutionAttemptRecord.run_id == run_id,
            )
            .order_by(ExecutionAttemptRecord.attempt_number)
        ).all()
        events = session.scalars(
            select(ExecutionEventRecord)
            .where(
                ExecutionEventRecord.tenant_id == tenant_id,
                ExecutionEventRecord.project_id == project_id,
                ExecutionEventRecord.run_id == run_id,
            )
            .order_by(ExecutionEventRecord.created_at, ExecutionEventRecord.id)
        ).all()
        return RunHistoryResponse(
            run=ExecutionRunView.model_validate(_record_dict(run, ExecutionRunView)),
            attempts=tuple(
                ExecutionAttemptView.model_validate(_record_dict(item, ExecutionAttemptView))
                for item in attempts
            ),
            events=tuple(
                ExecutionEventView.model_validate(_record_dict(item, ExecutionEventView))
                for item in events
            ),
        )

    return app


def _load_project_or_404(session: Session, tenant_id: str, project_id: str) -> ProjectRecord:
    try:
        return load_project(session, tenant_id, project_id)
    except ProjectNotFound as error:
        raise HTTPException(404, "resource not found") from error


def _project_access(
    session: Session, principal: Principal, tenant_id: str, project_id: str, roles: set[str]
) -> TenantMembershipRecord:
    _load_project_or_404(session, tenant_id, project_id)
    return _authorize(session, principal, tenant_id, roles)


def _record_dict(record: Any, schema: type[Any]) -> dict[str, object]:
    return {name: getattr(record, name) for name in schema.model_fields if hasattr(record, name)}


def _http_error(code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=code, content={"detail": detail})


app = create_app()
