from collections.abc import Iterator
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256

import pytest
from gamo_ca.approvals import ReviewerIdentity
from gamo_ca.events import EventReplayState
from gamo_ca.fingerprints import requirement_fingerprint
from gamo_ca.fixtures import NOW, change_event, toy_graph
from gamo_ca.models import Approval, ApprovalDecision, AssetVersion
from gamo_ca.planner import Policy, plan_change
from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from services.api.app.artifact_schemas import (
    ArtifactCreateRequest,
    DependencyVersion,
    ExecutionAttemptStartRequest,
    ExecutionMetric,
    ExecutionRunCreateRequest,
    ExecutionTransitionRequest,
    MetricStatus,
    ProvenanceInput,
)
from services.api.app.artifact_store import (
    ArtifactConflict,
    ExecutionTransitionConflict,
    StaleArtifactSource,
    check_artifact_eligibility,
    create_artifact_version,
    create_execution_run,
    record_execution_transition,
    start_execution_attempt,
)
from services.api.app.event_store import append_approval, append_graph_change, create_project
from services.api.app.models import (
    ArtifactProvenanceRecord,
    ArtifactVersionRecord,
    Base,
    ExecutionAttemptRecord,
    ExecutionEventRecord,
    ExecutionRunRecord,
    ImmutableRecordMutation,
)


@pytest.fixture
def db_engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, record) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def session(db_engine: Engine) -> Iterator[Session]:
    with Session(db_engine) as db:
        yield db


def setup_project(session: Session) -> tuple[str, str, object]:
    graph = toy_graph()
    create_project(
        session,
        graph.tenant_id,
        graph.project_id,
        EventReplayState.from_graph(graph),
        initial_graph=graph,
    )
    return graph.tenant_id, graph.project_id, graph


def artifact_command(graph, *, idempotency_key="artifact-key", version_id="artifact-version-1"):
    asset = next(node for node in graph.nodes if isinstance(node, AssetVersion))
    return ArtifactCreateRequest(
        artifact_version_id=version_id,
        artifact_id="creative-copy",
        node_id=asset.id,
        node_version=asset.version,
        expected_project_revision=0,
        graph_revision=0,
        graph_snapshot_hash=graph.snapshot_hash,
        dependencies=tuple(
            DependencyVersion(
                node_id=reference.source_id,
                node_version=reference.version,
                content_hash=reference.content_hash,
            )
            for reference in asset.inputs
        ),
        content=asset.content,
        planner_decision=plan_change(graph, change_event("note", graph), Policy()),
        idempotency_key=idempotency_key,
        provider_id="mock",
        model_id="fixture-v1",
        provenance=(
            ProvenanceInput(
                provenance_id=f"provenance-{version_id}",
                source_kind="graph_node",
                source_id=asset.inputs[0].source_id,
                details={"reason": "captured input"},
            ),
        ),
    )


def run_command(graph):
    return ExecutionRunCreateRequest(
        run_id="run-1",
        expected_project_revision=0,
        graph_revision=0,
        graph_snapshot_hash=graph.snapshot_hash,
        planner_decision=plan_change(graph, change_event("note", graph), Policy()),
        idempotency_key="run-key",
    )


def attempt_command(graph, number=1, attempt_id="attempt-1", key="attempt-key"):
    asset = next(node for node in graph.nodes if isinstance(node, AssetVersion))
    return ExecutionAttemptStartRequest(
        attempt_id=attempt_id,
        node_id=asset.id,
        attempt_number=number,
        dependencies=tuple(
            DependencyVersion(
                node_id=reference.source_id,
                node_version=reference.version,
                content_hash=reference.content_hash,
            )
            for reference in asset.inputs
        ),
        idempotency_key=key,
        provider_id="mock",
        model_id="fixture-v1",
        prompt_version="prompt-fixture-v1",
    )


def test_artifact_version_is_immutable_idempotent_and_snapshot_bound(session: Session) -> None:
    tenant_id, project_id, graph = setup_project(session)
    command = artifact_command(graph)
    first = create_artifact_version(
        session, tenant_id=tenant_id, project_id=project_id, command=command
    )
    duplicate = create_artifact_version(
        session, tenant_id=tenant_id, project_id=project_id, command=command
    )
    assert first.version == 1 and not first.replayed
    assert duplicate == replace(first, replayed=True)
    row = session.scalar(select(ArtifactVersionRecord))
    assert row is not None and row.graph_snapshot_hash == graph.snapshot_hash
    assert row.content_hash == sha256(command.content.encode("utf-8")).hexdigest()
    assert len(session.scalars(select(ArtifactProvenanceRecord)).all()) == 1
    row.content = "overwrite"
    with pytest.raises(ImmutableRecordMutation, match="append-only"):
        session.flush()


def test_artifact_conflict_stale_dependency_and_provenance_rollback(session: Session) -> None:
    tenant_id, project_id, graph = setup_project(session)
    command = artifact_command(graph)
    create_artifact_version(session, tenant_id=tenant_id, project_id=project_id, command=command)
    with pytest.raises(ArtifactConflict, match="conflicting payload"):
        create_artifact_version(
            session,
            tenant_id=tenant_id,
            project_id=project_id,
            command=command.model_copy(update={"content": "conflicting"}),
        )
    session.rollback()

    bad_dependencies = (command.dependencies[0].model_copy(update={"node_version": 99}),)
    with pytest.raises(StaleArtifactSource, match="dependency versions"):
        create_artifact_version(
            session,
            tenant_id=tenant_id,
            project_id=project_id,
            command=command.model_copy(
                update={
                    "artifact_version_id": "bad-dependency-version",
                    "artifact_id": "bad-dependency-artifact",
                    "idempotency_key": "bad-dependency-key",
                    "dependencies": bad_dependencies,
                }
            ),
        )
    session.rollback()
    bad_provenance = command.model_copy(
        update={
            "artifact_version_id": "rollback-version",
            "artifact_id": "rollback-artifact",
            "idempotency_key": "rollback-key",
            "provenance": (
                ProvenanceInput(
                    provenance_id="unknown-source",
                    source_kind="graph_node",
                    source_id="does-not-exist",
                ),
            ),
        }
    )
    with pytest.raises(StaleArtifactSource, match="provenance source"):
        create_artifact_version(
            session, tenant_id=tenant_id, project_id=project_id, command=bad_provenance
        )
    session.rollback()
    assert session.scalar(select(ArtifactVersionRecord.artifact_version_id)) == "artifact-version-1"


def test_artifact_eligibility_uses_current_graph_and_approval_authority(session: Session) -> None:
    tenant_id, project_id, graph = setup_project(session)
    result = create_artifact_version(
        session,
        tenant_id=tenant_id,
        project_id=project_id,
        command=artifact_command(graph),
    )
    eligibility = check_artifact_eligibility(
        session,
        tenant_id=tenant_id,
        project_id=project_id,
        artifact_version_id=result.artifact_version_id,
    )
    assert not eligibility.eligible
    assert any("approval" in reason for reason in eligibility.reasons)

    asset = next(node for node in graph.nodes if isinstance(node, AssetVersion))
    approval_identity = ReviewerIdentity("reviewer-1", tenant_id, project_id, "reviewer", True)
    req_hash = requirement_fingerprint(graph.requirements)
    submitted = Approval(
        id="artifact-review-submit",
        tenant_id=tenant_id,
        project_id=project_id,
        created_at=NOW + timedelta(seconds=2),
        asset_version_id=asset.id,
        asset_version=asset.version,
        requirement_fingerprint=req_hash,
        actor_id="reviewer-1",
        decision=ApprovalDecision.SUBMITTED,
        policy_version=asset.policy_version,
        idempotency_key="artifact-review-submit-key",
        expected_revision=0,
    )
    plan = plan_change(graph, change_event("note", graph), Policy())
    append_approval(
        session,
        command=submitted,
        identity=approval_identity,
        graph=graph,
        plan=plan,
    )
    approved = Approval(
        id="artifact-review-approved",
        tenant_id=tenant_id,
        project_id=project_id,
        created_at=NOW + timedelta(seconds=3),
        asset_version_id=asset.id,
        asset_version=asset.version,
        requirement_fingerprint=req_hash,
        actor_id="reviewer-1",
        decision=ApprovalDecision.APPROVED,
        policy_version=asset.policy_version,
        idempotency_key="artifact-review-approved-key",
        expected_revision=1,
        supersedes_id=submitted.id,
    )
    append_approval(
        session,
        command=approved,
        identity=approval_identity,
        graph=graph,
        plan=plan,
    )
    session.commit()
    eligible = check_artifact_eligibility(
        session,
        tenant_id=tenant_id,
        project_id=project_id,
        artifact_version_id=result.artifact_version_id,
    )
    assert eligible.eligible

    revoked = Approval(
        id="artifact-review-revoked",
        tenant_id=tenant_id,
        project_id=project_id,
        created_at=NOW + timedelta(seconds=4),
        asset_version_id=asset.id,
        asset_version=asset.version,
        requirement_fingerprint=req_hash,
        actor_id="reviewer-1",
        decision=ApprovalDecision.REVOKED,
        policy_version=asset.policy_version,
        idempotency_key="artifact-review-revoked-key",
        expected_revision=2,
        reason="approval withdrawn in test",
        supersedes_id=approved.id,
    )
    append_approval(
        session,
        command=revoked,
        identity=approval_identity,
        graph=graph,
        plan=plan,
    )
    session.commit()
    revoked_eligibility = check_artifact_eligibility(
        session,
        tenant_id=tenant_id,
        project_id=project_id,
        artifact_version_id=result.artifact_version_id,
    )
    assert not revoked_eligibility.eligible

    # A confirmed requirement version change makes the persisted artifact stale.
    from gamo_ca.models import Requirement

    instant = graph.as_of + timedelta(seconds=5)
    changed = replace(
        graph,
        as_of=instant,
        nodes=tuple(
            replace(
                node,
                version=node.version + 1,
                content="Revised requirement",
                valid_from=instant,
                confirmed_by="producer-1",
            )
            if isinstance(node, Requirement) and node.id == "slogan"
            else node
            for node in graph.nodes
        ),
    )
    new_graph_event = _graph_change_payload(graph, changed)
    append_graph_change(
        session,
        change=new_graph_event,
        identity=_graph_identity(graph),
        idempotency_key="advance-graph",
    )
    session.commit()
    stale = check_artifact_eligibility(
        session,
        tenant_id=tenant_id,
        project_id=project_id,
        artifact_version_id=result.artifact_version_id,
    )
    assert not stale.eligible and "no longer current" in stale.reasons[0]


def test_execution_run_attempt_events_and_measures_are_transactional(session: Session) -> None:
    tenant_id, project_id, graph = setup_project(session)
    command = run_command(graph)
    created = create_execution_run(
        session, tenant_id=tenant_id, project_id=project_id, command=command
    )
    replay = create_execution_run(
        session, tenant_id=tenant_id, project_id=project_id, command=command
    )
    assert created.status == "pending" and replay.replayed
    first_attempt = attempt_command(graph)
    started = start_execution_attempt(
        session,
        tenant_id=tenant_id,
        project_id=project_id,
        run_id=command.run_id,
        command=first_attempt,
    )
    assert started.status == "running"
    retryable = ExecutionTransitionRequest(
        event_id="attempt-1-retry",
        idempotency_key="attempt-1-retry-key",
        status="retryable_failure",
        error_classification="provider_timeout",
        elapsed=ExecutionMetric(status=MetricStatus.MEASURED, value=23),
    )
    ended = record_execution_transition(
        session,
        tenant_id=tenant_id,
        project_id=project_id,
        run_id=command.run_id,
        attempt_id=first_attempt.attempt_id,
        command=retryable,
    )
    assert ended.status == "retryable_failure"
    assert record_execution_transition(
        session,
        tenant_id=tenant_id,
        project_id=project_id,
        run_id=command.run_id,
        attempt_id=first_attempt.attempt_id,
        command=retryable,
    ).replayed
    second_attempt = attempt_command(graph, 2, "attempt-2", "attempt-2-key")
    start_execution_attempt(
        session,
        tenant_id=tenant_id,
        project_id=project_id,
        run_id=command.run_id,
        command=second_attempt,
    )
    success = ExecutionTransitionRequest(
        event_id="attempt-2-success",
        idempotency_key="attempt-2-success-key",
        status="succeeded",
        elapsed=ExecutionMetric(status=MetricStatus.ESTIMATED, value=5),
        tokens=ExecutionMetric(status=MetricStatus.MEASURED, value=42),
        cost_usd=ExecutionMetric(),
    )
    final = record_execution_transition(
        session,
        tenant_id=tenant_id,
        project_id=project_id,
        run_id=command.run_id,
        attempt_id=second_attempt.attempt_id,
        command=success,
    )
    assert final.status == "succeeded"
    run = session.scalar(select(ExecutionRunRecord))
    assert run is not None and run.status == "succeeded"
    events = session.scalars(select(ExecutionEventRecord).order_by(ExecutionEventRecord.id)).all()
    assert [event.status for event in events] == [
        "pending",
        "running",
        "retryable_failure",
        "running",
        "succeeded",
    ]
    assert events[2].elapsed_ms == 23 and events[2].elapsed_status == "measured"
    assert events[-1].token_count == 42 and events[-1].token_status == "measured"
    assert events[-1].cost_usd is None and events[-1].cost_status == "missing"
    events[-1].status = "failed"
    with pytest.raises(ImmutableRecordMutation, match="append-only"):
        session.flush()


def test_execution_rejects_stale_dependency_out_of_order_and_conflicting_retry(
    session: Session,
) -> None:
    tenant_id, project_id, graph = setup_project(session)
    create_execution_run(
        session, tenant_id=tenant_id, project_id=project_id, command=run_command(graph)
    )
    first = attempt_command(graph)
    invalid = first.model_copy(
        update={
            "dependencies": (first.dependencies[0].model_copy(update={"content_hash": "0" * 64}),)
        }
    )
    with pytest.raises(StaleArtifactSource, match="dependency versions"):
        start_execution_attempt(
            session, tenant_id=tenant_id, project_id=project_id, run_id="run-1", command=invalid
        )
    session.rollback()
    with pytest.raises(ExecutionTransitionConflict, match="attempt number"):
        start_execution_attempt(
            session,
            tenant_id=tenant_id,
            project_id=project_id,
            run_id="run-1",
            command=attempt_command(graph, 2),
        )
    session.rollback()
    start_execution_attempt(
        session, tenant_id=tenant_id, project_id=project_id, run_id="run-1", command=first
    )
    failure = ExecutionTransitionRequest(
        event_id="failure-one",
        idempotency_key="failure-key",
        status="failed",
        error_classification="validation",
    )
    record_execution_transition(
        session,
        tenant_id=tenant_id,
        project_id=project_id,
        run_id="run-1",
        attempt_id=first.attempt_id,
        command=failure,
    )
    conflict = failure.model_copy(update={"error_classification": "different"})
    with pytest.raises(ArtifactConflict, match="conflicting payload"):
        record_execution_transition(
            session,
            tenant_id=tenant_id,
            project_id=project_id,
            run_id="run-1",
            attempt_id=first.attempt_id,
            command=conflict,
        )


def test_execution_creation_rollback_and_pending_cancellation_are_atomic(session: Session) -> None:
    tenant_id, project_id, graph = setup_project(session)
    run = run_command(graph)

    def fail_pending_insert(mapper, connection, target) -> None:
        if target.status == "pending":
            raise RuntimeError("injected execution event insert failure")

    event.listen(ExecutionEventRecord, "before_insert", fail_pending_insert)
    try:
        with pytest.raises(RuntimeError, match="injected execution"):
            create_execution_run(session, tenant_id=tenant_id, project_id=project_id, command=run)
    finally:
        event.remove(ExecutionEventRecord, "before_insert", fail_pending_insert)
        session.rollback()
    assert session.scalars(select(ExecutionRunRecord)).all() == []
    assert session.scalars(select(ExecutionEventRecord)).all() == []
    session.rollback()

    create_execution_run(session, tenant_id=tenant_id, project_id=project_id, command=run)
    cancellation = ExecutionTransitionRequest(
        event_id="pending-cancelled",
        idempotency_key="pending-cancel-key",
        status="cancelled",
    )
    result = record_execution_transition(
        session,
        tenant_id=tenant_id,
        project_id=project_id,
        run_id=run.run_id,
        attempt_id=None,
        command=cancellation,
    )
    assert result.status == "cancelled"
    assert session.scalar(select(ExecutionAttemptRecord)) is None


def _graph_change_payload(graph, changed):
    from gamo_ca.events import GraphChangePayload

    instant = changed.as_of
    return GraphChangePayload(
        "stale-artifact-graph-change",
        graph.tenant_id,
        graph.project_id,
        "producer-1",
        instant,
        0,
        graph.snapshot_hash,
        changed,
    )


def _graph_identity(graph):
    from gamo_ca.events import GraphChangeIdentity

    return GraphChangeIdentity("producer-1", graph.tenant_id, graph.project_id, "producer", True)
