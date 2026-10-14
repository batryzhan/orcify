# ADR-001: Pure domain and a single application service

Status: accepted for prototype; 2026-10-14.

The research kernel must be reusable by every baseline without web/database/LLM
dependencies. `packages/gamo_ca` contains immutable Python dataclasses, graph
validation and pure planning. Standard-library types are the domain contract;
JSON Schema generation/decoding uses Pydantic in boundary tooling only.
`services/api` will translate request DTOs to the domain, enforce authorization,
and transact through explicit repositories. `apps/web` is reserved for React;
`packages/contracts` holds the minimal tested TS wire reader before UI work.
`packages/benchmark` will drive the same kernel from recorded fixtures.

Alternative: Pydantic/ORM domain objects or separate microservices. Rejected to
keep algorithm state immutable and independent of infrastructure. Trade-off:
boundary validation and schema export require explicit adapters. No queues,
Redis or UI are needed for the first kernel demonstration.
