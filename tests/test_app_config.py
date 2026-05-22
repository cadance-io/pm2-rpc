"""Unit tests for _app_config helpers. Pure functions, no socket I/O."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import get_type_hints

import pytest

from pm2_rpc import _app_config as ac
from pm2_rpc._types import AppConfig, PM2Env

# _sanitize_name --------------------------------------------------------------


def test_sanitize_name_keeps_alphanumeric_dot_dash() -> None:
    assert ac._sanitize_name("foo-bar.baz_qux") == "foo-bar.baz-qux"


def test_sanitize_name_replaces_other_chars_with_dash() -> None:
    assert ac._sanitize_name("a b/c@d") == "a-b-c-d"


# _resolve_script -------------------------------------------------------------


def test_resolve_script_absolute_path(tmp_path: Path) -> None:
    f = tmp_path / "x.py"
    f.write_text("print('hi')")
    assert ac._resolve_script(str(f), tmp_path) == f


def test_resolve_script_relative_to_cwd(tmp_path: Path) -> None:
    f = tmp_path / "x.py"
    f.write_text("print('hi')")
    assert ac._resolve_script("x.py", tmp_path) == f


def test_resolve_script_does_not_fall_back_to_path(tmp_path: Path) -> None:
    """`python3` is on $PATH but we deliberately do not resolve it.

    Otherwise `pm2.start('python3')` would happily start a bare interpreter
    that PM2 then thrashes restarting.
    """
    with pytest.raises(FileNotFoundError):
        ac._resolve_script("python3", tmp_path)


def test_resolve_script_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ac._resolve_script("definitely-not-a-real-thing-xyz", tmp_path)


# _resolve_interpreter --------------------------------------------------------


@pytest.mark.parametrize(
    "ext,expected",
    [
        (".py", sys.executable),
        (".js", "node"),
        (".mjs", "node"),
        (".cjs", "node"),
        (".ts", "ts-node"),
        (".sh", "bash"),
        (".rb", "ruby"),
        (".php", "php"),
        (".pl", "perl"),
        (".whatever", "none"),  # PM2's sentinel for "exec directly"
    ],
)
def test_resolve_interpreter_by_extension(ext, expected) -> None:
    assert ac._resolve_interpreter(ext, explicit=None) == expected


def test_resolve_interpreter_explicit_wins_over_extension() -> None:
    assert ac._resolve_interpreter(".py", "/opt/custom/python") == "/opt/custom/python"


# _default_paths --------------------------------------------------------------


def test_default_paths_under_pm2_dir() -> None:
    paths = ac._default_paths("myapp")
    home_pm2 = str(Path.home() / ".pm2")
    assert paths["pm_out_log_path"].startswith(home_pm2)
    assert paths["pm_err_log_path"].startswith(home_pm2)
    assert paths["pm_pid_path"].startswith(home_pm2)
    assert "myapp" in paths["pm_out_log_path"]
    assert paths["pm_out_log_path"].endswith("-out.log")
    assert paths["pm_err_log_path"].endswith("-error.log")
    assert paths["pm_pid_path"].endswith(".pid")


# _merge_env ------------------------------------------------------------------


def test_merge_env_starts_from_os_environ() -> None:
    merged = ac._merge_env({}, interpreter="/bin/true")
    assert merged.get("PATH") == os.environ.get("PATH")


def test_merge_env_extra_overrides_os_environ(monkeypatch) -> None:
    monkeypatch.setenv("FOO_BAR", "baseline")
    merged = ac._merge_env({"FOO_BAR": "override"}, interpreter="/bin/true")
    assert merged["FOO_BAR"] == "override"


def test_merge_env_python_sets_pythonunbuffered() -> None:
    merged = ac._merge_env({}, interpreter=sys.executable)
    assert merged["PYTHONUNBUFFERED"] == "1"


def test_merge_env_non_python_does_not_set_pythonunbuffered(monkeypatch) -> None:
    monkeypatch.delenv("PYTHONUNBUFFERED", raising=False)
    merged = ac._merge_env({}, interpreter="node")
    assert "PYTHONUNBUFFERED" not in merged


# build_app_config ------------------------------------------------------------


def test_build_app_config_minimum_inputs(tmp_path: Path) -> None:
    script = tmp_path / "sleeper.py"
    script.write_text("import time; time.sleep(1)")

    cfg = ac.build_app_config(script=str(script), cwd=tmp_path)

    # canonical shape PM2's prepare expects
    assert cfg["name"] == "sleeper"
    assert cfg["pm_exec_path"] == str(script)
    assert cfg["pm_cwd"] == str(tmp_path)
    assert cfg["exec_interpreter"] == sys.executable
    assert cfg["exec_mode"] == "fork_mode"
    assert cfg["autorestart"] is True
    assert cfg["instances"] == 1
    assert cfg["args"] == []
    assert cfg["node_args"] == []
    assert cfg["merge_logs"] is False
    assert isinstance(cfg["env"], dict)
    assert cfg["env"]["PYTHONUNBUFFERED"] == "1"


def test_build_app_config_explicit_name_is_sanitized(tmp_path: Path) -> None:
    script = tmp_path / "x.py"
    script.write_text("")
    cfg = ac.build_app_config(script=str(script), name="weird name/here", cwd=tmp_path)
    assert cfg["name"] == "weird-name-here"


def test_build_app_config_args_string_splits_to_list(tmp_path: Path) -> None:
    script = tmp_path / "x.py"
    script.write_text("")
    cfg = ac.build_app_config(script=str(script), args="--foo bar", cwd=tmp_path)
    assert cfg["args"] == ["--foo", "bar"]


def test_build_app_config_log_paths_match_name(tmp_path: Path) -> None:
    script = tmp_path / "x.py"
    script.write_text("")
    cfg = ac.build_app_config(script=str(script), name="myapp", cwd=tmp_path)
    assert "myapp-out.log" in cfg["pm_out_log_path"]
    assert "myapp-error.log" in cfg["pm_err_log_path"]


def test_build_app_config_custom_log_files(tmp_path: Path) -> None:
    script = tmp_path / "x.py"
    script.write_text("")
    out = tmp_path / "out.log"
    err = tmp_path / "err.log"
    cfg = ac.build_app_config(script=str(script), cwd=tmp_path, out_file=out, error_file=err)
    assert cfg["pm_out_log_path"] == str(out)
    assert cfg["pm_err_log_path"] == str(err)


def test_appconfig_has_optional_lifecycle_keys() -> None:
    hints = get_type_hints(AppConfig, include_extras=False)
    assert "kill_timeout" in hints
    assert "kill_signal" in hints
    assert "watch" in hints
    assert "kill_timeout" in AppConfig.__optional_keys__
    assert "kill_signal" in AppConfig.__optional_keys__
    assert "watch" in AppConfig.__optional_keys__


def test_pm2env_exposes_kill_signal() -> None:
    assert "kill_signal" in get_type_hints(PM2Env, include_extras=False)
