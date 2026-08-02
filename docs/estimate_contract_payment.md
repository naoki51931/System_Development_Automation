# Estimate, contract, payment, and maintenance billing

## Safety boundary

This phase uses local PostgreSQL and `MockPaymentProvider` only. `StripePaymentProviderStub` is network-disabled. It does not call Stripe, accept public webhooks, read Secrets Manager, send billing email, access AWS/RDS/S3, run Terraform, or delete resources. Production credentials and webhook secrets must be loaded at runtime from a secret manager and never persisted or logged.

## Estimate calculation

All amounts use Python `Decimal` and PostgreSQL `NUMERIC(18,8)`; float is rejected.

```text
item.amount = quantity × unit_price
subtotal = sum(non-tax item.amount)
tax_amount = subtotal × tax_rate
total_amount = subtotal + tax_amount
```

The initial tax policy is isolated in `calculate_tax()` and defaults to 10%. Only discount items may have a negative unit price. Quantity is never negative and a total below zero is rejected. Clients never provide authoritative line totals, subtotal, tax, contract amount, or payment amount.

Completed `ai_runs.calculated_cost` values become `ai_runtime` lines. Artifacts become `artifact_value` lines.

## Artifact value

A tenant or system `pricing_rules` row can override safe code defaults:

```text
base_price
× complexity_multiplier
× quality_multiplier
× (1 + screens×0.01 + APIs×0.02 + tables×0.015 + test cases×0.001)
```

Each line has an `artifact_pricing_snapshots` row containing the rule, prices, multipliers, counts, and result. Approved estimates and items are protected by services and PostgreSQL triggers, so later rules cannot alter history. Revisions create another estimate.

## Estimate and contract lifecycle

```text
estimate: draft → customer_review → approved
                           └──────→ rejected

contract: draft → awaiting_customer / awaiting_provider → active
```

Only an unexpired approved estimate can create a contract. Organization and project must match. Customer and provider acceptance record user and UTC time separately. The second acceptance activates the contract and audits the fixed `terms_version`. Electronic signatures are outside this phase.

## PaymentProvider and development payment

`PaymentProvider` defines customer, payment method, intent, subscription, invoice retry, status, and webhook boundaries. `MockPaymentProvider` supports deterministic `succeeded`, `failed`, and `processing`. The Stripe stub always returns a safe unavailable error and performs no I/O.

The server reads the immutable estimate total and compares any expected amount. Idempotency keys are mandatory and unique per organization/provider. Reusing a key returns the same intent; another live contract payment returns `DUPLICATE_PAYMENT`. A succeeded intent cannot be confirmed again. Only success moves the project to `requirements`.

Tables never contain card number, CVC, secret key, webhook secret, or raw provider response. Allowed method metadata is provider ID, brand, last four digits, and expiry month/year.

## Mock webhook idempotency

The mock endpoint requires authentication, organization membership, and an HMAC signature. It stores provider/event ID, type/status, SHA-256 payload hash, timestamps, retry count, and sanitized failure code. Raw payload is not persisted. Repeated IDs return `WEBHOOK_ALREADY_PROCESSED`. Stripe webhook reception remains disabled.

## Maintenance billing and delinquency

Local seed plans are `light`, `standard`, and `premium`. Maintenance requires an active maintenance contract and a project in `production` or `maintenance`.

```text
active
  → payment failure: past_due
  → day 7: retry boundary
  → day 30: grace_period
  → day 60: suspended
  → day 90: deletion_scheduled
  → create resource_deletion_request only
```

All boundaries use UTC. Payment recovery returns the contract to active and cancels unexecuted deletion requests.

`deletion_scheduled` never invokes AWS or Terraform. No code path moves requests to `executed`. Two distinct administrators are required for two approvals. Approval and contract acceptance are audited. Maintenance and payment events are append-only.

## Optimistic locking and errors

Estimates, contracts, payment intents, maintenance plans/contracts, pricing rules, subscriptions, and deletion requests use SQLAlchemy version columns. Stale transitions return HTTP 409 `VERSION_CONFLICT`.

Errors include `INVALID_AMOUNT`, `INVALID_CONTRACT_STATE`, `INVALID_ESTIMATE_STATE`, `PAYMENT_ACTION_FORBIDDEN`, `PAYMENT_RESOURCE_NOT_FOUND`, `DUPLICATE_PAYMENT`, `WEBHOOK_ALREADY_PROCESSED`, `ESTIMATE_EXPIRED`, `AMOUNT_MISMATCH`, `CONTRACT_NOT_ACTIVE`, and `PAYMENT_PROVIDER_UNAVAILABLE`. Responses do not expose SQL, card data, secrets, local details, or provider payloads.
