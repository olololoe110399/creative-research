"""Single source of truth for command discovery and stage dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class CommandSpec:
    name: str
    description: str
    group: str
    module: str | None = None


COMMAND_SPECS = (
    CommandSpec(
        "operator-setup",
        "Confirm operator/account grouping once, before scraping",
        "Capture & interpret",
        "creative_research.cli.commands.operator_setup",
    ),
    CommandSpec(
        "scrape",
        "Apify TikTok profile scrape (confirmed grouping required)",
        "Capture & interpret",
        "creative_research.cli.commands.scrape",
    ),
    CommandSpec(
        "select-accounts",
        "Merge scrape runs and keep selected accounts",
        "Capture & interpret",
        "creative_research.cli.commands.select_accounts",
    ),
    CommandSpec(
        "prepare-media",
        "Archive TikTok covers/slides/avatars locally",
        "Capture & interpret",
        "creative_research.cli.commands.prepare_media",
    ),
    CommandSpec(
        "manifest-slides",
        "Build manifest for all slideshow posts",
        "Capture & interpret",
        "creative_research.cli.commands.manifest_slides",
    ),
    CommandSpec(
        "vision-slides",
        "Gemini Vision analysis for slideshow posts (schema v2)",
        "Capture & interpret",
        "creative_research.cli.commands.vision_slides",
    ),
    CommandSpec(
        "download-videos",
        "Download all non-slideshow TikTok videos + manifest",
        "Capture & interpret",
        "creative_research.cli.commands.download_videos",
    ),
    CommandSpec(
        "vision-videos",
        "Gemini analysis for full videos",
        "Capture & interpret",
        "creative_research.cli.commands.vision_videos",
    ),
    CommandSpec(
        "build-master",
        "Merge slideshow + video Vision datasets",
        "Capture & interpret",
        "creative_research.cli.commands.build_master",
    ),
    CommandSpec(
        "build-warehouse",
        "Backfill operator-aware canonical tables from creative_master",
        "Analyze & infer",
        "creative_research.cli.commands.build_warehouse",
    ),
    CommandSpec(
        "analyze-performance",
        "Build account/operator relative performance baselines",
        "Analyze & infer",
        "creative_research.cli.commands.analyze_performance",
    ),
    CommandSpec(
        "analyze-cadence",
        "Build account/operator historical posting cadence",
        "Analyze & infer",
        "creative_research.cli.commands.analyze_cadence",
    ),
    CommandSpec(
        "build-families",
        "Group repeated creative concepts with auditable similarity evidence",
        "Analyze & infer",
        "creative_research.cli.commands.build_families",
    ),
    CommandSpec(
        "calibrate-families",
        "Measure family similarity/threshold behavior without changing families",
        "Analyze & infer",
        "creative_research.cli.commands.calibrate_families",
    ),
    CommandSpec(
        "preview-families-v2",
        "Inspect language-aware family clustering before publishing outputs",
        "Analyze & infer",
        "creative_research.cli.commands.preview_families_v2",
    ),
    CommandSpec(
        "judge-family-candidates",
        "AI-judge ambiguous family pairs with cache/budget guards",
        "Analyze & infer",
        "creative_research.cli.commands.judge_family_candidates",
    ),
    CommandSpec(
        "analyze-propagation",
        "Track family movement across verified operator accounts",
        "Analyze & infer",
        "creative_research.cli.commands.analyze_propagation",
    ),
    CommandSpec(
        "analyze-timeline",
        "Build historical strategy windows + change points",
        "Analyze & infer",
        "creative_research.cli.commands.analyze_timeline",
    ),
    CommandSpec(
        "discover-patterns",
        "Discover deterministic evidence-backed recurring patterns",
        "Analyze & infer",
        "creative_research.cli.commands.discover_patterns",
    ),
    CommandSpec(
        "infer-strategies",
        "Promote patterns into reviewable strategy hypotheses",
        "Analyze & infer",
        "creative_research.cli.commands.infer_strategies",
    ),
    CommandSpec(
        "promote-knowledge",
        "Build strategies/rules/lessons/templates/playbooks bank",
        "Analyze & infer",
        "creative_research.cli.commands.promote_knowledge",
    ),
    CommandSpec(
        "intelligence-build",
        "Build/reuse the full deterministic intelligence pipeline",
        "Build & inspect",
        "creative_research.cli.commands.intelligence_build",
    ),
    CommandSpec(
        "build-intelligence-workspace",
        "Build static operator intelligence workspace",
        "Build & inspect",
        "creative_research.cli.commands.build_intelligence_workspace",
    ),
    CommandSpec(
        "production-kit",
        "Export content recipes, account blueprint, assets and team handoff ZIP",
        "Build & inspect",
        "creative_research.cli.commands.production_kit",
    ),
    CommandSpec(
        "review-knowledge",
        "Build/apply a prioritized human review queue",
        "Build & inspect",
        "creative_research.cli.commands.review_knowledge",
    ),
    CommandSpec(
        "quality-audit",
        "Audit coverage, freshness, integrity, lineage, and trust status",
        "Build & inspect",
        "creative_research.cli.commands.quality_audit",
    ),
    CommandSpec(
        "outcome-audit",
        "Validate research brief, role flows, playbook and trust boundaries",
        "Build & inspect",
        "creative_research.cli.commands.outcome_audit",
    ),
    CommandSpec(
        "rank-posts",
        "Rank master posts for reference selection",
        "Build & inspect",
        "creative_research.cli.commands.rank_posts",
    ),
    CommandSpec(
        "extract-references",
        "Build whole-system map + representative reference workspace",
        "Build & inspect",
        "creative_research.cli.commands.extract_references",
    ),
    CommandSpec(
        "query",
        "Filter normalized creative tables without ad-hoc Pandas",
        "Build & inspect",
        "creative_research.cli.commands.query",
    ),
    CommandSpec(
        "group-references",
        "Build descriptive candidate groups from a reference pack",
        "Build & inspect",
        "creative_research.cli.commands.group_references",
    ),
    CommandSpec(
        "lab",
        "Serve the generated Operator Intelligence Lab",
        "Local workspaces",
        "creative_research.cli.commands.lab",
    ),
    CommandSpec(
        "references",
        "Serve a generated system/reference workspace locally",
        "Local workspaces",
        "creative_research.cli.commands.references",
    ),
    CommandSpec("init", "Create canonical workspace directories", "Project utilities"),
    CommandSpec(
        "demo",
        "Build a synthetic offline example in a new directory",
        "Project utilities",
        "creative_research.cli.commands.demo",
    ),
    CommandSpec(
        "doctor", "Check environment, binaries, and Python dependencies", "Project utilities"
    ),
    CommandSpec("status", "Summarize known pipeline outputs", "Project utilities"),
    CommandSpec("validate", "Validate creative_master schema and invariants", "Project utilities"),
    CommandSpec(
        "adopt", "Link/copy existing completed outputs into canonical paths", "Project utilities"
    ),
)
COMMANDS = MappingProxyType(
    {spec.name: spec.module for spec in COMMAND_SPECS if spec.module is not None}
)
