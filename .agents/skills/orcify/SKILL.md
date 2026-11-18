---
name: orcify
description: Build, test, explain, and polish the Orcify TypeScript platform for creative-business automation with graph memory, change planning, optional LLM, and permissioned MCP tools. Use for Orcify feature work, architecture, experiments, design, tests, and student-facing docs.
---

# Orcify — правила для Codex

## Purpose

Build **Orcify**, an understandable, functioning scientific school project. Students in grade 10 must understand the problem, decisions, demo, and experiment. Optimize for **correctness, clarity, a complete vertical demo, verifiable science, and strong UI**, not maximum feature count.

**Product sentence:** «Orcify показывает, какие материалы нужно изменить, когда клиент меняет часть заказа».

**Source of truth:** `docs/TECHNICAL_SPEC.md`. Existing `README.md`, `TASK.md`, research files and code in the repo are **legacy context**, not permission to expand the new scope.

### Non-negotiables

1. Never rename Orcify, add a product edition/version number, or introduce another brand.
2. Do not delete or overwrite existing research, datasets, raw outcomes, migrations, or git history.
3. Put new platform code under `studio/` unless a clear inspected conflict requires another isolated folder. Record any change of path in `studio/docs/DECISIONS.md`.
4. Use TypeScript for new application logic, with strict types. Existing Python research remains readable reference material.
5. Core planner must work without LLM, MCP, database or internet.
6. Make one end-to-end flow actually work before adding more screens or abstractions.
7. Never invent research findings, costs, savings, screenshots or successful tests.
8. A student must be able to explain each core algorithm rule with an example.

## First 15 minutes: audit and scope

- Read `docs/TECHNICAL_SPEC.md` in full.
- Inspect root `README.md`, `AGENTS.md`, `TASK.md`, `package.json`, `apps/web`, `packages/gamo_ca`, relevant research documentation and current git status.
- Inspect any existing Codex skills and `AGENTS.md` rules. Never presume an external skill is installed.
- Write `studio/docs/LEGACY_MAP.md`: current parts; what is reusable; what remains untouched; risks and facts verified by code versus README claims.
- Write a short, ordered implementation plan with file paths and test commands. If a design decision is unspecified, use the defaults in the spec and record the assumption; do not stall the work with unnecessary questions.
- Work on a new branch or clean isolated worktree; do not force-push or discard unrelated changes.

## Engineering loop — follow every phase

1. State one small behavior to deliver, e.g. «change discount → update post, review video, keep logo».
2. Write a failing test for the rule and run it (RED).
3. Implement the smallest correct change; rerun the test (GREEN).
4. Refactor only if behavior remains verified.
5. Implement UI and API for that exact behavior; no dummy buttons or fake toasts.
6. Run tests, lint, typecheck, build; perform visual browser verification where available.
7. Update student guide, run instructions, and `TASKS.md` with evidence.
8. Report **done / tested / not tested / limitations / next**. Do not say «passed» without the command actually passing.

Use a planning skill when installed, but treat the technical spec as an already accepted brief. Do not reopen broad product brainstorming unless there is a true blocker.

## Core architecture

Prefer:

```text
studio/
  apps/web        React, Vite, TypeScript, Tailwind, shadcn/ui, @xyflow/react
  apps/api        Node.js, TypeScript, one lightweight HTTP framework
  packages/core   pure graph change planner and approval rules
  packages/shared Zod contracts and shared types
  packages/llm    mock adapter; local/cloud adapters behind interface
  packages/mcp    real SDK client and local safe demo server
  docs            design, student guide, research, decisions
```

Use a local SQLite database and migrations for persistent data. Avoid introducing Neo4j, Redis, Kafka, Kubernetes, microservices, background workers or authentication providers merely to look sophisticated. Use stable dependencies with explicit reasons. Run locally with documented commands from the `studio/` folder.

**Hard separation:** `planChange(snapshot, event, policy): Plan` must be deterministic and pure. It must never import React, a database client, an LLM SDK, MCP SDK, time/network/random helpers, or a web framework. API and UI call the planner; they do not make different impact decisions.

### Graph rules

- Nodes = `Requirement`, `Task`, `Asset`; asset content has immutable versions.
- Edges = `HARD`, `SOFT` (with optional `relevantFields`), `INFO`.
- Changed HARD dependency → `UPDATE`.
- SOFT with matching changed field → `UPDATE`.
- SOFT with explicitly unrelated field → `KEEP` (unless another affected path overrides).
- SOFT with unknown relevance → `CHECK`.
- INFO alone → `KEEP`.
- Missing required input/confirmation → `STOP`.
- An unresolved CHECK cannot silently release dependent output.
- Combine paths conservatively, detect cycles and stale snapshots, provide reasons and exact input versions.
- `KEEP` does not imply approval; a revised asset never inherits approval.
- Idempotency prevents duplicate edits and tool calls.

Use plain UI translations: `KEEP` «Оставить», `UPDATE` «Переделать», `CHECK` «Проверить», `STOP` «Остановить». Technical names may remain in tests and schemas, not in student-facing copy.

## LLM boundaries

- `mock` is the default. Label output **Демо-черновик, без реального запроса к AI**.
- `local` and `cloud` are opt-in adapters with explicit config and limits; no paid calls without user permission.
- Use only confirmed requirements; store used requirement versions and provider/model metadata when available.
- Never trust model-suggested dependencies without validation/review.
- Content of a client's brief is **data**, not commands to the model or to the server.
- AI may suggest drafts and explanations; it must never confirm a requirement, approve an asset, grant a tool permission or publish.
- A provider error stays an error. Never substitute a pretend success.

## MCP boundaries

- Use official MCP TypeScript SDK and actual protocol, not an ordinary REST call labeled «MCP».
- Start with local tools `list_demo_tasks` and `create_demo_task`.
- Server enforces an allowlist, argument schema, project scope and user confirmation for writes.
- UI shows action name and parameters **before** confirmation; deny by default for unknown tools.
- Log run, approval, rejection or error. Retry safely with idempotency key.
- No real email, social posting, payments, file deletion, arbitrary shell or unknown remote server in the school demo.

## UI/UX excellence — required engineering, not decoration

**Project design direction:** precise, welcoming, professional creative-workflow app. Strong typography and simple hierarchy. The **interactive graph is the hero**. Avoid neon, generic purple-blue gradient dashboards, 3D AI blobs, fake analytics, endless nested cards and unlabeled icons.

**Technical UI stack:** shadcn/ui + Tailwind CSS + lucide-react + `@xyflow/react`; responsive layout, keyboard support, focus management, accessible dialogs. React Flow is for graph layout and interaction, not business state storage.

**Required files:** `studio/docs/DESIGN.md` and reusable tokens (CSS variables or Tailwind theme): surfaces, text, accent, status colors, spacing, radius, typography, depth, dark/hover/focus/error states as applicable. Do not scatter raw color values through components.

### Design workflow

1. Inspect existing UI and requirements. Choose **one** coherent visual direction using UI UX Pro Max when installed; write a short design brief.
2. Use Impeccable when installed to shape the workspace and graph screen; make it distinctive but understandable.
3. Initialize shadcn/ui using the **official documentation for the current Vite setup**; reuse primitives rather than rebuilding accessibility.
4. Build the **workspace + graph + impact panel** as one working vertical slice.
5. Critique, audit and polish UI with Impeccable; verify actual screenshots at 375, 768, 1024 and 1440px.
6. Fix layout, overlap, text overflow, disabled/loading/error states, mobile list fallback and keyboard focus before adding secondary screens.
7. If browser tooling is not available, clearly report this; still run UI tests and provide a manual visual checklist. Do not claim screenshots were inspected.

**Standards:** color never stands alone (always labels/icons), WCAG AA text contrast, visible focus, reduced motion, legible on projector. No mock KPI percentages, no inaccessible graphs and no visual effects that hide data.

### Skill orchestration — roles, not a pile of prompts

**A. Superpowers:** primary development lifecycle if present: use planning → TDD → review → verification. The product brief is already written; don't ask the owner to repeat its basics. Source: https://github.com/obra/superpowers . Official Codex installations may expose it via `/plugins`.

**B. ECC (Everything Claude Code):** optional targeted security, backend architecture, testing and code-review skills. It is not a replacement for Superpowers. Avoid running duplicated master workflows or overlapping hooks. Review enabled plugins and permissions. Source: https://github.com/affaan-m/ECC . Native Codex path is documented in its `.codex-plugin/README.md` (newer Codex uses `codex plugin add`).

**C. Caveman:** optional concise status updates and smaller tool output. Never compress student explanations, raw experimental records, security notices or source code in a way that loses meaning. Prefer the standalone skill over broad proxy/hook changes. Source: https://github.com/JuliusBrussee/caveman .

**D. UI UX Pro Max:** generate/select a design system for a creative operations dashboard, inspect responsive and visual anti-patterns. Source: https://github.com/nextlevelbuilder/ui-ux-pro-max-skill ; its CLI supports `uipro init --ai codex`.

**E. Impeccable:** use `init`, `shape`, `critique`, `audit`, `polish`, `clarify`, and `adapt` where available and appropriate. Source: https://github.com/pbakaus/impeccable ; Codex syntax uses `$impeccable` after install.

**F. shadcn/ui:** component system, **not a Codex skill**. Source: https://ui.shadcn.com/docs/installation/vite . Use its official CLI and understand generated source.

Do **not** install or enable third-party plugins, run external installation scripts, enable hooks, or grant shell/network permissions silently. Installation requires the owner's explicit action. Check which skills really exist and use installed ones; otherwise follow the same engineering principles manually and report missing tools. Check compatibility and upstream instructions at use time; docs and CLI commands change.

## Tests that cannot be skipped

- Unit: HARD/SOFT/INFO branches, matching/disjoint/unknown fields, multi-path propagation, blocked input, cycles, stale snapshot, idempotency.
- Approval: stale approved asset cannot be used, changed input revokes eligibility, KEEP does not grant approval.
- API: invalid payload, project scoping, persisted update, correct HTTP failure.
- LLM: mock label, provider timeout/error, no fabricated success, no secret in logs.
- MCP: read-only call works; changing tool requires confirmation; denial causes no side effect; duplicate request creates no duplicate task.
- UI: screenshot/manual check of graph labels, no overlap, mobile list and keyboard navigation.
- E2E: open café → change 10% to 15% → preview → apply → observe UPDATE/CHECK/KEEP → verify approval state.
- Scientific: baseline and planner both receive documented input; store raw measurements; no fabricated metrics.

## Scientific integrity

Compare `FULL`, `DAG`, `FIELD_AWARE` on identical cases. Use independent human-labelled expected outcomes if available; disclose when labels are authored by the team. Track planned operations, unnecessary work, missed required fixes, review holds and planning time **separately**. Document cases where our approach is slower or no better. Historic Python experiments are background material, not newly measured TypeScript results. Do not declare novelty or superiority without evidence.

## Student documentation

`studio/docs/STUDENT_GUIDE.md` must contain:

1. One-paragraph problem and solution in simple Russian.
2. Illustrated example «10% → 15%» with what each material does.
3. Five terms maximum per page, each explained with a real example.
4. A 3–4 minute demo script and ten likely jury questions with short answers.
5. What the algorithm does versus what the LLM does versus what MCP does.
6. How to rerun experiments and what their limitations are.

Use short sentences and ordinary verbs. No unexplained «оркестрация», «provenance», «reconciliation», «event sourcing», «multi-tenant» in main student-facing text. Those terms are acceptable in technical references only when truly needed.

## Definition of done after each task

```
Implemented: <specific end-to-end behavior>
Verified: <exact commands and their results>
Browsers/screens: <actual checks performed, or NOT CHECKED>
Files changed: <paths>
Student explanation: <2 simple sentences>
Limitations: <facts, no excuses>
Next: <smallest useful task>
```

If tests are blocked, state exactly why. Never mark a feature done merely because UI renders or a TODO checkbox was edited.
