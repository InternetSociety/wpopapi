# WorldPop Population API

This FastAPI service queries current-year WorldPop population rasters by country. It provides point, radius, and GeoJSON queries, an authenticated Swagger interface, and a small user and tile-cache administration UI.

## Run the service

Docker Compose is the only supported application environment. CPython and all application tools run in the `app` container.

1. Copy `.env.example` to `.env` and set a long, random `SECRET_KEY`. Set `SESSION_COOKIE_SECURE=true` for production HTTPS.
2. Copy `docker-compose.yml.example` to `docker-compose.yml`.
3. Build and start the service:

```bash
docker compose up --build
```

The application is available at `http://localhost:8002`. The SQLite database and downloaded rasters remain in the bind-mounted `app/data` directory.

Do not install Python packages or run Python tools on the host. Declare dependencies in `requirements.txt`, then rebuild the image.

## Configuration

Copy `.env.example` to `.env`, change the values there, and restart the app container. `app/config.py` defines the settings, their types, and their defaults. Environment variables override those defaults.

| Setting | Default | Purpose |
| --- | ---: | --- |
| `APP_NAME` | `WorldPop Population API` | Name shown in the UI and OpenAPI metadata |
| `DATABASE_URL` | Required | SQLAlchemy database connection URL |
| `TILE_CACHE_DIR` | `/app/data/tiles` | Directory for downloaded WorldPop rasters |
| `TILE_CACHE_EXPIRY_DAYS` | `365` | Number of days before an unused cached tile expires |
| `TILE_DOWNLOAD_TIMEOUT_SECONDS` | `120` | Timeout for a WorldPop raster download |
| `POP_RADIUS_MIN_METERS` | `1` | Smallest accepted radius query |
| `POP_RADIUS_MAX_METERS` | `100000` | Largest accepted radius query |
| `GEOJSON_MAX_SIZE_BYTES` | `5242880` (5 MiB) | Largest accepted GeoJSON upload |
| `GEOJSON_MAX_VERTICES` | `10000` | Most vertices accepted in one GeoJSON upload |
| `PASSWORD_MIN_LENGTH` | `12` | Minimum account password length |
| `PASSWORD_MAX_LENGTH` | `128` | Maximum account password length |
| `SECRET_KEY` | Required | Secret used to sign JWTs and CSRF tokens; use a long random value |
| `ALGORITHM` | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Lifetime of a short-lived API JWT |
| `SESSION_EXPIRE_MINUTES` | `10080` (7 days) | Lifetime of a browser session |
| `SESSION_COOKIE_SECURE` | `false` | Send session cookies only over HTTPS when `true` |
| `SMTP_ENABLED` | `false` | Enable password-reset email delivery |
| `SMTP_HOST` | `localhost` | SMTP server host |
| `SMTP_PORT` | `25` | SMTP server port |
| `SMTP_SENDER` | `noreply@example.invalid` | Password-reset sender address |

For example, to accept GeoJSON with up to 50,000 vertices, set `GEOJSON_MAX_VERTICES=50000` in `.env`, then restart the service:

```bash
docker compose up -d --force-recreate app
```

The WorldPop dataset, release, version, and year are developer-level constants at the end of `app/config.py`. Change them there and rebuild the image when switching raster releases.

## Database and first administrator

The container applies Alembic migrations when it starts. Use these commands for explicit migration work:

```bash
docker compose run --rm app alembic upgrade head
docker compose run --rm app alembic revision --autogenerate -m "description"
```

Create or remove an account through the shared user service:

```bash
docker compose run --rm app python manage_users.py create admin@example.com 'a-long-password'
docker compose run --rm app python manage_users.py remove user@example.com
```

The command does not print a password, password hash, JWT, or persistent token.

## Authentication and UI

Open `/` and sign in with an administrator account. Authenticated users can access:

- `/docs` for Swagger
- `/app-docs` for this guide
- `/manage-users` for their visible account information

Administrators manage all users. API users receive a random persistent bearer token. Administrators never receive one. `/token` exchanges a valid email and password for a short-lived JWT. Browser sessions use a separate typed JWT in an HTTP-only cookie.

Use `/forgot-password` to request a reset code. When SMTP delivery is enabled, the service emails a one-time code that expires after 30 minutes; paste it into `/reset-password`. The request acknowledgement is the same whether or not an eligible account exists.

Send API credentials in `Authorization: Bearer TOKEN`. The application tries a persistent token first and then accepts only an access-type JWT. Inactive accounts receive HTTP 403.

## API

- `GET /api/pop` accepts `iso3`, `lat`, and `lon`.
- `GET /api/pop-radius` also accepts `radius` in metres.
- `POST /api/pop-shape` accepts `iso3` and a `geojson_file` upload.

All routes return `{"pop": 12345}`. Radius, upload, and vertex limits are configurable through `.env` as described above.

The service caches one WorldPop GeoTIFF per ISO3 country code. Raster reads and file writes run outside the async event loop. GeoJSON and radius calculations read only the intersecting raster window.

## Checks

Run every check through Compose:

```bash
docker compose run --rm app pytest
docker compose run --rm app pytest --cov=app
docker compose run --rm app ruff check .
docker compose run --rm app ruff format --check .
docker compose run --rm app mypy app/
```

Tests use a separate SQLite database and isolate database changes with rollback transactions.

## Structure

```text
app/
├── main.py
├── config.py
├── database.py
├── dependencies.py
├── models/
├── schemas/
├── routers/
├── services/
├── repositories/
└── templates/
tests/
├── conftest.py
├── test_routers/
└── test_services/
migrations/
```
