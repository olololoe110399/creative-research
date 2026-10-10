"""Shared file contracts for the offline intelligence pipeline and its workspace."""

from __future__ import annotations

from types import MappingProxyType

DEFAULT_WORKSPACE = "data/07_exports/operator-intelligence"
WORKSPACE_SCHEMA_VERSION = "operator-intelligence-lab-v3"
STATIC_FILES = (
    "index.html",
    "app.js",
    "product_ui.js",
    "research_ui.js",
    "operating_ui.js",
    "production_ui.js",
    "style.css",
    "favicon.svg",
)
REQUIRED_DATA_FILES = (
    "workspace.json",
    "overview.json",
    "accounts.json",
    "timeline.json",
    "families.json",
    "patterns.json",
    "strategies.json",
    "knowledge.json",
    "evidence.json",
    "lab.json",
    "production.json",
    "production-kit.zip",
)
WORKSPACE_INPUTS = MappingProxyType(
    {
        "operators": "data/05_master/operators.parquet",
        "accounts": "data/05_master/accounts.parquet",
        "posts": "data/05_master/posts.parquet",
        "creative_analysis": "data/05_master/creative_analysis.parquet",
        "creative_sequence": "data/05_master/creative_sequence.parquet",
        "performance": "data/06_analytics/post_performance.parquet",
        "account_baselines": "data/06_analytics/account_performance_baselines.parquet",
        "account_cadence": "data/06_analytics/account_cadence_summary.parquet",
        "role_evidence": "data/06_analytics/account_role_evidence.parquet",
        "strategy_windows": "data/06_analytics/strategy_windows.parquet",
        "strategy_changes": "data/06_analytics/strategy_change_points.parquet",
        "families": "data/06_analytics/creative_families.parquet",
        "family_members": "data/06_analytics/creative_family_members.parquet",
        "propagation": "data/06_analytics/cross_account_propagation.parquet",
        "patterns": "data/06_analytics/patterns.parquet",
        "pattern_evidence_links": "data/06_analytics/pattern_evidence_links.parquet",
        "strategies": "data/06_analytics/strategy_hypotheses.parquet",
        "strategy_pattern_links": "data/06_analytics/strategy_pattern_links.parquet",
        "strategy_evidence_links": "data/06_analytics/strategy_evidence_links.parquet",
        "knowledge": "data/07_knowledge/knowledge_catalog.parquet",
        "knowledge_source_links": "data/07_knowledge/knowledge_source_links.parquet",
        "knowledge_evidence_links": "data/07_knowledge/knowledge_evidence_links.parquet",
    }
)
OUTCOME_INPUTS = MappingProxyType(
    {
        "lab": "lab.json",
        "families": "families.json",
        "strategies": "strategies.json",
        "knowledge": "knowledge.json",
        "evidence": "evidence.json",
    }
)
