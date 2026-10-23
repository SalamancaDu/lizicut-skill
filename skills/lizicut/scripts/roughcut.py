"""Compile evidence-backed source edits into one synchronized rough cut."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from render_media import ensure_output, render, sec
from timeline import LizicutError, asset_path, choice, executable, frame_index, frame_time, integer, obj, probe, read_srt, retime, run, stream_duration_ms, stream_window_ms, text, time_value, validate, write_srt


def overlaps(left: dict, right: dict) -> bool:
    return left["start_ms"] < right["end_ms"] and left["end_ms"] > right["start_ms"]


def time_range(raw: object, context: str, duration: int) -> dict:
    item = obj(raw, context, {"start_ms", "end_ms"})
    start = time_value(item.get("start_ms"), context + ".start_ms")
    end = time_value(item.get("end_ms"), context + ".end_ms", start + 0.001, duration)
    return {"start_ms": start, "end_ms": end}


def compile_plan(plan: dict, base: Path, *, media: bool = True) -> dict:
    obj(plan, "roughcut", {"version", "title", "source", "source_duration_ms", "decisions", "captions", "video", "splice_fade_ms"})
    if plan.get("version") != "lizicut.roughcut.v1":
        raise LizicutError("roughcut.version: expected lizicut.roughcut.v1")
    title = text(plan.get("title"), "roughcut.title")
    source = obj(plan.get("source"), "roughcut.source", {"path", "kind", "source_ref", "source_type", "license"})
    kind = choice(source.get("kind"), {"video", "audio"}, "roughcut.source.kind")
    text(source.get("source_ref"), "roughcut.source.source_ref")
    source_type = choice(source.get("source_type", "user"), {"user", "document", "stock", "generated", "designed", "synthetic_audio"}, "roughcut.source.source_type")
    source_path = asset_path(base, source)
    duration = time_value(plan.get("source_duration_ms"), "roughcut.source_duration_ms", 1)
    fade = integer(plan.get("splice_fade_ms", 5), "roughcut.splice_fade_ms", 0, 20)
    source_timing = {}
    if media:
        if not source_path.is_file():
            raise LizicutError(f"roughcut.source: missing file {source_path}")
        info = probe(source_path)
        available_durations = []
        for stream_kind in (("video", "audio") if kind == "video" else ("audio",)):
            window = stream_window_ms(info, stream_kind)
            if window is None or duration > window[1] + 1:
                raise LizicutError(f"roughcut.source: selected {stream_kind} duration is missing or shorter than {duration}ms")
            start, end = window
            if stream_kind == "video" and start > 1:
                raise LizicutError("roughcut.source: video does not begin at source clock zero; prepare a synchronized source master")
            source_timing[stream_kind] = {"start_ms": start, "end_ms": end}
            available_durations.append(end)
        usable_duration = min(available_durations)
        if abs(duration - usable_duration) > 1:
            raise LizicutError(f"roughcut.source_duration_ms: expected the usable source duration {usable_duration:.1f}ms; prepare a separate master for a selected source window instead of silently discarding the tail")
    decisions = plan.get("decisions")
    if not isinstance(decisions, list):
        raise LizicutError("roughcut.decisions: expected list; unlisted source material is retained")
    ids: set[str] = set()
    removes, retained = [], []
    for index, raw in enumerate(decisions):
        context = f"decisions[{index}]"
        item = obj(raw, context, {"id", "start_ms", "end_ms", "action", "category", "reason", "evidence", "timing_checked", "related_keep", "visual_note"})
        key = text(item.get("id"), context + ".id")
        if key in ids:
            raise LizicutError(f"{context}: duplicate id {key}")
        ids.add(key)
        time_range({name: item.get(name) for name in ("start_ms", "end_ms")}, context, duration)
        action = choice(item.get("action"), {"remove", "protect", "review"}, context + ".action")
        category = choice(item.get("category"), {"retake", "redundancy", "self_correction", "filler", "pause", "breath"}, context + ".category")
        text(item.get("reason"), context + ".reason")
        text(item.get("evidence"), context + ".evidence")
        if "timing_checked" in item and type(item["timing_checked"]) is not bool:
            raise LizicutError(f"{context}.timing_checked: expected boolean")
        if "visual_note" in item:
            text(item["visual_note"], context + ".visual_note")
        if "related_keep" in item:
            time_range(item["related_keep"], context + ".related_keep", duration)
        if action == "remove":
            if item.get("timing_checked") is not True:
                raise LizicutError(f"{key}: removal requires timing_checked=true from actual timing evidence")
            if category in {"retake", "redundancy", "self_correction"} and "related_keep" not in item:
                raise LizicutError(f"{key}: semantic removal requires a related_keep alternative")
            removes.append(item)
        else:
            retained.append(item)
    removes.sort(key=lambda item: item["start_ms"])
    for index, item in enumerate(removes):
        if index and overlaps(removes[index - 1], item):
            raise LizicutError(f"{item['id']}: overlapping removals; resolve the edit decisions first")
        for keep in retained:
            if overlaps(item, keep):
                raise LizicutError(f"{item['id']}: removal intersects {keep['action']} decision {keep['id']}")
    for item in removes:
        if item.get("related_keep") and any(overlaps(item["related_keep"], deleted) for deleted in removes):
            raise LizicutError(f"{item['id']}: related_keep would also be deleted")
    kept, cursor = [], 0
    for item in removes:
        if cursor < item["start_ms"]:
            kept.append({"start_ms": cursor, "end_ms": item["start_ms"]})
        cursor = item["end_ms"]
    if cursor < duration:
        kept.append({"start_ms": cursor, "end_ms": duration})
    if not kept:
        raise LizicutError("roughcut: no source material remains")
    video = None
    if kind == "video":
        video = obj(plan.get("video"), "roughcut.video", {"width", "height", "fps"})
        fps = integer(video.get("fps"), "roughcut.video.fps", 1, 60)
        kept = [{field: frame_time(frame_index(item[field], fps, "roughcut.video source"), fps)
                 for field in ("start_ms", "end_ms")} for item in kept]
        duration = frame_time(frame_index(duration, fps, "roughcut.video source duration"), fps)
    cuts = {"source_duration_ms": duration, "kept_ranges": kept}
    mapping, joins, cursor, frame_cursor = [], [], 0, 0
    for index, item in enumerate(kept):
        length = item["end_ms"] - item["start_ms"]
        if video is not None:
            frame_cursor += frame_index(item["end_ms"], fps) - frame_index(item["start_ms"], fps)
            output_end = frame_time(frame_cursor, fps)
        else:
            output_end = cursor + length
        mapping.append({**item, "output_start_ms": cursor, "output_end_ms": output_end})
        if index:
            gap = {"start_ms": kept[index - 1]["end_ms"], "end_ms": item["start_ms"]}
            at_join = [deleted for deleted in removes if overlaps(deleted, gap)]
            joins.append({"output_ms": cursor, "left_source_ms": gap["start_ms"], "right_source_ms": gap["end_ms"],
                          "decision_ids": [deleted["id"] for deleted in at_join],
                          "visual_notes": [deleted["visual_note"] for deleted in at_join if "visual_note" in deleted],
                          "review": "Check whole words, breath, room tone, head/hand position and lip sync; cover is not automatically applied."})
        cursor = output_end
    pending = []
    for item in retained:
        if item["action"] == "review":
            for interval in mapping:
                if overlaps(item, interval):
                    offset = interval["output_start_ms"] - interval["start_ms"]
                    pending.append({"id": item["id"], "output_start_ms": max(item["start_ms"], interval["start_ms"]) + offset,
                                    "output_end_ms": min(item["end_ms"], interval["end_ms"]) + offset, "reason": item["reason"]})
    cues, caption_path = None, None
    if "captions" in plan:
        caption_path = asset_path(base, {"path": plan["captions"]})
        cues = retime(read_srt(caption_path), cuts)
        if not cues:
            raise LizicutError("roughcut.captions: no spoken captions remain; check the edit plan")
    timeline = None
    if kind == "video":
        timeline = {
            "version": "lizicut.timeline.v1",
            "project": {"title": title, **video, "duration_ms": cursor, "timing_basis": "aligned", "audio_mode": "original"},
            "assets": {"source": {"path": str(source_path), "kind": "video", "source_ref": source["source_ref"], "source_type": source_type, "usage": "illustration", "license": source.get("license", "unknown")}},
            "shots": [], "audio": []}
        for index, item in enumerate(mapping):
            start, end = item["output_start_ms"], item["output_end_ms"]
            timeline["shots"].append({"id": f"keep-{index + 1}", "asset_id": "source", "start_ms": start, "end_ms": end, "source_in_ms": item["start_ms"], "fit": "contain", "carrier": "host", "information_shape": "spoken_argument", "purpose": "保留已核对的完整表达", "decision": "按同一源区间同步剪切视频与原声；切口见 roughcut-map.json"})
            edge_fade = min(fade, int((end - start) // 2))
            timeline["audio"].append({"id": f"voice-{index + 1}", "asset_id": "source", "role": "original", "start_ms": start, "end_ms": end, "source_in_ms": item["start_ms"],
                                      "fade_in_ms": edge_fade if index else 0, "fade_out_ms": edge_fade if index + 1 < len(mapping) else 0})
        validate(timeline, base)
    elif "video" in plan:
        raise LizicutError("roughcut.video: omit video settings for an audio-only cut")
    return {"title": title, "source": str(source_path), "kind": kind, "source_ref": source["source_ref"], "cuts": cuts,
            "duration_ms": cursor, "mapping": mapping, "joins": joins, "decisions": decisions, "pending_reviews": pending,
            "captions": cues, "caption_source": str(caption_path) if caption_path else None, "timeline": timeline, "splice_fade_ms": fade,
            "source_timing": source_timing}


def render_audio(bundle: dict, output: Path) -> dict:
    source = Path(bundle["source"])
    ensure_output(output, [source], False)
    ffmpeg = executable("ffmpeg")
    with tempfile.TemporaryDirectory(prefix=".lizicut-audio-", dir=output.parent) as folder:
        work = Path(folder)
        names = []
        for index, interval in enumerate(bundle["mapping"]):
            length = interval["end_ms"] - interval["start_ms"]
            fade = min(bundle["splice_fade_ms"], int(length // 2))
            filters = ["aresample=48000:async=1:first_pts=0", f"atrim=end_sample={round(length * 48)}", "asetpts=PTS-STARTPTS"]
            if index and fade:
                filters.append(f"afade=t=in:d={sec(fade)}")
            if index + 1 < len(bundle["mapping"]) and fade:
                filters.append(f"afade=t=out:st={sec(length - fade)}:d={sec(fade)}")
            name = f"voice{index:05}.wav"
            if interval["end_ms"] <= bundle["source_timing"]["audio"]["start_ms"]:
                inputs = ["-f", "lavfi", "-t", sec(length), "-i", "anullsrc=r=48000:cl=stereo"]
            else:
                inputs = ["-ss", sec(interval["start_ms"]), "-t", sec(length), "-i", str(source)]
            run([ffmpeg, "-v", "error", "-nostdin", "-y", *inputs,
                 "-map", "0:a:0", "-vn", "-af", ",".join(filters), "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", name], cwd=work)
            actual = stream_duration_ms(probe(work / name), "audio")
            if actual is None or abs(actual - length) > 1:
                raise LizicutError(f"roughcut audio range {index + 1}: source does not supply the expected {length}ms")
            names.append(name)
        (work / "parts.txt").write_text("".join(f"file '{name}'\n" for name in names), encoding="utf-8")
        run([ffmpeg, "-v", "error", "-nostdin", "-y", "-f", "concat", "-safe", "1", "-i", "parts.txt", "-c:a", "copy", "result.wav"], cwd=work)
        actual = stream_duration_ms(probe(work / "result.wav"), "audio")
        if actual is None or abs(actual - bundle["duration_ms"]) > 1:
            raise LizicutError("roughcut audio: encoded duration differs from the source mapping")
        run([ffmpeg, "-v", "error", "-xerror", "-nostdin", "-i", "result.wav", "-f", "null", "-"], cwd=work)
        with output.open("xb") as target, (work / "result.wav").open("rb") as recording:
            shutil.copyfileobj(recording, target)
    return {"file": str(output), "duration_ms": actual, "decoded": True, "boundary": "technical audio check; meaning and listening remain separate"}


def prepare(plan: dict, base: Path, output: Path, *, render_now: bool = False, threads: int = 2) -> dict:
    bundle = compile_plan(plan, base)
    output = output.resolve()
    if output.exists():
        raise LizicutError(f"roughcut output already exists: {output}; choose a new directory")
    # All source, decision and subtitle checks happen before creating output.
    output.mkdir(parents=True)
    def write(name: str, data: dict):
        (output / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write("cuts.json", bundle["cuts"])
    write("roughcut-map.json", {key: bundle[key] for key in ("title", "source", "source_ref", "duration_ms", "mapping", "joins", "decisions", "pending_reviews", "splice_fade_ms", "source_timing")})
    if bundle["captions"] is not None:
        write_srt(bundle["captions"], output / "captions.srt")
    timeline = bundle["timeline"]
    if timeline:
        try:
            timeline["assets"]["source"]["path"] = os.path.relpath(bundle["source"], output)
        except ValueError:  # Different Windows drives cannot share a relative path.
            timeline["assets"]["source"]["path"] = bundle["source"]
        write("timeline.json", timeline)
    report = {"directory": str(output), "duration_ms": bundle["duration_ms"], "joins": len(bundle["joins"]),
              "pending_reviews": len(bundle["pending_reviews"]), "boundary": "decision declarations are checked, not automatically inferred or independently verified"}
    if render_now:
        try:
            report["media"] = render(timeline, output, output / "roughcut.mp4", threads=threads) if timeline else render_audio(bundle, output / "roughcut.wav")
        except (LizicutError, OSError) as error:
            raise LizicutError(f"roughcut prepared in {output}, but media export failed: {error}") from error
    return report
