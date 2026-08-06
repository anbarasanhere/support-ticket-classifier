# Support Ticket Classifier

Production-aware AI support ticket classifier. Send raw customer ticket text; get structured routing data — category, team, priority, sentiment, and confidence — via GPT-4o-mini, wrapped in reliability layers.

## Features

- PII redaction
- Prompt-injection guard
- Schema / business-rule validation
- Retries and safe fallback
- Versioned prompts
- Cost tracking

## Stack

Python · FastAPI · LangGraph · LangChain/OpenAI · Pydantic · tiktoken · tenacity

## Quick start

```bash
# 1. Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env and set OPENAI_API_KEY

# 4. Run the API
uvicorn main:app --reload
```

Open the interactive docs at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs), or the demo UI at `demo_ui/index.html`.

## Example

**Input:**
```text
I was charged twice for order #9981. Please refund immediately!
```

**Output:**
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

## Project layout

| Path | Role |
|------|------|
| `main.py` | FastAPI app — HTTP entrypoint |
| `graph.py` | LangGraph pipeline orchestration |
| `schema.py` | Pydantic request/response models |
| `production_modules/` | PII, injection guard, retries, cost, prompts |
| `demo_ui/` | Simple browser demo |
| `tests/` | Pytest suite |
| `docs/ONBOARDING.md` | Deeper onboarding guide |

## Tests

```bash
pytest
```

## Docs

- [Onboarding guide](docs/ONBOARDING.md)
- [Full documentation](documentation.md)
