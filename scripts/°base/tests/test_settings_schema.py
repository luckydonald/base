from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[3]
SETTINGS_DIR = ROOT / "ai" / "settings"


def load_json(name: str) -> dict[str, Any]:
    value = json.loads((SETTINGS_DIR / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{name} must contain an object")
    # end if
    return value
# end def


def schema_registry() -> Registry:
    schemas = [
        load_json("settings.schema.json"),
        load_json("settings-local.schema.json"),
        load_json("mcp.schema.json"),
    ]
    resources = [
        (schema["$id"], Resource.from_contents(schema))
        for schema in schemas
    ]
    return Registry().with_resources(resources)
# end def


class ToolSettingsSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.shared_schema = load_json("settings.schema.json")
        cls.local_schema = load_json("settings-local.schema.json")
        registry = schema_registry()
        cls.shared_validator = Draft202012Validator(cls.shared_schema, registry=registry)
        cls.local_validator = Draft202012Validator(cls.local_schema, registry=registry)
    # end def

    def assertValid(self, validator: Draft202012Validator, value: dict[str, Any]) -> None:
        errors = sorted(validator.iter_errors(value), key=lambda error: list(error.path))
        self.assertEqual(errors, [], "\n".join(error.message for error in errors))
    # end def

    def assertInvalid(self, validator: Draft202012Validator, value: dict[str, Any]) -> None:
        self.assertTrue(list(validator.iter_errors(value)))
    # end def

    def test_repository_settings_matches_shared_schema(self) -> None:
        self.assertValid(self.shared_validator, load_json("settings.json"))
    # end def

    def test_shared_schema_accepts_yarn_policy(self) -> None:
        self.assertValid(
            self.shared_validator,
            {"pre_commit": {"yarn@4": {"enabled": True}}},
        )
    # end def

    def test_shared_schema_rejects_malformed_yarn_policy(self) -> None:
        for value in (
            {"pre_commit": {"yarn@4": {"enabled": "yes"}}},
            {"pre_commit": {"yarn@4": {}}},
            {"pre_commit": {"yarn@4": {"enabled": True, "extra": True}}},
        ):
            with self.subTest(value=value):
                self.assertInvalid(self.shared_validator, value)
            # end with
        # end for
    # end def

    def test_local_schema_accepts_other_pre_commit_settings(self) -> None:
        self.assertValid(
            self.local_validator,
            {
                "$schema": "./settings-local.schema.json",
                "pre_commit": {"other": {"enabled": False}},
            },
        )
    # end def

    def test_local_schema_rejects_yarn_policy_at_any_value(self) -> None:
        for value in (True, False, None, {"enabled": True}, {"enabled": False}):
            with self.subTest(value=value):
                self.assertInvalid(
                    self.local_validator,
                    {
                        "$schema": "./settings-local.schema.json",
                        "pre_commit": {"yarn@4": value},
                    },
                )
            # end with
        # end for
    # end def
# end class


if __name__ == "__main__":
    unittest.main()
