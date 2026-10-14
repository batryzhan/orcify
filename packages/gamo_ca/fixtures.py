"""Synthetic fixtures only, with fixed IDs, timestamps and simulated estimates."""

from datetime import UTC, datetime
from typing import TypedDict

from gamo_ca.fingerprints import fingerprint, requirement_fingerprint
from gamo_ca.graph import Graph
from gamo_ca.models import (
    Approval,
    ApprovalDecision,
    AssetVersion,
    Brief,
    Campaign,
    ChangeEvent,
    DependencyEdge,
    DependencyType,
    Entity,
    Evidence,
    ExecutionRecord,
    Feedback,
    InputRef,
    Requirement,
    RequirementStatus,
    Tenant,
)

START = datetime(2026, 10, 1, tzinfo=UTC)
NOW = datetime(2026, 10, 14, tzinfo=UTC)


class ScopeArgs(TypedDict):
    tenant_id: str
    project_id: str
    created_at: datetime


SCOPE: ScopeArgs = {"tenant_id": "demo-tenant", "project_id": "demo-project", "created_at": START}


def reference(node: Requirement | AssetVersion | Brief) -> InputRef:
    return InputRef(node.id, node.version, node.content_hash)


def toy_graph() -> Graph:
    evidence = Evidence(
        **SCOPE,
        id="evidence",
        version=1,
        content="Synthetic human-confirmed brief",
        valid_from=START,
        source_id="synthetic-brief",
        extracted_span="Use slogan: Hello",
        confirmed_by="synthetic-reviewer",
    )
    slogan = Requirement(
        **SCOPE,
        id="slogan",
        version=1,
        content="Hello",
        valid_from=START,
        source_id=evidence.id,
        evidence_ids=(evidence.id,),
        status=RequirementStatus.CONFIRMED,
        confirmed_by="synthetic-reviewer",
    )
    note = Brief(
        **SCOPE,
        id="note",
        version=1,
        content="Internal scheduling note",
        valid_from=START,
        filename="synthetic-note.txt",
    )
    requirements_hash = requirement_fingerprint((slogan,))

    def asset(node_id: str, upstream: Requirement | AssetVersion) -> AssetVersion:
        return AssetVersion(
            **SCOPE,
            id=node_id,
            version=1,
            content=f"Synthetic {node_id}",
            valid_from=START,
            asset_id=f"asset-{node_id}",
            requirement_fingerprint=requirements_hash,
            inputs=(reference(upstream),),
            evidence_ids=(evidence.id,),
            provider="mock",
            model_version="fixture-v1",
            prompt_version="draft-v1",
            estimated_cost_usd=0.0,
            estimated_latency_s=0.1,
        )

    copy = asset("copy", slogan)
    storyboard = asset("storyboard", copy)
    visual = asset("visual", slogan)
    visual_export = asset("visual_export", visual)
    logo = asset("logo", slogan)

    def edge(upstream: str, dependent: str, strength: DependencyType) -> DependencyEdge:
        return DependencyEdge(
            **SCOPE,
            id=f"{upstream}-{dependent}",
            upstream_id=upstream,
            dependent_id=dependent,
            strength=strength,
            valid_from=START,
        )

    return Graph(
        "demo-tenant",
        "demo-project",
        NOW,
        (slogan, evidence, note, copy, storyboard, visual, visual_export, logo),
        (
            edge("slogan", "copy", DependencyType.HARD),
            edge("copy", "storyboard", DependencyType.HARD),
            edge("slogan", "visual", DependencyType.SOFT),
            edge("visual", "visual_export", DependencyType.HARD),
            edge("slogan", "logo", DependencyType.INFORMATIONAL),
        ),
    )


def change_event(target_id: str = "slogan", graph: Graph | None = None) -> ChangeEvent:
    graph = graph or toy_graph()
    target = graph.node(target_id)
    return ChangeEvent(
        id=f"change-{target_id}",
        tenant_id=graph.tenant_id,
        project_id=graph.project_id,
        created_at=SCOPE["created_at"],
        target_id=target_id,
        source_id="evidence",
        actor_id="synthetic-reviewer",
        change_type="CONTENT_REVISION",
        old_version=target.version,
        new_version=target.version + 1,
        old_hash=target.content_hash,
        new_hash=fingerprint(f"Revised {target.content}"),
        changed_fields=(target_id,),
        occurred_at=graph.as_of,
        expected_snapshot_hash=graph.snapshot_hash,
    )


def entity_examples() -> tuple[Entity, ...]:
    from gamo_ca.models import Task

    graph = toy_graph()
    return (
        Tenant(**SCOPE, id="tenant", name="Synthetic tenant"),
        Campaign(**SCOPE, id="campaign", title="Synthetic campaign"),
        graph.node("note"),
        graph.node("slogan"),
        graph.node("evidence"),
        Task(
            **SCOPE,
            id="task",
            version=1,
            content="Generate draft",
            valid_from=START,
            task_type="copy",
        ),
        graph.node("copy"),
        Feedback(
            **SCOPE, id="feedback", asset_version_id="copy", actor_id="human", comment="Revise"
        ),
        Approval(
            **SCOPE,
            id="approval",
            asset_version_id="copy",
            asset_version=1,
            actor_id="human",
            requirement_fingerprint=requirement_fingerprint(graph.requirements),
            decision=ApprovalDecision.APPROVED,
            policy_version="v1",
            idempotency_key="fixture-approval",
            expected_revision=0,
        ),
        change_event(),
        ExecutionRecord(
            **SCOPE,
            id="execution",
            event_id="change-slogan",
            task_id="task",
            input_fingerprint=fingerprint("inputs"),
            output_hash=fingerprint("output"),
            provider="mock",
            model_version="fixture-v1",
            prompt_version="draft-v1",
            status="SUCCEEDED",
        ),
        graph.edges[0],
    )
