from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest
from google.genai import types

from creative_research.cli import app as cli
from creative_research.cli.commands import vision_slides as slides_command
from creative_research.cli.commands import vision_videos as videos_command
from creative_research.infrastructure import gemini
from creative_research.vision import slides as vision_slides
from creative_research.vision import videos as vision_videos
from creative_research.vision.models import SlideshowCreativeAnalysis, VideoCreativeAnalysis


def _run_command(module):
    command = slides_command if module is vision_slides else videos_command
    command.main()


def _schema_fingerprint(model):
    schema = model.model_json_schema()
    definitions = schema.get("$defs", {})

    def expand(value):
        if isinstance(value, list):
            return [expand(item) for item in value]
        if not isinstance(value, dict):
            return value
        if "$ref" in value:
            return expand(definitions[value["$ref"].rsplit("/", 1)[-1]])
        return {key: expand(item) for key, item in value.items() if key not in {"$defs", "title"}}

    return hashlib.sha256(json.dumps(expand(schema), sort_keys=True).encode()).hexdigest()


@pytest.mark.parametrize(
    ("model", "fingerprint"),
    [
        (
            SlideshowCreativeAnalysis,
            "13c92fbb3601644e011f68546cd8ca7029d6126f58b50796029c1975a41641e9",
        ),
        (VideoCreativeAnalysis, "7576b8b6a994ce68d6935df78fd3dba0ef57cf620ef9d4186343b8f37128eb0f"),
    ],
)
def test_response_field_enum_default_contract_matches_pre_refactor_schema(model, fingerprint):
    # Fingerprints captured before extracting/renaming model classes; titles are not data.
    assert _schema_fingerprint(model) == fingerprint


def _analysis(module):
    common = {
        "primary_language_code": "en",
        "mixed_language": False,
        "audience_segment": "college_student",
        "niche": "synthetic study tips",
        "topic": "study methods",
        "content_angle": "study_method",
        "value_type": "how_to",
        "narrative_structure": ["hook", "value"],
        "creative_formula": "synthetic hook -> value",
        "overall_confidence": 0.9,
    }
    if module is vision_slides:
        return SlideshowCreativeAnalysis.model_validate(
            {
                **common,
                "hook": {"slide_index": 1, "technique": "how_to"},
                "slides": [
                    {
                        "slide_index": 1,
                        "role": "hook",
                        "visual_type": "notes_or_document",
                        "visual_description": "synthetic notes",
                        "product_visible": False,
                        "confidence": 0.9,
                    }
                ],
                "content_format": "tutorial",
                "visual_style": {
                    "dominant_visual_type": "notes_or_document",
                    "aesthetic": "plain",
                    "image_realism": "uncertain",
                    "pinterest_like_aesthetic": "no",
                    "pinterest_note": "not inferred",
                    "text_overlay_style": "plain",
                    "visual_consistency_across_slides": "high",
                },
                "product": {
                    "has_visible_product": False,
                    "product_family": "none",
                    "placement_style": "none",
                },
                "cta": {"has_visible_cta": False, "cta_type": "none"},
            }
        )
    return VideoCreativeAnalysis.model_validate(
        {
            **common,
            "video_format": "tutorial",
            "hook": {"start_second": 0, "end_second": 2, "technique": "how_to"},
            "timeline": [],
            "dominant_visual_type": "notes_or_document",
            "visual_aesthetic": "plain",
            "text_overlay_style": "plain",
            "editing_style": "static",
            "camera_style": "static",
            "face_or_person_present": False,
            "audio": {
                "has_speech": False,
                "has_background_music": False,
                "narration_style": "no_speech",
                "pacing": "medium",
            },
            "product": {
                "has_visible_or_spoken_product": False,
                "product_family": "none",
                "placement_style": "none",
            },
            "cta": {"has_explicit_cta": False, "cta_type": "none", "modality": "none"},
        }
    )


@pytest.mark.parametrize("module", [vision_slides, vision_videos])
@pytest.mark.parametrize("parsed", [True, False])
def test_provider_response_accepts_typed_or_json_contract_and_closes_upload(
    tmp_path, module, parsed
):
    analysis = _analysis(module)
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(
        parsed=analysis if parsed else None, text=analysis.model_dump_json()
    )
    if module is vision_slides:
        (tmp_path / "slide_001.png").write_bytes(b"synthetic-image")
        result = module.analyze_slideshow(client, "synthetic-model", tmp_path, "creator", "1", 0.1)
    else:
        client.files.upload.return_value = types.File(name="files/synthetic", state="ACTIVE")
        result = module.analyze_video(
            client, "synthetic-model", tmp_path / "video.mp4", "creator", "1", 10, 0.1, 30, False
        )
        client.files.delete.assert_called_once_with(name="files/synthetic")
    assert result == analysis
    assert client.models.generate_content.call_args.kwargs["config"].response_schema is type(
        analysis
    )


@pytest.mark.parametrize("keep_uploaded", [False, True])
def test_video_upload_cleanup_does_not_hide_original_processing_failure(keep_uploaded, caplog):
    client = MagicMock()
    client.files.upload.return_value = types.File(name="files/synthetic", state="FAILED")
    client.files.delete.side_effect = RuntimeError("synthetic cleanup failure")
    with pytest.raises(RuntimeError, match="state=FAILED"):
        vision_videos.analyze_video(
            client, "synthetic", Path("unused"), "creator", "1", 10, 0.1, 30, keep_uploaded
        )
    assert client.files.delete.call_count == (0 if keep_uploaded else 1)
    if not keep_uploaded:
        assert "uploaded_file_cleanup_failed" in caplog.text
        assert caplog.records[-1].context["hint"]


def test_video_polling_uses_monotonic_deadline_without_exceeding_sleep_budget(monkeypatch):
    clock = [100.0]
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(vision_videos.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(vision_videos.time, "sleep", sleep)
    client = MagicMock()
    with pytest.raises(TimeoutError, match="within 2s"):
        vision_videos.wait_until_active(
            client, types.File(name="files/synthetic", state="PROCESSING"), 2
        )
    assert sleeps == [2]
    client.files.get.assert_not_called()
    with pytest.raises(RuntimeError, match="missing its identifier"):
        vision_videos.wait_until_active(client, types.File(state="PROCESSING"), 30)


def test_video_polling_returns_active_file(monkeypatch):
    client = MagicMock()
    active = types.File(name="files/synthetic", state="ACTIVE")
    client.files.get.return_value = active
    monkeypatch.setattr(vision_videos.time, "sleep", lambda seconds: None)
    assert (
        vision_videos.wait_until_active(
            client, types.File(name=active.name, state="PROCESSING"), 30
        )
        is active
    )


def test_slideshow_index_repairs_and_evidence_normalization_remain_supported():
    analysis = _analysis(vision_slides)
    analysis.slides[0].slide_index = 0
    analysis.hook.slide_index = 0
    analysis.product.product_family = "single_product"
    analysis.cta.cta_type = "download"
    normalized, events = vision_slides.normalize_and_validate(analysis, 1)
    assert normalized.slides[0].slide_index == normalized.hook.slide_index == 1
    assert normalized.product.product_family == normalized.cta.cta_type == "none"
    assert "repaired_zero_based_index" in events
    with pytest.raises(ValueError, match="Expected 2 slides"):
        vision_slides.normalize_and_validate(normalized, 2)


@pytest.mark.parametrize("condition", ["hook_reversed", "hook_exceeds_duration", "product", "cta"])
def test_video_validation_rejects_inconsistent_evidence(condition):
    analysis = _analysis(vision_videos)
    if condition == "hook_reversed":
        analysis.hook.start_second = 3
    elif condition == "hook_exceeds_duration":
        analysis.hook.end_second = 100
    elif condition == "product":
        analysis.product.has_visible_or_spoken_product = True
    else:
        analysis.cta.has_explicit_cta = True
    with pytest.raises(ValueError):
        vision_videos.normalize_and_validate(analysis, 10)


def _manifest(tmp_path, module, account="creator", post_id="1"):
    media = tmp_path / "media"
    media.mkdir()
    row = {"account": account, "post_id": post_id}
    if module is vision_slides:
        (media / "slide_001.png").write_bytes(b"synthetic-image")
        row.update(post_dir=str(media), slide_count=1)
    else:
        video = media / "video.mp4"
        video.write_bytes(b"synthetic-video")
        row.update(video_path=str(video), duration_seconds=10)
    path = tmp_path / "manifest.csv"
    pd.DataFrame([row]).to_csv(path, index=False)
    return path


@pytest.mark.parametrize("module", [vision_slides, vision_videos])
def test_stage_publishes_checkpoints_reuses_cache_and_closes_provider(
    tmp_path, monkeypatch, module
):
    manifest = _manifest(tmp_path, module)
    factory = MagicMock()
    monkeypatch.setattr(gemini.genai, "Client", factory)
    client = factory.return_value.__enter__.return_value
    client.files.upload.return_value = types.File(name="files/synthetic", state="ACTIVE")
    client.models.generate_content.side_effect = [
        TimeoutError("synthetic transient"),
        SimpleNamespace(parsed=_analysis(module)),
    ]
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-key")
    output = tmp_path / "output"
    monkeypatch.setattr(
        "sys.argv",
        [
            module.__name__,
            str(manifest),
            "--out",
            str(output),
            "--sleep-between",
            "0",
            "--retries",
            "1",
        ],
    )
    _run_command(module)
    _run_command(module)
    assert client.models.generate_content.call_count == 2
    assert factory.return_value.__exit__.call_count == 2
    assert len(list((output / "by_post/creator").glob("*.json"))) == 1
    report_name = "report_v2.json" if module is vision_slides else "report.json"
    report = json.loads((output / report_name).read_text())
    assert report["analyzed_posts"] == 1 and report["failed_posts"] == 0


@pytest.mark.parametrize("module", [vision_slides, vision_videos])
def test_stage_closes_client_on_interrupt(tmp_path, monkeypatch, module):
    manifest = _manifest(tmp_path, module)
    factory = MagicMock()
    monkeypatch.setattr(gemini.genai, "Client", factory)
    client = factory.return_value.__enter__.return_value
    client.files.upload.return_value = types.File(name="files/synthetic", state="ACTIVE")
    client.models.generate_content.side_effect = KeyboardInterrupt()
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-key")
    monkeypatch.setattr(
        "sys.argv", [module.__name__, str(manifest), "--out", str(tmp_path / "output")]
    )
    with pytest.raises(KeyboardInterrupt):
        _run_command(module)
    factory.return_value.__exit__.assert_called_once()


@pytest.mark.parametrize("module", [vision_slides, vision_videos])
@pytest.mark.parametrize("unsafe", ["../escape", "a\\b"])
def test_stage_rejects_untrusted_output_identifiers_before_provider_calls(
    tmp_path, monkeypatch, module, unsafe
):
    manifest = _manifest(tmp_path, module, account=unsafe)
    factory = MagicMock()
    monkeypatch.setattr(gemini.genai, "Client", factory)
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-key")
    monkeypatch.setattr(
        "sys.argv", [module.__name__, str(manifest), "--out", str(tmp_path / "output")]
    )
    with pytest.raises(ValueError, match="unsafe_path_component"):
        _run_command(module)
    factory.assert_not_called()


@pytest.mark.parametrize("module", [vision_slides, vision_videos])
def test_stage_reports_non_retryable_failure_with_nonzero_exit_and_redacted_checkpoint(
    tmp_path, monkeypatch, capsys, module
):
    manifest = _manifest(tmp_path, module)
    factory = MagicMock()
    monkeypatch.setattr(gemini.genai, "Client", factory)
    client = factory.return_value.__enter__.return_value
    client.files.upload.return_value = types.File(name="files/synthetic", state="ACTIVE")
    secret = "synthetic-private-credential"
    client.models.generate_content.side_effect = ValueError(f"invalid response {secret}")
    monkeypatch.setenv("GEMINI_API_KEY", secret)
    output = tmp_path / "output"
    command = "vision-slides" if module is vision_slides else "vision-videos"
    assert cli.execute([command, str(manifest), "--out", str(output), "--retries", "4"]) == 1
    assert client.models.generate_content.call_count == 1
    factory.return_value.__exit__.assert_called_once()
    failure_name = "failures_v2.jsonl" if module is vision_slides else "failures.jsonl"
    assert secret not in (output / failure_name).read_text()
    captured = capsys.readouterr()
    assert secret not in captured.out + captured.err


@pytest.mark.parametrize("module", [vision_slides, vision_videos])
def test_vision_symlink_escape_is_rejected_before_opening_provider(tmp_path, monkeypatch, module):
    manifest = _manifest(tmp_path, module)
    output, external = tmp_path / "output", tmp_path / "external"
    output.mkdir()
    external.mkdir()
    (output / "by_post").symlink_to(external, target_is_directory=True)
    factory = MagicMock()
    monkeypatch.setattr(gemini.genai, "Client", factory)
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic")
    monkeypatch.setattr("sys.argv", [module.__name__, str(manifest), "--out", str(output)])
    with pytest.raises(ValueError, match="path_outside_output"):
        _run_command(module)
    factory.assert_not_called()
    assert not list(external.iterdir())
