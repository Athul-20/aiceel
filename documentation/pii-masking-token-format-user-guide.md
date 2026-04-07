# PII Masking Token Format Update

This note explains the requirement that was implemented for the AICCEL text PII masking API, how to use it, what changed, and what the output looks like now.

Requirement reference:

- [AICCEL_API_TOKEN_FORMAT_REQUIREMENT.md](/C:/MY_PROJECTS/AICCEL/AICCEL_SAAS/saas-backend/user_req/AICCEL_API_TOKEN_FORMAT_REQUIREMENT.md)

## What Was Required

The goal was to improve reversible masking for LLM-based extraction workflows.

The old API returned opaque placeholders like:

- `__AICCEL_TOKEN_1__`
- `__AICCEL_TOKEN_2__`

That worked for privacy and reversible restore, but it was weak for downstream LLM extraction because the token did not tell the model whether the value was an email, phone number, person name, or something else.

The implemented requirement was:

- keep backward compatibility
- support semantically meaningful typed placeholders
- also support partially visible masked-readable output when explicitly requested
- keep reversible restore support through `token_map`
- document the new request and response contract clearly

## What Changed

The text PII endpoint below was updated:

- `POST /v1/pii/mask`

New request field:

- `token_format`

Supported values:

- `opaque`
- `typed`
- `masked_readable`

New response fields:

- `token_format`
- `token_metadata`

The old response fields still remain:

- `blocked`
- `risk_score`
- `detected_markers`
- `sensitive_entities`
- `sanitized_text`
- `tokenized_text`
- `token_map`
- `generated_at`

## Token Format Modes

### 1. `opaque`

This is the default and preserves the old behavior.

Example tokens:

- `__AICCEL_TOKEN_1__`
- `__AICCEL_TOKEN_2__`

Use this when:

- you need full backward compatibility with existing clients
- your downstream system already expects the older opaque placeholder format

### 2. `typed`

This returns semantic placeholders.

Example tokens:

- `__AICCEL_EMAIL_1__`
- `__AICCEL_PHONE_1__`
- `__AICCEL_PERSON_1__`

Use this when:

- you want LLMs to preserve field meaning better
- you want a stronger extraction-friendly reversible masking format
- you still want placeholders rather than partially visible values

### 3. `masked_readable`

This returns partially visible masked values directly in `sanitized_text` and `tokenized_text`.

Example values:

- `jane***e@acme.com`
- `+1-***-***-0100`

Use this when:

- you want masked outputs to remain visually understandable to humans or LLMs
- you accept partial shape disclosure in exchange for easier extraction quality

Important:

- this mode is still reversible because `token_map` is returned
- this mode reveals more structure than typed placeholders
- if two values mask to the same visible output, the backend may append a suffix to keep the `token_map` unique

## How To Use It

## Endpoint

- `POST /v1/pii/mask`

## Headers

Use one of:

- `X-API-Key: <raw_api_key>`
- `Authorization: Bearer <access_token>`

Also send:

- `Content-Type: application/json`

## Request Example: Opaque

```json
{
  "text": "Contact jane@acme.com or call +1-212-555-0100",
  "reversible": true,
  "token_format": "opaque",
  "remove_email": true,
  "remove_phone": true,
  "remove_person": true,
  "remove_blood_group": true,
  "remove_passport": true,
  "remove_pancard": true,
  "remove_organization": true
}
```

## Request Example: Typed

```json
{
  "text": "Contact jane@acme.com or call +1-212-555-0100",
  "reversible": true,
  "token_format": "typed",
  "remove_email": true,
  "remove_phone": true,
  "remove_person": true,
  "remove_blood_group": true,
  "remove_passport": true,
  "remove_pancard": true,
  "remove_organization": true
}
```

## Request Example: Masked Readable

```json
{
  "text": "Contact jane@acme.com or call +1-212-555-0100",
  "reversible": true,
  "token_format": "masked_readable",
  "remove_email": true,
  "remove_phone": true,
  "remove_person": true,
  "remove_blood_group": true,
  "remove_passport": true,
  "remove_pancard": true,
  "remove_organization": true
}
```

## What The Output Looks Like Now

### Opaque Output

```json
{
  "blocked": false,
  "risk_score": 0.16,
  "detected_markers": [],
  "sensitive_entities": [
    { "kind": "email", "value_preview": "jan***om" },
    { "kind": "phone", "value_preview": "+1-***00" }
  ],
  "sanitized_text": "Contact __AICCEL_TOKEN_1__ or call __AICCEL_TOKEN_2__",
  "tokenized_text": "Contact __AICCEL_TOKEN_1__ or call __AICCEL_TOKEN_2__",
  "token_format": "opaque",
  "token_map": {
    "__AICCEL_TOKEN_1__": "jane@acme.com",
    "__AICCEL_TOKEN_2__": "+1-212-555-0100"
  },
  "token_metadata": {
    "__AICCEL_TOKEN_1__": {
      "kind": "email",
      "index": 1,
      "reversible": true,
      "canonical_placeholder": "__AICCEL_EMAIL_1__",
      "display_value": "__AICCEL_TOKEN_1__"
    },
    "__AICCEL_TOKEN_2__": {
      "kind": "phone",
      "index": 1,
      "reversible": true,
      "canonical_placeholder": "__AICCEL_PHONE_1__",
      "display_value": "__AICCEL_TOKEN_2__"
    }
  },
  "generated_at": "2026-04-04T10:00:00Z"
}
```

### Typed Output

```json
{
  "blocked": false,
  "risk_score": 0.16,
  "detected_markers": [],
  "sensitive_entities": [
    { "kind": "email", "value_preview": "jan***om" },
    { "kind": "phone", "value_preview": "+1-***00" }
  ],
  "sanitized_text": "Contact __AICCEL_EMAIL_1__ or call __AICCEL_PHONE_1__",
  "tokenized_text": "Contact __AICCEL_EMAIL_1__ or call __AICCEL_PHONE_1__",
  "token_format": "typed",
  "token_map": {
    "__AICCEL_EMAIL_1__": "jane@acme.com",
    "__AICCEL_PHONE_1__": "+1-212-555-0100"
  },
  "token_metadata": {
    "__AICCEL_EMAIL_1__": {
      "kind": "email",
      "index": 1,
      "reversible": true,
      "canonical_placeholder": "__AICCEL_EMAIL_1__",
      "display_value": "__AICCEL_EMAIL_1__"
    },
    "__AICCEL_PHONE_1__": {
      "kind": "phone",
      "index": 1,
      "reversible": true,
      "canonical_placeholder": "__AICCEL_PHONE_1__",
      "display_value": "__AICCEL_PHONE_1__"
    }
  },
  "generated_at": "2026-04-04T10:00:00Z"
}
```

### Masked-Readable Output

```json
{
  "blocked": false,
  "risk_score": 0.16,
  "detected_markers": [],
  "sensitive_entities": [
    { "kind": "email", "value_preview": "jan***om" },
    { "kind": "phone", "value_preview": "+1-***00" }
  ],
  "sanitized_text": "Contact jane***e@acme.com or call +1-***-***-0100",
  "tokenized_text": "Contact jane***e@acme.com or call +1-***-***-0100",
  "token_format": "masked_readable",
  "token_map": {
    "jane***e@acme.com": "jane@acme.com",
    "+1-***-***-0100": "+1-212-555-0100"
  },
  "token_metadata": {
    "jane***e@acme.com": {
      "kind": "email",
      "index": 1,
      "reversible": true,
      "canonical_placeholder": "__AICCEL_EMAIL_1__",
      "display_value": "jane***e@acme.com"
    },
    "+1-***-***-0100": {
      "kind": "phone",
      "index": 1,
      "reversible": true,
      "canonical_placeholder": "__AICCEL_PHONE_1__",
      "display_value": "+1-***-***-0100"
    }
  },
  "generated_at": "2026-04-04T10:00:00Z"
}
```

## Supported Typed Kinds In This Update

This update focuses on the currently supported entity families already present in the text masking flow:

- `email`
- `phone`
- `person`
- `organization`
- `address`
- `passport`
- `pancard`
- `blood_group`
- `ssn`
- `card`
- `dob`
- `bank_account`

Not included in this update:

- `linkedin`
- `github`
- `portfolio`
- `website`

## Backward Compatibility

This change is backward compatible because:

- the default remains `token_format = "opaque"`
- legacy fields still exist
- existing clients do not need to change anything unless they want the new behavior

## Recommended Usage Guidance

Use:

- `opaque` for old clients
- `typed` for most LLM extraction workflows
- `masked_readable` only when you intentionally want partial readability in the masked output

If privacy should be strongest while still helping an LLM preserve meaning, `typed` is the recommended mode.

## Related Docs

- [pii-masking-api-integration.md](/C:/MY_PROJECTS/AICCEL/AICCEL_SAAS/documentation/pii-masking-api-integration.md)
- [pii-masking-api-change-log.md](/C:/MY_PROJECTS/AICCEL/AICCEL_SAAS/documentation/pii-masking-api-change-log.md)
