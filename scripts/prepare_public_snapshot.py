"""Build a deterministic public-source ZIP without Git history or local evidence."""

from __future__ import annotations

import hashlib
import zipfile

from verify_distribution import ROOT, source_files, verify

from creative_research import __version__
from creative_research.infrastructure.storage import atomic_output


def main() -> None:
    verify()
    files = source_files()
    target = ROOT / "dist" / f"creative-research-{__version__}-public.zip"
    with atomic_output(target) as temporary:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, source in sorted(files.items()):
                entry = zipfile.ZipInfo(
                    f"creative-research-{__version__}/{name}", (2026, 1, 1, 0, 0, 0)
                )
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = 0o100644 << 16
                archive.writestr(entry, source.read_bytes())
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    print(f"Public source snapshot: {target.name} ({len(files)} files), SHA-256 {digest}")
    print(
        "No Git history or local data included. Pattern scan is not a full privacy/security guarantee."
    )


if __name__ == "__main__":
    main()
