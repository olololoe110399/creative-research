"""Analyze archived slideshows with opt-in Gemini calls and resumable checkpoints."""

from __future__ import annotations

import hashlib
import json
import mimetypes
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
    SlideshowCreativeAnalysis,
)

SCHEMA_VERSION = "creative-vision-v2"


@dataclass(frozen=True, slots=True)
class SlideshowAnalysisOptions:
    """CLI-independent parameters for this workflow."""

    manifest: str
    out: str
    model: str
    max_posts: int | None
    sample_size: int | None
    sample_seed: int
    temperature: float
    retries: int
    retry_base_seconds: float
    sleep_between: float
    force: bool


def image_files(post_dir: Path) -> list[Path]:
    allowed = {".jpg", ".jpeg", ".png", ".webp"}
    return sorted(p for p in post_dir.glob("slide_*.*") if p.suffix.lower() in allowed)


def mime_type(path: Path) -> str:
    value = mimetypes.guess_type(path.name)[0]
    if value in {"image/jpeg", "image/png", "image/webp"}:
        return value
    return "image/jpeg"


def input_signature(post_dir: Path, model: str) -> str:
    payload = {
        "schema": SCHEMA_VERSION,
        "model": model,
        "slides": [{"name": p.name, "sha1": file_sha1(p)} for p in image_files(post_dir)],
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


# ----------------------------
# Prompt + model call
# ----------------------------


def build_prompt(account: str, post_id: str, slide_count: int) -> str:
    return f"""
Analyze this COMPLETE TikTok slideshow sequence for creative research.

Identity only:
- account: @{account}
- post_id: {post_id}
- slide_count: {slide_count}

IMPORTANT: You are intentionally NOT given views, likes, shares, saves, or any
performance signal. Do not guess whether the post performed well.

STRICT OUTPUT RULES:

1. SLIDE INDEXING
   - Use 1-based indexing ONLY.
   - First slide = 1.
   - Last slide = {slide_count}.
   - Return exactly {slide_count} slide objects.

2. LANGUAGE
   - primary_language_code refers to the CREATIVE NARRATIVE / OVERLAY language.
   - Do not let English app UI override Spanish/Vietnamese/etc overlay language.
   - Text embedded in app UI, tables, charts, notes, or documents should be
     separately classified in text_regions.
   - Preserve visible text in the original language.

3. PRODUCT
   - has_visible_product=true ONLY when the product/app/brand is visibly present.
   - Do not infer a promoted product only from topic or context.
   - product_family describes only whether one or multiple products are visibly present.
   - If no product is visibly present:
       has_visible_product=false
       product_family="none"
       first_appearance_slide=null
       placement_style="none"

4. CTA
   - has_visible_cta=true ONLY when a CTA is visibly written/shown.
   - Do NOT infer "link in bio", "download", "try it", etc unless visibly supported.
   - If no CTA is visibly present:
       has_visible_cta=false
       cta_type="none"
       text=null
       slide_index=null

5. VISUALS
   - Never claim an image actually came from Pinterest.
   - pinterest_like_aesthetic only means the style resembles imagery commonly
     used as Pinterest references.
   - Mark AI-generated appearance only when visible indicators support it;
     otherwise use uncertain.

6. SEQUENCE
   - Analyze the whole slideshow, not isolated images.
   - Infer hook/body/proof/product/CTA roles from sequence context.

7. TAXONOMY
   - Use the provided enum fields consistently.
   - Use "other" or "uncertain" instead of inventing a new category.

Focus on:
- audience segment
- niche/topic
- content angle and value type
- hook text/technique
- role of every slide
- visual choices
- product placement
- visible proof/credibility
- visible CTA
- concise replicable creative formula
""".strip()


def analyze_slideshow(
    client: genai.Client,
    model: str,
    post_dir: Path,
    account: str,
    post_id: str,
    temperature: float,
) -> SlideshowCreativeAnalysis:
    imgs = image_files(post_dir)
    if not imgs:
        raise RuntimeError("No slide images found")

    contents: list[Any] = [build_prompt(account, post_id, len(imgs))]

    for path in imgs:
        contents.append(
            types.Part.from_bytes(
                data=path.read_bytes(),
                mime_type=mime_type(path),
            )
        )

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=build_generation_config(SlideshowCreativeAnalysis, temperature=temperature),
    )

    if getattr(response, "parsed", None) is not None:
        parsed = response.parsed
        if isinstance(parsed, SlideshowCreativeAnalysis):
            return parsed

    if not response.text:
        raise RuntimeError("Empty model response")

    return SlideshowCreativeAnalysis.model_validate_json(response.text)


# ----------------------------
# Validation / normalization
# ----------------------------


def normalize_and_validate(
    analysis: SlideshowCreativeAnalysis,
    slide_count: int,
) -> tuple[SlideshowCreativeAnalysis, list[str]]:
    """
    Repairs the known v1 indexing issue:
    - [0..n-1] -> [1..n]
    Then validates exact contiguous slide coverage and visible evidence rules.
    """
    events: list[str] = []

    if len(analysis.slides) != slide_count:
        raise ValueError(f"Expected {slide_count} slides, got {len(analysis.slides)}")

    idxs = [s.slide_index for s in analysis.slides]
    expected_1 = list(range(1, slide_count + 1))
    expected_0 = list(range(slide_count))

    if idxs == expected_0:
        events.append("repaired_zero_based_index")
        for slide in analysis.slides:
            slide.slide_index += 1

        if analysis.hook.slide_index is not None:
            analysis.hook.slide_index += 1
        if analysis.product.first_appearance_slide is not None:
            analysis.product.first_appearance_slide += 1
        if analysis.cta.slide_index is not None:
            analysis.cta.slide_index += 1

    elif idxs != expected_1:
        raise ValueError(f"Slide indices must be contiguous 1..{slide_count}; got {idxs}")

    def valid_ref(value: int | None, name: str) -> None:
        if value is None:
            return
        if not (1 <= value <= slide_count):
            raise ValueError(f"{name}={value} outside 1..{slide_count}")

    valid_ref(analysis.hook.slide_index, "hook.slide_index")
    valid_ref(
        analysis.product.first_appearance_slide,
        "product.first_appearance_slide",
    )
    valid_ref(analysis.cta.slide_index, "cta.slide_index")

    # Evidence consistency: product
    if not analysis.product.has_visible_product:
        if analysis.product.product_family != "none":
            events.append("repaired_product_without_visible_evidence")
        analysis.product.product_family = "none"
        analysis.product.visible_product_name = None
        analysis.product.first_appearance_slide = None
        analysis.product.placement_style = "none"
        analysis.product.evidence = []
    else:
        if analysis.product.product_family == "none":
            raise ValueError("Visible product=true but product_family=none")
        if analysis.product.first_appearance_slide is None:
            raise ValueError("Visible product=true but first_appearance_slide=null")

    # Evidence consistency: CTA
    if not analysis.cta.has_visible_cta:
        if analysis.cta.cta_type != "none":
            events.append("repaired_cta_without_visible_evidence")
        analysis.cta.cta_type = "none"
        analysis.cta.text = None
        analysis.cta.slide_index = None
        analysis.cta.evidence = []
    else:
        if analysis.cta.cta_type == "none":
            raise ValueError("Visible CTA=true but cta_type=none")
        if analysis.cta.slide_index is None:
            raise ValueError("Visible CTA=true but slide_index=null")

    return analysis, events


# ----------------------------
# Flatten
# ----------------------------


def flatten_analysis(
    manifest_row: dict[str, Any],
    analysis: SlideshowCreativeAnalysis,
    validation_events: list[str],
) -> dict[str, Any]:
    payload = analysis.model_dump()
    hook = payload["hook"]
    visual_style = payload["visual_style"]
    product = payload["product"]
    cta = payload["cta"]

    return {
        # Identity + metrics joined only AFTER vision analysis.
        "account": manifest_row["account"],
        "post_id": str(manifest_row["post_id"]),
        "post_dir": manifest_row["post_dir"],
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
        "slide_count": manifest_row.get("slide_count"),
        "study_groups": manifest_row.get("study_groups"),
        # Normalized analysis fields.
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
        "hook_text": hook["text"],
        "hook_slide": hook["slide_index"],
        "hook_technique": hook["technique"],
        "hook_psychological_trigger": hook["psychological_trigger"],
        "hook_replicable_formula": hook["replicable_formula"],
        "content_format": payload["content_format"],
        "narrative_structure": json.dumps(payload["narrative_structure"], ensure_ascii=False),
        "dominant_visual_type": visual_style["dominant_visual_type"],
        "visual_aesthetic": visual_style["aesthetic"],
        "image_realism": visual_style["image_realism"],
        "pinterest_like_aesthetic": visual_style["pinterest_like_aesthetic"],
        "pinterest_note": visual_style["pinterest_note"],
        "text_overlay_style": visual_style["text_overlay_style"],
        "visual_consistency": visual_style["visual_consistency_across_slides"],
        "proof_or_credibility": json.dumps(payload["proof_or_credibility"], ensure_ascii=False),
        "has_visible_product": product["has_visible_product"],
        "product_family": product["product_family"],
        "visible_product_name": product["visible_product_name"],
        "product_first_slide": product["first_appearance_slide"],
        "product_placement_style": product["placement_style"],
        "product_evidence": json.dumps(product["evidence"], ensure_ascii=False),
        "has_visible_cta": cta["has_visible_cta"],
        "cta_type": cta["cta_type"],
        "cta_text": cta["text"],
        "cta_slide": cta["slide_index"],
        "cta_evidence": json.dumps(cta["evidence"], ensure_ascii=False),
        "creative_formula": payload["creative_formula"],
        "attention_mechanisms": json.dumps(
            payload["attention_mechanisms_used"], ensure_ascii=False
        ),
        "overall_confidence": payload["overall_confidence"],
        "uncertainty_notes": json.dumps(payload["uncertainty_notes"], ensure_ascii=False),
        "validation_events": "|".join(validation_events),
        "analysis_json": json.dumps(payload, ensure_ascii=False),
    }


# ----------------------------
# Main
# ----------------------------


def analyze_manifest(options: SlideshowAnalysisOptions) -> None:

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is not set")

    manifest_path = resolve_path(options.manifest)
    out = resolve_path(options.out)
    out.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(manifest_path)

    if options.sample_size is not None:
        n = min(options.sample_size, len(df))
        df = df.sample(
            n=n,
            random_state=options.sample_seed,
        ).reset_index(drop=True)

    if options.max_posts is not None:
        df = df.head(options.max_posts)

    rows = df.to_dict(orient="records")
    by_post_paths = [
        confined_path(out, "by_post", str(row["account"]), f"{row['post_id']}.json") for row in rows
    ]

    with gemini_client(
        api_key, timeout_seconds=RuntimeSettings.from_environ().ai_timeout
    ) as client:
        cache_path = out / "vision_cache_v2.jsonl"
        cached_rows = read_jsonl(cache_path, missing_ok=True, tolerate_invalid=True)
        cache = {
            (
                str(r.get("account")),
                str(r.get("post_id")),
                str(r.get("input_signature")),
            ): r
            for r in cached_rows
            if r.get("status") == "ok"
        }

        results: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        total = len(df)

        validation_event_counts: dict[str, int] = {}

        for i, (manifest_row, by_post_path) in enumerate(zip(rows, by_post_paths, strict=True), 1):
            account = str(manifest_row["account"])
            post_id = str(manifest_row["post_id"])
            post_dir = resolve_path(str(manifest_row["post_dir"]))

            if not post_dir.exists():
                failure: dict[str, Any] = {
                    "account": account,
                    "post_id": post_id,
                    "error": f"Missing post_dir: {post_dir}",
                }
                failures.append(failure)
                append_jsonl(out / "failures_v2.jsonl", failure)
                continue

            signature = input_signature(post_dir, options.model)
            cache_key = (account, post_id, signature)

            analysis: SlideshowCreativeAnalysis | None
            events: list[str]
            if not options.force and cache_key in cache:
                cache_record = cache[cache_key]
                analysis = SlideshowCreativeAnalysis.model_validate(cache_record["analysis"])
                events = cache_record.get("validation_events", [])
                results.append(flatten_analysis(manifest_row, analysis, events))
                for event in events:
                    validation_event_counts[event] = validation_event_counts.get(event, 0) + 1
                print(f"[{i}/{total}] cached @{account}/{post_id}")
                continue

            print(
                f"[{i}/{total}] analyze @{account}/{post_id} ({manifest_row.get('slide_count')} slides)"
            )

            analysis = None
            events = []
            last_error = None

            for attempt in range(options.retries + 1):
                try:
                    candidate = analyze_slideshow(
                        client=client,
                        model=options.model,
                        post_dir=post_dir,
                        account=account,
                        post_id=post_id,
                        temperature=options.temperature,
                    )
                    analysis, events = normalize_and_validate(
                        candidate,
                        slide_count=len(image_files(post_dir)),
                    )
                    break
                except Exception as exc:
                    last_error = redact(f"{type(exc).__name__}: {exc}")
                    if not is_retryable_api_error(exc):
                        break
                    if attempt < options.retries:
                        wait = options.retry_base_seconds * (2**attempt) + random.random()
                        print(
                            f"  retry {attempt + 1}/{options.retries} after {wait:.1f}s: {last_error}"
                        )
                        time.sleep(wait)

            if analysis is None:
                failure = {
                    "account": account,
                    "post_id": post_id,
                    "input_signature": signature,
                    "error": last_error,
                }
                failures.append(failure)
                append_jsonl(out / "failures_v2.jsonl", failure)
                print("  FAILED:", last_error)
                continue

            for event in events:
                validation_event_counts[event] = validation_event_counts.get(event, 0) + 1

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

            if options.sleep_between > 0:
                time.sleep(options.sleep_between)

        result_df = pd.DataFrame(results)

        csv_path = out / "creative_study_v2.csv"
        jsonl_path = out / "creative_study_v2.jsonl"
        parquet_path = out / "creative_study_v2.parquet"

        write_csv(csv_path, result_df, index=False, encoding="utf-8-sig")

        write_jsonl(jsonl_path, results)

        parquet_written = False
        if not result_df.empty:
            try:
                write_parquet(parquet_path, result_df)
                parquet_written = True
            except Exception as exc:
                print("Parquet skipped:", exc)

        report = {
            "model": options.model,
            "schema_version": SCHEMA_VERSION,
            "manifest_posts_this_run": int(total),
            "analyzed_posts": int(len(results)),
            "failed_posts": int(len(failures)),
            "validation_event_counts": validation_event_counts,
            "parquet_written": parquet_written,
            "output": str(out),
        }

        write_json(out / "report_v2.json", report)

        print("\nDONE")
        print(json.dumps(report, ensure_ascii=False, indent=2))

    if failures:
        raise ApplicationError(
            f"Slideshow analysis failed for {len(failures)} post(s).",
            code="vision_posts_failed",
            hint="Inspect failures_v2.jsonl; fix the cause and rerun to reuse completed checkpoints.",
        )
