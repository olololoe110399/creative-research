#!/usr/bin/env python3
"""Download all non-slideshow TikTok posts from creative_media.

Primary downloader: yt-dlp. Optional ffprobe adds duration/resolution metadata.
The script is resumable: existing video files are skipped.

Install:
  python -m pip install -U yt-dlp pandas

Run:
  python download_video_posts.py creative_media --out creative_videos

If TikTok requires login/cookies:
  python download_video_posts.py creative_media --out creative_videos \
    --cookies-from-browser chrome
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

import pandas as pd

from creative_research.pathing import portable_path

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}



def read_json(path: Path) -> dict[str, Any]:
    try:
        x = json.loads(path.read_text(encoding="utf-8"))
        return x if isinstance(x, dict) else {}
    except Exception:
        return {}


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def append_jsonl(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")
        f.flush(); os.fsync(f.fileno())


def first(*vals: Any) -> Any:
    for v in vals:
        if v is not None and v != "":
            return v
    return None


def recursively_find_post_url(*objs: Any) -> str | None:
    stack = list(objs)
    while stack:
        v = stack.pop()
        if isinstance(v, dict):
            stack.extend(v.values())
        elif isinstance(v, list):
            stack.extend(v)
        elif isinstance(v, str):
            low = v.lower()
            if "tiktok.com" in low and ("/video/" in low or "/photo/" in low or "/v/" in low):
                return v
    return None


def direct_video_urls(obj: Any) -> list[str]:
    out: list[str] = []
    def walk(v: Any, key: str = "") -> None:
        if isinstance(v, dict):
            for k, x in v.items(): walk(x, str(k).lower())
        elif isinstance(v, list):
            for x in v: walk(x, key)
        elif isinstance(v, str) and v.startswith(("http://", "https://")):
            low = v.lower().split("?")[0]
            if any(low.endswith(ext) for ext in IMAGE_EXTS): return
            key_ok = any(t in key for t in ("video", "play", "download", "playaddr", "downloadaddr"))
            url_ok = any(t in v.lower() for t in (".mp4", "video/tos", "v16-webapp", "v19-webapp", "mime_type=video"))
            if (key_ok or url_ok) and "tiktok.com/@" not in v.lower(): out.append(v)
    walk(obj)
    return list(dict.fromkeys(out))


def is_slideshow(meta: dict[str, Any], raw: dict[str, Any], post_dir: Path) -> bool:
    x = meta.get("is_slideshow")
    if x is None: x = raw.get("isSlideshow")
    if x is not None: return bool(x)
    return bool(list(post_dir.glob("slide_*.*")))


def existing_video(post_out: Path) -> Path | None:
    if not post_out.exists(): return None
    xs = [p for p in post_out.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS]
    return max(xs, key=lambda p: p.stat().st_size) if xs else None


def ytdlp_prefix() -> list[str]:
    exe = shutil.which("yt-dlp")
    return [exe] if exe else [sys.executable, "-m", "yt_dlp"]


def download_ytdlp(url: str, out_dir: Path, browser: str | None, cookies: str | None) -> tuple[Path | None, str | None]:
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = ytdlp_prefix()
    if browser: cmd += ["--cookies-from-browser", browser]
    if cookies: cmd += ["--cookies", cookies]
    cmd += [
        "--no-playlist", "--no-overwrites", "--retries", "5", "--fragment-retries", "5",
        "--socket-timeout", "30", "--restrict-filenames", "-f", "best[ext=mp4]/best",
        "-o", str(out_dir / "video.%(ext)s"), url,
    ]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    video = existing_video(out_dir)
    if p.returncode == 0 and video: return video, None
    return video, (p.stdout or f"yt-dlp exit {p.returncode}")[-5000:]


def download_direct(urls: list[str], out_dir: Path) -> tuple[Path | None, str | None]:
    errs = []
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, url in enumerate(urls[:8], 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 AppleWebKit/537.36 Chrome/130 Safari/537.36",
                "Referer": "https://www.tiktok.com/",
            })
            with urllib.request.urlopen(req, timeout=45) as r:
                ct = (r.headers.get("Content-Type") or "").lower().split(";")[0]
                if "video" not in ct and "octet-stream" not in ct:
                    errs.append(f"{i}: content-type {ct}"); continue
                ext = mimetypes.guess_extension(ct) or ".mp4"
                if ext not in VIDEO_EXTS: ext = ".mp4"
                target = out_dir / f"video{ext}"
                tmp = Path(str(target) + ".part")
                with tmp.open("wb") as f: shutil.copyfileobj(r, f)
                if tmp.stat().st_size < 20000:
                    errs.append(f"{i}: too small"); tmp.unlink(missing_ok=True); continue
                tmp.replace(target)
                return target, None
        except Exception as e:
            errs.append(f"{i}: {type(e).__name__}: {e}")
    return None, " | ".join(errs[-5:])


def ffprobe(path: Path) -> dict[str, Any]:
    exe = shutil.which("ffprobe")
    if not exe: return {}
    cmd = [exe, "-v", "error", "-show_entries",
           "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate",
           "-of", "json", str(path)]
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
        if p.returncode: return {}
        d = json.loads(p.stdout); out: dict[str, Any] = {}; fmt = d.get("format") or {}
        if fmt.get("duration") is not None: out["duration_seconds"] = float(fmt["duration"])
        if fmt.get("size") is not None: out["file_size_bytes"] = int(fmt["size"])
        for s in d.get("streams") or []:
            if s.get("codec_type") == "video":
                out.update(video_codec=s.get("codec_name"), width=s.get("width"), height=s.get("height"))
                fps = s.get("r_frame_rate")
                if isinstance(fps, str) and "/" in fps:
                    try:
                        a,b = fps.split("/",1); out["fps"] = float(a)/float(b) if float(b) else None
                    except Exception: pass
            elif s.get("codec_type") == "audio":
                out.update(has_audio=True, audio_codec=s.get("codec_name"))
        out.setdefault("has_audio", False)
        return out
    except Exception:
        return {}


def discover(root: Path) -> list[dict[str, Any]]:
    rows = []
    for ad in sorted(p for p in root.iterdir() if p.is_dir()):
        for pdx in sorted(ad.iterdir()):
            if not pdx.is_dir() or pdx.name == "profile": continue
            meta, raw = read_json(pdx/"meta.json"), read_json(pdx/"raw.json")
            if not meta and not raw: continue
            if is_slideshow(meta, raw, pdx): continue
            post_id = str(first(meta.get("post_id"), raw.get("id"), raw.get("idStr"), pdx.name))
            url = first(meta.get("url"), raw.get("webVideoUrl"), raw.get("url"), recursively_find_post_url(meta, raw))
            rows.append({
                "account": ad.name, "post_id": post_id, "source_post_dir": portable_path(pdx), "url": url,
                "created_at": first(meta.get("created_at"), raw.get("createTimeISO")),
                "views": first(meta.get("views"), raw.get("playCount")),
                "likes": first(meta.get("likes"), raw.get("diggCount")),
                "comments": first(meta.get("comments"), raw.get("commentCount")),
                "shares": first(meta.get("shares"), raw.get("shareCount")),
                "saves": first(meta.get("saves"), raw.get("collectCount")),
                "_meta": meta, "_raw": raw,
            })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--out", default="creative_videos")
    ap.add_argument("--cookies-from-browser", default=None)
    ap.add_argument("--cookies-file", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-direct-fallback", action="store_true")
    args = ap.parse_args()

    root, out = Path(args.input).expanduser().resolve(), Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    items = discover(root)
    if args.limit is not None: items = items[:args.limit]
    rows, failures = [], []

    for i, item in enumerate(items, 1):
        account, post_id = item["account"], item["post_id"]
        post_out = out/account/post_id; post_out.mkdir(parents=True, exist_ok=True)
        video = existing_video(post_out)
        method = "cached" if video and not args.force else None
        if method:
            print(f"[{i}/{len(items)}] cached @{account}/{post_id}")
        else:
            if args.force and video: video.unlink(missing_ok=True)
            video = None; errors = []
            print(f"[{i}/{len(items)}] download @{account}/{post_id}")
            if item.get("url"):
                video, err = download_ytdlp(item["url"], post_out, args.cookies_from_browser, args.cookies_file)
                if video: method = "yt-dlp"
                elif err: errors.append("yt-dlp: " + err)
            else: errors.append("No TikTok post URL found")
            if video is None and not args.no_direct_fallback:
                video, err = download_direct(direct_video_urls(item["_raw"]), post_out)
                if video: method = "direct_raw_url"
                elif err: errors.append("direct: " + err)
            if video is None:
                fail = {"account":account,"post_id":post_id,"url":item.get("url"),"error":"\n".join(errors)[-6000:]}
                failures.append(fail); append_jsonl(out/"failures.jsonl", fail); print("  FAILED"); continue

        probe = ffprobe(video)
        row = {k:v for k,v in item.items() if not k.startswith("_")}
        row.update({"video_path":portable_path(video),"download_method":method,
                    "file_size_bytes":probe.get("file_size_bytes",video.stat().st_size),
                    "duration_seconds":probe.get("duration_seconds"),"width":probe.get("width"),
                    "height":probe.get("height"),"fps":probe.get("fps"),"video_codec":probe.get("video_codec"),
                    "has_audio":probe.get("has_audio"),"audio_codec":probe.get("audio_codec")})
        write_json(post_out/"source_meta.json", {"manifest":row,"meta":item["_meta"],"raw":item["_raw"]})
        rows.append(row)

    df = pd.DataFrame(rows)
    if not df.empty:
        for c in ["views","likes","comments","shares","saves","duration_seconds","file_size_bytes"]:
            if c in df: df[c] = pd.to_numeric(df[c], errors="coerce")
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce", utc=True)
        df["share_rate"] = df["shares"] / df["views"].replace(0, pd.NA)
        df["save_rate"] = df["saves"] / df["views"].replace(0, pd.NA)
        df["account_views_pct"] = df.groupby("account")["views"].rank(pct=True, method="average")
        df["global_views_pct"] = df["views"].rank(pct=True, method="average")
    df.to_csv(out/"video_manifest.csv", index=False, encoding="utf-8-sig")
    with (out/"video_manifest.jsonl").open("w", encoding="utf-8") as f:
        for r in df.to_dict(orient="records"):
            if hasattr(r.get("created_at"), "isoformat"): r["created_at"] = r["created_at"].isoformat()
            f.write(json.dumps(r, ensure_ascii=False, default=str)+"\n")
    report = {"discovered_video_posts":len(items),"downloaded_or_cached":len(rows),"failed":len(failures),
              "total_bytes":int(pd.to_numeric(df.get("file_size_bytes",pd.Series(dtype=float)),errors="coerce").fillna(0).sum()) if not df.empty else 0,
              "duration_seconds_total":float(pd.to_numeric(df.get("duration_seconds",pd.Series(dtype=float)),errors="coerce").fillna(0).sum()) if not df.empty else 0.0,
              "download_methods":{str(k):int(v) for k,v in df["download_method"].value_counts().to_dict().items()} if not df.empty else {}}
    write_json(out/"report.json", report)
    print("\nDONE\n"+json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__": main()
