#!/usr/bin/env python3
"""Analyze archived TikTok videos with Gemini, one full video per request.

Input:
  creative_videos/video_manifest.csv

Output:
  video_visual_study/
    by_post/<account>/<post_id>.json
    video_cache.jsonl
    creative_video_study.csv
    creative_video_study.jsonl
    creative_video_study.parquet
    failures.jsonl
    report.json

Metrics are deliberately NOT sent to Gemini. They are joined back only after
creative analysis, matching the slideshow methodology.

Install:
  python -m pip install -U google-genai pydantic pandas pyarrow

Run a 10-video validation sample:
  python vision_analyze_videos.py creative_videos/video_manifest.csv \
    --out video_visual_study_test \
    --model gemini-3.5-flash-lite \
    --sample-size 10

Full run:
  python vision_analyze_videos.py creative_videos/video_manifest.csv \
    --out video_visual_study \
    --model gemini-3.5-flash-lite
"""
from __future__ import annotations

import argparse
import hashlib
import json
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
    raise SystemExit("Install: python -m pip install -U google-genai pydantic pandas pyarrow")

SCHEMA_VERSION = "creative-video-vision-v1"

LanguageCode = Literal[
    "en","es","pt","fr","de","it","vi","id","ms","tl","th",
    "zh","ja","ko","ar","hi","ru","tr","pl","nl","sv","other","unknown"
]
AudienceSegment = Literal[
    "general_student","college_student","high_school_student","medical_student",
    "nursing_student","premed_student","healthcare_student","other","uncertain"
]
ContentAngle = Literal[
    "study_method","exam_prep","memorization","active_recall","note_taking",
    "study_motivation","productivity","anatomy_medical_education","nursing_education",
    "app_tool_recommendation","relatable_student_life","other","uncertain"
]
ValueType = Literal[
    "educational_reference","how_to","checklist_or_list","study_resource","motivation",
    "relatable_story","tool_demo","comparison","other","uncertain"
]
VideoFormat = Literal[
    "talking_head","broll_text_overlay","screen_recording","app_demo","study_routine",
    "tutorial","meme_or_sketch","montage","mixed","other","uncertain"
]
HookTechnique = Literal[
    "pattern_interrupt","question","bold_claim","story_tease","curiosity_gap",
    "direct_address","relatable_pain","transformation_preview","list_or_number",
    "pov","how_to","other","uncertain"
]
BeatRole = Literal[
    "hook","problem","context","value","tutorial_step","proof","transition",
    "product_reveal","product_demo","cta","ending","other","uncertain"
]
VisualType = Literal[
    "talking_head","real_person_lifestyle","study_desk","notes_or_document",
    "app_screen","screen_recording","table_or_chart","illustration_or_infographic",
    "meme_or_graphic","broll","mixed","other","uncertain"
]
ProductFamily = Literal["none","single_product","multiple","other","uncertain"]
ProductPlacementStyle = Literal[
    "none","immediate","soft_reveal","late_reveal","integrated_throughout","uncertain"
]
CTAType = Literal[
    "none","link_in_bio","download","try_product","follow","save","share","comment","dm","other","uncertain"
]


class HookAnalysis(BaseModel):
    start_second: float = Field(ge=0)
    end_second: float = Field(ge=0)
    spoken_text: str | None = None
    overlay_text: str | None = None
    technique: HookTechnique
    psychological_trigger: str | None = None
    replicable_formula: str | None = None


class TimelineBeat(BaseModel):
    start_second: float = Field(ge=0)
    end_second: float = Field(ge=0)
    role: BeatRole
    visual_type: VisualType
    visual_description: str
    spoken_summary: str | None = None
    overlay_text: str | None = None
    product_visible: bool
    product_family_visible: ProductFamily = "none"


class ProductPlacement(BaseModel):
    has_visible_or_spoken_product: bool
    product_family: ProductFamily
    visible_or_spoken_name: str | None = None
    first_appearance_second: float | None = None
    placement_style: ProductPlacementStyle
    evidence: list[str] = Field(default_factory=list)


class CTAAnalysis(BaseModel):
    has_explicit_cta: bool
    cta_type: CTAType
    text_or_speech: str | None = None
    timestamp_second: float | None = None
    modality: Literal["spoken","visual","both","none","uncertain"]
    evidence: list[str] = Field(default_factory=list)


class AudioAnalysis(BaseModel):
    has_speech: bool
    has_background_music: bool
    narration_style: Literal[
        "direct_to_camera","voiceover","dialogue","no_speech","mixed","uncertain"
    ]
    pacing: Literal["slow","medium","fast","uncertain"]


class VideoCreativeAnalysis(BaseModel):
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

    video_format: VideoFormat
    hook: HookAnalysis
    timeline: list[TimelineBeat]
    spoken_transcript: str | None = None
    narrative_structure: list[str]

    dominant_visual_type: VisualType
    visual_aesthetic: str
    text_overlay_style: str
    editing_style: str
    camera_style: str
    face_or_person_present: bool
    audio: AudioAnalysis

    proof_or_credibility: list[str] = Field(default_factory=list)
    product: ProductPlacement
    cta: CTAAnalysis

    creative_formula: str
    attention_mechanisms_used: list[str] = Field(default_factory=list)
    overall_confidence: float = Field(ge=0, le=1)
    uncertainty_notes: list[str] = Field(default_factory=list)


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        f.flush(); os.fsync(f.fileno())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists(): return []
    rows = []
    with path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            try:
                x = json.loads(line)
                if isinstance(x, dict): rows.append(x)
            except Exception: pass
    return rows


def sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        while True:
            c = f.read(1024 * 1024)
            if not c: break
            h.update(c)
    return h.hexdigest()


def signature(path: Path, model: str) -> str:
    payload = {"schema":SCHEMA_VERSION,"model":model,"sha1":sha1_file(path),"size":path.stat().st_size}
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def prompt(account: str, post_id: str, duration: float | None) -> str:
    duration_text = f"{duration:.3f} seconds" if duration is not None and pd.notna(duration) else "unknown"
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


def generation_config(temperature: float):
    base = {"response_mime_type":"application/json","response_schema":VideoCreativeAnalysis,"temperature":temperature}
    try:
        return types.GenerateContentConfig(
            **base,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
    except Exception:
        return types.GenerateContentConfig(**base)


def wait_until_active(client, uploaded, timeout_seconds: int):
    deadline = time.time() + timeout_seconds
    current = uploaded
    while time.time() < deadline:
        state = getattr(getattr(current, "state", None), "name", None)
        if state == "ACTIVE": return current
        if state in {"FAILED", "ERROR"}:
            raise RuntimeError(f"Gemini file processing state={state}")
        time.sleep(3)
        current = client.files.get(name=current.name)
    raise TimeoutError(f"Video file did not become ACTIVE within {timeout_seconds}s")


def analyze_one(client, model: str, path: Path, account: str, post_id: str,
                duration: float | None, temperature: float, upload_timeout: int,
                keep_uploaded: bool) -> VideoCreativeAnalysis:
    uploaded = None
    try:
        uploaded = client.files.upload(file=str(path))
        uploaded = wait_until_active(client, uploaded, upload_timeout)
        response = client.models.generate_content(
            model=model,
            contents=[uploaded, prompt(account, post_id, duration)],
            config=generation_config(temperature),
        )
        if getattr(response, "parsed", None) is not None and isinstance(response.parsed, VideoCreativeAnalysis):
            return response.parsed
        if not response.text: raise RuntimeError("Empty Gemini response")
        return VideoCreativeAnalysis.model_validate_json(response.text)
    finally:
        if uploaded is not None and not keep_uploaded:
            try: client.files.delete(name=uploaded.name)
            except Exception: pass


def normalize_validate(a: VideoCreativeAnalysis, duration: float | None) -> tuple[VideoCreativeAnalysis, list[str]]:
    events: list[str] = []
    # Sort beats if model returned them out of order.
    sorted_beats = sorted(a.timeline, key=lambda x: (x.start_second, x.end_second))
    if [x.model_dump() for x in sorted_beats] != [x.model_dump() for x in a.timeline]:
        a.timeline = sorted_beats; events.append("sorted_timeline")

    max_t = float(duration) if duration is not None and pd.notna(duration) else None
    def check_ts(x: float | None, label: str) -> None:
        if x is None: return
        if x < 0: raise ValueError(f"{label} negative")
        if max_t is not None and x > max_t + 3:
            raise ValueError(f"{label}={x} exceeds duration={max_t}")

    check_ts(a.hook.start_second, "hook.start_second")
    check_ts(a.hook.end_second, "hook.end_second")
    if a.hook.end_second < a.hook.start_second: raise ValueError("hook end before start")
    for i,b in enumerate(a.timeline):
        check_ts(b.start_second, f"timeline[{i}].start")
        check_ts(b.end_second, f"timeline[{i}].end")
        if b.end_second < b.start_second: raise ValueError(f"timeline[{i}] end before start")

    p = a.product
    if not p.has_visible_or_spoken_product:
        p.product_family = "none"; p.visible_or_spoken_name = None
        p.first_appearance_second = None; p.placement_style = "none"; p.evidence = []
    else:
        if p.product_family == "none": raise ValueError("product present but family=none")
        check_ts(p.first_appearance_second, "product.first_appearance_second")

    c = a.cta
    if not c.has_explicit_cta:
        c.cta_type = "none"; c.text_or_speech = None; c.timestamp_second = None
        c.modality = "none"; c.evidence = []
    else:
        if c.cta_type == "none": raise ValueError("CTA present but type=none")
        check_ts(c.timestamp_second, "cta.timestamp_second")

    return a, events


def flatten(m: dict[str, Any], a: VideoCreativeAnalysis, events: list[str]) -> dict[str, Any]:
    d=a.model_dump(); h=d["hook"]; p=d["product"]; c=d["cta"]; au=d["audio"]
    return {
        "account":m["account"],"post_id":str(m["post_id"]),"video_path":m["video_path"],"url":m.get("url"),
        "created_at":m.get("created_at"),"views":m.get("views"),"likes":m.get("likes"),"comments":m.get("comments"),
        "shares":m.get("shares"),"saves":m.get("saves"),"share_rate":m.get("share_rate"),"save_rate":m.get("save_rate"),
        "account_views_pct":m.get("account_views_pct"),"global_views_pct":m.get("global_views_pct"),
        "duration_seconds":m.get("duration_seconds"),"width":m.get("width"),"height":m.get("height"),"fps":m.get("fps"),
        "primary_language_code":d["primary_language_code"],"secondary_language_codes":json.dumps(d["secondary_language_codes"],ensure_ascii=False),
        "mixed_language":d["mixed_language"],"audience_segment":d["audience_segment"],"niche":d["niche"],"topic":d["topic"],
        "content_angle":d["content_angle"],"value_type":d["value_type"],"pain_point":d["pain_point"],"desired_outcome":d["desired_outcome"],
        "video_format":d["video_format"],"hook_start_second":h["start_second"],"hook_end_second":h["end_second"],
        "hook_spoken_text":h["spoken_text"],"hook_overlay_text":h["overlay_text"],"hook_technique":h["technique"],
        "hook_psychological_trigger":h["psychological_trigger"],"hook_replicable_formula":h["replicable_formula"],
        "spoken_transcript":d["spoken_transcript"],"narrative_structure":json.dumps(d["narrative_structure"],ensure_ascii=False),
        "dominant_visual_type":d["dominant_visual_type"],"visual_aesthetic":d["visual_aesthetic"],"text_overlay_style":d["text_overlay_style"],
        "editing_style":d["editing_style"],"camera_style":d["camera_style"],"face_or_person_present":d["face_or_person_present"],
        "has_speech":au["has_speech"],"has_background_music":au["has_background_music"],"narration_style":au["narration_style"],"pacing":au["pacing"],
        "proof_or_credibility":json.dumps(d["proof_or_credibility"],ensure_ascii=False),
        "has_product":p["has_visible_or_spoken_product"],"product_family":p["product_family"],"product_name":p["visible_or_spoken_name"],
        "product_first_second":p["first_appearance_second"],"product_placement_style":p["placement_style"],"product_evidence":json.dumps(p["evidence"],ensure_ascii=False),
        "has_explicit_cta":c["has_explicit_cta"],"cta_type":c["cta_type"],"cta_text_or_speech":c["text_or_speech"],
        "cta_second":c["timestamp_second"],"cta_modality":c["modality"],"cta_evidence":json.dumps(c["evidence"],ensure_ascii=False),
        "creative_formula":d["creative_formula"],"attention_mechanisms":json.dumps(d["attention_mechanisms_used"],ensure_ascii=False),
        "overall_confidence":d["overall_confidence"],"uncertainty_notes":json.dumps(d["uncertainty_notes"],ensure_ascii=False),
        "validation_events":"|".join(events),"timeline_json":json.dumps(d["timeline"],ensure_ascii=False),"analysis_json":json.dumps(d,ensure_ascii=False),
    }


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("--out",default="video_visual_study")
    ap.add_argument("--model",default="gemini-3.5-flash-lite")
    ap.add_argument("--sample-size",type=int,default=None)
    ap.add_argument("--sample-seed",type=int,default=42)
    ap.add_argument("--max-posts",type=int,default=None)
    ap.add_argument("--temperature",type=float,default=.1)
    ap.add_argument("--retries",type=int,default=4)
    ap.add_argument("--retry-base-seconds",type=float,default=2.0)
    ap.add_argument("--sleep-between",type=float,default=.2)
    ap.add_argument("--upload-timeout",type=int,default=300)
    ap.add_argument("--keep-uploaded-files",action="store_true")
    ap.add_argument("--force",action="store_true")
    args=ap.parse_args()

    key=os.environ.get("GEMINI_API_KEY")
    if not key: raise SystemExit("GEMINI_API_KEY is not set")
    out=Path(args.out).expanduser().resolve(); out.mkdir(parents=True,exist_ok=True)
    df=pd.read_csv(Path(args.manifest).expanduser().resolve())
    if args.sample_size is not None:
        df=df.sample(n=min(args.sample_size,len(df)),random_state=args.sample_seed).reset_index(drop=True)
    if args.max_posts is not None: df=df.head(args.max_posts)

    client=genai.Client(api_key=key)
    cache_path=out/"video_cache.jsonl"
    cache={(str(r.get("account")),str(r.get("post_id")),str(r.get("input_signature"))):r for r in read_jsonl(cache_path) if r.get("status")=="ok"}
    results=[]; failures=[]; event_counts={}

    for i,m in enumerate(df.to_dict(orient="records"),1):
        account,post_id=str(m["account"]),str(m["post_id"]); path=resolve_path(str(m["video_path"]))
        if not path.exists():
            fail={"account":account,"post_id":post_id,"error":f"missing video: {path}"}; failures.append(fail); append_jsonl(out/"failures.jsonl",fail); continue
        sig=signature(path,args.model); ck=(account,post_id,sig)
        if not args.force and ck in cache:
            rec=cache[ck]; a=VideoCreativeAnalysis.model_validate(rec["analysis"]); events=rec.get("validation_events",[])
            results.append(flatten(m,a,events)); print(f"[{i}/{len(df)}] cached @{account}/{post_id}")
            continue
        print(f"[{i}/{len(df)}] analyze @{account}/{post_id} ({m.get('duration_seconds')}s)")
        a=None; events=[]; last_error=None
        duration=None
        try:
            if m.get("duration_seconds") is not None and pd.notna(m.get("duration_seconds")): duration=float(m["duration_seconds"])
        except Exception: pass
        for attempt in range(args.retries+1):
            try:
                candidate=analyze_one(client,args.model,path,account,post_id,duration,args.temperature,args.upload_timeout,args.keep_uploaded_files)
                a,events=normalize_validate(candidate,duration); break
            except Exception as e:
                last_error=f"{type(e).__name__}: {e}"
                if attempt<args.retries:
                    wait=args.retry_base_seconds*(2**attempt)+random.random(); print(f"  retry after {wait:.1f}s: {last_error}"); time.sleep(wait)
        if a is None:
            fail={"account":account,"post_id":post_id,"input_signature":sig,"error":last_error}; failures.append(fail); append_jsonl(out/"failures.jsonl",fail); print("  FAILED",last_error); continue
        for e in events: event_counts[e]=event_counts.get(e,0)+1
        rec={"status":"ok","schema_version":SCHEMA_VERSION,"model":args.model,"account":account,"post_id":post_id,
             "input_signature":sig,"validation_events":events,"analysis":a.model_dump()}
        append_jsonl(cache_path,rec)
        bp=out/"by_post"/account/f"{post_id}.json"; bp.parent.mkdir(parents=True,exist_ok=True)
        bp.write_text(json.dumps(rec,ensure_ascii=False,indent=2),encoding="utf-8")
        results.append(flatten(m,a,events))
        if args.sleep_between: time.sleep(args.sleep_between)

    rdf=pd.DataFrame(results)
    rdf.to_csv(out/"creative_video_study.csv",index=False,encoding="utf-8-sig")
    with (out/"creative_video_study.jsonl").open("w",encoding="utf-8") as f:
        for r in results: f.write(json.dumps(r,ensure_ascii=False,default=str)+"\n")
    parquet=False
    if not rdf.empty:
        try: rdf.to_parquet(out/"creative_video_study.parquet",index=False); parquet=True
        except Exception as e: print("Parquet skipped:",e)
    report={"model":args.model,"schema_version":SCHEMA_VERSION,"manifest_posts_this_run":len(df),"analyzed_posts":len(results),
            "failed_posts":len(failures),"validation_event_counts":event_counts,"parquet_written":parquet,"output":str(out)}
    (out/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("\nDONE\n"+json.dumps(report,ensure_ascii=False,indent=2))

if __name__=="__main__": main()
