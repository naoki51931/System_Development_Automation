# API performance breakdown — 2026-08-04 UTC

Local-only test on 2 logical CPUs and 3.7 GiB RAM. `APP_PERFORMANCE_TIMING=true`
enabled sanitized `Server-Timing`; production defaults to disabled. SQL text and
secrets are never emitted.

| Users | Duration | Requests | Errors | p50 | p95 | p99 |
|---:|---:|---:|---:|---:|---:|---:|
| 5 | 60 s | 767 | 0 | 16 ms | 62 ms | 180 ms |
| 10 | 60 s | 1,524 | 0 | 19 ms | 82 ms | 240 ms |
| 25 | 60 s | 3,337 | 0 | 48 ms | 260 ms | 500 ms |
| 50 | 60 s | 4,301 | 0 | 270 ms | 620 ms | 1,000 ms |

Final 50-user run: Locust was limited to 0.5 CPU; frontend/worker were stopped for
the isolation comparison. One Uvicorn worker is retained because the host has one
physical core/two threads; more workers increase DB connections/context switches.

| Category / endpoint | count | p50 | p95 | p99 | server | query | auth | authorization | response | SQL |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| normal / project detail | 557 | 256 | 609 | 1,019 | 262 | 54 | 81 | 25 | 209 B | 4 |
| normal / me | 50 | 307 | 432 | 563 | 264 | 21 | 106 | 0 | 170 B | 2 |
| normal / login | 50 | 295 | 424 | 488 | 252 | 10 | 0 | 0 | 147 B | 1 |
| list / projects | 1,625 | 273 | 684 | 1,025 | 278 | 56 | 89 | 26 | 10,530 B | 4 |
| list / notifications | 997 | 268 | 598 | 1,057 | 263 | 54 | 73 | 25 | 16,612 B | 4 |
| list / artifacts | 522 | 270 | 584 | 872 | 263 | 57 | 78 | 26 | 31 B | 4 |
| list / reviews | 513 | 269 | 565 | 726 | 257 | 57 | 72 | 27 | 31 B | 4 |

Normal API is **FAIL** (609 ms >500 ms). List API is **PASS** (worst 684 ms <1 s).
Error rate is **PASS** at 0%. The server/client p95 gap shows CPU queue contention;
db_session initialization averaged below 0.1 ms. Raw data is in the sibling JSON
and Locust CSV files.
