# Migration from an exploratory workspace

Do not rerun scraping, downloads, or Vision just to reorganize an existing research project.

Generic mapping:

| Existing artifact | Canonical location |
|---|---|
| raw scrape run(s) | `data/00_raw/apify/<run>/` |
| selected account subset | `data/01_selected/targets/` |
| local slideshow/cover media | `data/02_media/tiktok/` |
| slideshow manifest | `data/03_manifests/slides/` |
| downloaded video media | `data/03_video_media/` |
| slideshow Vision output | `data/04_vision/slides/` |
| video Vision output | `data/04_vision/videos/` |
| existing canonical master | `data/05_master/` |

Prefer regenerating the slideshow manifest after moving media because it is cheap and creates portable paths:

```bash
uv run creative-research manifest-slides \
  data/02_media/tiktok \
  --out data/03_manifests/slides
```

Use `creative-research adopt` to symlink existing expensive outputs:

```bash
uv run creative-research adopt \
  --selected /old/selected_accounts \
  --media /old/creative_media \
  --video-media /old/creative_videos \
  --slides-vision /old/slideshow_vision \
  --video-vision /old/video_vision \
  --apify run-001=/old/raw_snapshot_1 \
  --apify run-002=/old/raw_snapshot_2
```

Then:

```bash
uv run creative-research status
uv run creative-research build-master \
  --slides data/04_vision/slides/creative_study_v2.parquet \
  --videos data/04_vision/videos/creative_video_study.parquet \
  --out data/05_master
uv run creative-research validate
```

Old OCR, EDA, notebooks, temporary samples, and early script versions should stay outside this canonical repository.
