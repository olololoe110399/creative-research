from __future__ import annotations

import io
import json
import logging
from pathlib import Path

import pandas as pd
import pytest

from creative_research.infrastructure import storage
from creative_research.infrastructure.config import RuntimeSettings, load_env_file, project_context
from creative_research.infrastructure.logging import logging_context
from creative_research.infrastructure.source_graph import implementation_sources


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "invalid"])
@pytest.mark.parametrize(
    "setting", ["REQUEST_TIMEOUT", "SUBPROCESS_TIMEOUT", "SERVER_REQUEST_TIMEOUT", "AI_TIMEOUT"]
)
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
    monkeypatch.setenv("GEMINI_API_KEY", secret)
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


def test_private_json_and_dataframe_outputs_round_trip(tmp_path) -> None:
    path = tmp_path / "private.json"
    storage.write_json(path, {"state": "planned"}, mode=0o600)
    assert path.stat().st_mode & 0o777 == 0o600
    storage.write_json(path, {"state": "running"})
    assert path.stat().st_mode & 0o777 == 0o600
    frame = pd.DataFrame([{"id": "a", "value": 42}])
    storage.write_csv(tmp_path / "table.csv", frame, encoding="utf-8-sig")
    storage.write_parquet(tmp_path / "table.parquet", frame)
    pd.testing.assert_frame_equal(pd.read_csv(tmp_path / "table.csv"), frame)
    pd.testing.assert_frame_equal(pd.read_parquet(tmp_path / "table.parquet"), frame)
    storage.append_jsonl_rows(tmp_path / "checkpoint.jsonl", [{"id": 1}, {"id": 2}])
    assert len((tmp_path / "checkpoint.jsonl").read_text().splitlines()) == 2


def test_pipeline_implementation_graph_includes_domain_and_infrastructure() -> None:
    paths = implementation_sources("creative_research.cli.commands.build_warehouse")
    assert any(path.parts[-2:] == ("analysis", "build_warehouse.py") for path in paths)
    assert any(path.parts[-2:] == ("infrastructure", "storage.py") for path in paths)
    assert implementation_sources("creative_research_other.module") == ()
    assert all(isinstance(path, Path) and path.is_file() for path in paths)


def test_analysis_does_not_import_cli_adapters() -> None:
    import ast

    root = Path(__file__).resolve().parents[2] / "src/creative_research/analysis"
    for path in root.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("creative_research.cli.commands"), path


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


def test_shared_cache_fingerprint_preserves_sha1_identity(tmp_path):
    path = tmp_path / "media"
    path.write_bytes(b"abc")
    assert storage.file_sha1(path) == "a9993e364706816aba3e25717850c26c9cd0d89d"


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


def test_directory_replacement_retains_backup_and_partial_failures_keep_old_tree(tmp_path):
    target = tmp_path / "media"
    target.mkdir()
    (target / "original.txt").write_text("old")
    with pytest.raises(OSError, match="copy failed"):
        with storage.replace_directory(target) as staged:
            (staged / "partial.txt").write_text("partial")
            raise OSError("copy failed")
    assert list(tmp_path.iterdir()) == [target]
    assert (target / "original.txt").read_text() == "old"
    with storage.replace_directory(target) as staged:
        (staged / "new.txt").write_text("new")
    backups = list(tmp_path.glob(".media.backup-*"))
    assert len(backups) == 1
    assert (backups[0] / "original.txt").read_text() == "old"
    assert list(target.iterdir()) == [target / "new.txt"]


def test_atomic_output_replaces_leaf_symlink_without_modifying_external_target(tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text("private original")
    target = tmp_path / "export.json"
    target.symlink_to(outside)
    storage.write_json(target, {"safe": True})
    assert outside.read_text() == "private original"
    assert not target.is_symlink()
    assert json.loads(target.read_text()) == {"safe": True}


def test_directory_publication_failure_rolls_back_and_symlinks_are_rejected(tmp_path, monkeypatch):
    target = tmp_path / "details"
    target.mkdir()
    (target / "original.txt").write_text("old")
    original = Path.replace

    def fail_staged(path, destination):
        if path.name == "content":
            raise OSError("publish failed")
        return original(path, destination)

    monkeypatch.setattr(Path, "replace", fail_staged)
    with pytest.raises(OSError, match="publish failed"):
        with storage.replace_directory(target) as staged:
            (staged / "new.txt").write_text("new")
    assert list(tmp_path.iterdir()) == [target]
    assert (target / "original.txt").read_text() == "old"
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="regular output directory"):
        with storage.replace_directory(alias):
            pytest.fail("Must reject symlink before writing")
