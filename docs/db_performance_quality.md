# Local DB performance quality gate

Use `QUALITY_SCALE=0.01 python -m app.quality.seed_performance` for a small repeatable dataset. Scale 1.0 targets 10 organizations, 1,000 users, 5,000 projects, 100,000 chat messages, 100,000 notifications and 100,000 audit logs. Increase only after checking local disk/memory.

Run `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` for project, notification, chat, review and audit cursor queries and the Outbox claim query. Confirm tenant predicates, `(created_at,id)` stable cursor bounds, bounded `LIMIT`, expected composite indexes, no sequential scan at scaled volume, and short transactions. The worker claim must show `LockRows` and an index-supported candidate scan. Capture machine size, scale and JSON plans under `quality-results/`; local figures are not a production SLA.
