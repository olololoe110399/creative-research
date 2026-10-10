"""Analyze archived videos with opt-in Gemini calls and resumable checkpoints."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from google import genai
from google.genai import types

from creative_research.errors import ApplicationError
from creative_research.infrastructure.config import RuntimeSettings
from creative_research.infrastructure.gemini import (
    build_generation_config,
    gemini_client,
    is_retryable_api_error,
)
from creative_research.infrastructure.logging import redact
from creative_research.infrastructure.paths import confined_path, resolve_path
from creative_research.infrastructure.storage import (
    append_jsonl,
    file_sha1,
    read_jsonl,
    write_csv,
    write_json,
    write_jsonl,
    write_parquet,
)
from creative_research.vision.models import (
    VideoCreativeAnalysis,
)

SCHEMA_VERSION = "creative-video-vision-v1"


@dataclass(frozen=True, slots=True)
class VideoAnalysisOptions:
    """CLI-independent parameters for this workflow."""

    manifest: str
    out: str
    model: str
    sample_size: int | None
    sample_seed: int
    max_posts: int | None
    temperature: float
    retries: int
    retry_base_seconds: float
    sleep_between: float
    upload_timeout: int
    keep_uploaded_files: bool
    force: bool


def video_input_signature(path: Path, model: str) -> str:
    payload = {
        "schema": SCHEMA_VERSION,
        "model": model,
        "sha1": file_sha1(path),
        "size": path.stat().st_size,
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def build_video_prompt(account: str, post_id: str, duration: float | None) -> str:
    duration_text = (
        f"{duration:.3f} seconds" if duration is not None and pd.notna(duration) else "unknown"
    )
    return f"""
Analyze this COMPLETE TikTok video as a creative-research artifact.

Identity only:
- account: @{account}
- post_id: {post_id}
- technical duration: {duration_text}

You are intentionally NOT given views, likes, shares, saves, or any performance signal.
Do not guess whether the post performed well.

STRICT RULES:
1. Watch/listen across the whole timeline. Do not judge only the opening frame.
2. Hook = the first meaningful attention mechanism, usually within the opening seconds.
3. Distinguish SPOKEN/NARRATED words from VISUAL OVERLAY text and from text embedded
   in app UI, screenshots, tables, documents, or notes.
4. primary_language_code refers mainly to the creative narrative/spoken/overlay language,
   not incidental English UI labels.
5. Preserve transcript/visible text in the original language; do not silently translate.
6. Timeline timestamps are seconds from video start and should be approximate but ordered.
7. PRODUCT: only mark a product when visibly shown OR explicitly spoken/named.
   If absent, product_family="none", first_appearance_second=null, placement_style="none".
8. CTA: only mark an explicit CTA if visibly written or explicitly spoken. Never infer
   "link in bio", "download", "try it", etc from context alone.
9. Use the fixed taxonomy. Use other/uncertain rather than inventing categories.
10. spoken_transcript should capture intelligible speech/voiceover. If there is no speech,
    return null. Do not fabricate unclear words.
11. Focus on construction of the creative: hook, pacing, visual format, narrative beats,
    product placement, proof, CTA, and a concise replicable formula.
""".strip()


def wait_until_active(
    client: genai.Client, uploaded: types.File, timeout_seconds: int
) -> types.File:
    deadline = time.monotonic() + timeout_seconds
    current = uploaded
    while time.monotonic() < deadline:
        state = getattr(getattr(current, "state", None), "name", None)
        if state == "ACTIVE":
            return current
        if state in {"FAILED", "ERROR"}:
            raise RuntimeError(f"Gemini file processing state={state}")
        if not current.name:
            raise RuntimeError("Gemini uploaded file is missing its identifier")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(3, remaining))
        if time.monotonic() >= deadline:
            break
        current = client.files.get(name=current.name)
    raise TimeoutError(f"Video file did not become ACTIVE within {timeout_seconds}s")


def analyze_video(
    client: genai.Client,
    model: str,
    path: Path,
    account: str,
    post_id: str,
    duration: float | None,
    temperature: float,
    upload_timeout: int,
    keep_uploaded: bool,
) -> VideoCreativeAnalysis:
    uploaded = None
    try:
        uploaded = client.files.upload(file=str(path))
        uploaded = wait_until_active(client, uploaded, upload_timeout)
        response = client.models.generate_content(
            model=model,
            contents=[uploaded, build_video_prompt(account, post_id, duration)],
            config=build_generation_config(VideoCreativeAnalysis, temperature=temperature),
        )
        if getattr(response, "parsed", None) is not None and isinstance(
            response.parsed, VideoCreativeAnalysis
        ):
            return response.parsed
        if not response.text:
            raise RuntimeError("Empty Gemini response")
        return VideoCreativeAnalysis.model_validate_json(response.text)
    finally:
        if uploaded is not None and uploaded.name and not keep_uploaded:
            try:
                client.files.delete(name=uploaded.name)
            except Exception as exc:
                logging.getLogger(__name__).warning(
                    "uploaded_file_cleanup_failed",
                    extra={
                        "context": {
                            "file": uploaded.name,
                            "error_type": type(exc).__name__,
                            "hint": "Delete the retained upload through the provider Files API.",
                        }
                    },
                )


def normalize_and_validate(
    analysis: VideoCreativeAnalysis, duration: float | None
) -> tuple[VideoCreativeAnalysis, list[str]]:
    events: list[str] = []
    # Sort beats if model returned them out of order.
    sorted_beats = sorted(analysis.timeline, key=lambda beat: (beat.start_second, beat.end_second))
    if [beat.model_dump() for beat in sorted_beats] != [
        beat.model_dump() for beat in analysis.timeline
    ]:
        analysis.timeline = sorted_beats
        events.append("sorted_timeline")

    max_duration = float(duration) if duration is not None and pd.notna(duration) else None

    def validate_timestamp(timestamp: float | None, label: str) -> None:
        if timestamp is None:
            return
        if timestamp < 0:
            raise ValueError(f"{label} negative")
        if max_duration is not None and timestamp > max_duration + 3:
            raise ValueError(f"{label}={timestamp} exceeds duration={max_duration}")

    validate_timestamp(analysis.hook.start_second, "hook.start_second")
    validate_timestamp(analysis.hook.end_second, "hook.end_second")
    if analysis.hook.end_second < analysis.hook.start_second:
        raise ValueError("hook end before start")
    for index, beat in enumerate(analysis.timeline):
        validate_timestamp(beat.start_second, f"timeline[{index}].start")
        validate_timestamp(beat.end_second, f"timeline[{index}].end")
        if beat.end_second < beat.start_second:
            raise ValueError(f"timeline[{index}] end before start")

    product = analysis.product
    if not product.has_visible_or_spoken_product:
        product.product_family = "none"
        product.visible_or_spoken_name = None
        product.first_appearance_second = None
        product.placement_style = "none"
        product.evidence = []
    else:
        if product.product_family == "none":
            raise ValueError("product present but family=none")
        validate_timestamp(product.first_appearance_second, "product.first_appearance_second")

    cta = analysis.cta
    if not cta.has_explicit_cta:
        cta.cta_type = "none"
        cta.text_or_speech = None
        cta.timestamp_second = None
        cta.modality = "none"
        cta.evidence = []
    else:
        if cta.cta_type == "none":
            raise ValueError("CTA present but type=none")
        validate_timestamp(cta.timestamp_second, "cta.timestamp_second")

    return analysis, events


def flatten_analysis(
    manifest_row: dict[str, Any], analysis: VideoCreativeAnalysis, events: list[str]
) -> dict[str, Any]:
    payload = analysis.model_dump()
    hook = payload["hook"]
    product = payload["product"]
    cta = payload["cta"]
    audio = payload["audio"]
    return {
        "account": manifest_row["account"],
        "post_id": str(manifest_row["post_id"]),
        "video_path": manifest_row["video_path"],
        "url": manifest_row.get("url"),
        "created_at": manifest_row.get("created_at"),
        "views": manifest_row.get("views"),
        "likes": manifest_row.get("likes"),
        "comments": manifest_row.get("comments"),
        "shares": manifest_row.get("shares"),
        "saves": manifest_row.get("saves"),
        "share_rate": manifest_row.get("share_rate"),
        "save_rate": manifest_row.get("save_rate"),
        "account_views_pct": manifest_row.get("account_views_pct"),
        "global_views_pct": manifest_row.get("global_views_pct"),
        "duration_seconds": manifest_row.get("duration_seconds"),
        "width": manifest_row.get("width"),
        "height": manifest_row.get("height"),
        "fps": manifest_row.get("fps"),
        "primary_language_code": payload["primary_language_code"],
        "secondary_language_codes": json.dumps(
            payload["secondary_language_codes"], ensure_ascii=False
        ),
        "mixed_language": payload["mixed_language"],
        "audience_segment": payload["audience_segment"],
        "niche": payload["niche"],
        "topic": payload["topic"],
        "content_angle": payload["content_angle"],
        "value_type": payload["value_type"],
        "pain_point": payload["pain_point"],
        "desired_outcome": payload["desired_outcome"],
        "video_format": payload["video_format"],
        "hook_start_second": hook["start_second"],
        "hook_end_second": hook["end_second"],
        "hook_spoken_text": hook["spoken_text"],
        "hook_overlay_text": hook["overlay_text"],
        "hook_technique": hook["technique"],
        "hook_psychological_trigger": hook["psychological_trigger"],
        "hook_replicable_formula": hook["replicable_formula"],
        "spoken_transcript": payload["spoken_transcript"],
        "narrative_structure": json.dumps(payload["narrative_structure"], ensure_ascii=False),
        "dominant_visual_type": payload["dominant_visual_type"],
        "visual_aesthetic": payload["visual_aesthetic"],
        "text_overlay_style": payload["text_overlay_style"],
        "editing_style": payload["editing_style"],
        "camera_style": payload["camera_style"],
        "face_or_person_present": payload["face_or_person_present"],
        "has_speech": audio["has_speech"],
        "has_background_music": audio["has_background_music"],
        "narration_style": audio["narration_style"],
        "pacing": audio["pacing"],
        "proof_or_credibility": json.dumps(payload["proof_or_credibility"], ensure_ascii=False),
        "has_product": product["has_visible_or_spoken_product"],
        "product_family": product["product_family"],
        "product_name": product["visible_or_spoken_name"],
        "product_first_second": product["first_appearance_second"],
        "product_placement_style": product["placement_style"],
        "product_evidence": json.dumps(product["evidence"], ensure_ascii=False),
        "has_explicit_cta": cta["has_explicit_cta"],
        "cta_type": cta["cta_type"],
        "cta_text_or_speech": cta["text_or_speech"],
        "cta_second": cta["timestamp_second"],
        "cta_modality": cta["modality"],
        "cta_evidence": json.dumps(cta["evidence"], ensure_ascii=False),
        "creative_formula": payload["creative_formula"],
        "attention_mechanisms": json.dumps(
            payload["attention_mechanisms_used"], ensure_ascii=False
        ),
        "overall_confidence": payload["overall_confidence"],
        "uncertainty_notes": json.dumps(payload["uncertainty_notes"], ensure_ascii=False),
        "validation_events": "|".join(events),
        "timeline_json": json.dumps(payload["timeline"], ensure_ascii=False),
        "analysis_json": json.dumps(payload, ensure_ascii=False),
    }


def analyze_manifest(options: VideoAnalysisOptions) -> None:

    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit("GEMINI_API_KEY is not set")
    out = resolve_path(options.out)
    out.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(resolve_path(options.manifest))
    if options.sample_size is not None:
        df = df.sample(
            n=min(options.sample_size, len(df)), random_state=options.sample_seed
        ).reset_index(drop=True)
    if options.max_posts is not None:
        df = df.head(options.max_posts)

    rows = df.to_dict(orient="records")
    by_post_paths = [
        confined_path(out, "by_post", str(row["account"]), f"{row['post_id']}.json") for row in rows
    ]

    with gemini_client(key, timeout_seconds=RuntimeSettings.from_environ().ai_timeout) as client:
        cache_path = out / "video_cache.jsonl"
        cache = {
            (str(r.get("account")), str(r.get("post_id")), str(r.get("input_signature"))): r
            for r in read_jsonl(cache_path, missing_ok=True, tolerate_invalid=True)
            if r.get("status") == "ok"
        }
        results = []
        failures = []
        event_counts: dict[str, int] = {}

        for i, (manifest_row, by_post_path) in enumerate(zip(rows, by_post_paths, strict=True), 1):
            account, post_id = str(manifest_row["account"]), str(manifest_row["post_id"])
            path = resolve_path(str(manifest_row["video_path"]))
            if not path.exists():
                fail: dict[str, Any] = {
                    "account": account,
                    "post_id": post_id,
                    "error": f"missing video: {path}",
                }
                failures.append(fail)
                append_jsonl(out / "failures.jsonl", fail)
                continue
            signature = video_input_signature(path, options.model)
            cache_key = (account, post_id, signature)
            analysis: VideoCreativeAnalysis | None
            events: list[str]
            if not options.force and cache_key in cache:
                cache_record = cache[cache_key]
                analysis = VideoCreativeAnalysis.model_validate(cache_record["analysis"])
                events = cache_record.get("validation_events", [])
                results.append(flatten_analysis(manifest_row, analysis, events))
                print(f"[{i}/{len(df)}] cached @{account}/{post_id}")
                continue
            print(
                f"[{i}/{len(df)}] analyze @{account}/{post_id} "
                f"({manifest_row.get('duration_seconds')}s)"
            )
            analysis = None
            events = []
            last_error = None
            duration = None
            try:
                if manifest_row.get("duration_seconds") is not None and pd.notna(
                    manifest_row.get("duration_seconds")
                ):
                    duration = float(manifest_row["duration_seconds"])
            except (TypeError, ValueError):
                logging.getLogger(__name__).warning(
                    "invalid_video_duration",
                    extra={"context": {"account": account, "post_id": post_id}},
                )
            for attempt in range(options.retries + 1):
                try:
                    candidate = analyze_video(
                        client,
                        options.model,
                        path,
                        account,
                        post_id,
                        duration,
                        options.temperature,
                        options.upload_timeout,
                        options.keep_uploaded_files,
                    )
                    analysis, events = normalize_and_validate(candidate, duration)
                    break
                except Exception as exc:
                    last_error = redact(f"{type(exc).__name__}: {exc}")
                    if not is_retryable_api_error(exc):
                        break
                    if attempt < options.retries:
                        wait = options.retry_base_seconds * (2**attempt) + random.random()
                        print(f"  retry after {wait:.1f}s: {last_error}")
                        time.sleep(wait)
            if analysis is None:
                fail = {
                    "account": account,
                    "post_id": post_id,
                    "input_signature": signature,
                    "error": last_error,
                }
                failures.append(fail)
                append_jsonl(out / "failures.jsonl", fail)
                print("  FAILED", last_error)
                continue
            for event in events:
                event_counts[event] = event_counts.get(event, 0) + 1
            cache_record = {
                "status": "ok",
                "schema_version": SCHEMA_VERSION,
                "model": options.model,
                "account": account,
                "post_id": post_id,
                "input_signature": signature,
                "validation_events": events,
                "analysis": analysis.model_dump(),
            }
            append_jsonl(cache_path, cache_record)
            write_json(by_post_path, cache_record)
            results.append(flatten_analysis(manifest_row, analysis, events))
            if options.sleep_between:
                time.sleep(options.sleep_between)

        result_frame = pd.DataFrame(results)
        write_csv(out / "creative_video_study.csv", result_frame, index=False, encoding="utf-8-sig")
        write_jsonl(out / "creative_video_study.jsonl", results)
        parquet = False
        if not result_frame.empty:
            try:
                write_parquet(out / "creative_video_study.parquet", result_frame)
                parquet = True
            except Exception as exc:
                print("Parquet skipped:", exc)
        report = {
            "model": options.model,
            "schema_version": SCHEMA_VERSION,
            "manifest_posts_this_run": len(df),
            "analyzed_posts": len(results),
            "failed_posts": len(failures),
            "validation_event_counts": event_counts,
            "parquet_written": parquet,
            "output": str(out),
        }
        write_json(out / "report.json", report)
        print("\nDONE\n" + json.dumps(report, ensure_ascii=False, indent=2))

    if failures:
        raise ApplicationError(
            f"Video analysis failed for {len(failures)} post(s).",
            code="vision_posts_failed",
            hint="Inspect failures.jsonl; fix the cause and rerun to reuse completed checkpoints.",
        )
