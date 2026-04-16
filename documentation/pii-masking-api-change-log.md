# PII Masking API Change Log

## 2026-04-04

### Added

- Added `token_format` to `POST /v1/pii/mask`.
- Added three reversible output modes:
  - `opaque`
  - `typed`
  - `masked_readable`
- Added `token_metadata` to the text masking response.

### Behavior

- `opaque` keeps the legacy `__AICCEL_TOKEN_n__` placeholders for backward compatibility.
- `typed` returns semantic placeholders such as `__AICCEL_EMAIL_1__`.
- `masked_readable` returns partially visible masked values directly in `sanitized_text` and `tokenized_text`.

### Documentation

- Updated the integration guide in [pii-masking-api-integration.md](/C:/MY_PROJECTS/AICCEL/AICCEL_SAAS/documentation/pii-masking-api-integration.md) with:
  - request flag details
  - sample responses for all three token formats
  - updated code examples
  - caveats for masked-readable output

## 2026-04-07

### Added

- Added aggregate-only entity detection counts to usage analytics for:
  - `pii.masking`
  - `engine.pdf.mask`
- Added `entity_counts` to usage summary and usage event responses.
- Added Usage-page stats for detected entity types by scope and period.

### Privacy

- No raw detected values are stored in usage analytics.
- No original request text is stored in usage analytics.
- Only per-kind counts such as `email: 2` and `phone: 1` are persisted.

### Documentation

- Added [pii-usage-entity-stats.md](/C:/MY_PROJECTS/AICCEL/AICCEL_SAAS/documentation/pii-usage-entity-stats.md).
- Updated [pii-masking-api-integration.md](/C:/MY_PROJECTS/AICCEL/AICCEL_SAAS/documentation/pii-masking-api-integration.md) with the new usage analytics behavior.



### Endpoint split

- Added `POST /v1/pii/mask` as the dedicated public text PII masking endpoint.
- Added `POST /v1/sentinel/analyze` as the dedicated public Sentinel Shield endpoint.
- Removed `POST /v1/engine/security/process` from the public API surface after the split routes were in place.
- Updated in-app API docs and usage analytics labels so the UI shows `PII Masking` and `Sentinel Shield` instead of a shared `engine.security` label for new traffic. Historical rows may still retain the old label.
- Added [security-endpoint-split.md](/C:/MY_PROJECTS/AICCEL/AICCEL_SAAS/documentation/security-endpoint-split.md).
