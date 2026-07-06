# FastAPI Basic Information

It'd be good if you could follow the advice in this section when building the application.
if any of this advice conflicts with my previous instructions stop to talk to me about it.

## Commands
`uvicorn app.main:app --reload` — Start development server on port 8000
`pytest` — Run test suite
`pytest --cov=app` — Run tests with coverage report
`alembic upgrade head` — Apply database migrations
`alembic revision --autogenerate -m "description"` — Create new migration
`ruff check .` — Run linter
`ruff format .` — Format code
`mypy app/` — Type check

## Architecture
- **Framework**: FastAPI with async/await throughout
- **Database**: SQLAlchemy 2.0 async with PostgreSQL
- **Migrations**: Alembic for schema migrations
- **Validation**: Pydantic v2 models for request/response schemas
- **Auth**: JWT tokens via python-jose, password hashing with passlib
- **Testing**: pytest with httpx AsyncClient for API tests

## Project Structure
```
app/
├── main.py              # FastAPI app factory, middleware, startup/shutdown
├── config.py            # Settings via pydantic-settings (reads .env)
├── dependencies.py      # Shared FastAPI dependencies (get_db, get_current_user)
├── models/              # SQLAlchemy ORM models
├── schemas/             # Pydantic request/response models
├── routers/             # API route modules (one per domain)
├── services/            # Business logic layer (called by routers)
├── repositories/        # Database query layer (called by services)
└── tests/
    ├── conftest.py      # Fixtures: async client, test DB, auth headers
    ├── test_routers/    # API integration tests
    └── test_services/   # Unit tests for business logic
```

## Code Conventions
- All database operations use async SQLAlchemy sessions via `async with`
- Router functions are thin — delegate business logic to services/
- Use dependency injection for DB sessions: `db: AsyncSession = Depends(get_db)`
- Pydantic schemas separate Create, Update, and Response models (e.g., UserCreate, UserUpdate, UserResponse)
- All routes return typed Pydantic response models — never return raw dicts or ORM objects
- Use HTTPException for client errors (4xx), let unhandled exceptions become 500s
- Background tasks via FastAPI's BackgroundTasks, not Celery (unless explicitly needed)

## Error Handling
- Validation errors return 422 with Pydantic's default error format
- Business logic errors raise HTTPException with appropriate status codes
- Use custom exception handlers in main.py for domain-specific error types
- Never catch broad Exception — catch specific exception types

## Database Patterns
- Always use `select()` style queries (SQLAlchemy 2.0), not legacy `query()`
- Relationships use `selectinload()` or `joinedload()` to avoid N+1 queries
- Transactions are per-request — the dependency handles commit/rollback
- Use `Annotated` types for common column patterns (e.g., `created_at`, `updated_at`)

## HTML Styling
- Style HTML with Bootstrap5

## Testing
- Tests use a separate test database (configured in conftest.py)
- Each test runs in a transaction that rolls back — tests don't affect each other
- Use `httpx.AsyncClient` with `app=app` for integration tests
- Factory functions in conftest.py for creating test data (e.g., `create_test_user`)
- Mock external services (email, payment) but hit the real test database

## Things to Avoid
- Do NOT use synchronous database drivers or blocking I/O in async routes
- Do NOT return SQLAlchemy models directly from routes — always use Pydantic schemas
- Do NOT put business logic in router functions — use the service layer
- Do NOT use `*` imports
- Do NOT hardcode configuration — use pydantic-settings and environment variables
- Do NOT use global mutable state — use FastAPI's dependency injection system

## General information

These instructions should guide your thinking in developing this application.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

