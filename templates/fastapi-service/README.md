# FastAPI Service

A multi-file Python REST API scaffolded by Agentic OS.

## Run it

    pip install -r requirements.txt
    uvicorn app.main:app --reload

- API:  http://127.0.0.1:8000
- Docs: http://127.0.0.1:8000/docs

## Test it

    pytest -q

## Structure

    app/main.py     App entry point, health endpoint, router wiring
    app/models.py   Pydantic request/response schemas
    app/routes.py   CRUD endpoints over an in-memory store
    test_app.py     Endpoint tests

Swap the in-memory `_STORE` in `app/routes.py` for a real database when you
outgrow it — the handlers and schemas stay the same.
