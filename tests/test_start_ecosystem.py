"""TDD: pm2.start_ecosystem(config, only=NAME, cwd=...) bootstraps from an
ecosystem.config.js file via the pm2 CLI (since .js needs node). The --only
filter must NOT touch sibling apps in the file."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

import pm2
from tests.conftest import SLEEPER, cli_delete, unique_name


def _write_two_app_ecosystem(dest: Path, name_a: str, name_b: str) -> Path:
    config = dest / "ecosystem.config.js"
    config.write_text(textwrap.dedent(f"""
        module.exports = {{
          apps: [
            {{
              name: "{name_a}",
              script: "{SLEEPER}",
              interpreter: "{sys.executable}",
              autorestart: false
            }},
            {{
              name: "{name_b}",
              script: "{SLEEPER}",
              interpreter: "{sys.executable}",
              autorestart: false
            }}
          ]
        }}
    """).strip())
    return config


@pytest.fixture
def two_app_config(tmp_path: Path) -> tuple[Path, str, str]:
    name_a = unique_name() + "-a"
    name_b = unique_name() + "-b"
    config = _write_two_app_ecosystem(tmp_path, name_a, name_b)
    yield config, name_a, name_b
    cli_delete(name_a)
    cli_delete(name_b)


def test_start_ecosystem_with_only_starts_just_one(
    two_app_config: tuple[Path, str, str], tmp_path: Path
) -> None:
    config, name_a, name_b = two_app_config

    started = pm2.start_ecosystem(config, only=name_a, cwd=tmp_path)

    assert isinstance(started, list)
    assert [p.name for p in started] == [name_a]
    assert pm2.exists(name_a) is True
    assert pm2.exists(name_b) is False, "--only must not touch sibling apps"


def test_start_ecosystem_respects_cwd(
    two_app_config: tuple[Path, str, str], tmp_path: Path
) -> None:
    config, name_a, _ = two_app_config
    pm2.start_ecosystem(config, only=name_a, cwd=tmp_path)
    p = pm2.describe(name_a)
    assert p.pm2_env.get("pm_cwd") == str(tmp_path)
