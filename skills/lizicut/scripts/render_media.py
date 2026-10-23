"""Assemble prepared visuals and scheduled audio without a website runtime."""
from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from pathlib import Path

from timeline import LizicutError, asset_path, duration_ms, executable, probe, read_srt, run, stream_window_ms, validate, validate_media


def sec(milliseconds: int) -> str:
    return f"{milliseconds / 1000:.6f}"


def duck_expression(track: dict, voices: list[dict]) -> str | None:
    """A scheduled envelope; this is not speech activity detection."""
    attack = track.get("duck_attack_ms", 80)
    release = track.get("duck_release_ms", 240)
    hold = track.get("duck_hold_ms", 300)
    spans: list[list[int]] = []
    for voice in sorted(voices, key=lambda item: item["start_ms"]):
        if voice.get("gain", 1) <= 0:
            continue
        start, end = voice["start_ms"], voice["end_ms"]
        if spans and start <= spans[-1][1] + hold:
            spans[-1][1] = max(spans[-1][1], end)
        else:
            spans.append([start, end])
    expressions = []
    gain = track["duck_gain"]
    duration = track["end_ms"] - track["start_ms"]
    for start, end in spans:
        start -= track["start_ms"]
        end -= track["start_ms"]
        if end + release <= 0 or start - attack >= duration:
            continue
        expressions.append(
            f"if(lt(t,{sec(start - attack)}),1,"
            f"if(lt(t,{sec(start)}),1-(1-{gain})*(t-({sec(start - attack)}))/{sec(attack)},"
            f"if(lte(t,{sec(end)}),{gain},"
            f"if(lt(t,{sec(end + release)}),{gain}+(1-{gain})*(t-({sec(end)}))/{sec(release)},1))))")
    if not expressions:
        return None
    expression = expressions[0]
    for item in expressions[1:]:
        expression = f"min({expression},{item})"
    return expression


def ass_time(milliseconds: int) -> str:
    centiseconds = milliseconds // 10
    seconds, cs = divmod(centiseconds, 100)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02}:{seconds:02}.{cs:02}"


def write_ass(data: dict, base: Path, target: Path) -> None:
    project, captions = data["project"], data["captions"]
    cues = read_srt(asset_path(base, data["assets"][captions["asset_id"]]))
    header = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {project['width']}\nPlayResY: {project['height']}\nWrapStyle: 0\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{captions.get('font_name', 'sans-serif')},{captions.get('font_size', 32)},&H00FFFFFF,&H00FFFFFF,&H00151515,&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,40,40,{captions.get('margin_bottom', 36)},1\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    events = []
    for index, cue in enumerate(cues, 1):
        content = cue["text"]
        if any(char in content for char in "{}\\"):
            raise LizicutError(f"SRT cue {index}: ASS control characters are not supported by this plain-text burner; use a backend that preserves the required literal text")
        if ass_time(cue["end_ms"]) == ass_time(cue["start_ms"]):
            raise LizicutError(f"SRT cue {index}: duration is below ASS centisecond precision")
        content = content.replace("\n", r"\N")
        events.append(f"Dialogue: 0,{ass_time(cue['start_ms'])},{ass_time(cue['end_ms'])},Default,,0,0,0,,{content}")
    target.write_text(header + "\n".join(events) + "\n", encoding="utf-8")


def inspect(path: Path, *, decode: bool = False) -> dict:
    if not path.is_file():
        raise LizicutError(f"Missing media file: {path}")
    info = probe(path)
    video = next((stream for stream in info.get("streams", []) if stream["codec_type"] == "video"), None)
    audio = [stream for stream in info.get("streams", []) if stream["codec_type"] == "audio"]
    if not video:
        raise LizicutError(f"No video stream: {path}")
    if decode:
        run([executable("ffmpeg"), "-hide_banner", "-v", "error", "-xerror", "-nostdin", "-i", str(path), "-f", "null", "-"])
    return {"file": str(path), "duration_ms": duration_ms(info), "width": video.get("width"),
            "height": video.get("height"), "fps": video.get("avg_frame_rate"), "video_codec": video.get("codec_name"),
            "frames": video.get("nb_frames"), "audio_streams": len(audio), "audio_codec": audio[0].get("codec_name") if audio else None,
            "decoded": decode, "boundary": "technical media validation; semantic accuracy, listening and visual review remain separate"}


def ensure_output(path: Path, sources: list[Path], overwrite: bool) -> None:
    if path.resolve() in {source.resolve() for source in sources}:
        raise LizicutError(f"Output would replace an input: {path}")
    if path.exists() and (not overwrite or not path.is_file()):
        raise LizicutError(f"Output already exists: {path}; choose a new filename or explicitly use --overwrite for an existing output file")


def render(data: dict, base: Path, output: Path, *, overwrite: bool = False, threads: int = 2) -> dict:
    warnings = validate(data, base)
    project = data["project"]
    if project["timing_basis"] == "estimated":
        raise LizicutError("Cannot render final video with estimated timing; align foreground sound or author a fixed-duration nonverbal/silent film")
    source_infos = validate_media(data, base)
    output = output.resolve()
    if output.suffix.lower() != ".mp4":
        raise LizicutError("Output must end in .mp4 (H.264 video and AAC audio)")
    if not 1 <= threads <= 16:
        raise LizicutError("threads must be between 1 and 16")
    sources = [asset_path(base, asset) for asset in data["assets"].values()]
    ensure_output(output, sources, overwrite)
    ffmpeg = executable("ffmpeg")
    output.parent.mkdir(parents=True, exist_ok=True)
    width, height, fps = project["width"], project["height"], project["fps"]
    color = "0x" + project.get("background", "#20221f")[1:]
    common = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-filter_threads", "1", "-filter_complex_threads", "1"]
    # Only this newly-created temporary directory is cleaned up, including on failure.
    with tempfile.TemporaryDirectory(prefix=".lizicut-", dir=output.parent) as temporary:
        work = Path(temporary)
        if data.get("captions"):
            write_ass(data, base, work / "captions.ass")
        parts = []
        for index, shot in enumerate(data["shots"], 1):
            print(f"Rendering shot {index}/{len(data['shots'])}: {shot['id']}", flush=True)
            asset = data["assets"][shot["asset_id"]]
            command = list(common)
            if asset["kind"] == "image":
                command += ["-loop", "1", "-framerate", str(fps)]
            elif shot.get("loop"):
                command += ["-stream_loop", "-1"]
            if shot.get("source_in_ms", 0):
                command += ["-ss", sec(shot["source_in_ms"])]
            command += ["-i", str(asset_path(base, asset))]
            if shot.get("fit", "contain") == "cover":
                scaling = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
            else:
                scaling = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={color}"
            frames = (shot["end_ms"] - shot["start_ms"]) * fps // 1000
            name = f"part{index:04}.mp4"
            command += ["-an", "-vf", f"setpts=PTS-STARTPTS,{scaling},setsar=1,fps={fps},format=yuv420p", "-frames:v", str(frames),
                        "-c:v", "libx264", "-preset", "fast", "-crf", "19", "-threads", str(threads), name]
            run(command, cwd=work)
            actual_frames = probe(work / name)["streams"][0].get("nb_frames")
            if actual_frames is None or int(actual_frames) != frames:
                raise LizicutError(f"{shot['id']}: expected {frames} frames, encoded {actual_frames}; check the source range")
            parts.append(name)
        (work / "parts.txt").write_text("".join(f"file '{name}'\n" for name in parts), encoding="utf-8")
        command = [*common, "-f", "concat", "-safe", "1", "-i", "parts.txt"]
        filters = []
        labels = []
        voices = [track for track in data.get("audio", []) if track["role"] in {"narration", "original"}]
        for index, track in enumerate(data.get("audio", []), 1):
            duration = track["end_ms"] - track["start_ms"]
            audio_start, _ = stream_window_ms(source_infos[track["asset_id"]], "audio")
            if not track.get("loop") and track.get("source_in_ms", 0) + duration <= audio_start:
                # This source-clock range precedes the first audio packet.
                command += ["-f", "lavfi", "-t", sec(duration), "-i", "anullsrc=r=48000:cl=stereo"]
            else:
                if track.get("loop"):
                    command += ["-stream_loop", "-1"]
                if track.get("source_in_ms", 0):
                    command += ["-ss", sec(track["source_in_ms"])]
                command += ["-t", sec(duration), "-i", str(asset_path(base, data["assets"][track["asset_id"]]))]
            chain = [f"[{index}:a:0]aresample=48000:async=1:first_pts=0", f"atrim=duration={sec(duration)}", "asetpts=PTS-STARTPTS", f"volume={track.get('gain', 1)}"]
            if "duck_gain" in track:
                expression = duck_expression(track, voices)
                if expression:
                    chain.append(f"volume='{expression}':eval=frame")
            fade_in, fade_out = track.get("fade_in_ms", 0), track.get("fade_out_ms", 0)
            if fade_in:
                chain.append(f"afade=t=in:st=0:d={sec(fade_in)}")
            if fade_out:
                chain.append(f"afade=t=out:st={sec(duration - fade_out)}:d={sec(fade_out)}")
            chain.append(f"adelay={track['start_ms']}:all=1[a{index}]")
            filters.append(",".join(chain))
            labels.append(f"[a{index}]")
        total = sec(project["duration_ms"])
        filters.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={total}[silence]")
        mix_inputs = "[silence]" + "".join(labels)
        filters.append(f"{mix_inputs}amix=inputs={len(labels) + 1}:duration=longest:dropout_transition=0:normalize=0,alimiter=limit=0.98:level=0:latency=1,apad,atrim=duration={total}[mixed]")
        filters.append("[0:v:0]setpts=PTS-STARTPTS[base]")
        visual = "base"
        for index, layer in enumerate(data.get("overlays", [])):
            input_index = len(data.get("audio", [])) + index + 1
            asset = data["assets"][layer["asset_id"]]
            if asset["kind"] == "image":
                command += ["-loop", "1", "-framerate", str(fps)]
            elif layer.get("loop"):
                command += ["-stream_loop", "-1"]
            if layer.get("source_in_ms", 0):
                command += ["-ss", sec(layer["source_in_ms"])]
            duration = layer["end_ms"] - layer["start_ms"]
            command += ["-t", sec(duration), "-i", str(asset_path(base, asset))]
            w, h = layer["width"], layer["height"]
            if layer.get("fit", "contain") == "cover":
                scaling = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
            else:
                scaling = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black@0"
            chain = [f"[{input_index}:v:0]trim=duration={sec(duration)}", "setpts=PTS-STARTPTS", f"fps={fps}", "format=rgba", scaling, "setsar=1", f"colorchannelmixer=aa={layer.get('opacity', 1)}"]
            if layer.get("fade_in_ms", 0):
                chain.append(f"fade=t=in:st=0:d={sec(layer['fade_in_ms'])}:alpha=1")
            if layer.get("fade_out_ms", 0):
                chain.append(f"fade=t=out:st={sec(duration - layer['fade_out_ms'])}:d={sec(layer['fade_out_ms'])}:alpha=1")
            chain.append(f"setpts=PTS+{sec(layer['start_ms'])}/TB[ov{index}]")
            filters.append(",".join(chain))
            next_visual = f"v{index}"
            filters.append(f"[{visual}][ov{index}]overlay=x={layer['x']}:y={layer['y']}:eof_action=pass:repeatlast=0:enable='gte(t,{sec(layer['start_ms'])})*lt(t,{sec(layer['end_ms'])})'[{next_visual}]")
            visual = next_visual
        filters.append(f"[{visual}]" + ("ass=captions.ass" if data.get("captions") else "null") + "[outv]")
        graph = ";".join(filters)
        if len(graph) > 8000:
            # Recent FFmpeg can read an option argument from a file. Avoid the
            # Windows process command-line limit for many scheduled tracks.
            (work / "composition.ffgraph").write_text(graph, encoding="utf-8")
            command += ["-/filter_complex", "composition.ffgraph"]
        else:
            command += ["-filter_complex", graph]
        command += ["-map", "[outv]", "-map", "[mixed]"]
        command += ["-t", total, "-frames:v", str(project['duration_ms'] * fps // 1000), "-c:v", "libx264", "-preset", "fast", "-crf", "19", "-threads", str(threads), "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart", "result.mp4"]
        print("Mixing sound, burning captions and encoding final MP4", flush=True)
        run(command, cwd=work)
        report = inspect(work / "result.mp4", decode=True)
        if report["duration_ms"] is None or abs(report["duration_ms"] - project["duration_ms"]) > 1000 / fps + 25:
            raise LizicutError(f"Encoded duration mismatch: expected {project['duration_ms']}ms, got {report['duration_ms']}")
        if (report["width"], report["height"]) != (width, height) or report["audio_streams"] != 1:
            raise LizicutError("Encoded dimensions or audio stream count differ from timeline")
        if int(report.get("frames") or 0) != project["duration_ms"] * fps // 1000:
            raise LizicutError("Encoded frame count differs from timeline")
        # Recheck after encoding so an unrelated output created in the meantime is not overwritten.
        ensure_output(output, sources, overwrite)
        # A private temporary directory can have restrictive Windows ACLs.
        # Create the publication file under the output parent so normal parent
        # access is inherited, without changing any permissions or security settings.
        publication = output.parent / f".lizicut-export-{uuid.uuid4().hex}.mp4"
        try:
            with publication.open("xb") as target, (work / "result.mp4").open("rb") as source:
                shutil.copyfileobj(source, target)
            if overwrite:
                os.replace(publication, output)
            else:
                os.link(publication, output)
        finally:
            publication.unlink(missing_ok=True)
        report["file"] = str(output)
        report["warnings"] = warnings
        return report
