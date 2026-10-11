# Architecture

The package owns acquisition, local file archives and portable dataset publication.
It has no content interpretation, research pipeline or browser server.

- `cli/app.py` owns configuration and exit/error handling. `cli/registry.py` is the
  command catalog; `cli/commands/` parses arguments and presents results.
- `capture/scrape.py` calls Apify and retains raw batches and normalized records;
  it leaves media acquisition to the download stage.
- `capture/pipeline.py` coordinates capture/download/export/validation and owns
  versioned run checkpoints. `run` uses separate raw/media/dataset paths per run,
  skips completed crawl batches and resumes provider runs using their saved IDs.
- `capture/cache.py` binds cached bytes to source fingerprints and SHA-256.
- `capture/normalization.py` translates provider field names without inference or
  importing a provider SDK. Stable identifiers live in `identity.py`.
- `capture/download.py` coordinates image/video archiving. `media.py` handles
  bounded image requests and checkpoints; `videos.py` wraps yt-dlp/direct fallback
  and optional ffprobe. Manifests contain source/file metadata only.
- `capture/export_dataset.py` packages a snapshot without requests or source writes.
  `capture/contracts.py` declares the dataset schema; `validation.py` checks its
  inventories, references, relative paths and checksums offline.
- `infrastructure/` owns explicit environment parsing, paths, logging, atomic file
  publication, a process writer lock and workspace diagnostics.

CLI calls capture workflows; capture calls shared infrastructure. Business modules
must not import CLI or argparse. Imports never load environment files, make requests
or write files. No database or frontend runtime is required.

Files publish through sibling temporary files and replace. Export stages the whole
folder and optional ZIP before publication; caught failures roll back new outputs.
Folder/ZIP publication is not a crash-atomic transaction. Pipeline checkpoints let
resume validate a published folder and recover its missing ZIP before completion.
Acquisition/export entrypoints enforce one writer per project using OS file locks.
Local data and private configuration remain outside distribution allowlists.
