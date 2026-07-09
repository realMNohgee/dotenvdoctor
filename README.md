# dotenvdoctor

Validate `.env` files against a schema. Catch missing variables, type mismatches, insecure defaults, and duplicate keys.

## Commands

### `check` — Validate .env against schema

```bash
python -m dotenvdoctor.cli check --schema SCHEMA [--env .env] [--production] [--format json|text]
```

**Options:**
- `--schema` — Path to schema JSON file (required)
- `--env` — Path to .env file (default: `.env`)
- `--production` — Enable production-safety checks
- `--format` — Output format

### `init` — Generate schema from .env

```bash
python -m dotenvdoctor.cli init [--env .env] [--output schema.json] [--format json|text]
```

## Schema Format

```json
{
  "PORT": {"required": true, "type": "port"},
  "DEBUG": {"required": true, "type": "bool"},
  "DATABASE_URL": {"required": true, "type": "url"},
  "APP_NAME": {"required": false, "type": "string"}
}
```

## Supported Types

- `string` — Any text
- `int` — Integer number
- `float` — Decimal number
- `bool` — `true` or `false`
- `port` — Integer 1-65535
- `url` — `http://` or `https://` URL
- `email` — Email address format

## Production Safety Checks

When `--production` is passed, dotenvdoctor warns about:
- `DEBUG=true` in production
- Empty/insecure `SECRET_KEY`
- Default `ADMIN_PASSWORD`

---

Built by [Hermtica](https://hermtica.com/marketplace)
