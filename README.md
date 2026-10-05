# WS AI Builder Backend

FastAPI service for an AI-assisted compliance workflow. It sends user text to a
published Azure AI Foundry supervisor, normalizes the structured case report,
redacts sensitive values, and persists an auditable record in SQLite by default.

## Safety defaults

- Raw user text is not stored unless `STORE_RAW_USER_TEXT=true`.
- Supervisor-provided redactions are applied before sanitized content is persisted.
- Escalation and human-review decisions return deterministic user-facing messages.
- Credentials are loaded from the environment and must not be committed.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Set `FOUNDRY_SUPERVISOR_RESPONSES_URL` and authenticate with an Azure identity
supported by `DefaultAzureCredential` before calling `POST /chat`. The `/health`,
`/cases`, and `/kpis` endpoints are available without a Foundry call.

## Validate

```bash
python -m unittest discover -s tests -v
python -c "from app.main import app; assert app.title == 'WS AI Builder Backend'"
```

