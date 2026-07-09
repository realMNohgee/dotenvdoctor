#!/usr/bin/env python3
"""Tests for dotenvdoctor."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenvdoctor.cli import (
    parse_env_file,
    infer_type,
    generate_schema,
    validate_variables,
    load_schema,
)


class TestParseEnvFile(unittest.TestCase):
    def test_parse_basic(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("KEY=value\nPORT=8080\nDEBUG=true\n")
            env_path = f.name
        try:
            vars_dict, errors = parse_env_file(env_path)
            self.assertEqual(len(errors), 0)
            self.assertEqual(vars_dict["KEY"], "value")
            self.assertEqual(vars_dict["PORT"], "8080")
            self.assertEqual(vars_dict["DEBUG"], "true")
        finally:
            os.unlink(env_path)

    def test_parse_duplicates(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("KEY=first\nKEY=second\n")
            env_path = f.name
        try:
            vars_dict, errors = parse_env_file(env_path)
            self.assertTrue(any("Duplicate" in e for e in errors))
        finally:
            os.unlink(env_path)

    def test_parse_comments(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("# This is a comment\nKEY=value\n")
            env_path = f.name
        try:
            vars_dict, errors = parse_env_file(env_path)
            self.assertEqual(len(errors), 0)
            self.assertEqual(len(vars_dict), 1)
        finally:
            os.unlink(env_path)

    def test_parse_missing_file(self):
        vars_dict, errors = parse_env_file("/nonexistent/.env")
        self.assertTrue(any("not found" in e for e in errors))

    def test_parse_invalid_line(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("INVALID_LINE_NO_EQUALS\nKEY=value\n")
            env_path = f.name
        try:
            vars_dict, errors = parse_env_file(env_path)
            self.assertTrue(any("Invalid format" in e for e in errors))
        finally:
            os.unlink(env_path)


class TestInferType(unittest.TestCase):
    def test_int(self):
        self.assertEqual(infer_type("100000"), "int")  # outside port range
        self.assertEqual(infer_type("-10"), "int")

    def test_port(self):
        self.assertEqual(infer_type("8080"), "port")
        self.assertEqual(infer_type("3000"), "port")
        self.assertEqual(infer_type("99999"), "int")  # out of port range

    def test_bool(self):
        self.assertEqual(infer_type("true"), "bool")
        self.assertEqual(infer_type("false"), "bool")
        self.assertEqual(infer_type("TRUE"), "bool")

    def test_url(self):
        self.assertEqual(infer_type("https://example.com"), "url")
        self.assertEqual(infer_type("http://localhost:3000"), "url")

    def test_email(self):
        self.assertEqual(infer_type("user@example.com"), "email")

    def test_float(self):
        self.assertEqual(infer_type("3.14"), "float")

    def test_string(self):
        self.assertEqual(infer_type("hello world"), "string")

    def test_empty(self):
        self.assertEqual(infer_type(""), "empty")


class TestGenerateSchema(unittest.TestCase):
    def test_generate_basic(self):
        vars_dict = {"PORT": "8080", "DEBUG": "true", "DATABASE_URL": "postgres://localhost/db"}
        schema = generate_schema(vars_dict)
        self.assertIn("DATABASE_URL", schema)
        self.assertIn("PORT", schema)
        self.assertIn("DEBUG", schema)
        self.assertEqual(schema["PORT"]["type"], "port")
        self.assertEqual(schema["DEBUG"]["type"], "bool")


class TestValidateVariables(unittest.TestCase):
    def setUp(self):
        self.schema = {
            "PORT": {"required": True, "type": "port"},
            "DEBUG": {"required": True, "type": "bool"},
            "DATABASE_URL": {"required": True, "type": "url"},
            "OPTIONAL_KEY": {"required": False, "type": "string"},
        }

    def test_all_valid(self):
        vars_dict = {"PORT": "8080", "DEBUG": "true", "DATABASE_URL": "https://db.example.com"}
        issues = validate_variables(vars_dict, self.schema)
        self.assertEqual(len(issues), 0)

    def test_missing_required(self):
        vars_dict = {"PORT": "8080", "DEBUG": "true"}
        issues = validate_variables(vars_dict, self.schema)
        self.assertTrue(any("MISSING" in i and "DATABASE_URL" in i for i in issues))

    def test_type_mismatch_port(self):
        vars_dict = {"PORT": "not_a_port", "DEBUG": "true", "DATABASE_URL": "https://db.example.com"}
        issues = validate_variables(vars_dict, self.schema)
        self.assertTrue(any("PORT" in i and "TYPE" in i for i in issues))

    def test_type_mismatch_bool(self):
        vars_dict = {"PORT": "8080", "DEBUG": "yes", "DATABASE_URL": "https://db.example.com"}
        issues = validate_variables(vars_dict, self.schema)
        self.assertTrue(any("DEBUG" in i and "TYPE" in i for i in issues))

    def test_production_check(self):
        vars_dict = {"PORT": "8080", "DEBUG": "true", "DATABASE_URL": "https://db.example.com"}
        issues = validate_variables(vars_dict, self.schema, check_production=True)
        self.assertTrue(any("PROD" in i and "DEBUG" in i for i in issues))

    def test_optional_missing_ok(self):
        vars_dict = {"PORT": "8080", "DEBUG": "true", "DATABASE_URL": "https://db.example.com"}
        issues = validate_variables(vars_dict, self.schema)
        self.assertFalse(any("OPTIONAL_KEY" in i for i in issues))


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_check_command(self):
        env_path = os.path.join(self.test_dir, ".env")
        schema_path = os.path.join(self.test_dir, "schema.json")
        with open(env_path, "w") as f:
            f.write("PORT=8080\nDEBUG=true\n")
        with open(schema_path, "w") as f:
            json.dump({
                "PORT": {"required": True, "type": "port"},
                "DEBUG": {"required": True, "type": "bool"},
            }, f)

        result = subprocess.run(
            [sys.executable, "-m", "dotenvdoctor.cli", "check", "--schema", schema_path, "--env", env_path],
            capture_output=True, text=True, cwd=str(Path(__file__).resolve().parent.parent),
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("passed", result.stdout.lower())

    def test_check_with_issues(self):
        env_path = os.path.join(self.test_dir, ".env")
        schema_path = os.path.join(self.test_dir, "schema.json")
        with open(env_path, "w") as f:
            f.write("PORT=abc\n")
        with open(schema_path, "w") as f:
            json.dump({"PORT": {"required": True, "type": "port"}}, f)

        result = subprocess.run(
            [sys.executable, "-m", "dotenvdoctor.cli", "check", "--schema", schema_path, "--env", env_path],
            capture_output=True, text=True, cwd=str(Path(__file__).resolve().parent.parent),
        )
        self.assertIn("ISSUE", result.stdout)

    def test_init_command(self):
        env_path = os.path.join(self.test_dir, ".env")
        with open(env_path, "w") as f:
            f.write("PORT=8080\nDEBUG=true\nNAME=myapp\n")

        result = subprocess.run(
            [sys.executable, "-m", "dotenvdoctor.cli", "init", "--env", env_path],
            capture_output=True, text=True, cwd=str(Path(__file__).resolve().parent.parent),
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("PORT", result.stdout)
        self.assertIn("DEBUG", result.stdout)

    def test_init_with_output_file(self):
        env_path = os.path.join(self.test_dir, ".env")
        out_path = os.path.join(self.test_dir, "out.json")
        with open(env_path, "w") as f:
            f.write("KEY=val\n")

        result = subprocess.run(
            [sys.executable, "-m", "dotenvdoctor.cli", "init", "--env", env_path, "--output", out_path],
            capture_output=True, text=True, cwd=str(Path(__file__).resolve().parent.parent),
        )
        self.assertEqual(result.returncode, 0)
        self.assertTrue(os.path.exists(out_path))

    def test_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "dotenvdoctor.cli", "--help"],
            capture_output=True, text=True, cwd=str(Path(__file__).resolve().parent.parent),
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("check", result.stdout)
        self.assertIn("init", result.stdout)

    def test_production_flag(self):
        env_path = os.path.join(self.test_dir, ".env")
        schema_path = os.path.join(self.test_dir, "schema.json")
        with open(env_path, "w") as f:
            f.write("DEBUG=true\n")
        with open(schema_path, "w") as f:
            json.dump({"DEBUG": {"required": True, "type": "bool"}}, f)

        result = subprocess.run(
            [sys.executable, "-m", "dotenvdoctor.cli", "check", "--schema", schema_path, "--env", env_path, "--production"],
            capture_output=True, text=True, cwd=str(Path(__file__).resolve().parent.parent),
        )
        self.assertIn("PROD", result.stdout)


if __name__ == "__main__":
    unittest.main()
