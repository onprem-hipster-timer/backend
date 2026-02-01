# Configuration

This guide covers all configuration options available in Hipster Timer Backend.

## Environment Variables

Configuration is done via `.env` file or environment variables.

## Environment Mode

| Variable | Description | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | Runtime environment (`development`, `staging`, `production`) | `development` |

> ⚠️ **Production Mode**: When `ENVIRONMENT=production`, the following settings are automatically applied:
> - `DEBUG` → `False`
> - `OPENAPI_URL` → `""` (disabled)
> - `DOCS_URL` → `""` (disabled)
> - `REDOC_URL` → `""` (disabled)
> - `GRAPHQL_ENABLE_PLAYGROUND` → `False`
> - `GRAPHQL_ENABLE_INTROSPECTION` → `False`

## Core Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `DOCS_ENABLED` | Master switch for all API docs (Swagger, ReDoc, GraphQL Sandbox) | `True` |
| `DEBUG` | Enable debug mode | `True` |
| `OPENAPI_URL` | OpenAPI schema URL (empty string to disable) | `/openapi.json` |
| `DOCS_URL` | Swagger UI URL (empty string to disable) | `/docs` |
| `REDOC_URL` | ReDoc URL (empty string to disable) | `/redoc` |
| `LOG_LEVEL` | Log level | `INFO` |
| `HOLIDAY_API_SERVICE_KEY` | Korea Public Data Portal API key | - |
| `GRAPHQL_ENABLE_PLAYGROUND` | Enable GraphQL Sandbox | `True` |
| `GRAPHQL_ENABLE_INTROSPECTION` | Allow GraphQL introspection | `True` |

## Database Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | DB connection string | `sqlite:///./schedule.db` |
| `POOL_SIZE` | Connection pool size | `5` |
| `MAX_OVERFLOW` | Max overflow connections | `10` |
| `DB_POOL_PRE_PING` | Validate connections before use | `True` |
| `DB_POOL_RECYCLE` | Connection recycle time (seconds) | `3600` |

**Database URL Examples:**

```bash
# SQLite (development)
DATABASE_URL=sqlite:///./schedule.db

# PostgreSQL (production)
DATABASE_URL=postgresql://user:password@localhost:5432/dbname
```

## Authentication (OIDC)

| Variable | Description | Default |
|----------|-------------|---------|
| `OIDC_ENABLED` | Enable OIDC authentication | `True` |
| `OIDC_ISSUER_URL` | OIDC Provider issuer URL | - |
| `OIDC_AUDIENCE` | Client ID for token validation | - |
| `OIDC_DISCOVERY_URL` | Custom discovery endpoint | Auto-generated |
| `OIDC_JWKS_CACHE_TTL_SECONDS` | JWKS cache TTL | `3600` |

> 📖 **Detailed Guide**: [Authentication Guide](../guides/auth.ko.md)

## Rate Limiting

**HTTP Rate Limiting:**

| Variable | Description | Default |
|----------|-------------|---------|
| `RATE_LIMIT_ENABLED` | Enable rate limiting | `True` |
| `RATE_LIMIT_DEFAULT_WINDOW` | Default window size (seconds) | `60` |
| `RATE_LIMIT_DEFAULT_REQUESTS` | Default max requests per window | `60` |

**WebSocket Rate Limiting:**

| Variable | Description | Default |
|----------|-------------|---------|
| `WS_RATE_LIMIT_ENABLED` | Enable WebSocket rate limiting | `True` |
| `WS_CONNECT_WINDOW` | Connection limit window (seconds) | `60` |
| `WS_CONNECT_MAX` | Max connections per window | `10` |
| `WS_MESSAGE_WINDOW` | Message limit window (seconds) | `60` |
| `WS_MESSAGE_MAX` | Max messages per window | `120` |

> 📖 **Detailed Guide**: [Rate Limiting Guide](../development/rate-limit.ko.md)

## Proxy Settings (Cloudflare / Trusted Proxy)

| Variable | Description | Default |
|----------|-------------|---------|
| `PROXY_FORCE` | Enforce proxy usage (block direct access) | `False` |
| `CF_ENABLED` | Enable Cloudflare proxy mode | `False` |
| `CF_IP_CACHE_TTL` | Cloudflare IP list cache TTL (seconds) | `86400` |
| `TRUSTED_PROXY_IPS` | Trusted proxy IPs (comma-separated, CIDR supported) | `""` |
| `ORIGIN_VERIFY_HEADER` | Custom header name for origin verification (optional) | `""` |
| `ORIGIN_VERIFY_SECRET` | Secret value for origin verification header | `""` |

## CORS (Cross-Origin Resource Sharing)

| Variable | Description | Default |
|----------|-------------|---------|
| `CORS_ALLOWED_ORIGINS` | Allowed origins (comma-separated) | Development defaults |
| `CORS_ALLOW_CREDENTIALS` | Allow credentials (cookies, etc.) | `False` |
| `CORS_ALLOW_METHODS` | Allowed HTTP methods (comma-separated) | `*` |
| `CORS_ALLOW_HEADERS` | Allowed headers (comma-separated) | `*` |

> ⚠️ **Note**: `CORS_ALLOWED_ORIGINS="*"` and `CORS_ALLOW_CREDENTIALS=true` cannot be used together.

## Example .env File

```bash
# Environment
ENVIRONMENT=development

# Database
DATABASE_URL=sqlite:///./schedule.db

# Authentication (Development - disabled)
OIDC_ENABLED=false

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_DEFAULT_WINDOW=60
RATE_LIMIT_DEFAULT_REQUESTS=60

# Logging
LOG_LEVEL=INFO
```

## Production Configuration

For production deployment, see the [Production Guide](../deployment/production.md).
