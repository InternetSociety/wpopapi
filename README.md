# WorldPop Population API Server

This application provides a web API to query current-year WorldPop population data by country.

The dataset currently referenced is an alpha version (R2025A) product and may change over the coming year as improvements are made.

Bondarenko M., Priyatikanto R., Tejedor-Garavito N., Zhang W., McKeen T., Cunningham A., Woods T., Hilton J., Cihan D., Nosatiuk B., Brinkhoff T., Tatem A., Sorichetta A.. Constrained estimates of 2015-2030 total number of people per grid square at a resolution of 3 arc (approximately 100m at the equator) R2025A version v1. Global Demographic Data Project - Funded by The Bill and Melinda Gates Foundation (INV-045237). WorldPop - School of Geography and Environmental Science, University of Southampton. DOI:10.5258/SOTON/WP00839

## API Documentation

Access the interactive Swagger UI at `/docs`.

### Authentication

The API uses bearer token authentication.
- Admin users manage the system.
- Regular users can view their bearer token on the user management page.
- Use the `Authorize` button in `/docs` to enter your bearer token.

### Endpoints

- `GET /api/pop`
  - Query parameters: `iso3`, `lat`, `lon`
  - Returns: `{"pop": 12345}`
- `GET /api/pop-radius`
  - Query parameters: `iso3`, `lat`, `lon`, `radius`
  - `radius` is in metres and must be `<= 100000`
  - Returns: `{"pop": 12345}`
- `GET /api/pop-shape`
  - Query parameters: `iso3`, `lat`, `lon`
  - Request body: GeoJSON object
  - Body size limit: 5 MB
  - Vertex limit: 10,000
  - Returns: `{"pop": 12345}`

## Query Model

The application always loads and queries the single tile for the requested ISO3 country code.
- Radius and GeoJSON queries are clipped to that tile.
- Coverage outside the country tile is ignored.
- Tile URL configuration lives in `app/config.py`:
  - `dataset = "Global_2015_2030"`
  - `release = "R2025A"`
  - `version = "v1"`
  - `year = 2025`
  - `tile_expiry = 365`

## Tile Caching

The server caches one tile per country code:
- Identification: requested ISO3 code
- Download: on demand
- Storage: `/app/data/tiles`
- Expiration: cached tiles expire after `tile_expiry` days and are removed from disk and SQLite

## User Management

The existing user management UI remains available at `/manage-users`.

### CLI User Management

Create an admin user:

```bash
docker exec -it wpopapi-app python manage_users.py create admin@example.com YourSecretPassword
```

Remove a user:

```bash
docker exec -it wpopapi-app python manage_users.py remove admin@example.com
```

## Project Structure

```text
.
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── dependencies.py
│   ├── models/
│   ├── routers/
│   ├── services/
│   └── templates/
├── data_table_setup.sql
├── docker-compose.yml
├── Dockerfile
├── manage_users.py
└── requirements.txt
```

## Notes

- The service only loads the country tile for the requested ISO3 code.
- Multi-tile coverage is not used.
- Existing auth and UI routes remain in place.
