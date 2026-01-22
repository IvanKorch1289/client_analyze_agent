# Architecture Decision Records (ADR)

This directory contains Architecture Decision Records for the Client Analysis Agent project.

## What is an ADR?

An Architecture Decision Record (ADR) is a document that captures an important architectural decision made along with its context and consequences.

## ADR Index

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [ADR-001](001-tarantool-over-redis.md) | Use Tarantool instead of Redis for caching | Accepted | 2024-01 |
| [ADR-002](002-langgraph-orchestration.md) | Use LangGraph for multi-agent orchestration | Accepted | 2024-01 |
| [ADR-003](003-llm-fallback-chain.md) | LLM provider fallback chain strategy | Accepted | 2024-02 |
| [ADR-004](004-pii-protection-presidio.md) | Use Presidio for PII protection | Accepted | 2026-01 |
| [ADR-005](005-circuit-breaker-pattern.md) | Circuit breaker pattern for external services | Accepted | 2024-02 |

## ADR Template

When creating a new ADR, use the following template:

```markdown
# ADR-XXX: Title

## Status
[Proposed | Accepted | Deprecated | Superseded]

## Context
What is the issue that we're seeing that is motivating this decision?

## Decision
What is the change that we're proposing and/or doing?

## Consequences
What becomes easier or more difficult to do because of this change?

## Alternatives Considered
What other options were considered and why were they rejected?
```

## References

- [ADR GitHub Organization](https://adr.github.io/)
- [Michael Nygard's article on ADRs](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
