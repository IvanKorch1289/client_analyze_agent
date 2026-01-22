# ADR-001: Use Tarantool instead of Redis for caching

## Status
Accepted

## Context

The Client Analysis Agent requires a high-performance caching layer for:
- Caching API responses from external data sources (DaData, InfoSphere, Casebook)
- Storing analysis reports with 30-day retention
- Managing conversation threads and history
- Providing persistent storage for audit logs

We needed to choose between Redis (industry standard) and Tarantool (Lua-scriptable in-memory database).

## Decision

We chose **Tarantool** as the primary caching and storage solution.

### Key reasons:

1. **Lua Scripting**: Tarantool allows complex operations to be executed server-side via Lua procedures, reducing network round-trips and enabling atomic multi-step operations.

2. **Native Persistence**: Unlike Redis, Tarantool provides true ACID transactions with WAL (Write-Ahead Log) and snapshots out of the box, without requiring Redis AOF/RDB configuration.

3. **Typed Spaces**: Tarantool spaces (tables) have defined schemas with indexes, providing better data organization than Redis key-value model.

4. **Memory Efficiency**: Tarantool's msgpack serialization combined with built-in compression provides better memory efficiency for our JSON-heavy workloads.

5. **Russian Market**: Tarantool is developed by VK (Mail.ru Group) and has strong support in the Russian market, which aligns with our target audience.

## Consequences

### Positive:
- Complex caching logic can be implemented server-side (e.g., TTL-based eviction with custom rules)
- Better data organization with multiple spaces (cache, reports, threads, persistent)
- Native support for secondary indexes improves query flexibility
- Strong consistency guarantees for audit logs

### Negative:
- Smaller community compared to Redis
- Fewer client libraries and tools
- Team needs to learn Lua for advanced operations
- Harder to find DevOps expertise for production support

### Mitigations:
- Implemented in-memory fallback when Tarantool is unavailable
- Documented all Lua procedures with examples
- Created comprehensive repository abstractions to hide Tarantool specifics

## Alternatives Considered

### Redis
- **Pros**: Industry standard, huge ecosystem, easy to find expertise
- **Cons**: Less flexible for complex operations, persistence requires careful configuration
- **Rejected because**: Our use case benefits significantly from Lua scripting and typed spaces

### PostgreSQL with pg_cron
- **Pros**: Full SQL support, excellent tooling
- **Cons**: Higher latency for cache operations, overkill for our use case
- **Rejected because**: Not optimized for high-frequency cache access patterns

### In-Memory Only (Python dict with TTL)
- **Pros**: Simplest solution, no external dependencies
- **Cons**: No persistence, lost on restart, no horizontal scaling
- **Rejected because**: Reports need 30-day retention, audit logs must survive restarts
