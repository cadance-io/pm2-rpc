"""TDD: pm2.start_ecosystem() parses .json/.yaml natively over the socket.
--only filter must NOT touch sibling apps. .js raises UnsupportedConfigError."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

import pm2_rpc as pm2
from tests.conftest import SLEEPER, _safe_delete, unique_name


def _two_app_payload(name_a: str, name_b: str) -> dict:
    return {
        "apps": [
            {
                "name": name_a,
                "script": str(SLEEPER),
                "interpreter": sys.executable,
                "autorestart": False,
            },
            {
                "name": name_b,
                "script": str(SLEEPER),
                "interpreter": sys.executable,
                "autorestart": False,
            },
        ]
    }


@pytest.fixture
def two_app_names() -> tuple[str, str]:
    name_a = unique_name() + "-a"
    name_b = unique_name() + "-b"
    yield name_a, name_b
    _safe_delete(name_a)
    _safe_delete(name_b)


def _write_json(dest: Path, payload: dict) -> Path:
    p = dest / "ecosystem.config.json"
    p.write_text(json.dumps(payload))
    return p


def _write_yaml(dest: Path, payload: dict) -> Path:
    p = dest / "ecosystem.config.yaml"
    p.write_text(yaml.safe_dump(payload))
    return p


@pytest.mark.parametrize("writer", [_write_json, _write_yaml], ids=["json", "yaml"])
def test_start_ecosystem_only_starts_just_one(
    two_app_names: tuple[str, str], tmp_path: Path, writer
) -> None:
    name_a, name_b = two_app_names
    config = writer(tmp_path, _two_app_payload(name_a, name_b))

    started = pm2.start_ecosystem(config, only=name_a, cwd=tmp_path)

    assert [p["pm2_env"]["name"] for p in started] == [name_a]
    assert pm2.exists(name_a) is True
    assert pm2.exists(name_b) is False, "--only must not touch sibling apps"


def test_start_ecosystem_starts_all_apps_when_only_omitted(
    two_app_names: tuple[str, str], tmp_path: Path
) -> None:
    name_a, name_b = two_app_names
    config = _write_json(tmp_path, _two_app_payload(name_a, name_b))

    started = pm2.start_ecosystem(config, cwd=tmp_path)

    names = {p["pm2_env"]["name"] for p in started}
    assert names == {name_a, name_b}


def test_start_ecosystem_respects_cwd(two_app_names: tuple[str, str], tmp_path: Path) -> None:
    name_a, _ = two_app_names
    config = _write_json(tmp_path, _two_app_payload(name_a, _ + "ignored"))
    pm2.start_ecosystem(config, only=name_a, cwd=tmp_path)
    assert pm2.describe(name_a)["pm2_env"]["pm_cwd"] == str(tmp_path)


def test_start_ecosystem_js_raises_unsupported(tmp_path: Path) -> None:
    config = tmp_path / "ecosystem.config.js"
    config.write_text("module.exports = { apps: [] }")
    with pytest.raises(pm2.UnsupportedConfigError, match="node"):
        pm2.start_ecosystem(config)


def test_start_ecosystem_only_unknown_raises_notfound(tmp_path: Path) -> None:
    config = _write_json(tmp_path, _two_app_payload("a", "b"))
    with pytest.raises(pm2.NotFound):
        pm2.start_ecosystem(config, only="not-in-file")


def test_start_ecosystem_env_per_app_reaches_process(
    two_app_names: tuple[str, str], tmp_path: Path
) -> None:
    name_a, name_b = two_app_names
    payload = _two_app_payload(name_a, name_b)
    payload["apps"][0]["env"] = {"APP_MODE": "suite"}
    config = _write_json(tmp_path, payload)

    pm2.start_ecosystem(config, only=name_a, cwd=tmp_path)
    assert pm2.env(name_a)["APP_MODE"] == "suite"
