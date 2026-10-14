# API boundary

FastAPI/Pydantic routes, authorization, repository adapters and transactions are
Phase 2. The pure domain under `packages/gamo_ca` imports none of these frameworks.
Generated JSON contracts are under `docs/api/schemas`; they are not OpenAPI routes.
