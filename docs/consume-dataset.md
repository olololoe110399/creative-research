# Consume a dataset

Receive the folder or extract the ZIP, then open its included README.md. The ZIP
contains a top-level dataset directory; use that directory as the dataset root.
Reading the handoff requires no source checkout, Apify token or original run folder.
Use packaged files instead of remote media URLs, which can expire.

## Check integrity and completeness

From the extracted dataset directory, verify file checksums:

```sh
# macOS
shasum -a 256 -c checksums.sha256
# Linux
sha256sum -c checksums.sha256
```

If the CLI is installed, it also checks schema, references, counts and safe paths:

```sh
creative-research validate --dataset exports/dataset-001 --json
```

Replace the example path with the extracted dataset directory. Checksums detect
changed bytes; validation checks the package contract. Neither proves that source
metadata is correct, media decodes successfully or the provider returned every post.

Read manifest.json before processing:

| Field | Meaning |
| --- | --- |
| schema_version | Must be creative-dataset-export-v1 for this contract |
| completion.capture | true when the recorded acquisition succeeded without recorded batch/provider errors; false when incomplete; null without capture provenance |
| completion.media | true when no required assets are inventoried as missing |
| completion.complete | true only when both capture and media are true |
| counts.posts / counts.unique_assets | Exported posts and deduplicated local files |
| counts.missing_assets | Number of missing asset entries, not missing posts |

A valid package can be partial. Keep missing_assets.jsonl and incomplete posts when
importing; decide explicitly whether your downstream job can accept those gaps.
Exports with capture=null have unknown acquisition completeness, even when
all required media is present. A completed acquisition describes the requested
sample and filters, not an exhaustive history of an account.

## Read posts and local media

posts.jsonl contains one JSON object per exported post. Envelope IDs are strings;
preserve post_id, post_uid and account_id as text. raw retains original provider
fields and types; metadata contains normalized fields. Use JSONL for full payloads.
The CSV is a convenience view; spreadsheet numeric conversion can round TikTok IDs.
Missing source metrics remain absent or null, so do not silently turn them into zero.

Join media asset IDs to assets.jsonl and resolve each asset.path relative to the
dataset root. The cover/avatar/video lists contain IDs; slides contain index and
asset_id pairs in original 1-based order. Two slide positions may share one asset.
Deduplicated files do not imply duplicated posts or removable slide positions.

This Python 3.11+ example uses only the standard library:

```python
import json
from pathlib import Path

root = Path("exports/dataset-001").resolve()

def records(name):
    with (root / name).open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)

assets = {asset["asset_id"]: asset for asset in records("assets.jsonl")}

def asset_path(asset_id):
    path = (root / assets[asset_id]["path"]).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Asset path escapes dataset root")
    return path

for post in records("posts.jsonl"):
    print(post["post_uid"], post["post_id"], post["media_status"])
    for kind in ("covers", "avatars", "videos"):
        for asset_id in post["media"][kind]:
            print(kind, asset_path(asset_id))
    for slide in post["media"]["slides"]:
        print("slide", slide["index"], asset_path(slide["asset_id"]))
```

source.file/source.record and asset.source_paths describe original input locations;
they are provenance labels, not files the recipient must fetch. The package contains
valid post records and capture provenance, not complete provider batch/error logs.
Those logs remain in the producer's raw archive; recorded error counts are available
in manifest.capture. This is one selected observation per post, with no metric
history or generated interpretation. See the [dataset contract](dataset-contract.md)
for compatibility requirements and the [capture workflow](capture-workflow.md) for
producer handoff paths.
