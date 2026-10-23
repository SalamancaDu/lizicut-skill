from __future__ import annotations

import array
import copy
import math
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/lizicut/scripts"))
from render_media import inspect, render
from timeline import LizicutError, probe, run, validate, write_srt


def alpha_png(path: Path) -> None:
    # Hidden red RGB must not bleed through zero alpha; the right half is 50% alpha.
    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))
    rows = b"".join(b"\0" + b"".join(bytes((240, 30, 20,
                       (255 if x < 80 else 128) if 40 <= x < 120 and 30 <= y < 90 else 0))
                       for x in range(160)) for y in range(120))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 160, 120, 8, 6, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "existing FFmpeg/ffprobe required for media integration")
class MediaTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="lizicut media 中文 '")
        self.base = Path(self.temporary.name)
        # Intentionally wide image, so contain must preserve it with visible top/bottom padding.
        (self.base / "红色 board.ppm").write_bytes(b"P6\n640 160\n255\n" + bytes([210, 50, 40]) * (640 * 160))
        ffmpeg = shutil.which("ffmpeg")
        run([ffmpeg, "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i", "color=c=0x24a372:s=320x180:r=25:d=2.4", "-an", "-c:v", "libx264", "-threads", "2", str(self.base / "green.mp4")])
        run([ffmpeg, "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2.4:sample_rate=48000", str(self.base / "tone.wav")])
        write_srt([{"start_ms": 80, "end_ms": 880, "text": "Chinese caption / 第一镜"}, {"start_ms": 1080, "end_ms": 2200, "text": "Second shot / 第二镜"}], self.base / "captions.srt")
        def asset(path, kind):
            return {"path": path, "kind": kind, "source_type": "designed", "source_ref": "original integration fixture", "usage": "illustration", "license": "original"}
        self.data = {
            "version": "lizicut.timeline.v1",
            "project": {"title": "媒体连接测试", "width": 320, "height": 180, "fps": 25, "duration_ms": 2400, "timing_basis": "aligned", "audio_mode": "narrated"},
            "assets": {"red": asset("红色 board.ppm", "image"), "green": asset("green.mp4", "video"), "tone": asset("tone.wav", "audio"), "srt": asset("captions.srt", "subtitle")},
            "shots": [
                {"id": "red", "start_ms": 0, "end_ms": 1000, "asset_id": "red", "fit": "contain", "carrier": "graphic", "information_shape": "focus", "purpose": "preserve image", "decision": "contain the wide board"},
                {"id": "green", "start_ms": 1000, "end_ms": 2400, "asset_id": "green", "source_in_ms": 600, "fit": "cover", "carrier": "footage", "information_shape": "focus", "purpose": "source trim", "decision": "use later source range"}],
            "audio": [
                {"id": "voice", "asset_id": "tone", "role": "narration", "start_ms": 0, "end_ms": 1200, "source_in_ms": 400, "gain": 0.7, "fade_in_ms": 40, "fade_out_ms": 40},
                {"id": "music", "asset_id": "tone", "role": "bgm", "start_ms": 0, "end_ms": 2400, "gain": 0.12, "duck_gain": 0.45, "loop": True, "fade_in_ms": 80, "fade_out_ms": 120}],
            "captions": {"asset_id": "srt", "font_name": "sans-serif", "font_size": 14, "margin_bottom": 14},
        }

    def tearDown(self):
        self.temporary.cleanup()

    def pixel(self, path: Path, seconds: float, x: int, y: int):
        result = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-ss", str(seconds), "-i", str(path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], capture_output=True, check=True)
        offset = (y * 320 + x) * 3
        return tuple(result.stdout[offset:offset + 3])

    def silent_visual(self):
        data = copy.deepcopy(self.data)
        data.pop("captions")
        data["audio"] = []
        data["project"].update(duration_ms=1000, timing_basis="fixed", audio_mode="silent", background="#00aa00")
        data["shots"] = [{**data["shots"][0], "end_ms": 1000}]
        (self.base / "background.ppm").write_bytes(b"P6\n320 180\n255\n" + bytes((0, 170, 0)) * (320 * 180))
        data["assets"]["background"] = {**data["assets"]["red"], "path": "background.ppm"}
        return data

    def test_primary_png_composites_zero_and_partial_alpha_on_project_background(self):
        alpha_png(self.base / "alpha.png")
        for fit in ("contain", "cover"):
            with self.subTest(fit=fit):
                data = self.silent_visual()
                data["assets"]["alpha"] = {**data["assets"]["red"], "path": "alpha.png"}
                data["shots"][0].update(asset_id="alpha", fit=fit)
                output = self.base / f"primary-alpha-{fit}.mp4"
                report = render(data, self.base, output)
                self.assertEqual(int(report["frames"]), 25)
                for pixel, expected in ((self.pixel(output, 0.4, 20, 90), (0, 170, 0)),
                                        (self.pixel(output, 0.4, 140, 90), (240, 30, 20)),
                                        (self.pixel(output, 0.4, 200, 90), (120, 100, 10))):
                    self.assertTrue(all(abs(a - b) < 18 for a, b in zip(pixel, expected)), (fit, pixel, expected))

    def test_webm_alpha_is_decoded_for_primary_and_scheduled_overlay(self):
        alpha_png(self.base / "alpha.png")
        for codec in ("libvpx-vp9", "libvpx"):
            source = self.base / f"alpha-{codec}.webm"
            run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-loop", "1", "-framerate", "25",
                 "-i", str(self.base / "alpha.png"), "-t", "1", "-an", "-c:v", codec, "-b:v", "400k",
                 "-auto-alt-ref", "0", "-pix_fmt", "yuva420p", "-threads", "1", str(source)])
            self.assertEqual(probe(source)["streams"][0]["tags"]["alpha_mode"], "1")
            for role in ("primary", "overlay"):
                with self.subTest(codec=codec, role=role):
                    data = self.silent_visual()
                    data["assets"]["alpha"] = {**data["assets"]["green"], "path": source.name}
                    data["shots"][0].update(asset_id="alpha" if role == "primary" else "background")
                    if role == "overlay":
                        data["overlays"] = [{"id": "alpha", "asset_id": "alpha", "role": "element", "start_ms": 200,
                                             "end_ms": 1000, "x": 0, "y": 0, "width": 320, "height": 180,
                                             "opacity": 0.5, "fade_in_ms": 200, "fade_out_ms": 200,
                                             "purpose": "transparent source", "decision": "retain alpha during scheduled fades"}]
                    output = self.base / f"webm-{codec}-{role}.mp4"
                    render(data, self.base, output)
                    transparent = self.pixel(output, 0.6, 60, 20)
                    self.assertLess(transparent[0], 18)
                    self.assertGreater(transparent[1], 150)
                    solid = self.pixel(output, 0.6, 140, 90)
                    expected = (240, 30, 20) if role == "primary" else (120, 100, 10)
                    self.assertTrue(all(abs(a - b) < 22 for a, b in zip(solid, expected)), (codec, role, solid))
                    if role == "overlay":
                        self.assertLess(self.pixel(output, 0.08, 140, 90)[0], 18)
                        self.assertLess(self.pixel(output, 0.28, 140, 90)[0], solid[0] - 40)
                        self.assertLess(self.pixel(output, 0.92, 140, 90)[0], solid[0] - 35)
        # Missing alpha decoder fails before temporary work or publication, never exports an opaque substitute.
        output = self.base / "missing-decoder.mp4"
        with patch("render_media.run", return_value=" V..... h264 H.264 decoder\n"):
            with self.assertRaisesRegex(LizicutError, "assets.alpha: alpha_mode=1 requires FFmpeg decoder libvpx"):
                render(data, self.base, output)
        self.assertFalse(output.exists())
        self.assertEqual(list(self.base.glob(".lizicut-*")), [])

    def test_anamorphic_display_ratio_is_preserved_in_main_and_overlay_fits(self):
        rows = b"".join(b"".join(bytes((20, 210, 30) if 240 <= x < 480 and 192 <= y < 384 else (220, 20, 30))
                                 for x in range(720)) for y in range(576))
        (self.base / "pal.ppm").write_bytes(b"P6\n720 576\n255\n" + rows)
        source = self.base / "pal.mp4"
        run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-loop", "1", "-framerate", "25", "-i",
             str(self.base / "pal.ppm"), "-t", "0.4", "-vf", "setsar=16/15", "-an", "-c:v", "libx264",
             "-threads", "1", str(source)])
        self.assertEqual(probe(source)["streams"][0]["sample_aspect_ratio"], "16:15")
        for role in ("primary", "overlay"):
            for fit in ("contain", "cover"):
                with self.subTest(role=role, fit=fit):
                    data = self.silent_visual()
                    data["project"].update(width=640, height=360, duration_ms=400, background="#000000")
                    data["assets"]["pal"] = {**data["assets"]["green"], "path": "pal.mp4"}
                    data["shots"][0].update(asset_id="pal" if role == "primary" else "red", end_ms=400, fit=fit)
                    if role == "overlay":
                        data["overlays"] = [{"id": "pal", "asset_id": "pal", "role": "element", "start_ms": 0,
                                             "end_ms": 400, "x": 0, "y": 0, "width": 640, "height": 360,
                                             "fit": fit, "purpose": "display ratio", "decision": "preserve non-square pixels"}]
                    output = self.base / f"pal-{role}-{fit}.mp4"
                    render(data, self.base, output)
                    result = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-ss", "0.2", "-i", str(output),
                                             "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], capture_output=True, check=True)
                    def green(x, y):
                        pixel = result.stdout[(y * 640 + x) * 3:(y * 640 + x) * 3 + 3]
                        return pixel[1] > 150 and pixel[0] < 80
                    green_width = sum(green(x, 180) for x in range(640))
                    green_height = sum(green(320, y) for y in range(360))
                    expected = (160, 120) if fit == "contain" else (213, 160)
                    self.assertLessEqual(abs(green_width - expected[0]), 2, (role, fit, green_width))
                    self.assertLessEqual(abs(green_height - expected[1]), 2, (role, fit, green_height))
                    if role == "primary" and fit == "contain":
                        bounds = [x for x in range(640) if max(result.stdout[(180 * 640 + x) * 3:(180 * 640 + x) * 3 + 3]) > 100]
                        self.assertEqual((bounds[0], bounds[-1]), (80, 559))

    def test_real_export_with_chinese_paths_trim_captions_and_audio(self):
        output = self.base / "result 视频.mp4"
        report = render(self.data, self.base, output)
        self.assertTrue(report["decoded"])
        self.assertEqual((report["width"], report["height"], report["audio_streams"]), (320, 180, 1))
        self.assertEqual(int(report["frames"]), 60)
        self.assertLess(abs(report["duration_ms"] - 2400), 45)
        center = self.pixel(output, 0.4, 160, 90)
        self.assertGreater(center[0], center[1] + 100)
        top = self.pixel(output, 0.4, 160, 10)
        self.assertLess(max(top), 70)
        green = self.pixel(output, 1.4, 160, 90)
        self.assertGreater(green[1], green[0] + 60)
        decoded = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-i", str(output), "-vn", "-ac", "1", "-ar", "48000", "-f", "f32le", "pipe:1"], capture_output=True, check=True)
        samples = array.array("f", decoded.stdout)
        self.assertGreater(len(samples), 48000 * 2.35)
        rms = math.sqrt(sum(value * value for value in samples[4800:24000]) / 19200)
        self.assertGreater(rms, 0.02)
        self.assertLess(max(abs(value) for value in samples), 1)
        with self.assertRaisesRegex(LizicutError, "already exists"):
            render(self.data, self.base, output)

    def test_muted_visual_does_not_implicitly_supply_narration(self):
        data = copy.deepcopy(self.data)
        data["audio"][0]["asset_id"] = "green"
        with self.assertRaisesRegex(LizicutError, "source has no audio"):
            validate(data, self.base, media=True)

    def test_source_exhaustion_is_reported_before_export(self):
        data = copy.deepcopy(self.data)
        data["shots"][1]["source_in_ms"] = 2000
        with self.assertRaisesRegex(LizicutError, "source has"):
            validate(data, self.base, media=True)

    def test_fixed_text_and_music_export_does_not_require_a_voice(self):
        data = copy.deepcopy(self.data)
        data["project"].update(audio_mode="nonverbal", timing_basis="fixed")
        music = data["audio"][1]
        music.pop("duck_gain")
        data["audio"] = [music]
        report = render(data, self.base, self.base / "text-and-music.mp4")
        self.assertTrue(report["decoded"])
        self.assertEqual(int(report["frames"]), 60)

    def test_many_scheduled_tracks_use_a_file_graph_and_still_export(self):
        data = copy.deepcopy(self.data)
        data["audio"] += [{"id": f"event-{i}", "asset_id": "tone", "role": "sfx", "start_ms": i * 40, "end_ms": i * 40 + 40, "gain": 0.001, "fade_in_ms": 4, "fade_out_ms": 4} for i in range(48)]
        # This exceeds 8k of filter text but uses real local inputs and output.
        report = render(data, self.base, self.base / "many-tracks.mp4")
        self.assertTrue(report["decoded"])
        self.assertEqual(int(report["frames"]), 60)

    def test_mixed_container_cannot_hide_a_short_audio_or_video_stream(self):
        for video_duration, audio_duration, selected in ((2.4, 0.4, "audio"), (0.4, 2.4, "video")):
            with self.subTest(selected=selected):
                target = self.base / f"short-{selected}.mp4"
                run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i", f"color=s=320x180:r=25:d={video_duration}", "-f", "lavfi", "-i", f"sine=duration={audio_duration}:sample_rate=48000", "-c:v", "libx264", "-threads", "2", "-c:a", "aac", str(target)])
                data = copy.deepcopy(self.data)
                data["assets"]["short"] = {**data["assets"]["green"], "path": target.name}
                if selected == "audio":
                    data["audio"][0].update(asset_id="short", source_in_ms=0)
                else:
                    data["shots"][1].update(asset_id="short", source_in_ms=0)
                with self.assertRaisesRegex(LizicutError, "source has"):
                    validate(data, self.base, media=True)

    def test_layers_have_independent_onsets_transparency_order_and_shared_exit(self):
        # Original transparent PNG, no third-party image library or asset.
        def chunk(kind, payload):
            return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))
        rows = b"".join(b"\0" + b"".join(bytes((240, 190, 30, 255 if 10 <= x < 70 and 10 <= y < 30 else 0)) for x in range(80)) for y in range(40))
        png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 80, 40, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")
        (self.base / "transparent.png").write_bytes(png)
        data = copy.deepcopy(self.data)
        data.pop("captions")
        data["assets"]["transparent"] = {**data["assets"]["red"], "path": "transparent.png"}
        data["overlays"] = [
            {"id": "card", "asset_id": "red", "role": "template", "start_ms": 200, "end_ms": 2000, "x": 10, "y": 10, "width": 120, "height": 60, "fit": "cover", "purpose": "板面", "decision": "先于关键词铺底"},
            {"id": "badge", "asset_id": "transparent", "role": "element", "start_ms": 600, "end_ms": 2000, "x": 30, "y": 20, "width": 80, "height": 40, "fade_in_ms": 200, "fade_out_ms": 200, "purpose": "关键词", "decision": "独立入场，与板面一起退出"}]
        output = self.base / "layered.mp4"
        report = render(data, self.base, output)
        self.assertEqual(int(report["frames"]), 60)
        self.assertLess(max(self.pixel(output, 0.08, 20, 20)), 70)
        self.assertGreater(self.pixel(output, 0.4, 20, 20)[0], 150)
        solid = self.pixel(output, 0.88, 60, 40)
        transparent = self.pixel(output, 0.88, 32, 22)
        self.assertGreater(solid[1], 140)
        self.assertGreater(transparent[0], transparent[1] + 100)
        # Alpha fade is between background red and fully visible yellow.
        fade = self.pixel(output, 1.92, 60, 40)
        self.assertGreater(fade[1], 60)
        self.assertLess(fade[1], solid[1] - 20)
        exited = self.pixel(output, 2.08, 60, 40)
        self.assertGreater(exited[1], exited[0] + 60)

    def test_original_sound_ducks_music_smoothly_and_holds_short_gaps(self):
        run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i", "sine=frequency=120:duration=2.4:sample_rate=48000", str(self.base / "music.wav")])
        data = copy.deepcopy(self.data)
        data.pop("captions")
        data["project"]["audio_mode"] = "original"
        data["assets"]["music"] = {**data["assets"]["tone"], "path": "music.wav"}
        data["audio"] = [
            {"id": "quote1", "asset_id": "tone", "role": "original", "start_ms": 600, "end_ms": 1200, "gain": 0.2},
            {"id": "quote2", "asset_id": "tone", "role": "original", "start_ms": 1400, "end_ms": 1700, "gain": 0.2},
            {"id": "music", "asset_id": "music", "role": "bgm", "start_ms": 0, "end_ms": 2400, "gain": 0.5, "duck_gain": 0.25}]
        output = self.base / "original-duck.mp4"
        render(data, self.base, output)
        decoded = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-i", str(output), "-vn", "-ac", "1", "-ar", "48000", "-f", "f32le", "pipe:1"], capture_output=True, check=True)
        samples = array.array("f", decoded.stdout)
        def amplitude(start, end):
            left, right = round(start * 48000), round(end * 48000)
            real = sum(samples[i] * math.cos(2 * math.pi * 120 * i / 48000) for i in range(left, right))
            imaginary = sum(samples[i] * math.sin(2 * math.pi * 120 * i / 48000) for i in range(left, right))
            return 2 * math.hypot(real, imaginary) / (right - left)
        before = amplitude(0.1, 0.3)
        under_voice = amplitude(0.8, 1.0)
        gap = amplitude(1.24, 1.36)
        recovered = amplitude(2.1, 2.3)
        release = amplitude(1.75, 1.85)
        self.assertLess(under_voice, before * 0.4)
        self.assertLess(gap, before * 0.4)
        self.assertGreater(recovered, before * 0.8)
        self.assertGreater(release, under_voice * 1.3)
        self.assertLess(release, recovered * 0.9)


if __name__ == "__main__":
    unittest.main()
