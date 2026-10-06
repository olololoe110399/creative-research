#!/usr/bin/env python3
"""
vision_analyze_slideshows_v2.py

Schema-v2 multimodal analysis for TikTok slideshow creatives.

Design goals:
- Metrics are NEVER sent to the vision model.
- Slide indices are enforced/normalized to 1-based.
- Languages use compact ISO-like codes.
- Product / visual / audience / angle are enums for aggregation.
- CTA and product must have visible evidence.
- Resume cache is keyed by model + schema version + image SHA1s.
- Optional random validation sample before full run.

Install:
    python -m pip install -U google-genai pydantic pandas pyarrow

Set:
    export GEMINI_API_KEY="..."

Validation run:
    python vision_analyze_slideshows_v2.py \
      visual_study_sample/sample_manifest.csv \
      --out visual_study_v2_test \
      --model gemini-3.5-flash-lite \
      --sample-size 20 \
      --sample-seed 42

Full run:
    python vision_analyze_slideshows_v2.py \
      full_visual_manifest/full_manifest.csv \
      --out visual_study_full_v2 \
      --model gemini-3.5-flash-lite
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import random
import time
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, Field

from creative_research.pathing import resolve_path

try:
    from google import genai
    from google.genai import types
except ImportError:
    raise SystemExit(
        "Missing google-genai.\n"
        "Install with:\n"
        "  python -m pip install -U google-genai pydantic pandas pyarrow"
    )

SCHEMA_VERSION = "creative-vision-v2"


# ----------------------------
# Schema
# ----------------------------

LanguageCode = Literal[
    "en","es","pt","fr","de","it","vi","id","ms","tl","th",
    "zh","ja","ko","ar","hi","ru","tr","pl","nl","sv","other","unknown"
]

SlideRole = Literal[
    "hook","problem","body","study_tip","proof","transition",
    "product_reveal","product_demo","cta","other","uncertain"
]

VisualType = Literal[
    "real_person_photo",
    "lifestyle_photo",
    "study_desk_photo",
    "notes_or_document",
    "app_screenshot",
    "table_or_chart",
    "illustration_or_infographic",
    "meme_or_graphic",
    "mixed",
    "other",
    "uncertain",
]

AudienceSegment = Literal[
    "general_student",
    "college_student",
    "high_school_student",
    "medical_student",
    "nursing_student",
    "premed_student",
    "healthcare_student",
    "other",
    "uncertain",
]

ContentAngle = Literal[
    "study_method",
    "exam_prep",
    "memorization",
    "active_recall",
    "note_taking",
    "study_motivation",
    "productivity",
    "anatomy_medical_education",
    "nursing_education",
    "app_tool_recommendation",
    "relatable_student_life",
    "other",
    "uncertain",
]

ValueType = Literal[
    "educational_reference",
    "how_to",
    "checklist_or_list",
    "study_resource",
    "motivation",
    "relatable_story",
    "tool_demo",
    "comparison",
    "other",
    "uncertain",
]

HookTechnique = Literal[
    "pattern_interrupt",
    "question",
    "bold_claim",
    "story_tease",
    "curiosity_gap",
    "direct_address",
    "relatable_pain",
    "transformation_preview",
    "list_or_number",
    "pov",
    "how_to",
    "other",
    "uncertain",
]

ContentFormat = Literal[
    "problem_solution",
    "listicle",
    "tutorial",
    "story",
    "before_after",
    "day_in_life",
    "study_routine",
    "tool_demo",
    "educational_explainer",
    "motivation",
    "mixed",
    "other",
    "uncertain",
]

ProductFamily = Literal[
    "none",
    "single_product",
    "multiple",
    "other",
    "uncertain",
]

ProductPlacementStyle = Literal[
    "none",
    "immediate",
    "soft_reveal",
    "late_reveal",
    "integrated_throughout",
    "uncertain",
]

CTAType = Literal[
    "none",
    "link_in_bio",
    "download",
    "try_product",
    "follow",
    "save",
    "share",
    "comment",
    "dm",
    "other",
    "uncertain",
]


class TextRegion(BaseModel):
    text: str
    kind: Literal[
        "creative_overlay",
        "embedded_app_ui",
        "embedded_table_chart",
        "embedded_document_notes",
        "brand_logo",
        "other",
    ]
    language_code: LanguageCode = "unknown"


class SlideAnalysis(BaseModel):
    slide_index: int = Field(
        description="1-based slide number. First slide MUST be 1."
    )
    role: SlideRole
    primary_overlay_text: str | None = None
    text_regions: list[TextRegion] = Field(default_factory=list)
    visual_type: VisualType
    visual_description: str
    product_visible: bool
    product_family_visible: ProductFamily = "none"
    confidence: float = Field(ge=0, le=1)


class HookAnalysis(BaseModel):
    text: str | None = None
    slide_index: int | None = None
    technique: HookTechnique
    psychological_trigger: str | None = None
    replicable_formula: str | None = None


class VisualStyle(BaseModel):
    dominant_visual_type: VisualType
    aesthetic: str
    image_realism: Literal[
        "appears_real_photo",
        "appears_ai_generated",
        "mixed",
        "uncertain",
        "not_applicable",
    ]
    pinterest_like_aesthetic: Literal["yes","no","uncertain"]
    pinterest_note: str
    text_overlay_style: str
    visual_consistency_across_slides: Literal[
        "high","medium","low","uncertain"
    ]


class ProductPlacement(BaseModel):
    has_visible_product: bool
    product_family: ProductFamily
    visible_product_name: str | None = None
    first_appearance_slide: int | None = None
    placement_style: ProductPlacementStyle
    evidence: list[str] = Field(default_factory=list)


class CTAAnalysis(BaseModel):
    has_visible_cta: bool
    cta_type: CTAType
    text: str | None = None
    slide_index: int | None = None
    evidence: list[str] = Field(default_factory=list)


class CreativeAnalysis(BaseModel):
    primary_language_code: LanguageCode
    secondary_language_codes: list[LanguageCode] = Field(default_factory=list)
    mixed_language: bool

    audience_segment: AudienceSegment
    niche: str
    topic: str
    content_angle: ContentAngle
    value_type: ValueType
    pain_point: str | None = None
    desired_outcome: str | None = None

    hook: HookAnalysis
    slides: list[SlideAnalysis]

    narrative_structure: list[str]
    content_format: ContentFormat

    visual_style: VisualStyle
    proof_or_credibility: list[str] = Field(default_factory=list)

    product: ProductPlacement
    cta: CTAAnalysis

    creative_formula: str
    attention_mechanisms_used: list[str] = Field(default_factory=list)

    overall_confidence: float = Field(ge=0, le=1)
    uncertainty_notes: list[str] = Field(default_factory=list)


# ----------------------------
# IO helpers
# ----------------------------

def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    rows.append(obj)
            except Exception:
                pass
    return rows


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        f.flush()
        os.fsync(f.fileno())


def image_files(post_dir: Path) -> list[Path]:
    allowed = {".jpg", ".jpeg", ".png", ".webp"}
    return sorted(
        p for p in post_dir.glob("slide_*.*")
        if p.suffix.lower() in allowed
    )


def mime_type(path: Path) -> str:
    value = mimetypes.guess_type(path.name)[0]
    if value in {"image/jpeg", "image/png", "image/webp"}:
        return value
    return "image/jpeg"


def file_sha1(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def input_signature(post_dir: Path, model: str) -> str:
    payload = {
        "schema": SCHEMA_VERSION,
        "model": model,
        "slides": [
            {"name": p.name, "sha1": file_sha1(p)}
            for p in image_files(post_dir)
        ],
    }
    return hashlib.sha1(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()


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


def build_generation_config(temperature: float):
    base = {
        "response_mime_type": "application/json",
        "response_schema": CreativeAnalysis,
        "temperature": temperature,
    }

    # Disable AFC warning when supported by installed SDK.
    try:
        return types.GenerateContentConfig(
            **base,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True
            ),
        )
    except Exception:
        return types.GenerateContentConfig(**base)


def call_gemini(
    client,
    model: str,
    post_dir: Path,
    account: str,
    post_id: str,
    temperature: float,
) -> CreativeAnalysis:
    imgs = image_files(post_dir)
    if not imgs:
        raise RuntimeError("No slide images found")

    contents: list[Any] = [
        build_prompt(account, post_id, len(imgs))
    ]

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
        config=build_generation_config(temperature),
    )

    if getattr(response, "parsed", None) is not None:
        parsed = response.parsed
        if isinstance(parsed, CreativeAnalysis):
            return parsed

    if not response.text:
        raise RuntimeError("Empty model response")

    return CreativeAnalysis.model_validate_json(response.text)


# ----------------------------
# Validation / normalization
# ----------------------------

def normalize_and_validate(
    analysis: CreativeAnalysis,
    slide_count: int,
) -> tuple[CreativeAnalysis, list[str]]:
    """
    Repairs the known v1 indexing issue:
    - [0..n-1] -> [1..n]
    Then validates exact contiguous slide coverage and visible evidence rules.
    """
    events: list[str] = []

    if len(analysis.slides) != slide_count:
        raise ValueError(
            f"Expected {slide_count} slides, got {len(analysis.slides)}"
        )

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
        raise ValueError(
            f"Slide indices must be contiguous 1..{slide_count}; got {idxs}"
        )

    def valid_ref(value: int | None, name: str) -> None:
        if value is None:
            return
        if not (1 <= value <= slide_count):
            raise ValueError(
                f"{name}={value} outside 1..{slide_count}"
            )

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
            raise ValueError(
                "Visible product=true but product_family=none"
            )
        if analysis.product.first_appearance_slide is None:
            raise ValueError(
                "Visible product=true but first_appearance_slide=null"
            )

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
            raise ValueError(
                "Visible CTA=true but cta_type=none"
            )
        if analysis.cta.slide_index is None:
            raise ValueError(
                "Visible CTA=true but slide_index=null"
            )

    return analysis, events


# ----------------------------
# Flatten
# ----------------------------

def flatten(
    manifest_row: dict[str, Any],
    analysis: CreativeAnalysis,
    validation_events: list[str],
) -> dict[str, Any]:
    a = analysis.model_dump()
    h = a["hook"]
    v = a["visual_style"]
    p = a["product"]
    c = a["cta"]

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
        "primary_language_code": a["primary_language_code"],
        "secondary_language_codes": json.dumps(
            a["secondary_language_codes"], ensure_ascii=False
        ),
        "mixed_language": a["mixed_language"],

        "audience_segment": a["audience_segment"],
        "niche": a["niche"],
        "topic": a["topic"],
        "content_angle": a["content_angle"],
        "value_type": a["value_type"],
        "pain_point": a["pain_point"],
        "desired_outcome": a["desired_outcome"],

        "hook_text": h["text"],
        "hook_slide": h["slide_index"],
        "hook_technique": h["technique"],
        "hook_psychological_trigger": h["psychological_trigger"],
        "hook_replicable_formula": h["replicable_formula"],

        "content_format": a["content_format"],
        "narrative_structure": json.dumps(
            a["narrative_structure"], ensure_ascii=False
        ),

        "dominant_visual_type": v["dominant_visual_type"],
        "visual_aesthetic": v["aesthetic"],
        "image_realism": v["image_realism"],
        "pinterest_like_aesthetic": v["pinterest_like_aesthetic"],
        "pinterest_note": v["pinterest_note"],
        "text_overlay_style": v["text_overlay_style"],
        "visual_consistency": v["visual_consistency_across_slides"],

        "proof_or_credibility": json.dumps(
            a["proof_or_credibility"], ensure_ascii=False
        ),

        "has_visible_product": p["has_visible_product"],
        "product_family": p["product_family"],
        "visible_product_name": p["visible_product_name"],
        "product_first_slide": p["first_appearance_slide"],
        "product_placement_style": p["placement_style"],
        "product_evidence": json.dumps(
            p["evidence"], ensure_ascii=False
        ),

        "has_visible_cta": c["has_visible_cta"],
        "cta_type": c["cta_type"],
        "cta_text": c["text"],
        "cta_slide": c["slide_index"],
        "cta_evidence": json.dumps(
            c["evidence"], ensure_ascii=False
        ),

        "creative_formula": a["creative_formula"],
        "attention_mechanisms": json.dumps(
            a["attention_mechanisms_used"], ensure_ascii=False
        ),

        "overall_confidence": a["overall_confidence"],
        "uncertainty_notes": json.dumps(
            a["uncertainty_notes"], ensure_ascii=False
        ),

        "validation_events": "|".join(validation_events),
        "analysis_json": json.dumps(a, ensure_ascii=False),
    }


# ----------------------------
# Main
# ----------------------------

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("manifest", help="CSV manifest")
    p.add_argument("--out", default="visual_study_v2")
    p.add_argument("--model", default="gemini-3.5-flash-lite")
    p.add_argument("--max-posts", type=int, default=None)
    p.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="Randomly sample N manifest rows for validation.",
    )
    p.add_argument("--sample-seed", type=int, default=42)
    p.add_argument("--temperature", type=float, default=0.1)
    p.add_argument("--retries", type=int, default=4)
    p.add_argument("--retry-base-seconds", type=float, default=2.0)
    p.add_argument("--sleep-between", type=float, default=0.2)
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is not set")

    manifest_path = Path(args.manifest).expanduser().resolve()
    out = Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(manifest_path)

    if args.sample_size is not None:
        n = min(args.sample_size, len(df))
        df = df.sample(
            n=n,
            random_state=args.sample_seed,
        ).reset_index(drop=True)

    if args.max_posts is not None:
        df = df.head(args.max_posts)

    client = genai.Client(api_key=api_key)

    cache_path = out / "vision_cache_v2.jsonl"
    cached_rows = read_jsonl(cache_path)
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

    for i, manifest_row in enumerate(
        df.to_dict(orient="records"), start=1
    ):
        account = str(manifest_row["account"])
        post_id = str(manifest_row["post_id"])
        post_dir = resolve_path(str(manifest_row["post_dir"]))

        if not post_dir.exists():
            failure = {
                "account": account,
                "post_id": post_id,
                "error": f"Missing post_dir: {post_dir}",
            }
            failures.append(failure)
            append_jsonl(out / "failures_v2.jsonl", failure)
            continue

        sig = input_signature(post_dir, args.model)
        cache_key = (account, post_id, sig)

        if not args.force and cache_key in cache:
            rec = cache[cache_key]
            analysis = CreativeAnalysis.model_validate(rec["analysis"])
            events = rec.get("validation_events", [])
            results.append(
                flatten(manifest_row, analysis, events)
            )
            for event in events:
                validation_event_counts[event] = (
                    validation_event_counts.get(event, 0) + 1
                )
            print(f"[{i}/{total}] cached @{account}/{post_id}")
            continue

        print(
            f"[{i}/{total}] analyze "
            f"@{account}/{post_id} "
            f"({manifest_row.get('slide_count')} slides)"
        )

        analysis = None
        events: list[str] = []
        last_error = None

        for attempt in range(args.retries + 1):
            try:
                candidate = call_gemini(
                    client=client,
                    model=args.model,
                    post_dir=post_dir,
                    account=account,
                    post_id=post_id,
                    temperature=args.temperature,
                )
                analysis, events = normalize_and_validate(
                    candidate,
                    slide_count=len(image_files(post_dir)),
                )
                break
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < args.retries:
                    wait = (
                        args.retry_base_seconds * (2 ** attempt)
                        + random.random()
                    )
                    print(
                        f"  retry {attempt + 1}/{args.retries} "
                        f"after {wait:.1f}s: {last_error}"
                    )
                    time.sleep(wait)

        if analysis is None:
            failure = {
                "account": account,
                "post_id": post_id,
                "input_signature": sig,
                "error": last_error,
            }
            failures.append(failure)
            append_jsonl(out / "failures_v2.jsonl", failure)
            print("  FAILED:", last_error)
            continue

        for event in events:
            validation_event_counts[event] = (
                validation_event_counts.get(event, 0) + 1
            )

        cache_record = {
            "status": "ok",
            "schema_version": SCHEMA_VERSION,
            "model": args.model,
            "account": account,
            "post_id": post_id,
            "input_signature": sig,
            "validation_events": events,
            "analysis": analysis.model_dump(),
        }
        append_jsonl(cache_path, cache_record)

        by_post_path = (
            out / "by_post" / account / f"{post_id}.json"
        )
        by_post_path.parent.mkdir(
            parents=True, exist_ok=True
        )
        by_post_path.write_text(
            json.dumps(
                cache_record,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        results.append(
            flatten(manifest_row, analysis, events)
        )

        if args.sleep_between > 0:
            time.sleep(args.sleep_between)

    result_df = pd.DataFrame(results)

    csv_path = out / "creative_study_v2.csv"
    jsonl_path = out / "creative_study_v2.jsonl"
    parquet_path = out / "creative_study_v2.parquet"

    result_df.to_csv(
        csv_path,
        index=False,
        encoding="utf-8-sig",
    )

    with jsonl_path.open("w", encoding="utf-8") as f:
        for row in results:
            f.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                    default=str,
                )
                + "\n"
            )

    parquet_written = False
    if not result_df.empty:
        try:
            result_df.to_parquet(
                parquet_path,
                index=False,
            )
            parquet_written = True
        except Exception as exc:
            print("Parquet skipped:", exc)

    report = {
        "model": args.model,
        "schema_version": SCHEMA_VERSION,
        "manifest_posts_this_run": int(total),
        "analyzed_posts": int(len(results)),
        "failed_posts": int(len(failures)),
        "validation_event_counts": validation_event_counts,
        "parquet_written": parquet_written,
        "output": str(out),
    }

    (out / "report_v2.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\nDONE")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
