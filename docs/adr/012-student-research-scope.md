# ADR-012: Student research scope and infrastructure freeze

Status: accepted; 2026-10-14.

## Context

Orcify is developed by high-school students for Kazakhstan's Republican Scientific
Projects Competition. Earlier implementation planning had started to resemble a
commercial workflow product: it proposed expanded account and campaign features,
provider integrations, run-monitor UI, and enterprise-oriented hardening. Those
features do not establish the research hypothesis and would make the work harder for a
student to explain and defend. The repository already contains more infrastructure
than the scientific demonstration requires.

## Decision

Treat the project as a student research prototype. Prioritize a clear hypothesis, a
small explainable GAMO-CA algorithm, fair simple baselines, reproducible experiments,
measured observations, and limitations. Keep the existing FastAPI, PostgreSQL, Neo4j,
and read-only React explorer as frozen demonstration infrastructure. Extend them only
when required to run or explain an experiment or to preserve an existing safety
invariant.

Do not add SaaS/commercial features, enterprise identity or administration, production
infrastructure, broad UI features, paid AI providers, or external publishing. Before
adding any dependency, service, abstraction, or database table, document its direct
research need and a simpler alternative. A smaller experiment is preferred to a large
planned dataset when student annotation and review time is limited.

## Consequences

Phase 5 baseline experiments are the next research milestone. Proposed dataset sizes
are planning targets, not evidence that a dataset exists. Existing automated tests and
live integration checks support engineering correctness claims only; they are not
scientific performance results. The student should be able to explain every formula,
decision, metric, and limitation independently. No novelty, universal safety, or
performance-improvement claim is accepted without appropriate literature and measured
evidence.

README, TASK, limitations, and the experiment log define the operational boundary.
