"""Prepare self-authored inputs for the real Premiere MCP worked example.

This builds source media, not a final edit or a .prproj. The agent makes the
actual edit in Premiere. Uses existing example voice and installed FFmpeg only.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("Installed FFmpeg is needed to prepare the input fixture")
    example = ROOT / "examples/premiere-workflow"
    media = example / "media"
    media.mkdir(parents=True, exist_ok=True)
    voice = ROOT / "examples/revenue-profit/assets"

    def run(arguments: list[str]) -> None:
        result = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-n", *arguments],
                                capture_output=True, text=True, encoding="utf-8")
        if result.returncode:
            raise RuntimeError(f"Premiere fixture generation failed: {result.stderr.strip()}")

    source = media / "source.mov"
    if not source.exists():
        # Explicitly authored duplicate for source-range execution verification;
        # not a test of natural human retakes, breathing, or lip sync.
        audio = (
            "[1:a]aresample=48000,apad,atrim=end_sample=172800,asetpts=PTS-STARTPTS,asplit=2[a][b];"
            "[b]volume=0.28[bq];"
            "[2:a]aresample=48000,apad,atrim=end_sample=276480,asetpts=PTS-STARTPTS[c];"
            "[a][bq][c]concat=n=3:v=0:a=1[outa]"
        )
        run(["-f", "lavfi", "-i", "color=c=0x20221f:s=1280x720:r=25:d=12.96",
             "-i", str(voice / "contrast-1.wav"), "-i", str(voice / "contrast-2.wav"),
             "-filter_complex", audio, "-map", "0:v", "-map", "[outa]",
             "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p",
             "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", "-t", "12.96", str(source)])

    music = media / "music.wav"
    if not music.exists():
        run(["-f", "lavfi", "-i", "aevalsrc=0.025*sin(2*PI*110*t)+0.012*sin(2*PI*165*t):s=48000:d=9.36",
             "-c:a", "pcm_s16le", "-ac", "2", str(music)])

    captions = example / "captions.srt"
    if not captions.exists():
        captions.write_text("1\n00:00:00,000 --> 00:00:03,412\n营收增长了，利润却下降了。\n\n"
                            "2\n00:00:03,600 --> 00:00:08,584\n看懂这个反差，先把几个数字放在同一张板上。\n", encoding="utf-8")
    print(json.dumps({"source": str(source), "source_seconds": 12.96,
                      "source_kept_seconds": [[0, 3.6], [7.2, 12.96]], "edit_seconds": 9.36,
                      "boundary": "authored input fixture only; final edit must be made in Premiere"},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
