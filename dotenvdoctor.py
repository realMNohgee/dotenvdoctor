#!/usr/bin/env python3
"""dotenvdoctor — Validate .env files against a schema."""

import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    from common import common_args, output
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from common import common_args, output


# Type inference patterns
TYPE_PATTERNS = {
    "int": re.compile(r"^-?\d+$"),
    "float": re.compile(r"^-?\d+\.\d+$"),
    "bool": re.compile(r"^(true|false)$", re.IGNORECASE),
    "url": re.compile(r"^https?://\S+$"),
    "email": re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
    "port": re.compile(r"^\d{1,5}$"),
}

INSECURE_DEFAULTS = {
    "DEBUG": "true",
    "SECRET_KEY": "change-me",
    "ADMIN_PASSWORD": "admin",
    "API_KEY": "your-api-key-here",
}

# Known production-unsafe patterns
PRODUCTION_WARNINGS = {
    "DEBUG=true": "DEBUG should not be true in production",
    "DEBUG=1": "DEBUG should not be 1 in production",
    "SECRET_KEY=": "SECRET_KEY appears empty or default",
    "PASSWORD=admin": "Default admin password detected",
}


def parse_env_file(path: str) -> tuple:
    """Parse a .env file, returning (vars_dict, errors)."""
    variables = {}
    errors = []
    duplicates = set()

    if not os.path.exists(path):
        return variables, [f"File not found: {path}"]

    with open(path) as f:
        for lineno, raw_line in enumerate(f, 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            if "=" not in line:
                errors.append(f"Line {lineno}: Invalid format (missing '='): {line}")
                continue

            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if key in variables:
                duplicates.add(key)

            variables[key] = value

    if duplicates:
        errors.append(f"Duplicate keys: {', '.join(sorted(duplicates))}")

    return variables, errors


def infer_type(value: str) -> str:
    """Infer the type of an env var value."""
    if not value:
        return "empty"
    if TYPE_PATTERNS["bool"].match(value):
        return "bool"
    if TYPE_PATTERNS["int"].match(value):
        v = int(value)
        if 1 <= v <= 65535:
            return "port"
        return "int"
    if TYPE_PATTERNS["float"].match(value):
        return "float"
    if TYPE_PATTERNS["url"].match(value):
        return "url"
    if TYPE_PATTERNS["email"].match(value):
        return "email"
    return "string"


def load_schema(schema_path: str) -> dict:
    """Load a schema JSON file."""
    if not os.path.exists(schema_path):
        print(f"Schema file not found: {schema_path}", file=sys.stderr)
        sys.exit(1)
    with open(schema_path) as f:
        return json.load(f)


def generate_schema(variables: dict) -> dict:
    """Generate a schema from parsed variables."""
    schema = {}
    for key, value in sorted(variables.items()):
        inferred = infer_type(value)
        schema[key] = {
            "required": True,
            "type": inferred,
            "example": value,
        }
    return schema


def validate_variables(variables: dict, schema: dict, check_production: bool = False) -> list:
    """Validate variables against schema. Returns list of issues."""
    issues = []

    for key, rules in schema.items():
        required = rules.get("required", False)
        expected_type = rules.get("type", "string")
        allowed_values = rules.get("allowed", None)

        if key not in variables:
            if required:
                issues.append(f"MISSING: {key} is required but not set")
            continue

        value = variables[key]

        # Type check
        if expected_type == "int":
            if not TYPE_PATTERNS["int"].match(value):
                issues.append(f"TYPE: {key} should be int, got '{value}'")
        elif expected_type == "port":
            if not TYPE_PATTERNS["port"].match(value) or not (1 <= int(value) <= 65535):
                issues.append(f"TYPE: {key} should be a valid port (1-65535), got '{value}'")
        elif expected_type == "bool":
            if not TYPE_PATTERNS["bool"].match(value):
                issues.append(f"TYPE: {key} should be bool (true/false), got '{value}'")
        elif expected_type == "url":
            if not TYPE_PATTERNS["url"].match(value):
                issues.append(f"TYPE: {key} should be a valid URL, got '{value}'")
        elif expected_type == "email":
            if not TYPE_PATTERNS["email"].match(value):
                issues.append(f"TYPE: {key} should be a valid email, got '{value}'")
        elif expected_type == "float":
            if not TYPE_PATTERNS["float"].match(value) and not TYPE_PATTERNS["int"].match(value):
                issues.append(f"TYPE: {key} should be a number, got '{value}'")

        # Allowed values check
        if allowed_values and value not in allowed_values:
            issues.append(f"VALUE: {key}='{value}' not in allowed values: {allowed_values}")

    # Production safety check
    if check_production:
        for key, insecure_val in INSECURE_DEFAULTS.items():
            if variables.get(key, "").lower() == insecure_val.lower():
                issues.append(f"PROD: {key} has insecure default '{variables[key]}'")

    return issues


def cmd_check(args):
    """Check .env against schema."""
    variables, parse_errors = parse_env_file(args.env)

    if parse_errors:
        if args.format == "json":
            output({"status": "error", "errors": parse_errors}, args.format)
        else:
            for e in parse_errors:
                print(f"[ERROR] {e}")
        sys.exit(1)

    schema = load_schema(args.schema)
    issues = validate_variables(variables, schema, check_production=args.production)

    if issues:
        if args.format == "json":
            output({"status": "issues_found", "issues": issues, "count": len(issues)}, args.format)
        else:
            for issue in issues:
                print(f"[ISSUE] {issue}")
            print(f"\n{len(issues)} issue(s) found.")
    else:
        output({"status": "ok", "message": "All checks passed."}, args.format)
        if args.format == "text":
            print("✓ All checks passed.")


def cmd_init(args):
    """Generate a schema from a .env file."""
    variables, parse_errors = parse_env_file(args.env)
    if parse_errors:
        for e in parse_errors:
            print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    schema = generate_schema(variables)
    if args.format == "json":
        output(schema, "json")
    else:
        output(schema, "json")  # schema always outputs as JSON-like for readability

    if args.output:
        with open(args.output, "w") as f:
            json.dump(schema, f, indent=2)
        print(f"\nSchema saved to {args.output}", file=sys.stderr)


def main():
    parent = common_args()
    parser = argparse.ArgumentParser(
        description="Validate .env files against a schema",
        prog="dotenvdoctor",
    )
    sub = parser.add_subparsers(dest="command")

    # check
    chk = sub.add_parser("check", parents=[parent], help="Validate .env against schema")
    chk.add_argument("--schema", required=True, help="Path to schema JSON file")
    chk.add_argument("--env", default=".env", help="Path to .env file (default: .env)")
    chk.add_argument("--production", action="store_true", help="Enable production-safety checks")

    # init
    ini = sub.add_parser("init", parents=[parent], help="Generate schema from .env")
    ini.add_argument("--env", default=".env", help="Path to .env file (default: .env)")
    ini.add_argument("--output", "-o", help="Write schema to file")

    args = parser.parse_args()
    if args.command == "check":
        cmd_check(args)
    elif args.command == "init":
        cmd_init(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
