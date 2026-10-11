# Dataset contract

Schema: `creative-dataset-export-v1`. Export reads a capture folder
containing `posts/*.jsonl`; `normalized/posts.jsonl` is optional. Raw source fields
and types are preserved. Missing metrics remain null/absent, never invented zeroes.

| File | Contract |
| --- | --- |
| posts.jsonl | Unique platform/account/post ID; string post_uid/account_id/post_id; raw, metadata, source, content_type, media, media_status |
| posts.csv | UTF-8 BOM convenience columns; nested/raw fields live in JSONL |
| assets.jsonl | SHA-256 asset_id, hash, byte count, media type, relative path and source paths |
| missing_assets.jsonl | Post ID, media kind, slide index if relevant, missing/empty reason |
| manifest.json | Schema, export time, counts, capture provenance, completion and optional pipeline run/input fingerprints |
| checksums.sha256 | Every exported file except this checksum file |
| assets/images and assets/videos | Local bytes addressed by asset inventory |
| README.md | Consumer instructions included in every export |

Join media asset IDs to assets.jsonl; resolve asset.path against the extracted
folder. Slides retain original 1-based order, including positions sharing identical
image bytes. Identical files are deduplicated by SHA-256. Duplicate identical post
rows collapse; conflicting payloads fail rather than choosing a newer snapshot.
Identifiers in CSV must be imported as text to avoid rounding long TikTok IDs.
Post identifiers include account display casing; account identifiers are case-folded.

Capture provenance comes from run_info.json and includes actor, crawl timestamps,
requested accounts/settings and batch run/dataset IDs. Standalone inputs may
lack this metadata; manifest.capture is then null. source.file/source.record refer
to the input posts file and its 1-based nonblank row, not a dependency for reading.
The export contains one selected observation per post, not crawl history.

Export always retains posts with missing assets. media_status describes file
availability, not validity of the content, licensing or analytical quality.
Required media is inventoried using these rules:

| Kind | Required when |
| --- | --- |
| cover | Every exported post, including posts without a source cover URL |
| avatar | Raw authorMeta has avatar or originalAvatarUrl |
| video | content_type is video |
| slide | Each 1-based position in raw slideshowImageLinks for a slideshow |

A slideshow without source positions and without local slides gets a
no_slide_inventory entry. Other gap reasons are not_found and empty_file. In verified
mode, files absent from the current successful download inventory are excluded and
reported as missing; old bytes do not fill a failed refresh. media_status=complete
means these required file checks found no gaps, not that the media was decoded.

`validate` accepts inventoried missing assets and rejects corrupt files, unknown
references, unordered slides, inconsistent counts, unsafe paths and bad checksums.
Asset IDs must match their SHA-256 content checksum. When completion is present,
its capture value must match capture provenance and use a boolean or null; numeric
0/1 do not stand in for booleans.
The folder and ZIP contain the same files; ZIP64 supports large assets.

manifest.completion separates capture completeness and media availability. Missing
capture provenance gives manifest.capture=null, completion.capture=null and
completion.complete=false, even when all required media is present. With capture
provenance, completion.capture reflects recorded batch/provider success;
completion.media is true exactly when missing_assets is empty. Pipeline lineage
records run_id, capture_fingerprint and
inputs_fingerprint. A pipeline marks completed only after integrity validation and
complete capture/media; a valid partial dataset remains explicitly partial.
Export runs the validator on its staged folder before publishing. Verified mode
checks the download report's source fingerprint/file inventory and excludes old
unverified bytes retained after a failed refresh. Neither validation nor completion
proves live-provider accuracy or exhaustive account coverage. See the
[consumer guide](consume-dataset.md) for checksum checks and a JSONL/media join example.
