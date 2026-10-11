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
        "run",
        "Run or resume capture, download, export and validation",
        "Capture & export",
        "creative_research.cli.commands.run",
    ),
    CommandSpec(
        "scrape",
        "Capture public TikTok records through Apify",
        "Capture & export",
        "creative_research.cli.commands.scrape",
    ),
    CommandSpec(
        "download-media",
        "Download videos, slides, covers and avatars",
        "Capture & export",
        "creative_research.cli.commands.download_media",
    ),
    CommandSpec(
        "export-dataset",
        "Package source records and local media as a portable dataset",
        "Capture & export",
        "creative_research.cli.commands.export_dataset",
    ),
    CommandSpec("init", "Create capture workspace directories", "Project utilities"),
    CommandSpec("doctor", "Check capture/download dependencies", "Project utilities"),
    CommandSpec("status", "Summarize crawl, media and dataset files", "Project utilities"),
    CommandSpec(
        "validate", "Verify exported dataset records, assets and checksums", "Project utilities"
    ),
)
COMMANDS = MappingProxyType(
    {spec.name: spec.module for spec in COMMAND_SPECS if spec.module is not None}
)
