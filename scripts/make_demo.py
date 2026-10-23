"""Rebuild the worked fictional-data example using existing local tools."""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/lizicut/scripts"))
from timeline import LizicutError, executable, read_json, run, write_srt
from render_media import render

COLORS = {"paper": "0xf1eee3", "muted": "0xa2a99c", "teal": "0x60c7ac", "coral": "0xe89578", "panel": "0x30352e", "cost": "0x7e867a"}


class Board:
    def __init__(self, work: Path, title: str, index: int):
        self.work, self.filters, self.count = work, [], 0
        self.text(f"{index:02}  /  LIZICUT", 80, 38, 18, "muted")
        self.text(title, 80, 85, 42)
        self.box(80, 156, 1120, 2, "muted")
        self.text("虚构演示数据 · 不对应真实公司", 80, 607, 18, "muted")

    def text(self, content: str, x: int, y: int, size: int, color: str = "paper", at: float = 0):
        self.count += 1
        name = f"text{self.count:02}.txt"
        (self.work / name).write_text(content, encoding="utf-8")
        alpha = f"min(1,max(0,(t-{at:.3f})/0.28))" if at else "1"
        self.filters.append(f"drawtext=fontfile=font.ttc:textfile={name}:expansion=none:x={x}:y={y}:fontsize={size}:fontcolor={COLORS[color]}:alpha='{alpha}'")

    def box(self, x: int, y: int, width: int, height: int, color: str, at: float = 0):
        self.filters.append(f"drawbox=x={x}:y={y}:w={width}:h={height}:color={COLORS[color]}:t=fill:enable='gte(t,{at:.3f})'")


def make_board(unit: dict, index: int, timing: list[dict], duration: int, data: dict, work: Path, output: Path, font: Path, overwrite: bool):
    if output.exists() and not overwrite:
        return
    shutil.copyfile(font, work / "font.ttc")
    b = Board(work, unit["title"], index)
    before, after = data["periods"]
    second = timing[1]["local_start_ms"] / 1000
    revenue_growth = round((after["revenue"] / before["revenue"] - 1) * 100)
    profit_growth = round((after["profit"] / before["profit"] - 1) * 100)
    if unit["id"] == "contrast":
        b.text("营收", 100, 230, 30, "muted")
        b.text(f"+{revenue_growth}%", 100, 292, 108, "teal", 0.28)
        # Both relations are spoken in the first utterance. With sentence-level
        # timing, present the complete comparison instead of delaying profit.
        b.text("利润", 700, 230, 30, "muted")
        b.text(f"{profit_growth}%", 700, 292, 108, "coral", 0.28)
        b.text("同一家公司，两个方向", 100, 493, 28, at=0.6)
    elif unit["id"] == "relation":
        b.text("示例关系", 100, 222, 25, "muted")
        for value, x, color, at in [("营收", 100, "paper", 0.2), ("−", 380, "muted", second), ("成本", 500, "paper", second), ("=", 780, "muted", second + 0.25), ("利润", 930, "teal", second + 0.5)]:
            b.text(value, x, 316, 64, color, at)
        b.text("比较之前，先把计算关系固定下来", 100, 493, 28, at=second + 0.5)
        b.text("本例成本包含全部成本费用；利润为简化演示差额", 100, 560, 20, "muted")
    elif unit["id"] == "compare":
        scale = 7.0
        b.text("单位：万元 · 同一长度尺度", 100, 205, 24, "muted")
        for row, (period, at) in enumerate([(before, 0.2), (after, second)]):
            y = 295 + row * 155
            b.text(period["name"], 100, y - 2, 25, "muted", at)
            x, height = 265, 43
            b.box(x, y, int(period["cost"] * scale), height, "cost", at)
            b.box(x + int(period["cost"] * scale), y, int(period["profit"] * scale), height, "teal", at)
            b.text(f"成本 {period['cost']}", x, y + 56, 23, "muted", at)
            b.text(f"利润 {period['profit']}", x + int(period["cost"] * scale), y + 56, 23, "teal", at)
            b.text(str(period["revenue"]), x + int(period["revenue"] * scale) + 18, y + 3, 26, at=at)
    elif unit["id"] == "change":
        revenue_change = after["revenue"] - before["revenue"]
        cost_change = after["cost"] - before["cost"]
        b.text("新增金额 · 单位：万元", 100, 211, 24, "muted")
        b.text("营收", 100, 286, 27)
        b.box(260, 285, revenue_change * 24, 40, "teal", 0.2)
        b.text(f"+{revenue_change}", 260 + revenue_change * 24 + 20, 283, 32, "teal", 0.2)
        b.text("成本", 100, 396, 27, at=0.7)
        b.box(260, 395, cost_change * 24, 40, "coral", 0.7)
        b.text(f"+{cost_change}", 260 + cost_change * 24 + 20, 393, 32, "coral", 0.7)
        b.text(f"利润变化：{revenue_change} − {cost_change} = {revenue_change - cost_change}", 260, 505, 34, "paper", second)
    elif unit["id"] == "margin":
        margins = [round(period["profit"] / period["revenue"] * 100) for period in data["periods"]]
        b.text("利润率 = 利润 ÷ 营收", 100, 211, 26, "muted")
        for row, (label, value, at) in enumerate([(before["name"], margins[0], 0.2), (after["name"], margins[1], 0.7)]):
            y = 300 + row * 130
            b.text(label, 100, y, 27, "muted", at)
            b.box(265, y, value * 33, 42, "teal" if row == 0 else "coral", at)
            b.text(f"{value}%", 285 + value * 33, y - 3, 36, "teal" if row == 0 else "coral", at)
        b.text("规模扩大 ≠ 效率提高", 265, 532, 28, at=second)
    else:
        b.text("看到“增长”，先问：增长的是什么？", 100, 238, 40, at=0.2)
        for value, x, at in [("收入", 100, second), ("成本", 480, second + 0.3), ("利润", 860, second + 0.6)]:
            b.box(x, 364, 275, 4, "teal", at)
            b.text(value, x, 402, 48, at=at)
        b.text("让画面把关系讲清楚", 100, 520, 29, "teal", second + 0.8)
    (work / "board.ffscript").write_text(",\n".join(b.filters), encoding="utf-8")
    run([executable("ffmpeg"), "-hide_banner", "-v", "error", "-nostdin", "-y", "-filter_threads", "1", "-f", "lavfi", "-i", f"color=c=0x20221f:s=1280x720:r=25:d={duration / 1000:.3f}",
         "-vf", ",".join(b.filters), "-frames:v", str(duration // 40), "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "19", "-threads", "2", str(output)], cwd=work)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-voice", action="store_true", help="replace only this example's generated voice files using installed Windows SAPI")
    parser.add_argument("--rebuild-visuals", action="store_true")
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--overwrite", action="store_true", help="replace the generated example MP4")
    parser.add_argument("--font", type=Path, default=Path("C:/Windows/Fonts/msyh.ttc"))
    args = parser.parse_args()
    example = ROOT / "examples/revenue-profit"
    assets = example / "assets"
    assets.mkdir(exist_ok=True)
    document, dataset = read_json(example / "script.json"), read_json(example / "data.json")
    for period in dataset["periods"]:
        if period["revenue"] - period["cost"] != period["profit"]:
            raise LizicutError(f"Demo dataset equation does not hold: {period['name']}")
    missing = [assets / f"{unit['id']}-{index}.wav" for unit in document["units"] for index in (1, 2) if not (assets / f"{unit['id']}-{index}.wav").is_file()]
    if missing or args.refresh_voice:
        if os.name != "nt":
            raise LizicutError("Demo voice WAV files are missing. Reuse the provided files or supply local narration; this rebuild helper uses installed Windows SAPI.")
        from windows_voice import synthesize
        synthesize(document, assets, replace=args.refresh_voice)
    if not args.font.is_file():
        raise LizicutError("A local CJK font is required; pass --font with an existing font file. No system font is bundled.")
    timeline = {"version": "lizicut.timeline.v1", "project": {"title": document["title"], "width": 1280, "height": 720, "fps": 25, "duration_ms": 0, "timing_basis": "aligned", "audio_mode": "narrated", "background": "#20221f"}, "assets": {}, "shots": [], "audio": [], "captions": {"asset_id": "captions", "font_name": "Microsoft YaHei" if os.name == "nt" else "Noto Sans CJK SC", "font_size": 30, "margin_bottom": 32}}
    cues, cursor = [], 0
    rationales = ["同板对比增长与下降；完整口播放字幕，关键词保持简短。", "先固定收入、成本与利润的关系；虚构数据不充当事实证据。", "两期共用尺度和位置；第二期在对应句子出现，保留第一期便于比较。", "延续成本与利润的身份；用新增金额解释利润减少的原因。", "补充效率维度；百分比与条长保持一致，不用图形夸大差异。", "减少信息并收束问题；不引入未经论证的新结论。"]
    for index, unit in enumerate(document["units"], 1):
        unit_start = cursor
        local_cursor, times = 0, []
        for line_index, content in enumerate(unit["lines"], 1):
            name = f"{unit['id']}-{line_index}"
            path = assets / f"{name}.wav"
            with wave.open(str(path), "rb") as recording:
                length = round(recording.getnframes() / recording.getframerate() * 1000)
            timeline["assets"][name] = {"path": f"assets/{name}.wav", "kind": "audio", "source_type": "synthetic_audio", "source_ref": "Local installed Windows Simplified Chinese SAPI voice; authored demo text", "usage": "illustration", "license": "demo output; voice engine not redistributed", "note": "合成示范旁白，不是真实人物原声"}
            timeline["audio"].append({"id": name, "asset_id": name, "role": "narration", "start_ms": unit_start + local_cursor, "end_ms": unit_start + local_cursor + length, "source_in_ms": 0, "gain": 0.92, "fade_in_ms": 8, "fade_out_ms": 16})
            cues.append({"start_ms": unit_start + local_cursor, "end_ms": unit_start + local_cursor + length, "text": content})
            times.append({"local_start_ms": local_cursor, "duration_ms": length})
            local_cursor = math.ceil((local_cursor + length + 160) / 40) * 40
        duration = local_cursor + 600
        visual = assets / f"{unit['id']}.mp4"
        print(f"Preparing {unit['id']} ({duration / 1000:.2f}s)", flush=True)
        with tempfile.TemporaryDirectory(prefix=".lizicut-demo-", dir=example) as directory:
            make_board(unit, index, times, duration, dataset, Path(directory), visual, args.font, args.rebuild_visuals)
        timeline["assets"][unit["id"]] = {"path": f"assets/{unit['id']}.mp4", "kind": "video", "source_type": "designed", "source_ref": f"data.json + authored board {unit['id']}; all values fictional", "usage": "illustration", "license": "MIT"}
        timeline["shots"].append({"id": f"shot-{index:02}", "start_ms": unit_start, "end_ms": unit_start + duration, "asset_id": unit["id"], "source_in_ms": 0, "fit": "contain", "carrier": "graphic", "information_shape": ["comparison", "mechanism", "comparison", "change", "ratio", "summary"][index - 1], "purpose": unit["title"], "decision": rationales[index - 1], "evidence_refs": []})
        cursor += duration
    timeline["project"]["duration_ms"] = cursor
    timeline["assets"]["captions"] = {"path": "captions.srt", "kind": "subtitle", "source_type": "designed", "source_ref": "script.json; individually synthesized utterance durations, not word-level ASR", "usage": "illustration", "license": "MIT"}
    write_srt(cues, example / "captions.srt")
    (example / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {cursor / 1000:.2f}s; {len(cues)} measured utterance intervals", flush=True)
    if args.render:
        print(json.dumps(render(timeline, example, example / "film.mp4", overwrite=args.overwrite), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (LizicutError, OSError) as error:
        print(f"make_demo: {error}", file=sys.stderr)
        raise SystemExit(2)
