# AI settings, artifact storage, review resolution, and concurrency

## Scope and safety

This phase runs only against local PostgreSQL, local filesystem storage (or a local S3-compatible service), and `MockAIProvider`. `OpenAIProviderStub`, `AnthropicProviderStub`, and `S3ArtifactStorageStub` are deliberately disabled and never perform network I/O. No API key or secret is persisted. A future production provider must obtain credentials at runtime from AWS Secrets Manager and must not log prompts or customer content.

## AI setting resolution

Settings are selected by the tuple `provider/model/operation_type` in this order:

1. project-specific row (`project_id` matches);
2. organization default row (`project_id IS NULL`);
3. safe code default (enabled, threshold 95, at most 3 revisions, JPY, zero rates).

Partial unique indexes enforce uniqueness separately for project rows and organization-default rows, including PostgreSQL NULL semantics. Rates are customer billing rates today; snapshot columns on `ai_runs` deliberately leave room for separate provider-cost snapshots in a later additive migration.

## Billing

All arithmetic uses Python `Decimal` and PostgreSQL `NUMERIC(18,8)`; no float is used.

```text
billed_minutes = (duration_ms + 59999) // 60000
calculated_cost =
    billed_minutes * minute_rate
  + input_tokens * token_input_rate
  + output_tokens * token_output_rate
```

A non-zero duration shorter than or equal to 60 seconds is one billed minute; 61 seconds is two. `minute_rate_snapshot`, `input_rate_snapshot`, and `output_rate_snapshot` are stored with `calculated_cost` and `estimated_cost`, so later setting changes cannot alter historical charges.

Only request SHA-256, prompt version, input/output token counts, duration, and sanitized error codes are persisted. Full prompts and customer secrets are not stored or logged.

## Artifact storage and upload

The server generates keys; a client path is never accepted:

```text
organizations/{organization_id}/projects/{project_id}/artifacts/{artifact_id}/versions/{version_id}/{safe_filename}
```

Absolute paths, separators, `..`, empty names, and traversal outside the configured root are rejected. Allowed MIME types are text/plain, text/markdown, application/json, application/pdf, and application/zip. The default limit is 25 MiB.

The flow is upload intent, opaque expiring upload URL, object upload, `head_object`, exact MIME/size/SHA-256 validation, then immutable `artifact_versions` insertion. The DB row is not finalized until the object exists. Local paths and internal storage keys are not returned by download APIs. Approved objects cannot be deleted.

## Review comment transitions

The service permits:

```text
open -> accepted -> resolved
open -> rejected
open -> resolved  (reviewer/admin role only)
```

Resolving records `resolved_at` and `resolved_by_user_id`. AI-authored comments can be resolved by humans. History rows are retained, critical unresolved comments block approval, and every action writes a sanitized `audit_logs` entry.

## Automatic revision

For an artifact in `revision_requested`, the local worker reads unresolved comments, creates an `ai_run`, calls `MockAIProvider.revise()`, writes a new object and immutable artifact version, calls the mock review, snapshots billing, and creates an AI review. Passing the resolved threshold moves the artifact to `human_reviewing`. A failing score repeats from the newly created content.

`workflow_jobs.attempt_count` and `max_attempts` bound the loop. Exhaustion produces `escalated` with `AI_RETRY_LIMIT_REACHED`; every attempt still retains its version, AI run, score, hashes, and cost. Critical comments are included in revision input.

## Optimistic locking and errors

SQLAlchemy version columns protect `projects`, `artifacts`, `reviews`, `ai_settings`, and `workflow_jobs`. Clients send the current aggregate version for state transitions; stale versions return HTTP 409 `VERSION_CONFLICT`, and SQLAlchemy updates include the old version in the WHERE clause. Append-only version and approval tables need no optimistic lock.

Common API codes are `INVALID_REQUEST`, `AUTHENTICATION_REQUIRED`, `PERMISSION_DENIED`, `RESOURCE_NOT_FOUND`, `VERSION_CONFLICT`, `INVALID_STATE_TRANSITION`, `FILE_TOO_LARGE`, `UNSUPPORTED_MEDIA_TYPE`, `HASH_MISMATCH`, `AI_RETRY_LIMIT_REACHED`, and `AI_PROVIDER_UNAVAILABLE`. Responses never include SQL, local paths, raw internal exceptions, prompts, or secrets.
