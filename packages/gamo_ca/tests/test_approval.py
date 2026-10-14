from dataclasses import replace
from datetime import timedelta
from typing import Any

import pytest
from gamo_ca.approvals import (
    ApprovalConflict,
    ApprovalError,
    ApprovalResult,
    ApprovalState,
    ReviewerIdentity,
    approval_state,
    publication_eligibility,
)
from gamo_ca.approvals import (
    apply_approval as _apply_approval,
)
from gamo_ca.fingerprints import fingerprint, requirement_fingerprint
from gamo_ca.fixtures import NOW, change_event, toy_graph
from gamo_ca.graph import Graph
from gamo_ca.models import (
    Approval,
    ApprovalDecision,
    AssetVersion,
    ChangeEvent,
    Evidence,
    RequirementStatus,
)
from gamo_ca.planner import Plan, Policy, plan_change


def reviewer(graph: Graph | None = None, **overrides: Any) -> ReviewerIdentity:
    graph = graph or toy_graph()
    return ReviewerIdentity(
        actor_id=overrides.get("actor_id", "reviewer-1"),
        tenant_id=overrides.get("tenant_id", graph.tenant_id),
        project_id=overrides.get("project_id", graph.project_id),
        role=overrides.get("role", "reviewer"),
        is_human=overrides.get("is_human", True),
    )


def command(
    graph: Graph,
    *,
    decision: ApprovalDecision = ApprovalDecision.APPROVED,
    key: str = "approval-1",
    **overrides: Any,
) -> Approval:
    asset = next(node for node in graph.nodes if isinstance(node, AssetVersion))
    return Approval(
        id=overrides.get("id", key),
        tenant_id=overrides.get("tenant_id", graph.tenant_id),
        project_id=overrides.get("project_id", graph.project_id),
        created_at=overrides.get(
            "created_at", NOW + timedelta(seconds=2 * overrides.get("expected_revision", 0))
        ),
        asset_version_id=overrides.get("asset_version_id", asset.id),
        asset_version=overrides.get("asset_version", asset.version),
        requirement_fingerprint=overrides.get(
            "requirement_fingerprint", requirement_fingerprint(graph.requirements)
        ),
        actor_id=overrides.get("actor_id", "reviewer-1"),
        decision=decision,
        policy_version=overrides.get("policy_version", asset.policy_version),
        idempotency_key=overrides.get("idempotency_key", key),
        expected_revision=overrides.get("expected_revision", 0),
        reason=overrides.get("reason"),
        supersedes_id=overrides.get("supersedes_id"),
    )


def approved_history(graph: Graph | None = None) -> tuple[Approval, ...]:
    graph = graph or toy_graph()
    record = command(graph)
    result = apply_approval((), record, reviewer(graph), graph)
    return result.history


def current_plan(graph: Graph, event: ChangeEvent | None = None) -> Plan:
    return plan_change(graph, event or change_event("note", graph), Policy())


def apply_approval(
    history: tuple[Approval, ...],
    approval: Approval,
    identity: ReviewerIdentity,
    graph: Graph,
) -> ApprovalResult:
    if not history and approval.decision != ApprovalDecision.SUBMITTED:
        submitted = replace(
            approval,
            id=f"{approval.id}-submitted",
            decision=ApprovalDecision.SUBMITTED,
            idempotency_key=f"{approval.idempotency_key}-submitted",
            expected_revision=0,
            created_at=approval.created_at - timedelta(seconds=1),
            supersedes_id=None,
            reason=None,
        )
        history = _apply_approval(history, submitted, identity, graph, current_plan(graph)).history
        approval = replace(approval, expected_revision=1, supersedes_id=submitted.id)
    return _apply_approval(history, approval, identity, graph, current_plan(graph))


def test_approval_is_bound_to_asset_requirement_and_policy_snapshots() -> None:
    graph = toy_graph()
    approval = command(graph)
    with pytest.raises(ApprovalError, match="requirement"):
        apply_approval(
            (),
            replace(approval, requirement_fingerprint=fingerprint("stale")),
            reviewer(graph),
            graph,
        )
    with pytest.raises(ApprovalError, match="policy"):
        apply_approval((), replace(approval, policy_version="old"), reviewer(graph), graph)
    with pytest.raises(ApprovalError, match="plan policy"):
        _apply_approval(
            (), approval, reviewer(graph), graph, replace(current_plan(graph), policy_version="old")
        )
    with pytest.raises(ApprovalError, match="asset version"):
        apply_approval((), replace(approval, asset_version=8), reviewer(graph), graph)
    result = apply_approval((), approval, reviewer(graph), graph)
    assert result.history[-1].decision == ApprovalDecision.APPROVED
    assert (
        approval_state(
            result.history,
            approval.asset_version_id,
            tenant_id=graph.tenant_id,
            project_id=graph.project_id,
        )
        == ApprovalState.APPROVED
    )


def test_human_reviewer_scope_and_role_are_required() -> None:
    graph = toy_graph()
    approval = command(graph)
    for identity in (
        reviewer(graph, is_human=False),
        reviewer(graph, role="editor"),
        reviewer(graph, tenant_id="another-tenant"),
        reviewer(graph, project_id="another-project"),
        reviewer(graph, actor_id="spoofed-actor"),
    ):
        with pytest.raises(ApprovalError, match="reviewer|scope|actor|human"):
            apply_approval((), approval, identity, graph)


def test_approval_rejection_and_revocation_are_append_only_transitions() -> None:
    graph = toy_graph()
    copy = graph.node("copy")
    initial_submission = replace(
        command(graph, key="submission"),
        decision=ApprovalDecision.SUBMITTED,
        actor_id="editor",
        expected_revision=0,
    )
    submitter = reviewer(graph, actor_id="editor", role="editor")
    in_review = _apply_approval((), initial_submission, submitter, graph, current_plan(graph))
    assert (
        approval_state(
            in_review.history, copy.id, tenant_id=graph.tenant_id, project_id=graph.project_id
        )
        == ApprovalState.IN_REVIEW
    )
    rejected = replace(
        command(
            graph,
            decision=ApprovalDecision.REJECTED,
            key="rejected",
            reason="Needs copy edit",
            created_at=NOW + timedelta(seconds=2),
        ),
        expected_revision=1,
        supersedes_id=initial_submission.id,
    )
    first = _apply_approval(
        in_review.history, rejected, reviewer(graph), graph, current_plan(graph)
    )
    assert (
        approval_state(
            first.history, copy.id, tenant_id=graph.tenant_id, project_id=graph.project_id
        )
        == ApprovalState.REJECTED
    )
    with pytest.raises(ApprovalError, match="transition"):
        apply_approval(
            first.history,
            command(
                graph,
                key="approve-rejected",
                expected_revision=2,
                supersedes_id=first.history[-1].id,
            ),
            reviewer(graph),
            graph,
        )

    # A separate exact version can progress independently through review and approval.
    visual = graph.node("visual")
    visual_submission = replace(
        command(graph, key="visual-submit", asset_version_id=visual.id),
        decision=ApprovalDecision.SUBMITTED,
        actor_id="editor",
        created_at=NOW,
    )
    visual_history = _apply_approval(
        (), visual_submission, submitter, graph, current_plan(graph)
    ).history
    approved = replace(
        command(
            graph,
            key="visual-approve",
            asset_version_id=visual.id,
            created_at=NOW + timedelta(seconds=2),
        ),
        expected_revision=1,
        supersedes_id=visual_submission.id,
    )
    second = _apply_approval(visual_history, approved, reviewer(graph), graph, current_plan(graph))
    revoked = command(
        graph,
        decision=ApprovalDecision.REVOKED,
        key="visual-revoke",
        asset_version_id=visual.id,
        expected_revision=2,
        supersedes_id=approved.id,
        reason="Approval withdrawn",
    )
    third = _apply_approval(second.history, revoked, reviewer(graph), graph, current_plan(graph))
    assert third.history == (*visual_history, approved, revoked)
    assert third.history[-2] == approved
    assert third.latest.decision == ApprovalDecision.REVOKED
    assert (
        approval_state(
            third.history, visual.id, tenant_id=graph.tenant_id, project_id=graph.project_id
        )
        == ApprovalState.REVOKED
    )
    with pytest.raises(ApprovalError, match="transition|revision"):
        _apply_approval(
            third.history,
            replace(revoked, id="revoke-again", idempotency_key="revoke-again"),
            reviewer(graph),
            graph,
            current_plan(graph),
        )


def test_missing_reasons_wrong_revision_and_broken_supersession_fail() -> None:
    graph = toy_graph()
    with pytest.raises(ValueError, match="reason"):
        command(graph, decision=ApprovalDecision.REJECTED)
    rejected = command(graph, decision=ApprovalDecision.REJECTED, reason="Revise")
    with pytest.raises(ApprovalError, match="revision"):
        _apply_approval(
            (), replace(rejected, expected_revision=1), reviewer(graph), graph, current_plan(graph)
        )
    first = apply_approval((), rejected, reviewer(graph), graph)
    approved = command(
        graph,
        key="approved",
        expected_revision=2,
        supersedes_id="wrong-parent",
        created_at=NOW + timedelta(seconds=4),
    )
    with pytest.raises(ApprovalError, match="supersede"):
        apply_approval(first.history, approved, reviewer(graph), graph)


def test_draft_requires_submission_before_review_and_direct_approval_is_rejected() -> None:
    graph = toy_graph()
    assert (
        approval_state((), "copy", tenant_id=graph.tenant_id, project_id=graph.project_id)
        == ApprovalState.DRAFT
    )
    foreign = replace(command(graph), tenant_id="another-tenant")
    with pytest.raises(ApprovalError, match="scope"):
        approval_state(
            (foreign,),
            "copy",
            tenant_id=graph.tenant_id,
            project_id=graph.project_id,
        )
    with pytest.raises(ApprovalError, match="transition"):
        _apply_approval((), command(graph), reviewer(graph), graph, current_plan(graph))


def test_publication_rejects_an_impossible_forged_approval_transition() -> None:
    graph = toy_graph()
    approved = command(graph)
    second = command(
        graph,
        key="approval-2",
        expected_revision=1,
        supersedes_id=approved.id,
        created_at=NOW + timedelta(seconds=1),
    )
    forged_history = (approved, second)
    decision = publication_eligibility(
        graph, "copy", forged_history, current_plan(graph), policy_version="v1"
    )
    assert not decision.eligible
    assert any("invalid approval history" in reason for reason in decision.reasons)


def test_idempotent_replay_returns_existing_record_and_conflicts_on_key_reuse() -> None:
    graph = toy_graph()
    approval = command(graph)
    applied = apply_approval((), approval, reviewer(graph), graph)
    persisted_command = applied.latest
    replay = _apply_approval(
        applied.history, persisted_command, reviewer(graph), graph, current_plan(graph)
    )
    assert replay.replayed is True
    assert replay.history == applied.history
    with pytest.raises(ApprovalConflict, match="idempotency"):
        apply_approval(
            applied.history,
            replace(persisted_command, decision=ApprovalDecision.REJECTED, reason="No"),
            reviewer(graph),
            graph,
        )
    with pytest.raises(ApprovalConflict, match="identifier"):
        apply_approval(
            applied.history,
            replace(persisted_command, idempotency_key="new-key"),
            reviewer(graph),
            graph,
        )


def test_changed_requirement_and_new_asset_version_invalidate_old_approval() -> None:
    graph = toy_graph()
    history = approved_history(graph)
    plan = current_plan(graph, change_event(graph=graph))
    decision = publication_eligibility(graph, "copy", history, plan, policy_version="v1")
    assert not decision.eligible and decision.reasons
    asset = graph.node("copy")
    current = replace(asset, version=2, content="New approved candidate")
    revised = replace(graph, nodes=tuple(current if n.id == asset.id else n for n in graph.nodes))
    plan2 = current_plan(revised)
    result = publication_eligibility(revised, current.id, history, plan2, policy_version="v1")
    assert not result.eligible
    assert any("exact" in reason or "approval" in reason for reason in result.reasons)


def test_publication_requires_approval_never_keep_and_blocks_review_or_recompute() -> None:
    graph = toy_graph()
    history = approved_history(graph)
    safe = publication_eligibility(graph, "copy", history, current_plan(graph), policy_version="v1")
    assert safe.eligible
    missing = publication_eligibility(graph, "logo", (), current_plan(graph), policy_version="v1")
    assert not missing.eligible and any("approval" in reason for reason in missing.reasons)
    changed = change_event(graph=graph)
    risky_plan = current_plan(graph, changed)
    for asset_id in ("copy", "visual", "storyboard", "visual_export"):
        outcome = publication_eligibility(graph, asset_id, history, risky_plan, policy_version="v1")
        assert not outcome.eligible
        assert outcome.reasons
    wrong_policy = publication_eligibility(
        graph, "copy", history, current_plan(graph), policy_version="v2"
    )
    assert not wrong_policy.eligible
    stale_plan_policy = publication_eligibility(
        graph,
        "copy",
        history,
        replace(current_plan(graph), policy_version="v2"),
        policy_version="v1",
    )
    assert not stale_plan_policy.eligible
    assert any("plan policy" in reason for reason in stale_plan_policy.reasons)


def test_unconfirmed_requirement_evidence_and_asset_provenance_block_publication() -> None:
    graph = toy_graph()
    asset = graph.node("copy")
    evidence = graph.node("evidence")
    assert isinstance(evidence, Evidence)
    unconfirmed_evidence = replace(evidence, confirmed_by=None)
    nodes = tuple(unconfirmed_evidence if node.id == evidence.id else node for node in graph.nodes)
    changed_graph = replace(graph, nodes=nodes)
    result = publication_eligibility(
        changed_graph,
        asset.id,
        approved_history(graph),
        current_plan(graph),
        policy_version="v1",
    )
    assert not result.eligible
    assert any("evidence" in reason for reason in result.reasons)

    requirement = graph.requirements[0]
    unconfirmed = replace(requirement, status=RequirementStatus.UNCONFIRMED, confirmed_by=None)
    changed_graph = replace(
        graph, nodes=tuple(unconfirmed if n.id == requirement.id else n for n in graph.nodes)
    )
    result = publication_eligibility(
        changed_graph,
        asset.id,
        approved_history(graph),
        current_plan(graph),
        policy_version="v1",
    )
    assert not result.eligible


def test_stale_plan_and_cross_tenant_publication_attempts_fail_closed() -> None:
    graph = toy_graph()
    history = approved_history(graph)
    plan = current_plan(graph)
    changed = replace(
        graph,
        nodes=tuple(
            replace(n, content=n.content + " changed") if n.id == "note" else n for n in graph.nodes
        ),
    )
    result = publication_eligibility(changed, "copy", history, plan, policy_version="v1")
    assert not result.eligible and any("plan" in reason for reason in result.reasons)
    outcome = publication_eligibility(
        graph, "copy", (replace(history[0], tenant_id="foreign"),), plan, policy_version="v1"
    )
    assert not outcome.eligible and any("scope" in reason for reason in outcome.reasons)
