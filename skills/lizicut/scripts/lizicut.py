#!/usr/bin/env python3
"""CLI entry for local, dependency-light Lizicut execution."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from render_media import ensure_output, inspect, render
from timeline import LizicutError, executable, read_json, read_srt, retime, run, validate, write_srt


def doctor() -> dict:
    programs = {name: shutil.which(name) for name in ("ffmpeg", "ffprobe")}
    filters = run([programs["ffmpeg"], "-hide_banner", "-filters"]) if programs["ffmpeg"] else ""
    encoders = run([programs["ffmpeg"], "-hide_banner", "-encoders"]) if programs["ffmpeg"] else ""
    capabilities = {"subtitle_burn": " ass " in filters, "audio_mix": " amix " in filters, "audio_limiter": " alimiter " in filters,
                    "overlay": " overlay " in filters, "alpha_fade": " fade " in filters and " colorchannelmixer " in filters,
                    "h264": "libx264" in encoders, "aac": " aac " in encoders}
    candidates = [Path("C:/Windows/Fonts/msyh.ttc"), Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"), Path("/System/Library/Fonts/PingFang.ttc")]
    return {"python": sys.version.split()[0], "programs": programs, "capabilities": capabilities,
            "cjk_font_candidates": [str(path) for path in candidates if path.is_file()],
            "render_ready": all(programs.values()) and all(capabilities.values()),
            "note": "No ASR, search, generation or paid provider is invoked. Verify the selected CJK font in actual frames."}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="inspect existing local tools; install nothing")
    check = sub.add_parser("validate", help="validate a prepared timeline")
    check.add_argument("timeline", type=Path)
    check.add_argument("--media", action="store_true", help="check actual inputs and source durations with ffprobe")
    build = sub.add_parser("render", help="assemble a final-ready timeline into MP4")
    build.add_argument("timeline", type=Path)
    build.add_argument("--output", required=True, type=Path)
    build.add_argument("--overwrite", action="store_true")
    build.add_argument("--threads", type=int, default=2)
    captions = sub.add_parser("retime-captions", help="map captions through kept source ranges; reject text crossing cuts")
    captions.add_argument("source", type=Path)
    captions.add_argument("cuts", type=Path)
    captions.add_argument("--output", type=Path, required=True)
    captions.add_argument("--overwrite", action="store_true")
    roughcut = sub.add_parser("roughcut", help="prepare synchronized edits from an evidence-backed source cut plan")
    roughcut.add_argument("plan", type=Path)
    roughcut.add_argument("--output-dir", required=True, type=Path)
    roughcut.add_argument("--render", action="store_true", help="also export MP4 for video or PCM WAV for audio")
    roughcut.add_argument("--threads", type=int, default=2)
    materials = sub.add_parser("materials", help="check or acquire reviewed candidates with source and rights records")
    materials.add_argument("plan", type=Path)
    materials.add_argument("--check", action="store_true", help="validate declarations only; create no files or network requests")
    materials.add_argument("--output-dir", type=Path)
    materials.add_argument("--download", action="store_true", help="allow plain HTTP(S) downloads of selected direct media URLs")
    materials.add_argument("--max-mb", type=int, default=128, help="per-file size limit; default 128 MiB")
    materials.add_argument("--timeout", type=int, default=20, help="per-file timeout in seconds; default 20")
    media = sub.add_parser("inspect", help="probe an actual exported video")
    media.add_argument("file", type=Path)
    media.add_argument("--decode", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            report = doctor()
        elif args.command in {"validate", "render"}:
            path = args.timeline.resolve()
            data = read_json(path)
            if args.command == "validate":
                warnings = validate(data, path.parent, media=args.media)
                report = {"valid": True, "media_checked": args.media, "warnings": warnings,
                          "boundary": "structure/source checks do not prove timing recognition or visual quality"}
            else:
                ensure_output(args.output, [path], args.overwrite)
                report = render(data, path.parent, args.output, overwrite=args.overwrite, threads=args.threads)
        elif args.command == "roughcut":
            from roughcut import prepare
            path = args.plan.resolve()
            report = prepare(read_json(path), path.parent, args.output_dir, render_now=args.render, threads=args.threads)
        elif args.command == "materials":
            from materials import acquire, check_plan
            path = args.plan.resolve()
            data = read_json(path)
            if args.check:
                report = check_plan(data)
            else:
                if args.output_dir is None:
                    raise LizicutError("materials: --output-dir is required unless using --check")
                report = acquire(data, path.parent, args.output_dir, allow_download=args.download, max_mb=args.max_mb, timeout=args.timeout)
        elif args.command == "retime-captions":
            ensure_output(args.output, [args.source, args.cuts], args.overwrite)
            cues = retime(read_srt(args.source), read_json(args.cuts))
            if not cues:
                raise LizicutError("No captions remain; check the cut plan before writing an empty subtitle file")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            write_srt(cues, args.output)
            report = {"output": str(args.output.resolve()), "cues": len(cues), "note": "Only captions were remapped; apply the same kept ranges to source audio/video."}
        else:
            report = inspect(args.file.resolve(), decode=args.decode)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2 if args.command == "materials" and report.get("ready") is False else 0
    except (LizicutError, OSError) as error:
        print(f"lizicut: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
