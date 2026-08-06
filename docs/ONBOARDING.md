# Support Ticket Classifier — Onboarding Guide

A map of the project: what it does, how the LangGraph pipeline works, and the best order to learn the codebase.

---

## 1. Project Overview

This is a **production-aware AI support ticket classifier**. You send raw customer ticket text; it returns structured routing data — category, team, priority, sentiment, and confidence — via GPT-4o-mini, wrapped in reliability layers:

- PII redaction
- Prompt-injection guard
- Schema / business-rule validation
- Retries and safe fallback
- Versioned prompts
- Cost tracking

**Example input:**
```
"I was charged twice for order #9981. Please refund immediately!"
```

**Example output:**
```json
{
  "issue_category": "payment_issue",
  "assigned_team": "payments_team",
  "priority": "high",
  "user_sentiment": "angry",
  "confidence_score": 0.97,
  "reasoning": "Customer explicitly reports duplicate charge and requests refund",
  "requires_human_review": false
}
```

**Stack:** Python · FastAPI · LangGraph · LangChain/OpenAI · Pydantic · tiktoken · tenacity

---

## 2. Architecture Layers

Three layers, with thin orchestration on top of self-contained modules:

```
demo_ui/index.html
        │
        ▼
   main.py (FastAPI)     ← HTTP: validate request, call pipeline, return JSON
        │
        ▼
   graph.py (LangGraph)  ← Orchestration: nodes + edges only — no LLM wiring
        │
        ▼
 production_modules/*    ← Business logic: one concern per file
        │
        ├── schema.py    ← Contracts: enums + TicketClassification + TicketState
        └── OpenAI (GPT-4o-mini)
```

| Layer | File(s) | Role |
|-------|---------|------|
| HTTP | [`main.py`](../main.py) | Validates request, calls `run_pipeline()`, returns JSON |
| Orchestration | [`graph.py`](../graph.py) | LangGraph nodes + edges only — no LLM wiring |
| Contracts | [`schema.py`](../schema.py) | Enums + `TicketClassification` + `TicketState` |
| Business logic | [`production_modules/`](../production_modules/) | Each concern in one copyable module |

### Design principle

`graph.py` is intentionally thin. Each node:

1. Reads from the shared state dict
2. Calls one production-module function
3. Returns `{**state, ...updated fields}`

LLM classification calls live only in `structured_output.py`. The injection guard LLM lives in `prompt_injection.py`. Nodes never build LangChain chains themselves.

---

## 3. End-to-End Workflow

```
POST /classify  { ticket_text, channel }
        │
        ▼
   pii_redact          strip email / phone / credit card
        │
        ▼
   injection_check     guard LLM on raw ticket
        │
        ▼
   classify            versioned prompt + JSON-mode LLM (skips if blocked)
        │
        ▼
   validate            Pydantic + business rules (skips if blocked)
        │
        ├── pass / blocked ──► cost_log ──► END
        │
        └── fail ──► fallback (retry up to 3×) ──► cost_log ──► END
        │
        ▼
ClassifyResponse JSON (main.py)
```

### Three paths

1. **Happy path** — redact → safe injection check → classify (versioned prompt) → validate pass → cost → response
2. **Injection blocked** — guard LLM flags attack → `SAFE_CLASSIFICATION` → classify/validate skip → cost → response with `injection_blocked: true`
3. **Fallback** — validate fails → retry up to 3× with simpler prompt → else safe default with `requires_human_review=true`

Shared state starts as `{raw_ticket, channel}` and is enriched node by node (`redacted_ticket`, `classification`, `validation_status`, `cost_info`, etc.). The shape is defined by `TicketState` in [`schema.py`](../schema.py).

### Happy-path spine (core story)

```
POST /classify
  → run_pipeline
  → pii_redact_node
  → injection_check_node (safe)
  → classify_node
  → validate_node (pass)
  → cost_log_node
  → ClassifyResponse
```

That sequence, with one sample ticket, is the complete core story of the project.

---

## 4. Key Design Choices

- **`graph.py` is thin** — each node calls one module function and merges state; LLM calls live only in `structured_output.py` (and the guard in `prompt_injection.py`).
- **Classifier uses redacted text; injection guard uses raw text** — privacy for classification, full signal for attack detection.
- **Determinism** — `temperature=0`, `seed=42` so the same ticket classifies the same way.
- **Fail-safe** — guard failure blocks; classification failure eventually yields `SAFE_CLASSIFICATION` with human review.
- **Prompt versioning** — templates in `PROMPT_REGISTRY` (`v1` vs `v2` chain-of-thought); active version from `PROMPT_VERSION` env.

---

## 5. Guided Tour — Where to Start

Learn the project in this order. Do not jump into failure paths until the happy path is clear.

### Step 1 — Contracts first: [`schema.py`](../schema.py)

Learn the allowed enums and the shape of `TicketClassification` / `TicketState`. Everything else produces or mutates these.

| Type | Values |
|------|--------|
| `IssueCategory` | order_issue, payment_issue, delivery_issue, product_issue, account_issue, refund_request, other |
| `TeamOwner` | fulfillment_team, payments_team, logistics_team, customer_support, tech_team |
| `Priority` | low, medium, high, critical |
| `Sentiment` | positive, neutral, negative, angry |

### Step 2 — Entry point: [`main.py`](../main.py)

See `POST /classify` → `run_pipeline()` → `ClassifyResponse`. Thin HTTP shell; confirms the pipeline is the real brain.

Also note `GET /health` and `GET /prompts`.

### Step 3 — Pipeline map: [`graph.py`](../graph.py)

Walk nodes in order:

`pii_redact` → `injection_check` → `classify` → `validate` → (`fallback`) → `cost_log`

Plus `route_after_validate`. This is the happy-flow spine.

### Step 4 — Modules along the happy path (one at a time)

| Order | Module | What it does |
|-------|--------|--------------|
| 1 | [`pii_redaction.py`](../production_modules/pii_redaction.py) | Regex PII strip (email, phone, credit card) |
| 2 | [`prompt_injection.py`](../production_modules/prompt_injection.py) | LLM-as-judge injection guard |
| 3 | [`prompt_versioning.py`](../production_modules/prompt_versioning.py) | Which system prompt is active (v1 / v2) |
| 4 | [`structured_output.py`](../production_modules/structured_output.py) | The actual classify LLM call |
| 5 | [`validate_response.py`](../production_modules/validate_response.py) | Schema + business rules |
| 6 | [`cost_calculator.py`](../production_modules/cost_calculator.py) | Token counting and USD cost |

### Step 5 — Failure path last

[`fallback_retry.py`](../production_modules/fallback_retry.py) plus the injection branch in `graph.py` — only after the happy path is clear.

### Step 6 — Optional polish

- [`demo_ui/index.html`](../demo_ui/index.html) — browser demo
- [`tests/test_classifier.py`](../tests/test_classifier.py) — pytest coverage of happy / PII / injection / fallback
- [`documentation.md`](../documentation.md) — deep reference; use after the tour, not as the first read

---

## 6. File Map

| File | Purpose |
|------|---------|
| [`main.py`](../main.py) | FastAPI app — `/health`, `/prompts`, `/classify` |
| [`graph.py`](../graph.py) | LangGraph pipeline — node functions + edges + `run_pipeline()` |
| [`schema.py`](../schema.py) | Enums, `TicketClassification`, `TicketState` |
| [`production_modules/structured_output.py`](../production_modules/structured_output.py) | Single place for classification LLM calls |
| [`production_modules/validate_response.py`](../production_modules/validate_response.py) | Pydantic + business-rule validation |
| [`production_modules/non_determinism.py`](../production_modules/non_determinism.py) | Temperature/seed helpers and consistency demo |
| [`production_modules/pii_redaction.py`](../production_modules/pii_redaction.py) | Regex-based PII detection and redaction |
| [`production_modules/prompt_injection.py`](../production_modules/prompt_injection.py) | LLM-as-a-judge injection detection |
| [`production_modules/prompt_versioning.py`](../production_modules/prompt_versioning.py) | In-memory versioned prompt registry |
| [`production_modules/cost_calculator.py`](../production_modules/cost_calculator.py) | Token counting, pricing, session cost tracker |
| [`production_modules/fallback_retry.py`](../production_modules/fallback_retry.py) | Tenacity retries + `SAFE_CLASSIFICATION` |
| [`demo_ui/index.html`](../demo_ui/index.html) | Single-file browser UI calling `/classify` |
| [`tests/test_classifier.py`](../tests/test_classifier.py) | Pipeline and module tests |
| [`.env.example`](../.env.example) | `OPENAI_API_KEY`, `PROMPT_VERSION`, `DEFAULT_MODEL`, `LOG_COSTS` |

Each file under `production_modules/` is self-contained — you can copy any single file into another project and it will work independently.

---

## 7. Complexity Hotspots

Approach these carefully on first read:

| Area | Why it matters |
|------|----------------|
| [`graph.py`](../graph.py) routing | Conditional edge after validate; injection short-circuit skips classify/validate |
| [`structured_output.py`](../production_modules/structured_output.py) | Schema embedded in prompt; brace escaping for LangChain templates |
| [`prompt_injection.py`](../production_modules/prompt_injection.py) | Separate guard LLM; fail-closed on guard errors |
| [`fallback_retry.py`](../production_modules/fallback_retry.py) | Retry + prompt downgrade + final safe default |
| [`pii_redaction.py`](../production_modules/pii_redaction.py) | Right-to-left span replacement; phone vs credit-card digit overlap |

---

## 8. Quick Start (run locally)

```bash
pip3 install -r requirements.txt
cp .env.example .env   # set OPENAI_API_KEY
python3 -m uvicorn main:app --reload --port 8000
```

Then open `demo_ui/index.html` in a browser, or:

```bash
curl -X POST http://localhost:8000/classify \
  -H "Content-Type: application/json" \
  -d '{"ticket_text": "I was charged twice for order #9981!", "channel": "web_form"}'
```

Interactive docs: `http://localhost:8000/docs`

---

## Next step for deep understanding

Ask for a walkthrough of the **happy (good) flow** starting from:

> `POST /classify` → `run_pipeline` → `pii_redact_node` → `injection_check_node` (safe) → `classify_node` → `validate_node` (pass) → `cost_log_node` → `ClassifyResponse`

Use one sample ticket and follow state field-by-field through each node.
