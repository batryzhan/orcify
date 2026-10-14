# ADR-003: Deterministic providers behind a port

Status: accepted design; concrete executor/provider due Phase 3; 2026-10-14.

A provider port will accept a task, confirmed scoped context and explicit limits,
and return content, input/output hashes, provider/model/prompt versions and usage.
Mock mode is the default and requires no key. Synthetic fixtures and clock values
are explicit. Mock estimates are SIMULATED; unknown paid usage/cost stays null.
Failures (timeout, schema error, quota) are typed outcomes, never successful output.
No provider may approve, confirm requirements or publish. Source text is data.

Real adapters remain opt-in with explicit permission for paid calls and enforced
budgets. Contract tests mock network calls; no billing in CI. Alternative: SDK calls
inside routes. Rejected for isolation, repeatability and hidden side effects.

Phase 2C persists optional provider/model/prompt identifiers and caller-supplied
measurement values with explicit missing/estimated/measured provenance. This is a
storage contract only; no real provider execution, token reporting, latency sampling,
or cost measurement has been implemented or claimed.
