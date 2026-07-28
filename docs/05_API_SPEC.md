# Prediction Market Research Platform
## API Specification
- Document: `05_API_SPEC.md`
- Version: 1.0
- Status: Governing API contract
- Related documents:
  - `01_ARCHITECTURE.md`
  - `02_ENGINEERING.md`
  - `03_SCHEMAS.md`
  - `04_IMPLEMENTATION.md`
- Primary protocol: HTTPS
- Streaming protocols: WebSocket and Server-Sent Events
- Payload format: JSON
- Character set: ASCII only
- Intended audience: backend developers, operator-interface developers, SDK authors, reviewers, and coding agents
---
## Document Authority
This document defines the application programming interfaces for the Prediction
Market Research Platform, abbreviated as PMRP.
It governs:
- HTTP endpoint structure
- API versioning
- authentication
- authorization
- request and response envelopes
- error contracts
- pagination
- idempotency
- rate limiting
- operator controls
- research endpoints
- strategy endpoints
- order endpoints
- risk endpoints
- portfolio endpoints
- replay endpoints
- simulation endpoints
- matching endpoints
- WebSocket streams
- Server-Sent Event streams
- OpenAPI publication
- compatibility requirements
The API is an application boundary.
It does not expose concrete exchange clients, database sessions, internal task
objects, secrets, or raw implementation details.
---
# 1. Executive Summary
PMRP provides a versioned operator and research API.
The API is primarily intended for:
- operator dashboards
- command-line tools
- research utilities
- internal SDKs
- automation
- controlled service-to-service access
The first API version should remain intentionally narrow.
It should expose stable platform concepts:
- markets
- market data
- strategies
- signals
- orders
- fills
- positions
- balances
- risk
- replay
- simulation
- market relationships
- system health
The API should not mirror exchange APIs directly.
The canonical API uses the schemas defined in `03_SCHEMAS.md`.
API design priorities are:
- safety
- explicitness
- auditability
- idempotency
- predictable errors
- strong pagination
- bounded payload size
- backward compatibility
- secure operator actions
# 2. API Surface Categories
The API is divided into four logical surfaces.
## 2.1 Read API
Provides read-only access to:
- health
- markets
- order books
- trades
- strategies
- orders
- fills
- positions
- balances
- risk state
- replay sessions
- simulation sessions
- market relationships
## 2.2 Operator Control API
Provides controlled actions:
- start strategy
- stop strategy
- activate kill switch
- release kill switch
- trigger reconciliation
- start replay
- pause replay
- resume replay
- cancel replay
- start paper runtime
- stop paper runtime
- enable approved live runtime
## 2.3 Research API
Provides:
- dataset metadata
- replay configuration
- experiment metadata
- simulation configuration
- result retrieval
- export initiation
## 2.4 Streaming API
Provides:
- canonical events
- order updates
- fill updates
- strategy health
- risk alerts
- portfolio changes
- replay progress
- system health
# 3. Base URL and Versioning
Recommended base paths:
```text
https://host.example/api/v1
wss://host.example/api/v1/ws
https://host.example/api/v1/events
```
Versioning uses a path prefix.
Example:
```text
/api/v1/markets
```
A new major API version is required for breaking changes.
Backward-compatible additions may remain within the current major version.
The server should return:
```http
PMRP-API-Version: 1
PMRP-Schema-Version: 1
```
where useful.
Clients should not infer version from deployment environment.
# 4. Media Types
Default request and response media type:
```text
application/json
```
Optional versioned vendor media type:
```text
application/vnd.pmrp.v1+json
```
JSON Lines export media type:
```text
application/x-ndjson
```
Parquet export media type:
```text
application/vnd.apache.parquet
```
Server-Sent Events media type:
```text
text/event-stream
```
Clients shall send:
```http
Accept: application/json
Content-Type: application/json
```
for normal JSON requests.
# 5. Authentication
## 5.1 Supported Authentication
Recommended initial support:
- bearer access token
- service token
- optional mutual TLS for service-to-service traffic
Example:
```http
Authorization: Bearer <token>
```
## 5.2 Token Properties
Tokens should identify:
- subject
- issuer
- audience
- environment
- roles
- scopes
- issued time
- expiry
## 5.3 Token Restrictions
Tokens must not be accepted across environments.
A staging token must not authorize production.
## 5.4 Authentication Errors
Missing or invalid credentials return:
```http
401 Unauthorized
```
The error response must not reveal sensitive validation details.
# 6. Authorization
Authorization uses roles and scopes.
Recommended roles:
- viewer
- researcher
- strategy_operator
- risk_operator
- execution_operator
- administrator
- service
Recommended scopes:
```text
health:read
markets:read
market_data:read
strategies:read
strategies:control
signals:read
orders:read
orders:cancel
portfolio:read
risk:read
risk:control
replay:read
replay:control
simulation:read
simulation:control
matching:read
matching:review
admin:read
admin:write
```
Authorization is checked after authentication and before business execution.
A valid token without sufficient scope returns:
```http
403 Forbidden
```
# 7. Request Identity and Correlation
Clients should send:
```http
X-Correlation-ID: corr_...
```
If absent, the server creates one.
The server returns:
```http
X-Correlation-ID: corr_...
X-Request-ID: req_...
```
All logs, traces, audit records, commands, and events produced by the request
should carry the correlation ID.
The request ID identifies one HTTP request.
The correlation ID may span multiple requests and events.
# 8. Idempotency
Mutating endpoints that may produce business effects require:
```http
Idempotency-Key: unique-client-generated-value
```
Required for:
- starting strategy
- stopping strategy
- activating kill switch
- releasing kill switch
- triggering reconciliation
- starting replay
- starting simulation
- submitting an approved manual order, if supported
- cancelling an order
- approving market relationship
- live-mode activation
The server stores:
- idempotency key
- authenticated subject
- endpoint
- request hash
- response
- status
- expiry
Reusing the same key with the same request returns the original result.
Reusing the same key with a different request returns:
```http
409 Conflict
```
# 9. Standard Request Headers
Common request headers:
```text
Authorization
Accept
Content-Type
X-Correlation-ID
Idempotency-Key
If-Match
If-None-Match
X-PMRP-Environment
```
`X-PMRP-Environment` may be required for dangerous actions.
Example:
```http
X-PMRP-Environment: production
```
The server must verify that the header matches the authenticated environment and
the target deployment.
# 10. Standard Response Headers
Common response headers:
```text
X-Request-ID
X-Correlation-ID
PMRP-API-Version
ETag
Cache-Control
Retry-After
RateLimit-Limit
RateLimit-Remaining
RateLimit-Reset
```
Sensitive responses should use:
```http
Cache-Control: no-store
```
# 11. HTTP Status Codes
Recommended status usage:
```text
200 OK                    successful read or completed action
201 Created               resource created
202 Accepted              asynchronous action accepted
204 No Content            successful action without response body
304 Not Modified          conditional read
400 Bad Request           malformed request
401 Unauthorized          authentication missing or invalid
403 Forbidden             insufficient authorization
404 Not Found             resource absent
409 Conflict              state or idempotency conflict
412 Precondition Failed   ETag or version mismatch
415 Unsupported Media     unsupported content type
422 Unprocessable Entity  schema-valid request violates business validation
429 Too Many Requests     rate limit reached
500 Internal Error        unexpected server failure
502 Bad Gateway           upstream dependency invalid response
503 Service Unavailable   dependency or safety state unavailable
504 Gateway Timeout       upstream timeout
```
# 12. Standard Error Response
All error responses use:
```json
{
  "error_id": "err_01j00000000000000000000000",
  "status": 422,
  "code": "RISK_STATE_STALE",
  "message": "The request cannot be completed because required risk state is stale.",
  "details": [
    {
      "field": "market_id",
      "code": "MARKET_DATA_STALE",
      "message": "Market data exceeds the configured freshness limit."
    }
  ],
  "correlation_id": "corr_01j00000000000000000000000",
  "occurred_at": "2026-07-27T15:00:00Z"
}
```
Error codes are stable machine-readable strings.
Messages are human-readable and may improve over time.
# 13. Validation Errors
Schema validation errors use:
```http
422 Unprocessable Entity
```
Example:
```json
{
  "error_id": "err_01j00000000000000000000000",
  "status": 422,
  "code": "VALIDATION_FAILED",
  "message": "The request failed validation.",
  "details": [
    {
      "field": "limit_price",
      "code": "DECIMAL_REQUIRED",
      "message": "limit_price must be encoded as a decimal string."
    }
  ],
  "correlation_id": "corr_01j00000000000000000000000",
  "occurred_at": "2026-07-27T15:00:00Z"
}
```
# 14. Pagination
Cursor pagination is the default.
Request:
```text
GET /api/v1/orders?limit=100&cursor=opaque-token
```
Response:
```json
{
  "items": [],
  "page": {
    "next_cursor": null,
    "previous_cursor": null,
    "returned_count": 0,
    "has_more": false
  },
  "correlation_id": "corr_..."
}
```
Rules:
- default limit: 100
- maximum limit: 1000
- cursor is opaque
- cursor binds filters and sort order
- invalid or expired cursor returns 400
- ordering is stable
# 15. Filtering
Filters use query parameters.
Examples:
```text
?exchange=kalshi
?market_id=mkt_...
?status=open
?strategy_id=strat_...
?created_after=2026-07-01T00:00:00Z
?created_before=2026-07-31T00:00:00Z
```
Repeated values may be supported:
```text
?status=open&status=halted
```
Filter semantics must be documented per endpoint.
Unknown filters should return 400 rather than be silently ignored.
# 16. Sorting
Sort syntax:
```text
?sort=-created_at,market_id
```
Rules:
- leading `-` means descending
- no prefix means ascending
- only documented fields are allowed
- a stable unique tie-break field is always appended internally
- default ordering is documented per endpoint
# 17. Field Selection
Optional sparse field selection may use:
```text
?fields=market_id,title,status
```
The server may ignore unsupported sparse selection in version 1.
If implemented, required identity and correlation fields may still be returned.
Sensitive fields must never become available solely because a client requests
them.
# 18. Conditional Requests
Read resources may return an ETag.
Example:
```http
ETag: "market-mkt_123-v8"
```
Clients may send:
```http
If-None-Match: "market-mkt_123-v8"
```
Mutating versioned resources may require:
```http
If-Match: "strategy-strat_123-v4"
```
Version mismatch returns:
```http
412 Precondition Failed
```
# 19. Rate Limiting
Rate limits may be applied by:
- subject
- token
- IP range
- endpoint group
- environment
Responses may include:
```http
RateLimit-Limit: 120
RateLimit-Remaining: 17
RateLimit-Reset: 38
```
When limited:
```http
429 Too Many Requests
Retry-After: 38
```
Dangerous control endpoints should use stricter limits than read endpoints.
# 20. Health Endpoints
## GET /api/v1/health/live
Process liveness.
Response:
```json
{
  "alive": true,
  "service": "pmrp-operator-api",
  "checked_at": "2026-07-27T15:00:00Z"
}
```
## GET /api/v1/health/ready
Service readiness.
Response includes dependency health and trading impact.
## GET /api/v1/health/trading
Returns whether the environment is ready to trade.
This endpoint must not enable trading.
# 21. System Information Endpoint
## GET /api/v1/system/info
Returns:
- platform version
- API version
- schema bundle version
- code commit
- dependency lock hash
- environment
- build time
- enabled capabilities
Example:
```json
{
  "platform_version": "0.9.0",
  "api_version": "1",
  "schema_bundle_version": "1",
  "code_commit": "abcdef123456",
  "dependency_lock_hash": "sha256:lock123",
  "environment": "shadow",
  "build_time": "2026-07-27T12:00:00Z",
  "capabilities": [
    "markets.read",
    "orders.read",
    "replay.control"
  ]
}
```
# 22. Exchange Health Endpoints
## GET /api/v1/exchanges
Returns configured exchanges and health summaries.
## GET /api/v1/exchanges/{exchange}
Returns adapter capabilities and health.
## GET /api/v1/exchanges/{exchange}/rate-limits
Returns current rate-limit status.
Sensitive credential information is never returned.
# 23. Exchange Reconciliation Endpoint
## POST /api/v1/exchanges/{exchange}/accounts/{account_id}/reconcile
Scope:
```text
risk:control
```
Headers:
```text
Idempotency-Key
X-PMRP-Environment
```
Request:
```json
{
  "include_fills_since": "2026-07-27T00:00:00Z",
  "reason": "Post-reconnect validation"
}
```
Response:
```http
202 Accepted
```
with reconciliation resource.
# 24. Market List Endpoint
## GET /api/v1/markets
Filters:
- exchange
- status
- category
- outcome_type
- updated_after
- closes_before
- search
Default sort:
```text
-updated_at,market_id
```
Response:
```json
{
  "items": [],
  "page": {
    "next_cursor": null,
    "previous_cursor": null,
    "returned_count": 0,
    "has_more": false
  },
  "correlation_id": "corr_..."
}
```
# 25. Market Detail Endpoint
## GET /api/v1/markets/{market_id}
Returns:
- market
- outcomes
- contracts
- lifecycle summary
- precision rules
- current health
- exchange references
Optional query:
```text
?include=outcomes,contracts,relationships
```
Not-found response:
```http
404 Not Found
```
# 26. Market Outcomes Endpoint
## GET /api/v1/markets/{market_id}/outcomes
Returns all canonical outcomes.
The response order is stable by outcome index.
# 27. Market Contracts Endpoint
## GET /api/v1/markets/{market_id}/contracts
Returns tradeable contracts and precision rules.
This endpoint is read-only.
# 28. Order Book Snapshot Endpoint
## GET /api/v1/markets/{market_id}/order-book
Query parameters:
- contract_id
- depth
- exchange
Maximum depth is deployment configured.
Response includes:
- sequence
- receive time
- validity
- bids
- asks
- data age
- quality flags
If the local book is invalid:
```http
503 Service Unavailable
```
or a response with `is_valid=false`, according to endpoint policy.
# 29. Market Trades Endpoint
## GET /api/v1/markets/{market_id}/trades
Filters:
- contract_id
- exchange
- occurred_after
- occurred_before
Default order:
```text
-exchange_occurred_at,-trade_id
```
# 30. Market Statistics Endpoint
## GET /api/v1/markets/{market_id}/statistics
Returns derived statistics.
Every derived metric should include:
- measured_at
- calculation_version
- data quality
# 31. Market Lifecycle Endpoint
## GET /api/v1/markets/{market_id}/lifecycle
Returns status transition history.
This is useful for:
- replay
- incident analysis
- settlement review
# 32. Settlement Endpoint
## GET /api/v1/markets/{market_id}/settlement
Returns current settlement state and correction lineage.
If unresolved, the endpoint still returns a resource with:
```json
{
  "status": "unresolved"
}
```
# 33. Strategy List Endpoint
## GET /api/v1/strategies
Filters:
- state
- strategy_type
- environment
- health_status
Response includes strategy instances, not secret configuration.
# 34. Strategy Detail Endpoint
## GET /api/v1/strategies/{strategy_id}
Returns:
- identity
- type
- version
- state
- health
- approved configuration version
- capital allocation
- runtime statistics
Private strategy source code is not returned.
# 35. Strategy Configuration Endpoint
## GET /api/v1/strategies/{strategy_id}/configuration
Scope:
```text
strategies:read
```
Returns redacted typed configuration.
Sensitive fields are omitted or replaced with references.
# 36. Start Strategy Endpoint
## POST /api/v1/strategies/{strategy_id}/start
Scope:
```text
strategies:control
```
Headers:
```text
Idempotency-Key
If-Match
X-PMRP-Environment
```
Request:
```json
{
  "configuration_version": 4,
  "reason": "Approved shadow trial"
}
```
Responses:
- 202 accepted
- 409 invalid lifecycle state
- 412 version mismatch
- 422 configuration invalid
- 503 dependency unavailable
# 37. Stop Strategy Endpoint
## POST /api/v1/strategies/{strategy_id}/stop
Request:
```json
{
  "reason": "Operator requested shutdown",
  "cancel_open_orders": true
}
```
Stopping is normally asynchronous.
Response:
```http
202 Accepted
```
# 38. Strategy Health Endpoint
## GET /api/v1/strategies/{strategy_id}/health
Returns:
- lifecycle state
- health status
- last event time
- last signal time
- queue depth
- failure count
- trading impact
# 39. Strategy Signals Endpoint
## GET /api/v1/strategies/{strategy_id}/signals
Filters:
- market_id
- signal_type
- created_after
- valid_at
Signals are immutable read resources.
# 40. Global Signal Endpoint
## GET /api/v1/signals
Allows research and operations to query signals across strategies.
Default access should be read-only.
Signal metadata may be confidential depending on strategy policy.
# 41. Order List Endpoint
## GET /api/v1/orders
Filters:
- exchange
- account_id
- strategy_id
- market_id
- status
- created_after
- created_before
Default order:
```text
-created_at,-order_id
```
# 42. Order Detail Endpoint
## GET /api/v1/orders/{order_id}
Returns:
- canonical order
- state transition history
- fills
- risk decision reference
- signal references
- exchange references
- reconciliation state
# 43. Order Transition Endpoint
## GET /api/v1/orders/{order_id}/transitions
Returns ordered state transitions.
Default order:
```text
aggregate_version_after,occurred_at
```
# 44. Order Fills Endpoint
## GET /api/v1/orders/{order_id}/fills
Returns all fills applied to the order.
Duplicate exchange fill identifiers should not appear more than once.
# 45. Cancel Order Endpoint
## POST /api/v1/orders/{order_id}/cancel
Scope:
```text
orders:cancel
```
Headers:
```text
Idempotency-Key
X-PMRP-Environment
```
Request:
```json
{
  "reason": "Operator risk reduction"
}
```
Responses:
- 202 accepted
- 409 order terminal
- 404 not found
- 503 exchange unavailable
# 46. Manual Order Submission
Manual live order submission should be disabled by default.
If supported:
## POST /api/v1/orders
Requirements:
- execution operator scope
- explicit environment
- idempotency key
- full risk evaluation
- audit
- configured feature flag
The endpoint must accept an order intent, not an already approved order.
Risk cannot be bypassed.
# 47. Fill List Endpoint
## GET /api/v1/fills
Filters:
- exchange
- account_id
- order_id
- market_id
- occurred_after
- occurred_before
Default order:
```text
-exchange_occurred_at,-fill_id
```
# 48. Portfolio Endpoint
## GET /api/v1/portfolio
Returns an aggregate portfolio snapshot for authorized accounts.
Query parameters may include:
- exchange
- account_id
- strategy_id
- currency
The response should state the mark policy used.
# 49. Position List Endpoint
## GET /api/v1/positions
Filters:
- exchange
- account_id
- strategy_id
- market_id
- nonzero_only
The API should distinguish exchange position from strategy attribution when both
are available.
# 50. Position Detail Endpoint
## GET /api/v1/positions/{position_id}
Returns:
- current position
- source fills
- PnL
- fees
- settlement state
- reconciliation status
# 51. Balance Endpoint
## GET /api/v1/balances
Returns available, reserved, and total balances.
Scope may restrict full account identifiers.
The endpoint must state capture time.
# 52. PnL Endpoint
## GET /api/v1/pnl
Query parameters:
- starts_at
- ends_at
- strategy_id
- exchange
- market_id
- mark_policy
Returns attribution components:
- realized trading PnL
- unrealized change
- fees
- rebates
- settlement
- slippage
- total
# 53. Risk Status Endpoint
## GET /api/v1/risk/status
Returns:
- global risk health
- active kill switches
- stale dependencies
- recent breaches
- trading gate status
- limit utilization summary
# 54. Risk Limits Endpoint
## GET /api/v1/risk/limits
Filters:
- scope
- scope_id
- rule_id
- enabled
Sensitive production limits may require elevated scope.
# 55. Risk Decision Endpoint
## GET /api/v1/risk/decisions/{risk_decision_id}
Returns:
- decision
- input snapshot
- rule results
- approved modifications
- order reference
# 56. Risk Decision List Endpoint
## GET /api/v1/risk/decisions
Filters:
- status
- strategy_id
- market_id
- rule_id
- evaluated_after
- evaluated_before
# 57. Risk Breach Endpoint
## GET /api/v1/risk/breaches
Filters:
- severity
- scope
- active
- detected_after
Critical breaches should also be available through streaming alerts.
# 58. Kill Switch List Endpoint
## GET /api/v1/risk/kill-switches
Returns active and recently released kill switches.
Scope:
```text
risk:read
```
# 59. Activate Kill Switch Endpoint
## POST /api/v1/risk/kill-switches/activate
Scope:
```text
risk:control
```
Headers:
```text
Idempotency-Key
X-PMRP-Environment
```
Request:
```json
{
  "scope": "strategy",
  "scope_id": "strat_fed_value_v1",
  "reason": "Unexpected fill behavior"
}
```
Response:
```http
201 Created
```
The server should begin containment before returning when feasible.
# 60. Release Kill Switch Endpoint
## POST /api/v1/risk/kill-switches/{kill_switch_id}/release
Request:
```json
{
  "reason": "Reconciliation completed and incident reviewed"
}
```
Release may fail with 409 when required recovery conditions are not satisfied.
# 61. Reconciliation List Endpoint
## GET /api/v1/reconciliations
Filters:
- exchange
- account_id
- status
- started_after
Returns reconciliation summaries.
# 62. Reconciliation Detail Endpoint
## GET /api/v1/reconciliations/{reconciliation_id}
Returns:
- status
- mismatches
- counts checked
- trading-gate result
- timing
# 63. Replay Session List Endpoint
## GET /api/v1/replays
Filters:
- state
- dataset_id
- created_by
- created_after
Returns replay session summaries.
# 64. Start Replay Endpoint
## POST /api/v1/replays
Scope:
```text
replay:control
```
Headers:
```text
Idempotency-Key
```
Request body is a ReplayManifest or a reference to an approved manifest.
Response:
```http
202 Accepted
```
with replay session resource.
# 65. Replay Detail Endpoint
## GET /api/v1/replays/{replay_session_id}
Returns:
- manifest
- state
- current replay time
- processed event count
- progress
- result checksum
- failure details
# 66. Pause Replay Endpoint
## POST /api/v1/replays/{replay_session_id}/pause
Requires replay control scope and idempotency key.
Response:
```http
202 Accepted
```
# 67. Resume Replay Endpoint
## POST /api/v1/replays/{replay_session_id}/resume
Returns 409 if the replay is not paused.
# 68. Seek Replay Endpoint
## POST /api/v1/replays/{replay_session_id}/seek
Request:
```json
{
  "seek_to": "2026-07-15T14:00:00Z"
}
```
Seek semantics must state whether downstream projections are rebuilt.
# 69. Cancel Replay Endpoint
## POST /api/v1/replays/{replay_session_id}/cancel
Cancellation is graceful and asynchronous.
Completed replay sessions cannot be cancelled.
# 70. Replay Result Endpoint
## GET /api/v1/replays/{replay_session_id}/result
Returns the typed ReplayResult.
If incomplete:
```http
409 Conflict
```
# 71. Replay Export Endpoint
## POST /api/v1/replays/{replay_session_id}/exports
Request:
```json
{
  "format": "jsonl",
  "include": [
    "signals",
    "orders",
    "fills",
    "portfolio"
  ]
}
```
Response is an asynchronous export resource.
The API should return a signed or controlled download reference, not local file
paths.
# 72. Simulation Session List Endpoint
## GET /api/v1/simulations
Returns simulation sessions with filters for:
- state
- replay_session_id
- configuration version
- created_after
# 73. Start Simulation Endpoint
## POST /api/v1/simulations
Request:
```json
{
  "replay_session_id": "rpl_...",
  "configuration": {
    "simulation_version": "1.0",
    "fill_model": "trade_through",
    "queue_model": "volume_ahead",
    "latency_model": "fixed",
    "fee_model": "exchange_configured",
    "rejection_model": "basic",
    "slippage_model": "fixed_bps",
    "settlement_model": "canonical",
    "random_seed": 20260727,
    "fixed_latency_ms": 75,
    "maker_fill_probability": null,
    "taker_slippage_bps": "10",
    "parameters": {}
  }
}
```
# 74. Simulation Detail Endpoint
## GET /api/v1/simulations/{simulation_session_id}
Returns:
- configuration
- state
- progress
- result checksum
- linked replay
# 75. Simulation Result Endpoint
## GET /api/v1/simulations/{simulation_session_id}/result
Returns simulation metrics and final portfolio.
# 76. Experiment List Endpoint
## GET /api/v1/experiments
Filters:
- owner
- strategy_version
- model_version
- approved_for_next_stage
- created_after
# 77. Experiment Detail Endpoint
## GET /api/v1/experiments/{experiment_id}
Returns:
- manifest
- result
- artifacts
- approval state
- notes
# 78. Dataset List Endpoint
## GET /api/v1/datasets
Returns approved replay and research datasets.
Metadata includes:
- dataset ID
- checksum
- time range
- event count
- schema versions
- license or source note
- redaction status
# 79. Dataset Detail Endpoint
## GET /api/v1/datasets/{dataset_id}
Does not return the full event archive inline.
Returns controlled artifact references and metadata.
# 80. Market Relationship List Endpoint
## GET /api/v1/market-relationships
Filters:
- source_market_id
- target_market_id
- relationship_type
- minimum_confidence
- review_status
# 81. Market Relationship Detail Endpoint
## GET /api/v1/market-relationships/{relationship_id}
Returns:
- relationship
- evidence
- candidate scores
- validator version
- human review status
# 82. Matching Candidate Endpoint
## GET /api/v1/matching/candidates
Scope:
```text
matching:read
```
Returns proposed relationships pending validation or review.
# 83. Approve Relationship Endpoint
## POST /api/v1/matching/candidates/{candidate_id}/approve
Scope:
```text
matching:review
```
Request:
```json
{
  "relationship_type": "equivalent",
  "valid_until": null,
  "review_note": "Settlement language and date match."
}
```
Requires idempotency and audit.
# 84. Reject Relationship Endpoint
## POST /api/v1/matching/candidates/{candidate_id}/reject
Request:
```json
{
  "reason_code": "SETTLEMENT_RULE_MISMATCH",
  "review_note": "The source markets use different resolution authorities."
}
```
# 85. Arbitrage Opportunity Endpoint
## GET /api/v1/arbitrage/opportunities
Filters:
- relationship_id
- minimum_net_edge
- active_at
- exchange
- status
This endpoint is read-only in the initial API.
# 86. Arbitrage Plan Endpoint
## GET /api/v1/arbitrage/plans/{plan_id}
Returns:
- opportunity
- legs
- policy
- reservations
- current leg state
- recovery state
# 87. Data Quality Findings Endpoint
## GET /api/v1/data-quality/findings
Filters:
- severity
- exchange
- market_id
- rule_id
- blocks_trading
- detected_after
This endpoint supports incident review and adapter debugging.
# 88. Dead Letter Endpoint
## GET /api/v1/dead-letters
Scope:
```text
admin:read
```
Returns metadata and safe payload references.
Raw sensitive payload content requires separate authorization.
# 89. Resolve Dead Letter Endpoint
## POST /api/v1/dead-letters/{dead_letter_id}/resolve
Scope:
```text
admin:write
```
Request:
```json
{
  "resolution_note": "Mapper corrected and event successfully replayed."
}
```
Resolution must not delete the original record.
# 90. Audit Records Endpoint
## GET /api/v1/audit
Filters:
- actor
- action
- scope
- scope_id
- requested_after
- result
Audit records are immutable.
# 91. Configuration Snapshot Endpoint
## GET /api/v1/configuration
Returns the active redacted configuration snapshot and hash.
Scope:
```text
admin:read
```
Secrets are never returned.
# 92. API Capability Endpoint
## GET /api/v1/capabilities
Returns the capabilities available to the authenticated caller.
Example:
```json
{
  "scopes": [
    "markets:read",
    "orders:read"
  ],
  "features": [
    "replay",
    "paper_trading"
  ],
  "environment": "shadow"
}
```
# 93. WebSocket Connection
Endpoint:
```text
GET /api/v1/ws
```
Authentication may use:
- Authorization header
- short-lived connection token
Do not place long-lived bearer tokens in query strings.
The WebSocket connection should begin with a server hello message.
# 94. WebSocket Server Hello
Example:
```json
{
  "type": "system.hello",
  "connection_id": "conn_01j00000000000000000000000",
  "api_version": "1",
  "heartbeat_interval_seconds": 20,
  "maximum_subscriptions": 100,
  "server_time": "2026-07-27T15:00:00Z"
}
```
# 95. WebSocket Subscribe Message
Client message:
```json
{
  "type": "subscribe",
  "request_id": "subreq_1",
  "channels": [
    {
      "name": "orders",
      "filters": {
        "strategy_id": "strat_fed_value_v1"
      }
    },
    {
      "name": "risk.alerts",
      "filters": {}
    }
  ]
}
```
# 96. WebSocket Subscription Acknowledgement
Server response:
```json
{
  "type": "subscription.accepted",
  "request_id": "subreq_1",
  "subscriptions": [
    {
      "subscription_id": "sub_1",
      "channel": "orders"
    },
    {
      "subscription_id": "sub_2",
      "channel": "risk.alerts"
    }
  ]
}
```
# 97. WebSocket Event Message
Example:
```json
{
  "type": "event",
  "subscription_id": "sub_1",
  "sequence": 145,
  "event": {
    "envelope": {
      "event_id": "evt_...",
      "event_type": "order.partially_filled",
      "schema_version": 1
    },
    "payload": {}
  }
}
```
The complete envelope and payload follow canonical schemas.
# 98. WebSocket Channels
Recommended channels:
```text
markets
market_data.order_books
market_data.trades
strategies
signals
orders
fills
portfolio
risk.alerts
risk.kill_switches
replays
simulations
system.health
data_quality
```
# 99. WebSocket Heartbeats
Server sends:
```json
{
  "type": "ping",
  "sent_at": "2026-07-27T15:00:20Z"
}
```
Client responds:
```json
{
  "type": "pong",
  "sent_at": "2026-07-27T15:00:20Z"
}
```
The server closes stale connections according to policy.
# 100. WebSocket Ordering
Each subscription has a monotonically increasing connection-local sequence.
The sequence supports gap detection.
It is not a global event order.
Clients detecting a gap should:
1. mark local stream state uncertain
2. request a fresh HTTP snapshot
3. resubscribe
# 101. WebSocket Backpressure
The server uses bounded per-connection buffers.
If a client is too slow:
- noncritical channels may be sampled
- critical channels may close the connection
- the client receives a terminal slow-consumer message where possible
Example:
```json
{
  "type": "system.slow_consumer",
  "action": "disconnect",
  "last_sequence": 145
}
```
# 102. WebSocket Errors
Example:
```json
{
  "type": "error",
  "request_id": "subreq_1",
  "code": "SUBSCRIPTION_LIMIT_EXCEEDED",
  "message": "The connection exceeds the maximum subscription count."
}
```
# 103. Server-Sent Events Endpoint
Endpoint:
```text
GET /api/v1/events
```
Query example:
```text
?channels=orders,risk.alerts&strategy_id=strat_...
```
SSE is appropriate for one-way operator dashboards.
Each event should include:
```text
id:
event:
data:
```
Reconnect uses `Last-Event-ID` where supported.
# 104. Streaming Snapshot Pattern
Clients should use:
1. HTTP snapshot
2. stream subscription
3. sequence validation
4. snapshot recovery on gap
Example:
```text
GET /orders/{id}
CONNECT orders stream
APPLY events after snapshot version
```
The API must document the snapshot-to-stream handoff semantics.
# 105. Asynchronous Operation Resources
Long-running operations return resource objects.
Examples:
- replay session
- simulation session
- export job
- reconciliation run
- strategy transition
An asynchronous response uses:
```http
202 Accepted
Location: /api/v1/replays/rpl_...
```
The resource exposes state and failure details.
# 106. Operation State Model
Common operation states:
```text
created
queued
running
paused
completed
failed
cancelled
```
Operation resources include:
- operation ID
- state
- created time
- started time
- completed time
- progress
- error reference
- correlation ID
# 107. Request Size Limits
The API should define maximum body sizes.
Recommended defaults:
- normal JSON request: 1 MB
- manifest request: 5 MB
- bulk metadata request: 10 MB
- direct raw archive upload: unsupported in version 1
Large datasets use object storage or multipart upload services.
# 108. Response Size Limits
List endpoints use pagination.
Order-book depth is bounded.
Large exports are asynchronous.
The API should not return:
- millions of events inline
- full raw archives inline
- large model binaries inline
- unbounded logs
# 109. Bulk Endpoints
Version 1 should minimize bulk mutation endpoints.
Possible read bulk endpoints:
- multiple market lookup
- multiple order lookup
- multiple health lookup
Bulk requests require per-item result status.
One item failure should not make success ambiguous.
# 110. Cache Policy
Public or low-sensitivity market metadata may use short-lived caching.
Sensitive resources use:
```http
Cache-Control: no-store
```
Order books should normally use:
```http
Cache-Control: no-cache
```
ETags may support conditional reads.
Operator controls are never cached.
# 111. Environment Safety
Every dangerous response should include environment.
Example:
```json
{
  "environment": "production"
}
```
Production control endpoints may require:
- environment header
- elevated scope
- recent authentication
- confirmation token
- idempotency key
The UI should display environment prominently.
# 112. Live Activation Endpoint
A live activation endpoint is optional and should be strongly protected.
## POST /api/v1/runtime/live/activate
Requirements:
- administrator or execution operator
- production environment
- all readiness checks pass
- reason
- idempotency
- audit
- optional dual approval
The endpoint should activate a preconfigured runtime, not accept arbitrary
strategy code or risk limits.
# 113. Live Deactivation Endpoint
## POST /api/v1/runtime/live/deactivate
This action should be easier to execute than activation.
It should:
- block new approvals
- begin configured cancellations
- preserve market-data collection
- emit audit records
# 114. Paper Runtime Endpoints
## POST /api/v1/runtime/paper/start
Starts a paper runtime.
## POST /api/v1/runtime/paper/stop
Stops a paper runtime.
## GET /api/v1/runtime/paper
Returns current paper sessions.
# 115. Shadow Runtime Endpoints
## POST /api/v1/runtime/shadow/start
## POST /api/v1/runtime/shadow/stop
## GET /api/v1/runtime/shadow
Shadow responses must clearly state:
```json
{
  "submits_live_orders": false
}
```
# 116. API Audit Requirements
Audit all mutating requests that affect:
- strategies
- risk
- kill switches
- replay
- simulation
- live runtime
- reconciliation
- market relationship review
- dead-letter resolution
- configuration
Audit records include:
- actor
- action
- request hash
- scope
- target
- result
- correlation ID
- time
# 117. API Logging Requirements
Log:
- request ID
- correlation ID
- method
- route template
- status
- latency
- authenticated subject
- environment
- response size
- error code
Do not log:
- bearer tokens
- private keys
- authorization headers
- full confidential request bodies
# 118. API Metrics
Recommended metrics:
```text
pmrp_api_requests_total
pmrp_api_request_duration_seconds
pmrp_api_response_bytes
pmrp_api_errors_total
pmrp_api_idempotency_replays_total
pmrp_api_rate_limit_rejections_total
pmrp_api_websocket_connections
pmrp_api_websocket_messages_total
pmrp_api_websocket_slow_consumer_total
pmrp_api_sse_connections
```
Labels should remain low cardinality.
# 119. API Health Dependencies
API readiness may depend on:
- database
- event bus
- configuration
- authorization provider
Trading readiness additionally depends on:
- adapters
- market-data freshness
- risk
- reconciliation
- kill switches
The operator API may remain available while trading is unavailable.
# 120. OpenAPI Requirements
Publish OpenAPI 3.1.
Recommended endpoints:
```text
/openapi.json
/docs
/redoc
```
Production documentation access may require authentication.
OpenAPI should include:
- schemas
- examples
- security schemes
- error responses
- pagination
- idempotency headers
- rate-limit headers
- environment requirements
# 121. OpenAPI Operation IDs
Operation IDs should be stable.
Examples:
```text
listMarkets
getMarket
getOrderBook
listStrategies
startStrategy
listOrders
cancelOrder
getPortfolio
getRiskStatus
activateKillSwitch
startReplay
getReplayResult
```
SDK generation depends on stable operation IDs.
# 122. SDK Design
A Python SDK may provide:
```python
client.markets.list(...)
client.markets.get(...)
client.orders.list(...)
client.orders.cancel(...)
client.risk.status(...)
client.replays.start(...)
client.stream.subscribe(...)
```
The SDK should:
- preserve Decimal
- preserve timezone-aware datetime
- expose typed models
- support idempotency keys
- propagate correlation IDs
- map API errors to typed exceptions
# 123. API Error Exception Mapping
Suggested SDK exception hierarchy:
```text
PmrpApiError
|
+-- AuthenticationError
+-- AuthorizationError
+-- NotFoundError
+-- ConflictError
+-- ValidationError
+-- RateLimitError
+-- ServiceUnavailableError
+-- TimeoutError
```
The original API error response remains available on the exception.
# 124. Backward Compatibility
Within API v1:
Allowed:
- new optional response field
- new endpoint
- new enum value only where clients are required to tolerate unknown values
- new optional request field
- new error code
Breaking:
- required field removal
- field rename
- unit change
- semantic change
- endpoint removal
- status-code meaning change
- required request field addition
Breaking changes require API v2 or a documented migration.
# 125. Deprecation
Deprecated endpoints return:
```http
Deprecation: true
Sunset: Wed, 31 Dec 2027 23:59:59 GMT
Link: </api/v2/resource>; rel="successor-version"
```
Deprecation documentation includes:
- replacement
- migration steps
- sunset date
- compatibility notes
# 126. Error Code Registry
Initial error categories:
```text
AUTHENTICATION_REQUIRED
AUTHENTICATION_INVALID
AUTHORIZATION_DENIED
VALIDATION_FAILED
RESOURCE_NOT_FOUND
IDEMPOTENCY_CONFLICT
VERSION_CONFLICT
INVALID_STATE_TRANSITION
DEPENDENCY_UNAVAILABLE
MARKET_DATA_STALE
RISK_REJECTED
KILL_SWITCH_ACTIVE
RECONCILIATION_REQUIRED
ORDER_TERMINAL
ORDER_STATE_UNKNOWN
REPLAY_NOT_READY
SIMULATION_NOT_READY
RATE_LIMITED
INTERNAL_ERROR
```
Each error code should be documented in a registry.
# 127. Security Requirements
The API must implement:
- TLS
- authentication
- authorization
- environment separation
- input validation
- output redaction
- audit
- rate limiting
- dependency timeouts
- security headers
- safe error messages
Recommended security headers:
```text
Strict-Transport-Security
X-Content-Type-Options
Content-Security-Policy
Referrer-Policy
```
Exact browser headers depend on deployment.
# 128. Cross-Origin Resource Sharing
CORS should be disabled by default.
If operator UI requires it:
- allow explicit origins
- allow explicit methods
- allow explicit headers
- disallow wildcard credentials
- separate environment origins
# 129. CSRF
Bearer-token APIs are less exposed to traditional cookie CSRF.
If browser cookies are used:
- use SameSite
- use CSRF tokens
- validate origin
- restrict dangerous methods
Authentication architecture must document the CSRF model.
# 130. Sensitive Response Handling
Sensitive endpoints should use:
```http
Cache-Control: no-store
Pragma: no-cache
```
Avoid returning:
- full account identifiers unless required
- private strategy parameters to unauthorized roles
- model artifact credentials
- raw exchange authentication responses
# 131. API Timeouts
The server should define endpoint budgets.
Examples:
- health read: 1 second
- normal read: 5 seconds
- control acceptance: 5 seconds
- long operation: return 202 quickly
- upstream exchange query: adapter-defined timeout
Do not keep an HTTP request open for a long replay or simulation.
# 132. Graceful Shutdown
During shutdown:
- stop accepting new control requests
- continue health endpoint with draining state
- finish safe in-flight reads
- reject new long operations
- close streams with a terminal message
- preserve audit records
# 133. Read Consistency
Read endpoints should document whether data is:
- strongly consistent
- transactionally current
- projection based
- eventually consistent
- snapshot based
Order and portfolio endpoints should expose projection version or update time.
# 134. Resource Versioning
Mutable resources include a version.
Examples:
- strategy configuration version
- kill-switch version
- order aggregate version
- market projection version
ETags should derive from the version.
Clients should use `If-Match` for critical updates.
# 135. API Resource Naming
Use plural nouns.
Good:
```text
/markets
/orders
/strategies
/replays
```
Use action subresources for controlled commands.
Good:
```text
/strategies/{id}/start
/orders/{id}/cancel
```
Avoid RPC-style query names such as:
```text
/doStartStrategy
```
# 136. Identifier Handling
Identifiers are path-safe opaque strings.
Clients must not parse prefixes for business logic.
The API validates prefix and format.
Unknown well-formed IDs return 404.
# 137. Decimal Encoding
All financial Decimal values are strings.
Correct:
```json
{
  "price": "0.43"
}
```
Incorrect:
```json
{
  "price": 0.43
}
```
OpenAPI schemas should describe these as strings with a decimal pattern.
# 138. Timestamp Encoding
All timestamps are ISO 8601 UTC.
Correct:
```text
2026-07-27T15:00:00.123456Z
```
Naive timestamps are rejected.
Clients should not send local timezone abbreviations.
# 139. Boolean Semantics
Use JSON booleans.
Do not encode booleans as:
- `"yes"`
- `"no"`
- `0`
- `1`
unless an external raw payload is being preserved.
# 140. Null Semantics
Use JSON null for absent optional values.
Do not omit required fields.
The API should document whether optional fields are omitted or returned as null.
Canonical response preference:
- include the field
- set null when absent
Consistency is more important than either choice.
# 141. Empty Collection Semantics
Return empty arrays rather than null for collections.
Correct:
```json
{
  "items": []
}
```
Avoid:
```json
{
  "items": null
}
```
# 142. API Example - Start Strategy
Request:
```http
POST /api/v1/strategies/strat_fed_value_v1/start
Authorization: Bearer token
Idempotency-Key: 8c6326ef-1e78-4e60-96e8-7dc986877b6c
X-PMRP-Environment: shadow
Content-Type: application/json
```
Body:
```json
{
  "configuration_version": 4,
  "reason": "Approved shadow run"
}
```
Response:
```http
202 Accepted
Location: /api/v1/strategies/strat_fed_value_v1
```
# 143. API Example - Activate Kill Switch
Request:
```http
POST /api/v1/risk/kill-switches/activate
Authorization: Bearer token
Idempotency-Key: d4221445-6d25-4a5a-97d0-bae9dd81d3e5
X-PMRP-Environment: production
Content-Type: application/json
```
Body:
```json
{
  "scope": "global",
  "scope_id": null,
  "reason": "Portfolio reconciliation mismatch"
}
```
# 144. API Example - Start Replay
Request:
```http
POST /api/v1/replays
Authorization: Bearer token
Idempotency-Key: 8e92f14d-863f-40ec-aac7-02ff2c3efddf
Content-Type: application/json
```
Response:
```http
202 Accepted
Location: /api/v1/replays/rpl_01j00000000000000000000000
```
# 145. API Example - Risk Rejection
```json
{
  "error_id": "err_01j00000000000000000000000",
  "status": 422,
  "code": "RISK_REJECTED",
  "message": "The order intent was rejected by risk policy.",
  "details": [
    {
      "field": "quantity",
      "code": "MARKET_POSITION_LIMIT",
      "message": "The resulting position would exceed the configured market limit."
    }
  ],
  "correlation_id": "corr_01j00000000000000000000000",
  "occurred_at": "2026-07-27T15:00:00Z"
}
```
# 146. API Example - Order Detail
```json
{
  "order": {
    "order_id": "ord_01j00000000000000000000000",
    "status": "partially_filled",
    "quantity": "10",
    "filled_quantity": "4",
    "remaining_quantity": "6",
    "limit_price": "0.43"
  },
  "transitions": [],
  "fills": [],
  "risk_decision_id": "risk_01j00000000000000000000000",
  "signal_ids": [
    "sig_01j00000000000000000000000"
  ],
  "correlation_id": "corr_01j00000000000000000000000"
}
```
# 147. API Example - Portfolio
```json
{
  "portfolio": {
    "portfolio_id": "portfolio_main",
    "captured_at": "2026-07-27T15:00:00Z",
    "positions": [],
    "balances": [],
    "realized_pnl": [],
    "unrealized_pnl": [],
    "gross_exposure": [],
    "net_exposure": [],
    "reconciliation_status": "healthy"
  },
  "mark_policy": "best_executable",
  "correlation_id": "corr_01j00000000000000000000000"
}
```
# 148. API Example - WebSocket Order Event
```json
{
  "type": "event",
  "subscription_id": "sub_orders_1",
  "sequence": 1024,
  "event": {
    "envelope": {
      "event_id": "evt_01j00000000000000000000000",
      "event_type": "order.filled",
      "schema_version": 1,
      "occurred_at": "2026-07-27T15:00:00.480000Z",
      "received_at": "2026-07-27T15:00:00.500000Z",
      "published_at": "2026-07-27T15:00:00.505000Z",
      "producer": "execution-service",
      "exchange": "kalshi",
      "market_id": "mkt_01j00000000000000000000000",
      "account_id": "acct_shadow",
      "strategy_id": "strat_fed_value_v1",
      "order_id": "ord_01j00000000000000000000000",
      "correlation_id": "corr_01j00000000000000000000000",
      "causation_id": "evt_previous",
      "trace_id": "trace-abc",
      "replay_session_id": null,
      "simulation_session_id": null,
      "quality_flags": [],
      "attributes": {}
    },
    "payload": {
      "order_id": "ord_01j00000000000000000000000"
    }
  }
}
```
# 149. API Testing Strategy
Test layers:
- schema tests
- handler unit tests
- authorization tests
- integration tests
- idempotency tests
- pagination tests
- OpenAPI validation
- WebSocket tests
- SSE tests
- end-to-end operator tests
Every mutating endpoint requires:
- success
- unauthorized
- forbidden
- invalid body
- idempotent replay
- idempotency conflict
- invalid state
- dependency unavailable
- audit verification
# 150. Contract Tests
API contract tests should verify:
- status codes
- response schemas
- required headers
- error schemas
- Decimal strings
- UTC timestamps
- cursor behavior
- ETag behavior
- idempotency behavior
- authorization behavior
- OpenAPI agreement
# 151. Authorization Test Matrix
```text
Endpoint                       Viewer  Researcher  Strategy Op  Risk Op  Admin
--------------------------------------------------------------------------------
GET /markets                   yes     yes         yes          yes      yes
GET /orders                    yes     yes         yes          yes      yes
POST /strategies/{id}/start    no      no          yes          no       yes
POST /kill-switches/activate   no      no          no           yes      yes
POST /replays                  no      yes         yes          no       yes
POST /live/activate            no      no          optional     optional yes
GET /audit                     no      no          no           optional yes
```
The actual policy should be centrally configured.
# 152. Idempotency Test Matrix
```text
Scenario                                Expected
------------------------------------------------------------
same key, same request                  original response
same key, different request             409 conflict
same key, different subject             separate namespace or reject
missing key on required endpoint        400
expired key                             treated according to retention policy
concurrent duplicate requests           one business effect
server restart                          retained result
```
# 153. Pagination Test Matrix
```text
Scenario                                Expected
------------------------------------------------------------
first page                              stable items
next cursor                             next items
same cursor repeated                    same items
filter changed with old cursor          400
invalid cursor                          400
deleted item between pages              stable cursor policy
new item between pages                  no duplicate under snapshot policy
limit above maximum                     422 or clamped by documented policy
```
# 154. WebSocket Test Matrix
```text
Scenario                                Expected
------------------------------------------------------------
valid connect                           hello
invalid token                           close unauthorized
subscribe valid channel                 accepted
subscribe forbidden channel             error
heartbeat                               connection remains open
missed heartbeat                        close
slow consumer                           warning or close
sequence increments                     yes
unsubscribe                             stops events
server shutdown                         terminal message
```
# 155. Performance Requirements
Initial API targets:
- health p95 below 100 ms
- common read p95 below 500 ms
- control acceptance p95 below 1 second
- stream delivery lag observable
- bounded memory per connection
- no unbounded list endpoint
- no synchronous long replay request
Targets are deployment dependent and should be measured.
# 156. Availability Behavior
The operator API should remain available when:
- one exchange is disconnected
- trading is halted
- replay worker is unavailable
Read responses should expose degraded state.
Control requests requiring unavailable dependencies return 503.
The API must not pretend a control succeeded when only request receipt succeeded.
# 157. API Implementation Packages
Recommended source layout:
```text
src/pmrp/operator_api/
|
+-- app.py
+-- dependencies.py
+-- auth.py
+-- authorization.py
+-- idempotency.py
+-- errors.py
+-- middleware.py
+-- pagination.py
+-- responses.py
+-- openapi.py
+-- routes/
|   +-- health.py
|   +-- system.py
|   +-- exchanges.py
|   +-- markets.py
|   +-- strategies.py
|   +-- orders.py
|   +-- portfolio.py
|   +-- risk.py
|   +-- replays.py
|   +-- simulations.py
|   +-- matching.py
|   +-- audit.py
|
+-- streaming/
    +-- websocket.py
    +-- sse.py
    +-- subscriptions.py
    +-- backpressure.py
```
# 158. Framework Guidance
A modern ASGI framework may be used.
Selection criteria:
- OpenAPI 3.1 support
- Pydantic integration
- async support
- dependency injection
- WebSocket support
- active maintenance
- security ecosystem
- testability
The framework must not become the domain layer.
# 159. Handler Design
Route handlers should be thin.
A handler should:
1. authenticate
2. authorize
3. parse and validate
4. call application service
5. map result
6. return response
Business logic belongs in application services.
Database sessions should not leak into response schemas.
# 160. Middleware Order
Recommended middleware order:
1. request ID
2. correlation ID
3. security headers
4. authentication
5. rate limiting
6. request size
7. structured logging
8. exception mapping
9. metrics
10. routing
Exact order depends on framework behavior.
# 161. API Service Interfaces
Handlers should depend on application protocols.
Example:
```python
class StrategyControlService(Protocol):
    async def start(
        self,
        *,
        strategy_id: str,
        configuration_version: int,
        actor: Actor,
        reason: str | None,
        idempotency_key: str,
    ) -> StrategyInstance:
        ...
```
This keeps HTTP concerns separate from business services.
# 162. API Transaction Boundaries
A mutating application service should own the transaction.
The HTTP handler should not manually coordinate multiple repositories.
Audit and command persistence should be included atomically where required.
# 163. API Event Publication
A successful mutating request may:
- persist command
- apply state change
- publish event
- return resource
If an outbox pattern is used, the API transaction writes the outbox record.
The handler must not claim event publication if only database commit succeeded
unless the response semantics explicitly represent acceptance.
# 164. Outbox Integration
Recommended for durable mutations:
```text
HTTP request
  |
application transaction
  |
business state + audit + outbox
  |
commit
  |
outbox publisher
  |
event bus
```
This avoids lost events after successful HTTP responses.
# 165. API Audit Correlation
Every audit record should reference:
- request ID
- correlation ID
- actor
- idempotency key
- route
- target resource
- resulting command ID
- resulting event ID where available
# 166. API Documentation Examples
Every endpoint should include:
- purpose
- required scope
- request headers
- path parameters
- query parameters
- request body
- success response
- error responses
- idempotency behavior
- environment restrictions
- example
# 167. API Change Review Checklist
```text
[ ] Endpoint belongs in the API surface.
[ ] Resource name follows conventions.
[ ] Authentication is defined.
[ ] Authorization scope is defined.
[ ] Idempotency requirement is defined.
[ ] Request schema exists.
[ ] Response schema exists.
[ ] Error codes are defined.
[ ] Pagination is bounded.
[ ] Decimal and time encoding are correct.
[ ] Environment safety is reviewed.
[ ] Audit behavior is defined.
[ ] OpenAPI is updated.
[ ] Contract tests exist.
[ ] Streaming impact is reviewed.
[ ] Backward compatibility is reviewed.
```
# 168. API Definition of Done
An endpoint is complete when:
- route exists
- request and response schemas exist
- OpenAPI is correct
- authentication works
- authorization works
- validation works
- errors are mapped
- idempotency is implemented if required
- audit is implemented if required
- metrics and logs exist
- unit tests pass
- integration tests pass
- contract tests pass
- documentation includes examples
- live safety is reviewed
# 169. Initial API Delivery Order
Recommended sequence:
1. health
2. system info
3. market reads
4. strategy reads
5. order reads
6. portfolio reads
7. risk reads
8. replay controls
9. strategy controls
10. reconciliation control
11. kill-switch controls
12. streaming
13. simulation
14. matching review
15. live runtime controls
# 170. API Version 1 Minimum Scope
Version 1 minimum:
- health
- system info
- exchanges
- markets
- order books
- strategies
- signals
- orders
- fills
- positions
- balances
- risk status
- kill switches
- reconciliations
- replays
- simulations
- WebSocket events
- audit reads
# 171. Deferred API Features
Defer until justified:
- GraphQL
- arbitrary SQL analytics
- public anonymous API
- user-defined webhook execution
- direct model artifact upload
- bulk live order submission
- unrestricted manual trading
- mobile push API
- external partner API
# 172. API Risk Register
Key risks:
- authorization misconfiguration
- environment confusion
- idempotency gaps
- stale projection reads
- oversized responses
- WebSocket slow consumers
- sensitive data leakage
- unsafe live controls
- inconsistent errors
- generated SDK incompatibility
Each risk requires tests and monitoring.
# 173. Final API Position
The PMRP API is an operator and research boundary.
It should expose the platform's canonical language without exposing its
infrastructure internals.
A good API makes safe operations obvious.
A good API makes dangerous operations explicit.
A good API makes errors machine-readable.
A good API makes every action auditable.
The API must remain usable while trading is unavailable.
It must never turn a degraded system into an apparently healthy one.
The correct API is not the one with the most endpoints.
It is the one that exposes the smallest complete set of stable, safe, and
observable capabilities.
