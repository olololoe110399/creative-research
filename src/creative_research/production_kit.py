"""Evidence-linked, team-facing creator production plan.

Consumes already-materialized public operator research. It does NOT fetch
Pinterest, copy source media, grant usage rights, invent sound metadata, infer
internal operator intent, or claim an experiment is proven effective.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import statistics
import zipfile
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "creator-production-kit-v1"
DEFAULT_RECIPES = 16
DEFAULT_DAYS = 30
MAX_RECIPES = 40
MAX_DAYS = 90


def _text(value: Any) -> str:
    return str(value or "").strip()


def _slug(value: Any) -> str:
    return " ".join(re.findall(r"\w+", _text(value).casefold(), flags=re.UNICODE))


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
        return result if result == result and abs(result) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 4) if values else None


def _clean_copy(value: Any, limit: int = 250) -> str:
    return _text(value).replace("\r", " ").replace("\n", " ")[:limit]


def _read_json(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value) if value else None
    except (ValueError, TypeError):
        return None


def _creative_kind(topic: str, angle: str, hook: str) -> str:
    t = " ".join([topic, angle, hook]).casefold()
    if any(x in t for x in ("schedule", "horario", "timetable", "time block", "thời khóa")):
        return "schedule"
    if any(x in t for x in ("exam", "thi cử", "test prep", "revision")):
        return "exam"
    if any(x in t for x in ("nurs", "medic", "clinical")):
        return "specialist"
    if any(x in t for x in ("note", "flashcard", "mindmap", "mind map")):
        return "notes"
    if any(x in t for x in ("tool", "app", "ai", "product")):
        return "tool"
    if any(x in t for x in ("motiv", "burnout", "tired", "procrastinat")):
        return "motivation"
    return "study_method"


_COPY_VI = {
    "schedule": (
        "4 kiểu người học, 4 cách chia lịch thực tế",
        [
            "Lịch cho người học buổi sáng: dành phiên tỉnh táo nhất cho môn khó.",
            "Lịch cho cú đêm: chốt giờ kết thúc, tránh học xuyên đêm.",
            "Lịch cho người đi làm: chia môn học thành các phiên 25 phút.",
            "Lịch tuần thi: ưu tiên chủ đề yếu và dành chỗ cho tự kiểm tra.",
            "Điều chỉnh lịch theo nhịp sống của bạn, đừng sao chép nguyên mẫu.",
        ],
    ),
    "exam": (
        "Đang gần kỳ thi? Thử kế hoạch ôn tập có kiểm tra lại",
        [
            "Liệt kê chủ đề chưa chắc trước khi bắt đầu.",
            "Ôn một phần nhỏ rồi tự trả lời khi không nhìn tài liệu.",
            "Tạo một bài kiểm tra ngắn cho chính mình.",
            "Ghi lại câu sai và quay lại vào phiên học tiếp theo.",
            "Chỉ giữ cách học nào giúp bạn giải thích được kiến thức.",
        ],
    ),
    "specialist": (
        "Khối ngành nhiều kiến thức: thử cách ôn bài bớt rối",
        [
            "Chia nội dung thành khái niệm, quy trình và ví dụ.",
            "Vẽ sơ đồ liên hệ cho những thuật ngữ hay nhầm.",
            "Tự giải thích một trường hợp đơn giản bằng lời của bạn.",
            "Kiểm tra câu trả lời với nguồn học liệu chính thức.",
            "Không coi mẹo học tập là hướng dẫn chuyên môn hoặc y tế.",
        ],
    ),
    "notes": (
        "Ghi chép nhiều nhưng khó nhớ? Đổi cách ôn thử xem",
        [
            "Sau khi học, viết lại ý chính bằng ba dòng.",
            "Biến mỗi ý thành một câu hỏi để tự kiểm tra.",
            "Vẽ một sơ đồ nối các phần có liên quan.",
            "Một ngày sau, thử trả lời khi không mở ghi chú.",
            "Chọn công cụ ghi chú bạn đã tự sử dụng và kiểm chứng.",
        ],
    ),
    "tool": (
        "Một workflow học tập 4 bước để bạn tự thử",
        [
            "Chọn một bài học thật thay vì ví dụ được dựng sẵn.",
            "Gom ghi chú chính thành các khái niệm rõ ràng.",
            "Tạo câu hỏi ôn tập rồi tự kiểm tra kết quả.",
            "Sửa chỗ sai bằng tài liệu học chính thống.",
            "Chỉ giới thiệu sản phẩm nếu đã kiểm chứng chức năng và có quyền quảng bá.",
        ],
    ),
    "motivation": (
        "Không có động lực học? Hãy thử một phiên thật nhỏ",
        [
            "Chọn đúng một nhiệm vụ hoàn thành được trong 20 phút.",
            "Cất thiết bị gây xao nhãng trước khi bắt đầu.",
            "Đặt một điểm dừng, không ép bản thân học bất tận.",
            "Sau phiên học, ghi lại phần đã hiểu và phần còn vướng.",
            "Lặp lại khi phù hợp; không hứa hẹn kết quả chỉ từ một mẹo.",
        ],
    ),
    "study_method": (
        "4 thay đổi nhỏ giúp việc học có cấu trúc hơn",
        [
            "Xác định chính xác kiến thức cần nắm trong phiên này.",
            "Học một ví dụ thật trước khi ghi chép lại công thức.",
            "Tự giải thích mà không nhìn tài liệu.",
            "Dùng một bài tập ngắn để phát hiện chỗ chưa hiểu.",
            "Lưu checklist và thử lại với một môn khác.",
        ],
    ),
}

_VARIANT_HOOK_VI = {
    "schedule": "Lịch học nào hợp nhịp sống của bạn nhất?",
    "exam": "Tuần thi tới rồi: bạn đã có cách ôn lại bài sai chưa?",
    "specialist": "Thử quy trình 4 bước ôn môn nhiều thuật ngữ",
    "notes": "Ghi chú thế nào để tự kiểm tra lại mà không học vẹt?",
    "tool": "Thử một buổi học có ghi chú, câu hỏi và tự kiểm tra",
    "motivation": "Chỉ có 20 phút để học: bạn sẽ bắt đầu thế nào?",
    "study_method": "Bạn đã thử học bằng cách tự giải thích chưa?",
}

_VISUAL_QUERY = {
    "study_desk_photo": "cozy study desk overhead notebook warm natural light portrait photography",
    "lifestyle_photo": "student lifestyle studying at desk warm minimal vertical photography",
    "notes_or_document": "original handwritten study notes paper planner close up vertical",
    "app_screen": "clean original mobile app mockup white background study productivity",
    "screen_recording": "study productivity app screen tutorial original UI mockup",
    "illustration": "minimal study planner editorial illustration portrait",
    "infographic": "study schedule minimal infographic editorial vertical",
    "text_overlay": "clean typographic study advice card textured neutral background",
}


def _visual_query(visual_type: Any, topic: Any) -> str:
    visual = _slug(visual_type).replace(" ", "_")
    if visual in _VISUAL_QUERY:
        return _VISUAL_QUERY[visual]
    brief = "original editorial study desk image minimal portrait"
    if "app" in _slug(topic):
        brief = "original study app mockup portrait"
    return brief


def _draft_for_role(kind: str, role: str, index: int, count: int) -> str:
    hook, body = _COPY_VI.get(kind, _COPY_VI["study_method"])
    r = _slug(role)
    if index == 1 or "hook" in r or "intro" in r:
        return hook
    if "product" in r or "cta" in r or "reveal" in r:
        return "Lưu checklist này. Chỉ giới thiệu công cụ sau khi team dùng thử và xác minh."
    if index == count and count > 2:
        return "Bạn sẽ thử phiên bản nào? Lưu bài để thực hành rồi ghi kết quả."
    return body[(index - 2) % len(body)]


def _family_members(family: dict[str, Any], posts: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    members = family.get("members") or []
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for member in members:
        uid = _text(member.get("post_uid"))
        if uid and uid in posts and uid not in seen:
            seen.add(uid)
            unique.append(posts[uid])
    if not unique:
        uid = _text(family.get("representative_post_uid") or family.get("family_origin_post_uid"))
        if uid in posts:
            unique.append(posts[uid])
    return unique


def _pct(post: dict[str, Any]) -> float | None:
    perf = post.get("performance") or {}
    return _num(perf.get("views_percentile_account") or post.get("account_views_pct"))


def _rank_family(fam: dict[str, Any], members: list[dict[str, Any]]) -> float:
    pct = [_pct(p) for p in members]
    pct = [v for v in pct if v is not None]
    save = [(_num(p.get("save_rate")) or 0) for p in members]
    coverage = len({p.get("account_id") for p in members})
    # Ranking heuristic for editorial inspection, NOT probability of success.
    return round(
        1.15 * min(coverage, 5) + 0.8 * min(len(members), 5)
        + 3.0 * (statistics.median(pct) if pct else 0)
        + 0.4 * (max(pct) if pct else 0)
        + 4.0 * (statistics.median(save) if save else 0),
        4,
    )


def _family_signature(fam: dict[str, Any], members: list[dict[str, Any]]) -> str:
    example = (members[0].get("creative") or {}) if members else {}
    topic = _slug(fam.get("core_topic") or example.get("topic"))
    hook = _slug(fam.get("core_hook_formula") or example.get("hook_replicable_formula"))
    return (topic[:64] + "|" + hook[:90]).strip("|")


def _select_families(
    families: list[dict[str, Any]],
    post_map: dict[str, dict[str, Any]],
    limit: int,
) -> list[tuple[dict[str, Any], list[dict[str, Any]], float]]:
    candidates: list[tuple[dict[str, Any], list[dict[str, Any]], float]] = []
    for fam in families:
        members = _family_members(fam, post_map)
        if not members:
            continue
        if not any((p.get("sequence") or []) for p in members):
            continue
        candidates.append((fam, members, _rank_family(fam, members)))
    candidates.sort(key=lambda item: (
        -int(len(item[1]) >= 2),
        -item[2],
        _text(item[0].get("family_id")),
    ))
    # Keep most recipes grounded in repeated patterns, plus a few single-post
    # explorations with high observed percentile; never call the latter validated.
    selected: list[tuple[dict[str, Any], list[dict[str, Any]], float]] = []
    used: set[str] = set()
    used_signature: set[str] = set()
    repeated_target = max(1, round(limit * 0.70))
    for pass_single in (False, True):
        for fam, members, score in candidates:
            if (len(members) == 1) != pass_single:
                continue
            if len(selected) >= limit:
                break
            if not pass_single and len(selected) >= repeated_target:
                break
            fid = _text(fam.get("family_id"))
            sig = _family_signature(fam, members)
            if fid in used or (sig and sig in used_signature):
                continue
            selected.append((fam, members, score))
            used.add(fid)
            if sig:
                used_signature.add(sig)
    # If there were few singletons, use more distinct repeated examples.
    if len(selected) < limit:
        for fam, members, score in candidates:
            fid = _text(fam.get("family_id"))
            sig = _family_signature(fam, members)
            if len(selected) >= limit:
                break
            if fid not in used and (not sig or sig not in used_signature):
                selected.append((fam, members, score))
                used.add(fid)
                if sig:
                    used_signature.add(sig)
    return selected


def _reference_posts(members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for post in members:
        creative = post.get("creative") or {}
        rows.append({
            "post_uid": post["post_uid"],
            "account": post.get("account"),
            "account_id": post.get("account_id"),
            "post_id": post.get("post_id"),
            "url": post.get("url"),
            "views": post.get("views"),
            "account_relative_views_percentile": _pct(post),
            "saves": post.get("saves"),
            "created_at": post.get("created_at"),
            "hook_reference": _clean_copy(creative.get("hook_text")),
        })
    return rows


def _candidate_false_splits(
    families: list[dict[str, Any]], post_map: dict[str, dict[str, Any]],
    max_pairs: int = 50,
) -> list[dict[str, Any]]:
    by_hook: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fam in families:
        if int(fam.get("member_count") or 0) != 1:
            continue
        uid = _text(fam.get("family_origin_post_uid") or fam.get("representative_post_uid"))
        post = post_map.get(uid)
        hook = _slug(fam.get("core_hook_text") or (post or {}).get("creative", {}).get("hook_text"))
        if hook and post and len(hook) >= 25:
            by_hook[hook].append(fam)
    matches: list[dict[str, Any]] = []
    for hook, group in sorted(by_hook.items()):
        if len(group) < 2:
            continue
        group = sorted(group, key=lambda f: str(f.get("family_id")))[:20]
        for a, b in combinations(group, 2):
            if len(matches) >= max_pairs:
                return matches
            pa = post_map.get(_text(a.get("family_origin_post_uid")))
            pb = post_map.get(_text(b.get("family_origin_post_uid")))
            if not pa or not pb or pa.get("account_id") == pb.get("account_id"):
                continue
            aa, bb = pa.get("creative") or {}, pb.get("creative") or {}
            shared_product = _slug(aa.get("product_family")) == _slug(bb.get("product_family"))
            if not shared_product:
                continue
            role_a = [_slug(s.get("role")) for s in pa.get("sequence") or []]
            role_b = [_slug(s.get("role")) for s in pb.get("sequence") or []]
            if not role_a or role_a != role_b:
                continue
            matches.append({
                "family_a": a.get("family_id"),
                "family_b": b.get("family_id"),
                "post_a": pa["post_uid"],
                "post_b": pb["post_uid"],
                "url_a": pa.get("url"), "url_b": pb.get("url"),
                "accounts": [pa.get("account"), pb.get("account")],
                "shared_hook_reference": hook[:180],
                "matching_sequence_roles": role_a,
                "shared_product_family": aa.get("product_family"),
                "finding": "possible_false_split_needs_semantic_or_visual_check",
                "validated_same_concept": False,
            })
    return matches


def _blueprints(
    accounts: list[dict[str, Any]],
    recipes: list[dict[str, Any]],
    posts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    niche_counts = Counter(
        _slug((p.get("creative") or {}).get("audience_segment"))
        for p in posts
        if p.get("creative")
    )
    audience = [x for x, n in niche_counts.most_common(7) if x and n >= 5]
    if not audience:
        audience = ["student"]
    observed = sorted(
        accounts, key=lambda a: -(int(a.get("observed_posts") or 0))
    )[:4]
    source_account_refs = [{
        "account_id": a.get("account_id"), "handle": a.get("account"),
        "observed_posts": a.get("observed_posts"),
        "median_views": (a.get("performance_baseline") or {}).get("median_views"),
        "median_gap_hours": (a.get("cadence_summary") or {}).get("median_gap_hours"),
        "top_posting_hours_utc": _read_json(
            (a.get("cadence_summary") or {}).get("top_posting_hours_json")
        ) or [],
    } for a in observed]
    return [
        {
            "slot_id": "PILOT-A",
            "account_type": "owned_original_content",
            "positioning": "Mẹo học và lịch học thực tế cho sinh viên",
            "audience": "Sinh viên muốn học có kế hoạch",
            "suggested_handle_pattern": "study.<topic>.<your_brand> (verify availability)",
            "bio_draft": "Lịch học dễ áp dụng • Mẹo ghi nhớ • Chia sẻ trải nghiệm học thật",
            "avatar_brief": "Original minimal study-themed icon; do not mimic the operator identity",
            "content_pillars": ["study schedules", "study methods", "exam planning"],
            "proposed_cadence": "1 post every two days during pilot",
            "proposed_local_time": "19:00",
            "time_zone": "Asia/Ho_Chi_Minh",
            "reference_audience_labels": audience[:4],
            "source_account_observations": source_account_refs[:2],
            "setup_checklist": [
                "Create and verify a unique account that you own",
                "Choose a consistent audience and language",
                "Use a brand-owned avatar and authentic bio",
                "Enable appropriate account security and disclose promotions",
                "Prepare a tracking sheet and original licensed content",
            ],
            "evidence_boundary": "Pilot account strategy, NOT a proven operator internal role.",
        },
        {
            "slot_id": "PILOT-B",
            "account_type": "owned_original_content",
            "positioning": "Ôn thi, ghi chú và thử các phương pháp ghi nhớ",
            "audience": "Người cần ôn tập và ghi chép có hệ thống",
            "suggested_handle_pattern": "notes.<topic>.<your_brand> (verify availability)",
            "bio_draft": "Ôn thi có hệ thống • Ghi chú • Thử nghiệm phương pháp học",
            "avatar_brief": "Original notebook/flashcard brand mark with documented source",
            "content_pillars": ["note taking", "exam prep", "study tools"],
            "proposed_cadence": "1 post every two days during pilot",
            "proposed_local_time": "21:00",
            "time_zone": "Asia/Ho_Chi_Minh",
            "reference_audience_labels": audience[:4],
            "source_account_observations": source_account_refs[2:4],
            "setup_checklist": [
                "Verify unique handle and own the account",
                "Choose one audience and one voice",
                "Set avatar and bio with owned creative",
                "Prepare a repeatable original visual template",
                "Log publication and outcomes consistently",
            ],
            "evidence_boundary": "Pilot segmentation is a proposal; hours are not validated best times.",
        },
    ]


def build_production_kit(
    *,
    evidence: dict[str, Any],
    families: dict[str, Any],
    accounts: dict[str, Any],
    lab: dict[str, Any] | None = None,
    recipes_limit: int = DEFAULT_RECIPES,
    calendar_days: int = DEFAULT_DAYS,
) -> dict[str, Any]:
    """Build a reproducible, public-evidence-linked production starter pack."""
    if not 1 <= recipes_limit <= MAX_RECIPES:
        raise ValueError(f"recipes_limit must be 1..{MAX_RECIPES}")
    if not 1 <= calendar_days <= MAX_DAYS:
        raise ValueError(f"calendar_days must be 1..{MAX_DAYS}")
    posts = evidence.get("posts") or []
    family_rows = families.get("families") or []
    account_rows = accounts.get("accounts") or []
    if not posts or not family_rows or not account_rows:
        raise ValueError("Production Kit needs posts, families and account baseline data.")
    post_map = {str(p["post_uid"]): p for p in posts if p.get("post_uid")}
    if len(post_map) != len(posts):
        raise ValueError("Duplicate or empty canonical post_uid in Production Kit source.")
    account_scopes = {str(a.get("operator_id")) for a in account_rows if a.get("operator_id")}
    post_scopes = {str(p.get("operator_id")) for p in posts if p.get("operator_id")}
    if len(account_scopes | post_scopes) != 1:
        raise ValueError("Production Kit must be scoped to exactly one operator.")
    operator_id = next(iter(account_scopes | post_scopes))
    source_digest = hashlib.sha256(json.dumps(
        [(p.get("post_uid"), p.get("views"), p.get("created_at")) for p in posts],
        sort_keys=True, ensure_ascii=False, default=str,
    ).encode("utf-8")).hexdigest()

    selected = _select_families(family_rows, post_map, recipes_limit)
    if not selected:
        raise ValueError("No complete creative sequences available for production.")
    recipes: list[dict[str, Any]] = []
    assets: list[dict[str, Any]] = []
    for idx, (fam, members, rank) in enumerate(selected, 1):
        recipe_id = f"REC-{idx:03d}"
        representative = max(
            members, key=lambda p: (_pct(p) or 0, _num(p.get("saves")) or 0)
        )
        c = representative.get("creative") or {}
        seq = sorted(representative.get("sequence") or [], key=lambda s: int(s.get("position") or 0))
        kind = _creative_kind(
            _text(fam.get("core_topic") or c.get("topic")),
            _text(fam.get("core_angle") or c.get("content_angle")),
            _text(fam.get("core_hook_text") or c.get("hook_text")),
        )
        pct_vals = [_pct(p) for p in members]
        pct_vals = [v for v in pct_vals if v is not None]
        source_posts = _reference_posts(members)
        if len(seq) < 2:
            seq = [
                {"role": "hook", "position": 1, "visual_type": c.get("dominant_visual_type")},
                {"role": "body", "position": 2, "visual_type": c.get("dominant_visual_type")},
                {"role": "body", "position": 3, "visual_type": c.get("dominant_visual_type")},
                {"role": "body", "position": 4, "visual_type": c.get("dominant_visual_type")},
                {"role": "product_reveal", "position": 5, "visual_type": "app_screen"},
            ]
        slides: list[dict[str, Any]] = []
        for sequence_idx, row in enumerate(seq[:10], 1):
            visual_type = _text(row.get("visual_type") or c.get("dominant_visual_type"))
            asset_id = f"AST-{idx:03d}-{sequence_idx:02d}"
            visual = _visual_query(visual_type, c.get("topic"))
            draft = _draft_for_role(kind, _text(row.get("role")), sequence_idx, len(seq[:10]))
            slides.append({
                "slide_number": sequence_idx,
                "role": _text(row.get("role") or "body"),
                "source_text_reference_only": _clean_copy(
                    row.get("primary_text") or row.get("overlay_text")
                ),
                "new_draft_text_vi": draft,
                "source_visual_description": _clean_copy(row.get("visual_description"), 320),
                "production_visual_brief": (
                    "Create/photograph an ORIGINAL asset inspired by the composition: "
                    + (_clean_copy(row.get("visual_description"), 170) or visual)
                    + ". Do not copy source media or branded screenshots."
                ),
                "visual_search_query": visual,
                "asset_id": asset_id,
                "visual_type": visual_type,
                "source_post_uid": representative["post_uid"],
            })
            assets.append({
                "asset_id": asset_id, "recipe_id": recipe_id,
                "kind": "image", "role": f"slide_{sequence_idx}",
                "search_query": visual,
                "reference_post_uid": representative["post_uid"],
                "reference_post_url": representative.get("url"),
                "file_or_licensed_source_url": "",
                "license_evidence_url": "",
                "license_scope": "",
                "rights_status": "not_verified",
                "production_status": "needs_original_or_licensed_asset",
                "safe_to_publish": False,
                "note": "TikTok/Pinterest appearance is a visual reference, not image reuse permission.",
            })
        sound_id = f"SOUND-{idx:03d}"
        assets.append({
            "asset_id": sound_id, "recipe_id": recipe_id,
            "kind": "music", "role": "background",
            "search_query": (
                "licensed calm instrumental study background audio"
                if kind not in {"motivation"} else "licensed gentle upbeat instrumental"
            ),
            "reference_post_uid": representative["post_uid"],
            "reference_post_url": representative.get("url"),
            "file_or_licensed_source_url": "",
            "license_evidence_url": "",
            "license_scope": "",
            "rights_status": "not_verified",
            "production_status": "sound_metadata_and_clearance_required",
            "safe_to_publish": False,
            "note": "Historical music ID not in Lab export; verify the sound and commercial-use rights.",
        })
        source_rights = "reference_only_not_licensed"
        grade = (
            "observed_multi_account_structure"
            if len({p.get("account_id") for p in members}) > 1
            else "observed_multi_execution_structure"
            if len(members) > 1
            else "single_observed_example"
        )
        recipes.append({
            "recipe_id": recipe_id, "family_id": fam.get("family_id"),
            "title": _COPY_VI[kind][0],
            "concept_reference": _clean_copy(fam.get("core_topic") or c.get("topic")),
            "creative_angle": _text(c.get("content_angle") or fam.get("core_angle")),
            "hook_mechanism_reference": _clean_copy(
                fam.get("core_hook_formula") or c.get("hook_replicable_formula")
            ),
            "observed_original_hook_reference_only": _clean_copy(
                fam.get("core_hook_text") or c.get("hook_text")
            ),
            "new_hook_draft_vi": _COPY_VI[kind][0],
            "content_type": representative.get("content_type"),
            "creative_kind": kind,
            "format": _text(c.get("content_format") or c.get("video_format")),
            "source_product_reference": c.get("product_family"),
            "slides": slides,
            "new_caption_draft_vi": (
                _COPY_VI[kind][0] + ". Lưu lại để thử rồi cho mình biết "
                "bạn đã điều chỉnh cách học nào nhé."
            ),
            "proposed_hashtags": ["#meohoc", "#studywithme", "#hoc_tap"],
            "proposed_cta": "Save this original checklist; share results, not guaranteed outcomes",
            "suggested_music_asset_id": sound_id,
            "observed_source_posts": source_posts,
            "evidence_grade": grade,
            "evidence": {
                "family_member_count": len(members),
                "distinct_accounts": len({p.get("account_id") for p in members}),
                "median_account_relative_views_percentile": _median(pct_vals),
                "lowest_account_relative_views_percentile": min(pct_vals) if pct_vals else None,
                "highest_account_relative_views_percentile": max(pct_vals) if pct_vals else None,
                "under_account_p35_examples": sum(v <= 0.35 for v in pct_vals),
                "selected_representative_uid": representative["post_uid"],
                "rank_for_editorial_inspection_only": rank,
                "chronology_not_causation": True,
            },
            "readiness": "draft_requires_copy_fact_check_and_asset_clearance",
            "rights_scope": source_rights,
            "is_proven_to_work_for_user": False,
            "editorial_checks": [
                "Review every generated slide against brand voice and factual sources.",
                "Use owned/licensed images and fonts; document rights.",
                "Confirm sound ID and TikTok/commercial usage terms in target region.",
                "No implication of proven operator intentions or expected views.",
                "Publish with authentic promotion disclosures when applicable.",
            ],
        })

    account_blueprints = _blueprints(account_rows, recipes, posts)
    calendar: list[dict[str, Any]] = []
    for day in range(1, calendar_days + 1):
        rec = recipes[(day - 1) % len(recipes)]
        account = account_blueprints[(day - 1) % len(account_blueprints)]
        variant = "A" if day <= len(recipes) else "B"
        calendar.append({
            "day": day, "slot_id": f"PUB-{day:03d}",
            "pilot_account": account["slot_id"],
            "recipe_id": rec["recipe_id"],
            "family_id": rec["family_id"],
            "variant": variant,
            "test_dimension": "hook wording",
            "hook_to_publish_draft_vi": (
                rec["new_hook_draft_vi"] if variant == "A" else
                _VARIANT_HOOK_VI.get(rec["creative_kind"], _VARIANT_HOOK_VI["study_method"])
            ),
            "controlled_test": (
                "A/B test changes only the first-slide hook; keep account, "
                "visual style, CTA, content structure and slot constant "
                "unless separately tracked."
            ),
            "stop_or_recheck": (
                "Do not scale on a single post. Review at least five age-matched "
                "A/B pairs or stop earlier if copyright/fact review fails. "
                "Five pairs is a proposed experimental guardrail, NOT an "
                "operator-derived threshold."
            ),
            "planned_local_time": account["proposed_local_time"],
            "timezone": account["time_zone"],
            "time_basis": "proposed_experiment_not_validated_best_time",
            "content_type": rec["content_type"],
            "work_status": "draft",
            "publish_gate": "blocked_until_rights_and_copy_review",
            "measure_at": ["24h", "72h", "7d"],
            "tracking": "new_tracking_required",
            "primary_metric": "views_at_same_age_vs_own_recent_age_matched_baseline",
            "secondary_metrics": ["saves_per_view", "shares_per_view"],
            "post_url": "", "owner": "", "asset_clearance": "pending",
        })

    false_splits = _candidate_false_splits(family_rows, post_map)
    repeat_count = sum(int(f.get("member_count") or 0) > 1 for f in family_rows)
    cross_count = sum(bool(f.get("cross_account")) and int(f.get("member_count") or 0) > 1 for f in family_rows)
    sample_refs = [r["observed_source_posts"][0]["post_uid"] for r in recipes]
    observed_slides = sum(p.get("content_type") == "slideshow" for p in posts)
    lessons = [
        {
            "id": "LES-FORMAT", "kind": "observed",
            "statement": (
                f"{observed_slides} of {len(posts)} observed posts use a slideshow format."
            ),
            "source_post_uids": sample_refs[:8],
            "action": "Start with a small slideshow pilot; do not assume it beats videos.",
            "qualification": "Format prevalence does not establish causal performance.",
        },
        {
            "id": "LES-REUSE", "kind": "observed",
            "statement": (
                f"{repeat_count} candidate families contain multiple posts; "
                f"{cross_count} repeat across accounts."
            ),
            "source_family_ids": [r["family_id"] for r in recipes if r["evidence"]["family_member_count"] > 1],
            "action": "Test distinct original executions while tracking the same underlying concept.",
            "qualification": "Clustering may split or merge concepts incorrectly; no intent inferred.",
        },
        {
            "id": "LES-COUNTER", "kind": "bounded_inference",
            "statement": (
                "Repeated concepts show variable account-relative views; "
                "one execution does not determine another's result."
            ),
            "source_post_uids": sample_refs[:8],
            "action": "Collect underperforming as well as strong posts and compare account baselines.",
            "qualification": "No controlled test or future-success guarantee.",
        },
    ]
    return {
        "schema_version": SCHEMA_VERSION, "operator_id": operator_id,
        "source_post_count": len(posts),
        "source_family_count": len(family_rows),
        "source_account_count": len(account_rows),
        "source_fingerprint": source_digest,
        "research_context": {
            "source": "materialized Lab JSON (public posts + Vision interpretation)",
            "account_grouping": "researcher_declared_not_independent_ownership_proof",
            "calendar_timezone": "Asia/Ho_Chi_Minh",
            "planned_language": "vi",
            "assumptions": [
                "Two brand-owned pilot accounts are proposed, not observed operator roles.",
                "All new overlay/caption text is a DRAFT inspired by observed structure.",
                "Post source text is evidence-only; do not republish without permission.",
                "Historical posting hours are descriptive, not validated best posting times.",
                "No actual asset usage rights have been granted by this kit.",
            ],
        },
        "account_blueprints": account_blueprints,
        "recipes": recipes,
        "calendar": calendar,
        "asset_bank": assets,
        "music_bank": [],
        "caption_bank": [],
        "hashtag_bank": [],
        "suspected_false_splits": false_splits,
        "lessons": lessons,
        "quality": {
            "recipes_generated": len(recipes),
            "calendar_slots": len(calendar),
            "post_evidence_links": sum(len(r["observed_source_posts"]) for r in recipes),
            "slides_drafted": sum(len(r["slides"]) for r in recipes),
            "asset_candidates": len(assets),
            "assets_with_verified_rights": 0,
            "ready_to_publish": 0,
            "sound_metadata_coverage": 0,
            "raw_enrichment": "not_supplied",
            "source_coverage_is_sample_not_full_license_audit": True,
            "readiness": "TEAM_BRIEF_DRAFT_not_auto_publishable",
        },
    }



def enrich_production_kit_from_raw(
    kit: dict[str, Any],
    raw_root: Path,
    *,
    evidence_posts: list[dict[str, Any]] | None = None,
    max_files: int = 300,
    max_rows: int = 200_000,
) -> dict[str, Any]:
    """Recover the observed operator's FULL music/caption/hashtag library.

    All values are from local public scrape metadata, not guesses. A sound ID
    or photograph does NOT imply permission to use it in a new publication.
    """
    if not raw_root.is_dir():
        raise ValueError(f"raw_root does not exist: {raw_root}")
    chosen_by_key: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}
    for recipe in kit["recipes"]:
        for post in recipe["observed_source_posts"]:
            key = (_text(post.get("account")).casefold(), _text(post.get("post_id")))
            chosen_by_key[key] = (recipe["recipe_id"], post)

    # If canonical evidence is available, collect sound/caption metadata
    # across ALL observed posts, not just hand-picked high-view recipes.
    expected: dict[tuple[str, str], dict[str, Any]] = {}
    for p in evidence_posts or []:
        key = (_text(p.get("account")).casefold(), _text(p.get("post_id")))
        if all(key):
            expected[key] = {
                "post_uid": _text(p.get("post_uid")),
                "post_url": _text(p.get("url")),
                "account": _text(p.get("account")),
                "account_relative_views_percentile": _pct(p),
            }
    for key, (_, source) in chosen_by_key.items():
        expected.setdefault(key, {
            "post_uid": _text(source.get("post_uid")),
            "post_url": _text(source.get("url")),
            "account": _text(source.get("account")),
            "account_relative_views_percentile": _num(
                source.get("account_relative_views_percentile")
            ),
        })

    located: dict[tuple[str, str], dict[str, Any]] = {}
    files = sorted({
        *raw_root.rglob("all_items.jsonl"),
        *raw_root.rglob("posts.jsonl"),
    })[:max_files]
    scanned = 0
    for path in files:
        if scanned >= max_rows or len(located) == len(expected):
            break
        try:
            stream = path.open("r", encoding="utf-8-sig")
        except OSError:
            continue
        with stream:
            for line in stream:
                if scanned >= max_rows or len(located) == len(expected):
                    break
                if not line.strip():
                    continue
                scanned += 1
                try:
                    raw = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(raw, dict):
                    continue
                pid = _text(
                    raw.get("post_id") or raw.get("id") or raw.get("idStr")
                    or raw.get("postId") or raw.get("awemeId")
                )
                author = raw.get("authorMeta") or raw.get("author") or {}
                if not isinstance(author, dict):
                    author = {}
                handle = _text(
                    raw.get("input") or raw.get("account")
                    or author.get("name") or author.get("uniqueId")
                ).casefold().lstrip("@").split("?")[0].split("/")[-1]
                key = (handle, pid)
                if key not in expected or key in located:
                    continue
                music = raw.get("musicMeta") or raw.get("music") or {}
                if not isinstance(music, dict):
                    music = {}
                hashtags = raw.get("hashtags") or []
                if isinstance(hashtags, str):
                    hashtags = [part for part in re.split(r"[,| ]+", hashtags) if part]
                clean_tags: list[str] = []
                if isinstance(hashtags, list):
                    for tag in hashtags[:30]:
                        name = (
                            tag.get("name") or tag.get("hashtagName")
                            if isinstance(tag, dict) else str(tag)
                        )
                        if name:
                            clean_tags.append(str(name).lstrip("#")[:60])
                located[key] = {
                    **expected[key],
                    "caption": _clean_copy(
                        raw.get("text") or raw.get("caption") or raw.get("desc"),
                        600,
                    ),
                    "hashtags": list(dict.fromkeys(clean_tags)),
                    "music_id": _text(
                        music.get("musicId") or music.get("id")
                        or raw.get("music_id")
                    ),
                    "music_name": _text(
                        music.get("musicName") or music.get("title")
                        or raw.get("music_name")
                    ),
                    "music_author": _text(
                        music.get("musicAuthor") or music.get("authorName")
                        or raw.get("music_author")
                    ),
                }

    sound_index: dict[str, dict[str, Any]] = {}
    hashtag_index: dict[str, dict[str, Any]] = {}
    caption_examples: list[dict[str, Any]] = []
    for key, meta in located.items():
        if key in chosen_by_key:
            _, source = chosen_by_key[key]
            source["observed_caption_reference_only"] = meta["caption"]
            source["observed_hashtags_reference_only"] = meta["hashtags"]
        if meta["caption"]:
            caption_examples.append({
                "post_uid": meta["post_uid"],
                "account": meta["account"],
                "url": meta["post_url"],
                "caption_reference_only": meta["caption"],
                "views_percentile_account": meta["account_relative_views_percentile"],
                "rights_scope": "research_reference_not_republication_permission",
            })
        for hashtag in meta["hashtags"]:
            hkey = hashtag.casefold()
            item = hashtag_index.setdefault(hkey, {
                "hashtag": hashtag,
                "observed_post_count": 0,
                "example_post_uids": [],
                "usage_not_recommended_without_relevance_check": True,
            })
            item["observed_post_count"] += 1
            if len(item["example_post_uids"]) < 5:
                item["example_post_uids"].append(meta["post_uid"])
        if not (meta["music_id"] or meta["music_name"]):
            continue
        sound_key = meta["music_id"] or (
            "name:"+_slug(meta["music_name"])+":"+_slug(meta["music_author"])
        )
        sound = sound_index.setdefault(sound_key, {
            "sound_key": sound_key,
            "music_id": meta["music_id"] or None,
            "music_name": meta["music_name"] or None,
            "music_author": meta["music_author"] or None,
            "source_post_uids": [],
            "source_urls": [],
            "observed_post_count": 0,
            "license_status": "not_verified",
            "rights_scope": "reference_only",
            "usable_as_commercial_sound": False,
            "source": "raw_scrape_metadata",
        })
        sound["observed_post_count"] += 1
        if len(sound["source_post_uids"]) < 25:
            sound["source_post_uids"].append(meta["post_uid"])
            sound["source_urls"].append(meta["post_url"])
        if key in chosen_by_key:
            rid, source = chosen_by_key[key]
            if source["post_uid"] == kit["recipes"][int(rid[4:])-1]["evidence"]["selected_representative_uid"]:
                for asset in kit["asset_bank"]:
                    if asset["recipe_id"] == rid and asset["kind"] == "music":
                        asset["observed_sound_key"] = sound_key
                        asset["production_status"] = "sound_found_but_license_not_verified"

    kit["music_bank"] = sorted(
        sound_index.values(),
        key=lambda s: (-s["observed_post_count"],s["sound_key"]),
    )
    kit["caption_bank"] = sorted(
        caption_examples,
        key=lambda p: (-(p["views_percentile_account"] or 0),p["post_uid"]),
    )[:250]
    kit["hashtag_bank"] = sorted(
        hashtag_index.values(),
        key=lambda h: (-h["observed_post_count"],h["hashtag"].casefold()),
    )[:500]
    q = kit["quality"]
    q["raw_enrichment"] = "scanned_public_local_archive"
    q["raw_files_scanned"] = len(files)
    q["raw_rows_scanned"] = scanned
    q["raw_posts_matched"] = len(located)
    q["raw_posts_expected"] = len(expected)
    q["observed_caption_count"] = len(caption_examples)
    q["observed_hashtag_types"] = len(kit["hashtag_bank"])
    q["observed_sound_post_count"] = sum(
        s["observed_post_count"] for s in kit["music_bank"]
    )
    q["sound_metadata_coverage"] = round(
        q["observed_sound_post_count"] / len(expected),4
    ) if expected else 0
    return kit


def apply_team_asset_clearance(
    kit: dict[str, Any], rows: list[dict[str, str]]
) -> dict[str, Any]:
    """Record team attestations, not automatic legal/third-party verification."""
    assets_by_id = {row["asset_id"]: row for row in kit["asset_bank"]}
    seen: set[str] = set()
    for row in rows:
        aid = _text(row.get("asset_id"))
        if aid not in assets_by_id or aid in seen:
            raise ValueError(f"Unknown/duplicate asset ID in clearance CSV: {aid}")
        seen.add(aid)
        asset = assets_by_id[aid]
        status = _text(row.get("rights_status"))
        if status not in {"not_verified", "team_attested_licensed"}:
            raise ValueError(f"Invalid asset rights_status for {aid}")
        if status == "team_attested_licensed":
            location = _text(row.get("file_or_licensed_source_url"))
            evidence_url = _text(row.get("license_evidence_url"))
            verifier = _text(row.get("verified_by"))
            scope = _text(row.get("license_scope"))
            if not all((location, evidence_url, verifier, scope)):
                raise ValueError(f"Asset {aid} lacks evidence, ownership, or license scope")
            if "tiktok" not in scope.casefold():
                raise ValueError(f"Asset {aid} not licensed for target platform TikTok")
            asset.update({
                "file_or_licensed_source_url": location,
                "license_evidence_url": evidence_url,
                "license_scope": scope,
                "rights_status": status,
                "production_status": "team_attested_rights_editorial_review_pending",
                # Attestation of rights is not proof that copy, claims, partner
                # disclosures, brand policy and TikTok terms have been checked.
                "safe_to_publish": False,
                "verified_by": verifier,
                "rights_verified_at": _text(row.get("verified_at")),
            })
    kit["quality"]["assets_with_verified_rights"] = sum(
        asset["rights_status"] == "team_attested_licensed"
        for asset in kit["asset_bank"]
    )
    kit["quality"]["ready_to_publish"] = 0
    return kit


def attach_own_experiment_outcomes(
    kit: dict[str, Any], rows: list[dict[str, str]]
) -> dict[str, Any]:
    """Track actual first-party results with provenance, including failures."""
    valid_recipes = {r["recipe_id"] for r in kit["recipes"]}
    outcome_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows, 1):
        recipe_id = _text(row.get("recipe_id"))
        if recipe_id not in valid_recipes:
            raise ValueError(f"Outcome row {index}: unknown recipe_id {recipe_id!r}")
        views = _num(row.get("views"))
        baseline = _num(row.get("account_median_views"))
        saves = _num(row.get("saves"))
        shares = _num(row.get("shares"))
        if views is not None and views < 0:
            raise ValueError(f"Outcome row {index}: negative views")
        if baseline is not None and baseline <= 0:
            raise ValueError(f"Outcome row {index}: baseline must be > 0")
        if any(v is not None and v < 0 for v in (saves, shares)):
            raise ValueError(f"Outcome row {index}: negative interaction count")
        comparison = round(views / baseline, 3) if views is not None and baseline else None
        outcome_rows.append({
            "recipe_id": recipe_id,
            "account_slot": _text(row.get("account_slot")),
            "published_url": _text(row.get("published_url")),
            "posted_at": _text(row.get("posted_at")),
            "measurement_age_hours": _num(row.get("measurement_age_hours")),
            "views": views, "saves": saves, "shares": shares,
            "account_median_views": baseline,
            "views_vs_account_median": comparison,
            "saves_per_view": round(saves / views, 6) if views and saves is not None else None,
            "shares_per_view": round(shares / views, 6) if views and shares is not None else None,
            "editorial_notes": _clean_copy(row.get("notes"), 800),
            "evidence_origin": "first_party_team_reported_not_scraped_operator",
            "causal_claim": False,
        })
    kit["own_experiment_outcomes"] = outcome_rows
    kit["quality"]["first_party_results_recorded"] = len(outcome_rows)
    return kit


def audit_production_kit(
    kit: dict[str, Any], post_ids: set[str] | None = None
) -> dict[str, Any]:
    errors: list[str] = []
    recipe_rows = kit.get("recipes") or []
    recipe_ids = [r.get("recipe_id") for r in recipe_rows]
    if not recipe_ids or len(recipe_ids) != len(set(recipe_ids)):
        errors.append("empty_or_duplicate_recipe_ids")
    asset_rows = kit.get("asset_bank") or []
    asset_ids = [a.get("asset_id") for a in asset_rows]
    if len(asset_ids) != len(set(asset_ids)):
        errors.append("duplicate_asset_ids")
    for recipe in recipe_rows:
        rid = recipe.get("recipe_id")
        if not recipe.get("observed_source_posts"):
            errors.append(f"{rid}:missing_source_posts")
        if not recipe.get("slides"):
            errors.append(f"{rid}:no_production_slides")
        if recipe.get("is_proven_to_work_for_user") is not False:
            errors.append(f"{rid}:unjustified_success_claim")
        if recipe.get("readiness") != "draft_requires_copy_fact_check_and_asset_clearance":
            errors.append(f"{rid}:missing_readiness_warning")
        for post in recipe.get("observed_source_posts", []):
            if not post.get("post_uid") or not post.get("url"):
                errors.append(f"{rid}:untraceable_post")
            if post_ids is not None and post.get("post_uid") not in post_ids:
                errors.append(f"{rid}:orphan_post_reference")
        for slide in recipe.get("slides", []):
            if slide.get("asset_id") not in asset_ids:
                errors.append(f"{rid}:slide_without_asset")
    for asset in asset_rows:
        if asset.get("recipe_id") not in recipe_ids:
            errors.append(f"{asset.get('asset_id')}:orphan_asset_recipe")
        if asset.get("rights_status") != "team_attested_licensed" and asset.get("safe_to_publish"):
            errors.append(f"{asset.get('asset_id')}:unlicensed_asset_marked_publishable")
    for calendar in kit.get("calendar", []):
        if calendar.get("recipe_id") not in recipe_ids:
            errors.append(f"{calendar.get('slot_id')}:orphan_calendar_recipe")
        if calendar.get("publish_gate") != "blocked_until_rights_and_copy_review":
            errors.append(f"{calendar.get('slot_id')}:unsafe_publish_gate")
        if calendar.get("tracking") != "new_tracking_required":
            errors.append(f"{calendar.get('slot_id')}:unsupported_existing_tracking_claim")
    return {
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "schema_version": SCHEMA_VERSION,
        "recipes_checked": len(recipe_rows),
        "calendar_slots_checked": len(kit.get("calendar", [])),
        "asset_candidates_checked": len(asset_rows),
        "meaning": (
            "Lineage, honesty and handoff contract check; not external "
            "copyright verification, creative accuracy, or proven outcomes."
        ),
    }


def _csv_bytes(rows: list[dict[str, Any]], columns: list[str]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({
            column: (
                json.dumps(row.get(column), ensure_ascii=False)
                if isinstance(row.get(column), (dict, list))
                else row.get(column)
            )
            for column in columns
        })
    return stream.getvalue().encode("utf-8-sig")


def _source_markdown(recipe: dict[str, Any]) -> str:
    source_links = "\n".join(
        f"- {p['post_uid']} / @{p.get('account')}: {p.get('url')} "
        f"(views {p.get('views')}, own-account percentile "
        f"{p.get('account_relative_views_percentile')})"
        for p in recipe["observed_source_posts"]
    )
    slides = "\n".join(
        f"### Slide/scene {s['slide_number']} — {s['role']}\n\n"
        f"New Vietnamese draft: {s['new_draft_text_vi']}\n\n"
        f"Make original visual: {s['production_visual_brief']}\n\n"
        f"Reference-only text: {s['source_text_reference_only']}\n\n"
        f"Search prompt: {s['visual_search_query']} | asset {s['asset_id']}\n"
        for s in recipe["slides"]
    )
    return (
        f"# {recipe['recipe_id']} — {recipe['title']}\n\n"
        "STATUS: Draft for editorial fact-check and LICENSED/ORIGINAL ASSETS. "
        "Not approved for publication as-is.\n\n"
        f"Evidence grade: {recipe['evidence_grade']}\n\n"
        f"Creative structure: {recipe['hook_mechanism_reference']}\n\n"
        f"New hook: {recipe['new_hook_draft_vi']}\n\n"
        f"Original operator hook (EVIDENCE ONLY): "
        f"{recipe['observed_original_hook_reference_only']}\n\n"
        f"Observed evidence: {json.dumps(recipe['evidence'],ensure_ascii=False,indent=2)}\n\n"
        "## Research source links\n\n"+source_links+"\n\n"
        "## Production storyboard\n\n"+slides+"\n\n"
        f"## Caption draft\n\n{recipe['new_caption_draft_vi']}\n\n"
        f"Proposed hashtags: {' '.join(recipe['proposed_hashtags'])}\n\n"
        f"Sound to source: {recipe['suggested_music_asset_id']}; rights NOT verified.\n\n"
        "## Do not publish before\n\n"+
        "\n".join(f"- [ ] {check}" for check in recipe["editorial_checks"])+"\n"
    )


def _summary_md(kit: dict[str, Any]) -> str:
    q = kit["quality"]
    return (
        "# Production Handoff — START HERE\n\n"
        f"Operator reference: {kit['operator_id']} "
        "(public posts, researcher-declared account grouping)\n\n"
        f"Source: {kit['source_post_count']} posts; "
        f"{kit['source_family_count']} family candidates; "
        f"{kit['source_account_count']} accounts.\n\n"
        f"Prepared: {q['recipes_generated']} recipes, {q['slides_drafted']} "
        f"slides/scenes, {q['calendar_slots']} planned posts and "
        f"{q['asset_candidates']} required asset candidates.\n\n"
        "## Team handoff order\n\n"
        "1. Read ACCOUNT_BLUEPRINTS.md and own the pilot account identities.\n"
        "2. Open CONTENT_PLAN.csv. Each slot points to one numbered recipe.\n"
        "3. Open briefs/REC-xxx.md for new overlay copy, per-slide visual "
        "directions, caption draft and source TikTok links.\n"
        "4. Work through ASSET_BANK.csv: photograph/create original images, "
        "document file and permission source, then verify TikTok-appropriate "
        "music rights. Pinterest references are NOT licensed assets.\n"
        "5. Record brand factual/claims review and any promotion disclosures. "
        "Only then mark a calendar slot ready in your own production tracker.\n"
        "6. Record your own post URLs, 24h/72h/7d metrics in "
        "OWN_RESULTS_TEMPLATE.csv. Re-export to get evidence-labelled learnings.\n\n"
        "## NON-NEGOTIABLE EVIDENCE LIMITS\n\n"
        "- The operator's internal test/scale workflow has NOT been proven.\n"
        "- The source hooks/media are references only; draft text must be "
        "fact-checked and edited in the team's own voice.\n"
        "- No asset here is automatically licensed, and no content is "
        "automatically marked ready to publish.\n"
        "- Publishing times/2-account pilot structure are proposed "
        "experiments, NOT statistically validated operator advice.\n"
        "- Individual historical high views do not predict your own outcomes.\n\n"
        f"Raw caption/music enrichment: {q['raw_enrichment']}. "
        f"Music references found: {len(kit['music_bank'])}; "
        f"team-attested assets: {q['assets_with_verified_rights']}.\n"
    )


def production_kit_artifacts(kit: dict[str, Any]) -> dict[str, bytes]:
    """All team files; stable path names, no external media or credentials."""
    audit = audit_production_kit(kit)
    if audit["status"] != "pass":
        raise ValueError("Invalid production kit: "+", ".join(audit["errors"][:12]))
    accounts_md = "# Original-account launch blueprint (proposals, not observed intent)\n\n"
    for a in kit["account_blueprints"]:
        accounts_md += (
            f"## {a['slot_id']}: {a['positioning']}\n\n"
            f"Audience: {a['audience']}\n\n"
            f"Handle pattern: {a['suggested_handle_pattern']}\n\n"
            f"Bio draft: {a['bio_draft']}\n\n"
            f"Avatar: {a['avatar_brief']}\n\n"
            f"Pilot cadence: {a['proposed_cadence']} at "
            f"{a['proposed_local_time']} {a['time_zone']} "
            "(UNVALIDATED EXPERIMENT TIME)\n\n"
            "Setup checklist:\n"+
            "\n".join(f"- [ ] {s}" for s in a["setup_checklist"])+
            "\n\nObserved reference accounts: "+
            ", ".join(str(s["handle"]) for s in a["source_account_observations"])+
            "\n\n"
        )
    result: dict[str, bytes] = {
        "START_HERE.md": _summary_md(kit).encode("utf-8"),
        "ACCOUNT_BLUEPRINTS.md": accounts_md.encode("utf-8"),
        "PRODUCTION.json": json.dumps(kit,ensure_ascii=False,indent=2,default=str).encode("utf-8"),
        "CONTENT_PLAN.csv": _csv_bytes(kit["calendar"], [
            "day", "slot_id", "pilot_account", "recipe_id", "family_id",
            "variant", "test_dimension", "hook_to_publish_draft_vi",
            "controlled_test", "stop_or_recheck",
            "planned_local_time", "timezone",
            "time_basis", "content_type", "work_status", "publish_gate",
            "tracking", "primary_metric", "secondary_metrics",
            "post_url", "owner", "asset_clearance",
        ]),
        "ASSET_BANK.csv": _csv_bytes(kit["asset_bank"], [
            "asset_id", "recipe_id", "kind", "role", "search_query",
            "reference_post_uid", "reference_post_url",
            "observed_sound_key", "file_or_licensed_source_url",
            "license_evidence_url", "license_scope", "rights_status",
            "production_status", "safe_to_publish", "verified_by", "note",
        ]),
        "SOUND_BANK.csv": _csv_bytes(kit["music_bank"], [
            "sound_key", "music_id", "music_name", "music_author",
            "observed_post_count", "source_post_uids", "source_urls",
            "license_status", "rights_scope", "usable_as_commercial_sound", "source",
        ]),
        "CAPTION_BANK.csv": _csv_bytes(kit.get("caption_bank", []), [
            "post_uid", "account", "url", "caption_reference_only",
            "views_percentile_account", "rights_scope",
        ]),
        "HASHTAG_BANK.csv": _csv_bytes(kit.get("hashtag_bank", []), [
            "hashtag", "observed_post_count", "example_post_uids",
            "usage_not_recommended_without_relevance_check",
        ]),
        "SOURCE_EVIDENCE.csv": _csv_bytes([
            {"recipe_id": r["recipe_id"], "family_id": r["family_id"],
             **p, "evidence_grade": r["evidence_grade"]}
            for r in kit["recipes"] for p in r["observed_source_posts"]
        ], [
            "recipe_id", "family_id", "post_uid", "account", "post_id", "url",
            "views", "account_relative_views_percentile", "saves",
            "created_at", "hook_reference", "evidence_grade",
            "observed_caption_reference_only", "observed_hashtags_reference_only",
        ]),
        "SUSPECTED_FALSE_SPLITS.csv": _csv_bytes(kit["suspected_false_splits"], [
            "family_a", "family_b", "post_a", "post_b", "url_a", "url_b",
            "accounts", "shared_hook_reference", "matching_sequence_roles",
            "shared_product_family", "finding", "validated_same_concept",
        ]),
        "ASSET_CLEARANCE_TEMPLATE.csv": _csv_bytes([], [
            "asset_id", "rights_status", "file_or_licensed_source_url",
            "license_evidence_url", "license_scope", "verified_by", "verified_at",
        ]),
        "OWN_RESULTS_TEMPLATE.csv": _csv_bytes([], [
            "recipe_id", "account_slot", "published_url", "posted_at",
            "measurement_age_hours", "views", "saves", "shares",
            "account_median_views", "notes",
        ]),
        "OWN_EXPERIMENT_RESULTS.csv": _csv_bytes(
            kit.get("own_experiment_outcomes", []), [
                "recipe_id", "account_slot", "published_url", "posted_at",
                "measurement_age_hours", "views", "saves", "shares",
                "account_median_views", "views_vs_account_median",
                "saves_per_view", "shares_per_view",
                "editorial_notes", "evidence_origin",
            ],
        ),
        "QUALITY_REPORT.json": json.dumps(audit, ensure_ascii=False, indent=2).encode("utf-8"),
        "LESSONS.md": (
            "# Evidence-bound lessons, not operator intent\n\n"+
            "\n\n".join(
                f"## {l['id']} ({l['kind']})\n\n"
                f"Observation: {l['statement']}\n\n"
                f"Trial: {l['action']}\n\n"
                f"Limit: {l['qualification']}\n\n"
                for l in kit["lessons"]
            )
        ).encode("utf-8"),
    }
    for recipe in kit["recipes"]:
        result[f"briefs/{recipe['recipe_id']}.md"] = _source_markdown(recipe).encode("utf-8")
    return result


def write_production_kit(
    kit: dict[str, Any],
    *,
    workspace: Path,
) -> dict[str, Any]:
    workspace.mkdir(parents=True, exist_ok=True)
    audit = audit_production_kit(kit)
    if audit["status"] != "pass":
        raise ValueError("Production Kit fails evidence quality gate: "+str(audit["errors"][:10]))
    artifacts = production_kit_artifacts(kit)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as package:
        for name, content in sorted(artifacts.items()):
            package.writestr(name, content)
    production = workspace / "production.json"
    handoff = workspace / "production-kit.zip"
    # Avoid partially writing the public entry-point JSON if package build fails.
    handoff.write_bytes(archive.getvalue())
    production.write_text(
        json.dumps(kit, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return {
        "workspace": str(workspace),
        "production_json": str(production),
        "handoff_zip": str(handoff),
        "handoff_bytes": len(archive.getvalue()),
        "entries": len(artifacts),
        "quality": audit,
    }
