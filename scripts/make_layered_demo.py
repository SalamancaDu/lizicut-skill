"""Rebuild a portrait example using original layers and existing demo narration."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/lizicut/scripts"))
from render_media import render
from timeline import LizicutError, executable, read_json, run, write_srt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", type=Path, default=Path("C:/Windows/Fonts/msyh.ttc"))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if not args.font.is_file():
        raise LizicutError("Pass --font with an existing CJK font; no font is installed or bundled")
    example = ROOT / "examples/layered-edit"
    assets = example / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    original = read_json(ROOT / "examples/revenue-profit/timeline.json")
    tracks = original["audio"][:2]
    # Measured sentence audio is reused unchanged; no new voice or provider call.
    for track in tracks:
        path = ROOT / "examples/revenue-profit" / original["assets"][track["asset_id"]]["path"]
        if not path.is_file():
            raise LizicutError(f"Missing supplied demo narration: {path}")
    ffmpeg = executable("ffmpeg")
    common = [ffmpeg, "-hide_banner", "-v", "error", "-nostdin", "-y", "-filter_threads", "1"]
    with tempfile.TemporaryDirectory(prefix=".lizicut-layers-", dir=example) as folder:
        work = Path(folder)
        shutil.copyfile(args.font, work / "font.ttc")

        def png(name: str, width: int, height: int, text_lines: list[tuple[str, int, int, int, str]], extra: list[str] | None = None):
            # drawbox must replace alpha as well as RGB on a transparent canvas.
            filters = [item + ":replace=1" if item.startswith("drawbox=") else item for item in (extra or [])]
            for index, (content, x, y, size, color) in enumerate(text_lines):
                filename = f"{name}-{index}.txt"
                (work / filename).write_text(content, encoding="utf-8")
                filters.append(f"drawtext=fontfile=font.ttc:textfile={filename}:expansion=none:x={x}:y={y}:fontsize={size}:fontcolor={color}")
            run([*common, "-f", "lavfi", "-i", f"color=c=black@0:s={width}x{height},format=rgba", "-vf", ",".join(filters), "-frames:v", "1", "-c:v", "png", "-threads", "1", str(assets / f"{name}.png")], cwd=work)

        png("title", 656, 176, [("营收涨了", 0, 0, 62, "0xf1eee3"), ("利润为什么反而下降？", 0, 86, 42, "0xf1eee3")])
        png("contrast", 656, 260, [("营收", 22, 24, 30, "0xa2a99c"), ("+20%", 22, 92, 84, "0x60c7ac"), ("利润", 365, 24, 30, "0xa2a99c"), ("−40%", 365, 92, 84, "0xe89578")], ["drawbox=x=326:y=24:w=2:h=200:color=0x50554a:t=fill"])
        png("context", 656, 96, [("虚构数据 · 不对应真实公司", 0, 0, 25, "0xa2a99c"), ("分层编排示例 / LIZICUT", 0, 44, 23, "0xa2a99c")])
        png("relation", 656, 100, [("先把两期放在同一尺度", 0, 0, 39, "0x60c7ac"), ("成本与利润相加，构成演示营收", 0, 58, 27, "0xa2a99c")])
        # A transparent original object marker, independent from the type layer.
        png("marker", 320, 120, [("同一家演示公司", 92, 42, 28, "0xa2a99c")], ["drawbox=x=8:y=12:w=60:h=88:color=0x60c7ac:t=3", "drawbox=x=24:y=32:w=28:h=4:color=0x60c7ac:t=fill", "drawbox=x=24:y=52:w=28:h=4:color=0x60c7ac:t=fill", "drawbox=x=24:y=72:w=28:h=4:color=0x60c7ac:t=fill"])
        png("comparison-card", 656, 420, [("上一期 · 营收100万", 0, 0, 32, "0xf1eee3"), ("成本80", 0, 120, 30, "0xa2a99c"), ("利润20", 336, 120, 30, "0x60c7ac"), ("100", 438, 64, 32, "0xf1eee3"), ("这一期 · 营收120万", 0, 210, 32, "0xf1eee3"), ("成本108", 0, 330, 30, "0xa2a99c"), ("利润12", 454, 330, 30, "0x60c7ac"), ("120", 520, 274, 32, "0xf1eee3")], ["drawbox=x=0:y=60:w=336:h=44:color=0x7e867a:t=fill", "drawbox=x=336:y=60:w=84:h=44:color=0x60c7ac:t=fill", "drawbox=x=0:y=270:w=454:h=44:color=0x7e867a:t=fill", "drawbox=x=454:y=270:w=50:h=44:color=0x60c7ac:t=fill"])
        run([*common, "-f", "lavfi", "-i", "color=c=0x20221f:s=720x1280:r=25:d=2", "-vf", "drawgrid=w=80:h=80:t=1:c=0xffffff@0.035", "-an", "-c:v", "libx264", "-threads", "2", str(assets / "background.mp4")], cwd=work)
        run([*common, "-f", "lavfi", "-i", "sine=frequency=220:duration=2:sample_rate=48000", "-af", "afade=t=in:d=0.04,afade=t=out:st=1.96:d=0.04", str(assets / "music.wav")], cwd=work)
        run([*common, "-loop", "1", "-framerate", "25", "-i", str(assets / "comparison-card.png"), "-t", "8", "-vf", "format=yuv420p", "-an", "-c:v", "libx264", "-threads", "2", str(assets / "comparison.mp4")], cwd=work)

    def asset(path: str, kind: str, source: str = "designed", note: str = "原创演示素材，不是真实公司证据") -> dict:
        return {"path": path, "kind": kind, "source_type": source, "source_ref": note, "usage": "illustration", "license": "MIT"}

    data = {"version": "lizicut.timeline.v1", "project": {"title": "营收与利润 · 竖屏分层示例", "width": 720, "height": 1280, "fps": 25, "duration_ms": 9360, "timing_basis": "aligned", "audio_mode": "narrated", "background": "#20221f"}, "assets": {}, "shots": [{"id": "background", "asset_id": "background", "start_ms": 0, "end_ms": 9360, "loop": True, "carrier": "graphic", "information_shape": "comparison", "purpose": "保持稳定阅读空间", "decision": "背景长循环，元素与模板独立进入，不逐句换整帧"}], "overlays": [], "audio": [], "captions": {"asset_id": "captions", "font_name": "Microsoft YaHei" if os.name == "nt" else "Noto Sans CJK SC", "font_size": 34, "margin_bottom": 80}}
    for name in ("title", "context", "contrast", "relation", "marker"):
        data["assets"][name] = asset(f"assets/{name}.png", "image")
    data["assets"]["background"] = asset("assets/background.mp4", "video")
    data["assets"]["music"] = asset("assets/music.wav", "audio", "synthetic_audio", "原创低电平测试音，不是正式音乐或原声证据")
    data["assets"]["comparison"] = asset("assets/comparison.mp4", "video", note="依据同一组虚构两期数据为竖屏重新排版，共用同一尺度")
    cues = []
    lines = read_json(ROOT / "examples/revenue-profit/script.json")["units"][0]["lines"]
    for index, track in enumerate(tracks):
        source = dict(original["assets"][track["asset_id"]])
        source["path"] = "../revenue-profit/" + source["path"]
        data["assets"][track["asset_id"]] = source
        data["audio"].append(dict(track))
        cues.append({"start_ms": track["start_ms"], "end_ms": track["end_ms"], "text": lines[index]})
    data["audio"].append({"id": "music", "asset_id": "music", "role": "bgm", "start_ms": 0, "end_ms": 9360, "loop": True, "gain": 0.06, "duck_gain": 0.35, "fade_in_ms": 200, "fade_out_ms": 500})

    def layer(name: str, start: int, end: int, x: int, y: int, width: int, height: int, role: str = "template", source_in: int = 0):
        data["overlays"].append({"id": name, "asset_id": name, "role": role, "start_ms": start, "end_ms": end, "source_in_ms": source_in, "x": x, "y": y, "width": width, "height": height, "fade_in_ms": 200, "fade_out_ms": 160, "purpose": {"contrast": "第一句完整呈现营收与利润的反差", "comparison": "第二句在同板上建立两期对照"}.get(name, "保持标题、来源身份与解释锚点"), "decision": "句级时间下保守揭示；保持独立图层，可直接修改时序"})

    layer("title", 0, 9360, 32, 150, 656, 176)
    layer("context", 0, 9360, 32, 36, 656, 96)
    layer("marker", 240, 3600, 32, 365, 320, 120, "element")
    layer("contrast", 240, 3600, 32, 520, 656, 260)
    layer("comparison", 3600, 9360, 32, 510, 656, 420, source_in=1600)
    layer("relation", 3600, 9360, 32, 365, 656, 100)
    data["assets"]["captions"] = asset("captions.srt", "subtitle", note="复用实测句段声音时间，非词级识别")
    write_srt(cues, example / "captions.srt")
    (example / "timeline.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(render(data, example, example / "film.mp4", overwrite=args.overwrite), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (LizicutError, OSError) as error:
        print(f"make_layered_demo: {error}", file=sys.stderr)
        raise SystemExit(2)
