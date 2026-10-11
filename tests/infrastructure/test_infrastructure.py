from __future__ import annotations

import io
import json
import logging
from pathlib import Path

import pytest

from creative_research.infrastructure import storage
from creative_research.infrastructure.config import RuntimeSettings, load_env_file, project_context
from creative_research.infrastructure.logging import logging_context


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "invalid"])
@pytest.mark.parametrize("setting", ["REQUEST_TIMEOUT", "SUBPROCESS_TIMEOUT"])
def test_timeout_settings_reject_non_positive_or_non_finite_numbers(setting, value) -> None:
    with pytest.raises(ValueError, match=setting):
        RuntimeSettings.from_environ({"CREATIVE_RESEARCH_" + setting: value})


def test_settings_normalize_and_validate(tmp_path) -> None:
    settings = RuntimeSettings.from_environ(
        {
            "CREATIVE_RESEARCH_PROJECT_ROOT": str(tmp_path),
            "CREATIVE_RESEARCH_LOG_LEVEL": "debug",
            "CREATIVE_RESEARCH_LOG_FORMAT": "JSON",
        }
    )
    assert settings.project_root == tmp_path
    assert settings.log_level == "DEBUG"
    assert settings.log_format == "json"
    for key in ("LOG_LEVEL", "LOG_FORMAT"):
        with pytest.raises(ValueError, match=key):
            RuntimeSettings.from_environ({"CREATIVE_RESEARCH_" + key: "unknown"})


def test_env_loading_is_explicit_literal_and_preserves_process_values(tmp_path) -> None:
    path = tmp_path / ".env"
    path.write_text(
        "\ufeff# comment\nexport EXISTING=changed\nVALUE='$(never-execute)'\nTEXT=\"two words\" # comment\nEMPTY=\n"
    )
    env = {"EXISTING": "original"}
    load_env_file(path, env)
    assert env == {
        "EXISTING": "original",
        "VALUE": "$(never-execute)",
        "TEXT": "two words",
        "EMPTY": "",
    }


@pytest.mark.parametrize(
    "invalid", ["BAD KEY=secret", "TOKEN='unterminated-secret", "TOKEN=unquoted secret"]
)
def test_invalid_env_file_does_not_partially_change_environment_or_expose_values(
    tmp_path, invalid
) -> None:
    path = tmp_path / ".env"
    path.write_text("VALID=value\n" + invalid)
    env = {}
    with pytest.raises(ValueError) as error:
        load_env_file(path, env)
    assert env == {}
    assert "secret" not in str(error.value)
    assert ":2" in str(error.value)


def test_project_context_restores_after_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CREATIVE_RESEARCH_PROJECT_ROOT", "previous")
    with pytest.raises(RuntimeError), project_context(tmp_path):
        assert RuntimeSettings.from_environ().project_root == tmp_path
        raise RuntimeError("failure")
    import os

    assert os.environ["CREATIVE_RESEARCH_PROJECT_ROOT"] == "previous"


@pytest.mark.parametrize("structured", [False, True])
def test_logging_redacts_credentials_and_restores_handlers(monkeypatch, structured) -> None:
    secret = 'credential-with-"quote\\and-unicode-đ'
    monkeypatch.setenv("APIFY_TOKEN", secret)
    logger = logging.getLogger("creative_research.test")
    app_logger = logging.getLogger("creative_research")
    previous = (app_logger.handlers[:], app_logger.level, app_logger.propagate)
    stream = io.StringIO()
    with logging_context(level="DEBUG", log_format="json" if structured else "text", stream=stream):
        logger.info(
            "request failed %s",
            secret,
            extra={
                "context": {
                    "api_key": "hidden",
                    "nested": [{"password": "hidden"}],
                    "url": "https://example.test?token=abcdef",
                }
            },
        )
    text = stream.getvalue()
    assert secret not in text
    assert "abcdef" not in text
    assert (app_logger.handlers, app_logger.level, app_logger.propagate) == previous
    if structured:
        payload = json.loads(text)
        assert payload["context"]["nested"][0]["password"] == "[REDACTED]"
        assert payload["context"]["api_key"] == "[REDACTED]"


def test_atomic_write_retains_old_content_when_publication_fails(tmp_path, monkeypatch) -> None:
    path = tmp_path / "state.json"
    path.write_text("original")

    def fail(*args):
        raise OSError("disk failure")

    monkeypatch.setattr(storage.os, "replace", fail)
    with pytest.raises(OSError, match="disk failure"):
        storage.write_json(path, {"new": True})
    assert path.read_text() == "original"
    assert list(tmp_path.iterdir()) == [path]


def test_atomic_writer_cleans_up_on_serialization_failure(tmp_path) -> None:
    path = tmp_path / "records.jsonl"
    path.write_text("original")

    def rows():
        yield {"ok": True}
        raise ValueError("broken source")

    with pytest.raises(ValueError), storage.atomic_output(path) as temporary:
        temporary.write_text("unfinished")
        raise ValueError("broken source")
    with pytest.raises(ValueError):
        storage.write_jsonl(path, rows())
    assert path.read_text() == "original"
    assert list(tmp_path.iterdir()) == [path]


def test_private_json_and_append_checkpoints_round_trip(tmp_path) -> None:
    path = tmp_path / "private.json"
    storage.write_json(path, {"state": "planned"}, mode=0o600)
    assert path.stat().st_mode & 0o777 == 0o600
    storage.write_json(path, {"state": "running"})
    assert path.stat().st_mode & 0o777 == 0o600
    storage.append_jsonl_rows(tmp_path / "checkpoint.jsonl", [{"id": 1}, {"id": 2}])
    assert len((tmp_path / "checkpoint.jsonl").read_text().splitlines()) == 2


def test_jsonl_defaults_to_strict_location_errors_without_payload_disclosure(tmp_path):
    path = tmp_path / "cache.jsonl"
    path.write_text('\ufeff{"id": 1}\n\nsecret-partial-json\n', encoding="utf-8")
    with pytest.raises(ValueError, match="cache.jsonl:3") as error:
        storage.read_jsonl(path)
    assert isinstance(error.value.__cause__, json.JSONDecodeError)
    assert "secret-partial-json" not in str(error.value)


def test_resumable_jsonl_skips_invalid_rows_with_safe_diagnostics(tmp_path, caplog):
    path = tmp_path / "cache.jsonl"
    path.write_text('{"id": 1}\n[]\n{"id": 2}\nsecret-partial-json', encoding="utf-8")
    assert storage.read_jsonl(path, tolerate_invalid=True) == [{"id": 1}, {"id": 2}]
    records = [record for record in caplog.records if record.message == "invalid_jsonl_row"]
    assert [record.context["line"] for record in records] == [2, 4]
    assert "secret-partial-json" not in caplog.text


def test_jsonl_missing_and_non_object_inputs_are_explicit(tmp_path):
    path = tmp_path / "input.jsonl"
    with pytest.raises(FileNotFoundError):
        storage.read_jsonl(path)
    assert storage.read_jsonl(path, missing_ok=True) == []
    path.write_text('"not an object"\n')
    with pytest.raises(ValueError, match="input.jsonl:1"):
        storage.read_jsonl(path)


def test_tolerant_jsonl_does_not_suppress_io_failures(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise PermissionError("synthetic denial")

    monkeypatch.setattr(Path, "open", fail)
    with pytest.raises(PermissionError):
        storage.read_jsonl(tmp_path / "cache", tolerate_invalid=True)


def test_json_metadata_recovery_is_explicit_and_does_not_hide_io(tmp_path, monkeypatch, caplog):
    path = tmp_path / "metadata.json"
    assert storage.read_json_object(path, missing_ok=True) == {}
    with pytest.raises(FileNotFoundError):
        storage.read_json_object(path)
    path.write_text("secret-invalid-json")
    with pytest.raises(ValueError, match="Invalid JSON object"):
        storage.read_json_object(path)
    assert storage.read_json_object(path, tolerate_invalid=True) == {}
    assert "invalid_json_metadata" in caplog.text and "secret-invalid-json" not in caplog.text
    path.write_text("[]")
    with pytest.raises(ValueError):
        storage.read_json_object(path)
    path.write_text('\ufeff{"id": 1}', encoding="utf-8")
    assert storage.read_json_object(path) == {"id": 1}

    def denied(*args, **kwargs):
        raise PermissionError("synthetic denial")

    monkeypatch.setattr(Path, "read_text", denied)
    with pytest.raises(PermissionError):
        storage.read_json_object(path, tolerate_invalid=True)


def test_atomic_output_replaces_leaf_symlink_without_modifying_external_target(tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text("private original")
    target = tmp_path / "export.json"
    target.symlink_to(outside)
    storage.write_json(target, {"safe": True})
    assert outside.read_text() == "private original"
    assert not target.is_symlink()
    assert json.loads(target.read_text()) == {"safe": True}
