# apartment-agent-error-safety Specification

## Purpose
Defines the typed error envelope for the apartment-agent routes and the
hardening of the FE `requestJson` helper so the Agent tab never shows
an opaque `Internal Server Error: <Type>: <msg>` again.

## Requirements

### Requirement: Typed error envelope exists
The system SHALL provide `app/modules/apartment_agent/schemas.py::ApartmentAgentError` with the shape:
```python
kind: Literal["missing_config", "llm_auth", "llm_schema", "llm_rate_limit", "godanang_rest", "validation"]
message: str
missing: list[str] = []
status: int | None = None
request_id: str
```

#### Scenario: Missing env var returns missing_config
- **WHEN** `LLM_API_KEY` is unset and `/api/apartment-agent/test-extract` is called
- **THEN** the response is HTTP 400 with body `{"success": false, "error": {"kind": "missing_config", "missing": ["LLM_API_KEY"], "message": "...", "request_id": "<uuid>"}}`

#### Scenario: LLM 401 returns llm_auth
- **WHEN** the LLM provider returns 401 (invalid key)
- **THEN** the response is HTTP 502 with body `{"success": false, "error": {"kind": "llm_auth", "message": "401 from LLM provider", "request_id": "<uuid>"}}`

#### Scenario: GoDaNang 500 returns godanang_rest
- **WHEN** a sync call to GoDaNang's REST endpoint returns HTTP 500
- **THEN** the response is HTTP 502 with body `{"success": false, "error": {"kind": "godanang_rest", "status": 500, "message": "...", "request_id": "<uuid>"}}`

### Requirement: /test-extract calls validate_settings first
The route handler for `POST /api/apartment-agent/test-extract` MUST call `validate_settings()` before any LLM work. If `missing` is non-empty, it MUST return the typed `missing_config` error envelope and MUST NOT attempt the LLM call.

#### Scenario: Empty config in /test-extract
- **WHEN** `/api/apartment-agent/test-extract` is called with no `GODANANG_*` or `LLM_API_KEY` set
- **THEN** HTTP 400, body shows `missing=["LLM_API_KEY", "GODANANG_SUPABASE_URL", "GODANANG_SUPABASE_SERVICE_KEY"]`, no LLM API call is made (verified by mock counter)

### Requirement: Global exception handler logs traceback and request_id
The global exception handler in `app/main.py` MUST log the full traceback at ERROR level with the `request_id` field, and MUST include the `request_id` in the response body. The current behavior of returning `Internal Server Error: <Type>: <msg>` is replaced by a structured body when the error originates in the apartment-agent module.

#### Scenario: Unhandled exception in apartment-agent route
- **WHEN** a route in `app/modules/apartment_agent/` raises an unhandled exception
- **THEN** the response is HTTP 500 with body `{"success": false, "error": {"kind": "validation", "message": "<Type>: <msg>", "request_id": "<uuid>"}}` and the log line at ERROR level includes the same `request_id` and the full traceback

### Requirement: FE requestJson helper guards response.json()
The frontend `services/zaloCrawlerService.ts::requestJson` MUST wrap `await response.json()` in a try/catch and MUST throw `Error("API <status>: phản hồi không phải JSON (<url>)")` on parse failure, mirroring the existing pattern in `services/linkedinCrawlerService.ts:76-83`. The same guard MUST be added to the raw `fetch` in `ZaloAgentTestPanel.tsx::handleGenerateFake`.

#### Scenario: Backend returns HTML 502 from a proxy
- **WHEN** a cloudflared/nginx proxy returns an HTML error page
- **THEN** the FE shows a toast `"API 502: phản hồi không phải JSON (http://localhost:8000/api/apartment-agent/test-extract)"` instead of a raw `SyntaxError`

#### Scenario: Backend returns typed ApartmentAgentError JSON
- **WHEN** the backend returns the new envelope
- **THEN** the FE renders a friendly message: e.g. `"Thiếu LLM_API_KEY trong .env — xem .env.example"`, with the `request_id` shown in a collapsible "Chi tiết" panel for support
