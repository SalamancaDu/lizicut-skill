"""Portable timeline and caption validation; Python standard library only."""
from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from pathlib import Path


class LizicutError(ValueError):
    """An actionable input or media error."""


def run(command: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(command, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace")
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()[-1800:]
        raise LizicutError(f"{Path(command[0]).name} failed ({result.returncode}): {detail}")
    return result.stdout


def executable(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise LizicutError(f"Missing {name}. Use an existing installation on PATH; no automatic install is performed.")
    return path


def _pairs(items: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in items:
        if key in result:
            raise LizicutError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise LizicutError(f"Cannot read JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise LizicutError(f"Expected JSON object: {path}")
    return value


def obj(value: object, context: str, allowed: set[str]) -> dict:
    if not isinstance(value, dict):
        raise LizicutError(f"{context}: expected object")
    unknown = set(value) - allowed
    if unknown:
        raise LizicutError(f"{context}: unsupported fields {sorted(unknown)}; pre-render unsupported visual effects")
    return value


def integer(value: object, context: str, minimum: int = 0, maximum: int | None = None) -> int:
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        raise LizicutError(f"{context}: expected integer >= {minimum}" + (f" and <= {maximum}" if maximum else ""))
    return value


def number(value: object, context: str, minimum: float = 0, maximum: float = 2) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise LizicutError(f"{context}: expected finite number in [{minimum}, {maximum}]")
    return float(value)


def text(value: object, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LizicutError(f"{context}: expected nonempty text")
    return value


def choice(value: object, values: set[str], context: str) -> str:
    if not isinstance(value, str) or value not in values:
        raise LizicutError(f"{context}: expected one of {sorted(values)}")
    return value


def asset_path(base: Path, asset: dict) -> Path:
    raw = text(asset.get("path"), "asset.path")
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", raw):
        raise LizicutError("asset.path: local files required; acquire remote media separately")
    path = Path(raw).expanduser()
    return (path if path.is_absolute() else base / path).resolve()


def probe(path: Path) -> dict:
    output = run([executable("ffprobe"), "-v", "error", "-show_entries",
                  "format=duration,size,start_time:stream=codec_type,codec_name,width,height,start_time,duration,duration_ts,time_base,avg_frame_rate,sample_rate,channels,nb_frames",
                  "-of", "json", str(path)])
    return json.loads(output)


def duration_ms(info: dict) -> float | None:
    values = [info.get("format", {}).get("duration")]
    values.extend(stream.get("duration") for stream in info.get("streams", []))
    durations = []
    for value in values:
        try:
            seconds = float(value)
        except (ValueError, TypeError):
            continue
        if math.isfinite(seconds) and seconds >= 0:
            durations.append(seconds * 1000)
    return max(durations) if durations else None


def stream_duration_ms(info: dict, kind: str) -> float | None:
    """Bound the first selected stream, never a longer sibling stream."""
    streams = [item for item in info.get("streams", []) if item.get("codec_type") in {"video", "audio"}]
    selected = next((item for item in streams if item.get("codec_type") == kind), None)
    if selected is None:
        return None
    available = duration_ms({"streams": [selected]})
    if available is not None:
        return available
    try:
        numerator, denominator = map(int, selected["time_base"].split("/"))
        available = float(selected["duration_ts"]) * numerator / denominator * 1000
        if math.isfinite(available) and available >= 0:
            return available
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        pass  # Try the container only when it cannot hide a different A/V stream.
    return duration_ms(info) if len(streams) == 1 else None


def stream_window_ms(info: dict, kind: str) -> tuple[float, float] | None:
    """First stream's interval on the demuxer's shared source clock."""
    streams = [s for s in info.get("streams", []) if s.get("codec_type") in {"video", "audio"}]
    selected = next((s for s in streams if s.get("codec_type") == kind), None)
    duration = stream_duration_ms(info, kind)
    if selected is None or duration is None:
        return None

    def timestamp(value):
        try:
            seconds = float(value)
        except (TypeError, ValueError):
            return None
        return seconds * 1000 if math.isfinite(seconds) else None

    starts = [timestamp(s.get("start_time")) for s in streams]
    origin = timestamp(info.get("format", {}).get("start_time"))
    if origin is None:
        origin = min((value for value in starts if value is not None), default=0)
    start = timestamp(selected.get("start_time"))
    if start is None:
        # Plain WAV/image files have no timestamp fields. A mixed container with
        # partial timing metadata cannot safely infer a missing stream offset.
        if len(streams) > 1 and any(value is not None for value in starts):
            raise LizicutError(f"Selected {kind} stream start time is unknown; prepare a synchronized source master")
        start = origin
    relative = start - origin
    if relative < -1:
        raise LizicutError(f"Selected {kind} stream precedes the source clock; prepare a synchronized source master")
    return max(0, relative), max(0, relative) + duration


def _referenced(data: dict) -> set[str]:
    visuals = [*data["shots"], *data.get("overlays", [])]
    refs = {shot["asset_id"] for shot in visuals}
    refs.update(track["asset_id"] for track in data.get("audio", []))
    if data.get("captions"):
        refs.add(data["captions"]["asset_id"])
    for shot in visuals:
        refs.update(shot.get("evidence_refs", []))
    return refs


def validate(data: dict, base: Path, *, media: bool = False) -> list[str]:
    obj(data, "timeline", {"version", "project", "assets", "shots", "overlays", "audio", "captions"})
    if data.get("version") != "lizicut.timeline.v1":
        raise LizicutError("version: expected lizicut.timeline.v1")
    project = obj(data.get("project"), "project", {"title", "width", "height", "fps", "duration_ms", "timing_basis", "audio_mode", "background"})
    text(project.get("title"), "project.title")
    for key in ("width", "height"):
        if integer(project.get(key), f"project.{key}", 16, 3840) % 2:
            raise LizicutError(f"project.{key}: use an even dimension for yuv420p")
    fps = integer(project.get("fps"), "project.fps", 1, 60)
    total = integer(project.get("duration_ms"), "project.duration_ms", 1)
    basis = choice(project.get("timing_basis"), {"estimated", "aligned", "fixed"}, "project.timing_basis")
    mode = choice(project.get("audio_mode"), {"narrated", "original", "nonverbal", "silent"}, "project.audio_mode")
    color = project.get("background", "#20221f")
    if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise LizicutError("project.background: expected #RRGGBB")
    warnings = ["Timing is estimated; align foreground sound or author a fixed-duration nonverbal/silent film before final render."] if basis == "estimated" else []
    assets = data.get("assets")
    if not isinstance(assets, dict) or not assets:
        raise LizicutError("assets: expected nonempty object indexed by asset id")
    for key, raw in assets.items():
        text(key, "asset id")
        asset = obj(raw, f"assets.{key}", {"path", "kind", "source_type", "source_ref", "usage", "license", "note"})
        choice(asset.get("kind"), {"image", "video", "audio", "subtitle"}, f"assets.{key}.kind")
        source = choice(asset.get("source_type"), {"user", "document", "stock", "generated", "designed", "synthetic_audio"}, f"assets.{key}.source_type")
        usage = choice(asset.get("usage"), {"evidence", "illustration"}, f"assets.{key}.usage")
        text(asset.get("source_ref"), f"assets.{key}.source_ref")
        asset_path(base, asset)
        if usage == "evidence" and source in {"generated", "synthetic_audio"}:
            raise LizicutError(f"assets.{key}: generated or synthetic material cannot be factual evidence")
        if not asset.get("license") or asset.get("license") == "unknown":
            warnings.append(f"assets.{key}: distribution rights are not established")

    def ref(value: object, kinds: set[str], context: str) -> dict:
        key = text(value, context)
        if key not in assets or assets[key]["kind"] not in kinds:
            raise LizicutError(f"{context}: missing asset or incompatible kind: {key}")
        return assets[key]

    shots = data.get("shots")
    if not isinstance(shots, list) or not shots:
        raise LizicutError("shots: expected nonempty ordered list")
    cursor = 0
    seen: set[str] = set()
    for index, raw in enumerate(shots):
        context = f"shots[{index}]"
        shot = obj(raw, context, {"id", "start_ms", "end_ms", "asset_id", "source_in_ms", "fit", "loop", "purpose", "decision", "carrier", "information_shape", "evidence_refs"})
        key = text(shot.get("id"), f"{context}.id")
        if key in seen:
            raise LizicutError(f"{context}: duplicate shot id {key}")
        seen.add(key)
        start = integer(shot.get("start_ms"), f"{context}.start_ms")
        end = integer(shot.get("end_ms"), f"{context}.end_ms", start + 1)
        if start != cursor:
            raise LizicutError(f"{context}: gap or overlap at {start}ms; expected {cursor}ms")
        if start * fps % 1000 or end * fps % 1000:
            raise LizicutError(f"{context}: boundaries must be on the {fps}fps frame grid")
        cursor = end
        asset = ref(shot.get("asset_id"), {"image", "video"}, f"{context}.asset_id")
        source_in = integer(shot.get("source_in_ms", 0), f"{context}.source_in_ms")
        choice(shot.get("fit", "contain"), {"contain", "cover"}, f"{context}.fit")
        choice(shot.get("carrier"), {"host", "footage", "graphic"}, f"{context}.carrier")
        text(shot.get("information_shape"), f"{context}.information_shape")
        text(shot.get("purpose"), f"{context}.purpose")
        text(shot.get("decision"), f"{context}.decision")
        if type(shot.get("loop", False)) is not bool:
            raise LizicutError(f"{context}.loop: expected boolean")
        if source_in and (asset["kind"] == "image" or shot.get("loop")):
            raise LizicutError(f"{context}: images and looped media require source_in_ms=0; prepare a trimmed loop asset first")
        evidence = shot.get("evidence_refs", [])
        if not isinstance(evidence, list):
            raise LizicutError(f"{context}.evidence_refs: expected asset id list")
        for evidence_id in evidence:
            item = ref(evidence_id, {"image", "video", "audio"}, f"{context}.evidence_refs")
            if item["usage"] != "evidence":
                raise LizicutError(f"{context}: illustration {evidence_id} cannot serve as factual evidence")
    if cursor != total:
        raise LizicutError(f"shots end at {cursor}ms, project duration is {total}ms")
    overlays = data.get("overlays", [])
    if not isinstance(overlays, list):
        raise LizicutError("overlays: expected list in back-to-front order")
    for index, raw in enumerate(overlays):
        context = f"overlays[{index}]"
        layer = obj(raw, context, {"id", "asset_id", "role", "start_ms", "end_ms", "source_in_ms", "fit", "loop", "x", "y", "width", "height", "opacity", "fade_in_ms", "fade_out_ms", "purpose", "decision", "evidence_refs"})
        key = text(layer.get("id"), f"{context}.id")
        if key in seen:
            raise LizicutError(f"{context}: duplicate visual id {key}")
        seen.add(key)
        asset = ref(layer.get("asset_id"), {"image", "video"}, f"{context}.asset_id")
        choice(layer.get("role"), {"element", "template"}, f"{context}.role")
        start = integer(layer.get("start_ms"), f"{context}.start_ms")
        end = integer(layer.get("end_ms"), f"{context}.end_ms", start + 1, total)
        if start * fps % 1000 or end * fps % 1000:
            raise LizicutError(f"{context}: boundaries must be on the {fps}fps frame grid")
        for axis, dimension in (("x", "width"), ("y", "height")):
            position = integer(layer.get(axis), f"{context}.{axis}")
            size = integer(layer.get(dimension), f"{context}.{dimension}", 2, project[dimension])
            if position + size > project[dimension]:
                raise LizicutError(f"{context}: rectangle extends beyond project {dimension}")
        source_in = integer(layer.get("source_in_ms", 0), f"{context}.source_in_ms")
        choice(layer.get("fit", "contain"), {"contain", "cover"}, f"{context}.fit")
        if type(layer.get("loop", False)) is not bool:
            raise LizicutError(f"{context}.loop: expected boolean")
        if source_in and (asset["kind"] == "image" or layer.get("loop")):
            raise LizicutError(f"{context}: images and looped media require source_in_ms=0; prepare a trimmed loop asset first")
        number(layer.get("opacity", 1), f"{context}.opacity", 0, 1)
        fades = sum(integer(layer.get(field, 0), f"{context}.{field}") for field in ("fade_in_ms", "fade_out_ms"))
        if fades > end - start:
            raise LizicutError(f"{context}: fades exceed layer duration")
        text(layer.get("purpose"), f"{context}.purpose")
        text(layer.get("decision"), f"{context}.decision")
        evidence = layer.get("evidence_refs", [])
        if not isinstance(evidence, list):
            raise LizicutError(f"{context}.evidence_refs: expected asset id list")
        for evidence_id in evidence:
            if ref(evidence_id, {"image", "video", "audio"}, f"{context}.evidence_refs")["usage"] != "evidence":
                raise LizicutError(f"{context}: illustration {evidence_id} cannot serve as factual evidence")
    tracks = data.get("audio", [])
    if not isinstance(tracks, list):
        raise LizicutError("audio: expected list")
    roles = []
    track_ids: set[str] = set()
    for index, raw in enumerate(tracks):
        context = f"audio[{index}]"
        track = obj(raw, context, {"id", "asset_id", "role", "start_ms", "end_ms", "source_in_ms", "gain", "fade_in_ms", "fade_out_ms", "loop", "duck_gain", "duck_attack_ms", "duck_release_ms", "duck_hold_ms"})
        track_id = text(track.get("id"), f"{context}.id")
        if track_id in track_ids:
            raise LizicutError(f"{context}: duplicate track id {track_id}")
        track_ids.add(track_id)
        ref(track.get("asset_id"), {"audio", "video"}, f"{context}.asset_id")
        role = choice(track.get("role"), {"narration", "original", "bgm", "sfx"}, f"{context}.role")
        start = integer(track.get("start_ms"), f"{context}.start_ms")
        end = integer(track.get("end_ms"), f"{context}.end_ms", start + 1, total)
        source_in = integer(track.get("source_in_ms", 0), f"{context}.source_in_ms")
        gain = number(track.get("gain", 1), f"{context}.gain")
        if gain > 0:
            roles.append(role)
        if type(track.get("loop", False)) is not bool:
            raise LizicutError(f"{context}.loop: expected boolean")
        if track.get("loop") and source_in:
            raise LizicutError(f"{context}: loop starts at source zero; prepare a trimmed loop asset first")
        fades = sum(integer(track.get(key, 0), f"{context}.{key}") for key in ("fade_in_ms", "fade_out_ms"))
        if fades > end - start:
            raise LizicutError(f"{context}: fades exceed track duration")
        if "duck_gain" in track:
            number(track["duck_gain"], f"{context}.duck_gain", 0, 1)
            if role != "bgm":
                raise LizicutError(f"{context}: duck_gain is supported for BGM only")
        for field in ("duck_attack_ms", "duck_release_ms", "duck_hold_ms"):
            if field in track:
                integer(track[field], f"{context}.{field}", 0 if field == "duck_hold_ms" else 1, 5000)
                if "duck_gain" not in track:
                    raise LizicutError(f"{context}: {field} requires duck_gain")
    if mode == "silent" and tracks:
        raise LizicutError("silent project must not contain audio tracks")
    if mode == "narrated" and "narration" not in roles:
        raise LizicutError("narrated project requires at least one narration track")
    if mode == "original" and "original" not in roles:
        raise LizicutError("original project requires at least one original-sound track")
    if mode == "nonverbal" and (not {"bgm", "sfx"}.intersection(roles) or any(track["role"] in {"narration", "original"} for track in tracks)):
        raise LizicutError("nonverbal project requires audible BGM/SFX only; use narrated/original for foreground voices")
    if any("duck_gain" in track for track in tracks) and not {"narration", "original"}.intersection(roles):
        raise LizicutError("BGM ducking requires audible narration or original-sound tracks")
    caption = data.get("captions")
    if caption is not None:
        obj(caption, "captions", {"asset_id", "font_name", "font_size", "margin_bottom"})
        ref(caption.get("asset_id"), {"subtitle"}, "captions.asset_id")
        font = text(caption.get("font_name", "sans-serif"), "captions.font_name")
        if any(char in font for char in ",\\\n\r{}"):  # ASS style is not an arbitrary filter string.
            raise LizicutError("captions.font_name: unsupported style delimiter")
        integer(caption.get("font_size", 32), "captions.font_size", 8, 128)
        integer(caption.get("margin_bottom", 36), "captions.margin_bottom", 0, project["height"] // 2)
    if media:
        validate_media(data, base)
    return warnings


def validate_media(data: dict, base: Path) -> dict[str, dict]:
    infos = {}
    for key in _referenced(data):
        asset = data["assets"][key]
        path = asset_path(base, asset)
        if not path.is_file():
            raise LizicutError(f"assets.{key}: missing file {path}")
        if asset["kind"] == "subtitle":
            cues = read_srt(path)
            if cues[-1]["end_ms"] > data["project"]["duration_ms"]:
                raise LizicutError(f"assets.{key}: captions extend beyond project duration")
            continue
        info = probe(path)
        infos[key] = info
        kind = "audio" if asset["kind"] == "audio" else "video"
        if not any(stream["codec_type"] == kind for stream in info.get("streams", [])):
            raise LizicutError(f"assets.{key}: expected {kind} stream in {path}")
    for track in data.get("audio", []):
        key = track["asset_id"]
        if not any(stream["codec_type"] == "audio" for stream in infos[key].get("streams", [])):
            raise LizicutError(f"audio.{track['id']}: source has no audio stream")
    visual_entries = [*data["shots"], *data.get("overlays", [])]
    for entry, kind in [(entry, "video") for entry in visual_entries] + [(entry, "audio") for entry in data.get("audio", [])]:
        key = entry["asset_id"]
        if data["assets"][key]["kind"] == "image":
            continue
        window = stream_window_ms(infos[key], kind)
        required = entry.get("source_in_ms", 0) + entry["end_ms"] - entry["start_ms"]
        if window is None:
            raise LizicutError(f"{entry['id']}: selected {kind} stream duration is unavailable; inspect or prepare a separate source")
        start, available = window
        if kind == "video" and entry.get("source_in_ms", 0) < start - 1:
            raise LizicutError(f"{entry['id']}: requested video begins before its first frame; prepare a synchronized source master")
        if entry.get("source_in_ms", 0) >= available or (not entry.get("loop") and required > available + 40):
            raise LizicutError(f"{entry['id']}: requested source range needs {required}ms; source has {available:.1f}ms")
    return infos


_STAMP = re.compile(r"^(\d{2,}):([0-5]\d):([0-5]\d)[,.](\d{3})$")


def _ms(value: str) -> int:
    match = _STAMP.fullmatch(value.strip())
    if not match:
        raise LizicutError(f"Invalid SRT timestamp: {value}")
    hours, minutes, seconds, milliseconds = map(int, match.groups())
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + milliseconds


def read_srt(path: Path) -> list[dict]:
    try:
        raw = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").strip()
    except (OSError, UnicodeError) as error:
        raise LizicutError(f"Cannot read subtitles {path}: {error}") from error
    cues = []
    for index, block in enumerate(re.split(r"\n[ \t]*\n", raw), 1):
        lines = block.splitlines()
        if lines and lines[0].strip().isdigit():
            lines = lines[1:]
        parts = re.split(r"\s*-->\s*", lines[0]) if lines else []
        if len(lines) < 2 or len(parts) != 2:
            raise LizicutError(f"{path}: malformed SRT cue {index}")
        start, end = (_ms(value) for value in parts)
        if end <= start or (cues and start < cues[-1]["end_ms"]):
            raise LizicutError(f"{path}: overlapping or invalid SRT cue {index}")
        content = "\n".join(lines[1:]).strip()
        text(content, f"{path}: SRT cue {index}")
        cues.append({"start_ms": start, "end_ms": end, "text": content})
    if not cues:
        raise LizicutError(f"{path}: no subtitle cues")
    return cues


def stamp(milliseconds: int) -> str:
    seconds, ms = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02},{ms:03}"


def write_srt(cues: list[dict], path: Path) -> None:
    path.write_text("\n\n".join(f"{index}\n{stamp(cue['start_ms'])} --> {stamp(cue['end_ms'])}\n{cue['text']}" for index, cue in enumerate(cues, 1)) + "\n", encoding="utf-8")


def retime(cues: list[dict], cuts: dict) -> list[dict]:
    obj(cuts, "cuts", {"source_duration_ms", "kept_ranges"})
    total = integer(cuts.get("source_duration_ms"), "cuts.source_duration_ms", 1)
    ranges = cuts.get("kept_ranges")
    if not isinstance(ranges, list) or not ranges:
        raise LizicutError("cuts.kept_ranges: expected nonempty list")
    cursor = 0
    mapped = []
    previous = 0
    for index, raw in enumerate(ranges):
        item = obj(raw, f"kept_ranges[{index}]", {"start_ms", "end_ms"})
        start = integer(item.get("start_ms"), "range.start_ms", previous)
        end = integer(item.get("end_ms"), "range.end_ms", start + 1, total)
        if mapped and start == mapped[-1][1]:
            mapped[-1] = (mapped[-1][0], end, mapped[-1][2])
        else:
            mapped.append((start, end, cursor))
        cursor += end - start
        previous = end
    result = []
    for index, cue in enumerate(cues, 1):
        if cue["end_ms"] > total:
            raise LizicutError(f"SRT cue {index} extends beyond source duration")
        intersections = [(start, end, offset) for start, end, offset in mapped if cue["start_ms"] < end and cue["end_ms"] > start]
        if not intersections:
            continue
        start, end, offset = intersections[0]
        if len(intersections) != 1 or cue["start_ms"] < start or cue["end_ms"] > end:
            raise LizicutError(f"SRT cue {index} crosses a cut ({stamp(cue['start_ms'])} --> {stamp(cue['end_ms'])}); split the text using actual audio before retiming")
        result.append({**cue, "start_ms": offset + cue["start_ms"] - start, "end_ms": offset + cue["end_ms"] - start})
    return result
