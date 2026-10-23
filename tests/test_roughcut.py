from __future__ import annotations

import copy
import json
import math
import shutil
import subprocess
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/lizicut/scripts"))
from roughcut import compile_plan, prepare
from timeline import LizicutError, read_json, read_srt, run, write_srt


def plan() -> dict:
    # Authored decision fixture; these declarations are not a speech detector.
    return {
        "version": "lizicut.roughcut.v1", "title": "粗剪规则执行夹具",
        "source": {"path": "source.mp4", "kind": "video", "source_type": "designed", "source_ref": "original synthetic color/tone fixture, not human speech", "license": "MIT"},
        "source_duration_ms": 6000, "video": {"width": 192, "height": 108, "fps": 25},
        "decisions": [
            {"id": "retake", "start_ms": 1000, "end_ms": 2000, "action": "remove", "category": "retake",
             "reason": "discard authored alternative, retain the selected complete interval", "evidence": "fixture intervals with distinct colors and tones", "timing_checked": True,
             "related_keep": {"start_ms": 2000, "end_ms": 3000}, "visual_note": "visible hard cut retained for review; no cover was applied"},
            {"id": "breath", "start_ms": 3800, "end_ms": 4000, "action": "protect", "category": "breath",
             "reason": "preserve the authored boundary", "evidence": "explicit fixture annotation; no natural breath detection claim"},
            {"id": "uncertain", "start_ms": 3200, "end_ms": 3400, "action": "review", "category": "redundancy",
             "reason": "do not infer redundant meaning", "evidence": "unresolved review fixture"},
            {"id": "pause", "start_ms": 4000, "end_ms": 4200, "action": "remove", "category": "pause",
             "reason": "trim only the annotated gap after the protected boundary", "evidence": "authored source timing", "timing_checked": True}
        ]}


class RoughcutPlanTests(unittest.TestCase):
    def test_mapping_and_pending_material_are_preserved(self):
        data = plan()
        original = copy.deepcopy(data)
        result = compile_plan(data, Path.cwd(), media=False)
        self.assertEqual(result["cuts"]["kept_ranges"], [{"start_ms": 0, "end_ms": 1000}, {"start_ms": 2000, "end_ms": 4000}, {"start_ms": 4200, "end_ms": 6000}])
        self.assertEqual(result["duration_ms"], 4800)
        self.assertEqual([item["output_ms"] for item in result["joins"]], [1000, 3000])
        self.assertEqual(result["pending_reviews"][0]["output_start_ms"], 2200)
        for shot, track in zip(result["timeline"]["shots"], result["timeline"]["audio"]):
            self.assertEqual([shot[key] for key in ("start_ms", "end_ms", "source_in_ms")], [track[key] for key in ("start_ms", "end_ms", "source_in_ms")])
        self.assertEqual(data, original)

    def test_uncertain_protected_or_unverified_removals_are_rejected(self):
        for target, change, message in (
            (0, {"timing_checked": False}, "timing_checked"),
            (0, {"related_keep": {"start_ms": 1000, "end_ms": 2000}}, "also be deleted"),
            (3, {"start_ms": 3920}, "intersects protect"),
            (3, {"start_ms": 3200, "end_ms": 3440}, "intersects review"),
        ):
            with self.subTest(change=change), self.assertRaisesRegex(LizicutError, message):
                data = plan()
                data["decisions"][target].update(change)
                compile_plan(data, Path.cwd(), media=False)
        data = plan()
        del data["decisions"][0]["related_keep"]
        with self.assertRaisesRegex(LizicutError, "related_keep alternative"):
            compile_plan(data, Path.cwd(), media=False)

    def test_caption_crossing_deleted_words_is_not_guessed(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            write_srt([{"start_ms": 800, "end_ms": 2200, "text": "必须按实际声音拆分"}], base / "source.srt")
            data = plan()
            data["captions"] = "source.srt"
            with self.assertRaisesRegex(LizicutError, "cue 1 crosses a cut"):
                compile_plan(data, base, media=False)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "existing FFmpeg required")
class RoughcutMediaTests(unittest.TestCase):
    def test_delayed_audio_preserves_shared_clock_leading_silence_and_source_tail(self):
        with tempfile.TemporaryDirectory(prefix="lizicut shared clock ") as folder:
            base = Path(folder)
            ffmpeg = shutil.which("ffmpeg")
            source = base / "delayed.mov"
            run([ffmpeg, "-v", "error", "-nostdin", "-f", "lavfi", "-i", "color=c=green:s=128x72:r=20:d=3",
                 "-itsoffset", "0.5", "-f", "lavfi", "-i", "sine=frequency=440:duration=2.5:sample_rate=48000",
                 "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-threads", "1", "-c:a", "pcm_s16le",
                 "-output_ts_offset", "2", str(source)])
            data = {"version": "lizicut.roughcut.v1", "title": "shared clock fixture",
                    "source": {"path": source.name, "kind": "video", "source_type": "designed", "source_ref": "synthetic 500ms audio offset fixture", "license": "MIT"},
                    "source_duration_ms": 3000, "video": {"width": 128, "height": 72, "fps": 20}, "splice_fade_ms": 0,
                    "decisions": [{"id": "gap", "start_ms": 200, "end_ms": 600, "action": "remove", "category": "pause",
                                   "reason": "test an entirely silent kept range followed by source audio", "evidence": "authored synthetic timing", "timing_checked": True}]}
            bundle = compile_plan(data, base)
            self.assertAlmostEqual(bundle["source_timing"]["audio"]["start_ms"], 500)
            self.assertAlmostEqual(bundle["source_timing"]["audio"]["end_ms"], 3000)
            wrong = copy.deepcopy(data)
            wrong["source_duration_ms"] = 2500
            with self.assertRaisesRegex(LizicutError, "silently discarding the tail"):
                compile_plan(wrong, base)
            result = prepare(data, base, base / "video", render_now=True, threads=1)
            self.assertEqual(result["duration_ms"], 2600)

            def rms_at(path, start):
                raw = subprocess.run([ffmpeg, "-v", "error", "-ss", str(start), "-i", str(path), "-t", "0.1", "-map", "0:a:0",
                                      "-ac", "1", "-ar", "48000", "-f", "f32le", "pipe:1"], capture_output=True, check=True).stdout
                samples = struct.unpack("<" + "f" * (len(raw) // 4), raw)
                self.assertTrue(samples)
                return math.sqrt(sum(value * value for value in samples) / len(samples))

            self.assertLess(rms_at(base / "video/roughcut.mp4", 0), 0.001)
            self.assertGreater(rms_at(base / "video/roughcut.mp4", 0.3), 0.05)
            self.assertGreater(rms_at(base / "video/roughcut.mp4", 2.4), 0.05)
            data["source"]["kind"] = "audio"
            del data["video"]
            data["decisions"][0].update({"start_ms": 1500, "end_ms": 2000})
            prepare(data, base, base / "audio", render_now=True)
            self.assertLess(rms_at(base / "audio/roughcut.wav", 0.2), 0.001)
            self.assertGreater(rms_at(base / "audio/roughcut.wav", 0.7), 0.05)
            self.assertGreater(rms_at(base / "audio/roughcut.wav", 2.3), 0.05)

    def test_cli_video_and_audio_export_share_the_exact_edit_mapping(self):
        with tempfile.TemporaryDirectory(prefix="lizicut roughcut 中文 '") as folder:
            base = Path(folder)
            ffmpeg = shutil.which("ffmpeg")
            run([ffmpeg, "-v", "error", "-nostdin", "-y", "-filter_threads", "1", "-f", "lavfi", "-i", "color=c=0x249b74:s=192x108:r=25:d=6",
                 "-f", "lavfi", "-i", "sine=frequency=440:duration=6:sample_rate=48000",
                 "-vf", "drawbox=x=0:y=0:w=iw:h=ih:color=0xc94439:t=fill:enable='gte(t,1)*lt(t,2)'",
                 "-c:v", "libx264", "-threads", "2", "-c:a", "aac", str(base / "source.mp4")])
            cues = [{"start_ms": 40, "end_ms": 800, "text": "保留第一句"}, {"start_ms": 1040, "end_ms": 1800, "text": "删除的夹具段"},
                    {"start_ms": 2040, "end_ms": 2800, "text": "保留选择段"}, {"start_ms": 3040, "end_ms": 3800, "text": "保留完整对比与待复核内容"},
                    {"start_ms": 4240, "end_ms": 5800, "text": "保留最后一句"}]
            write_srt(cues, base / "source.srt")
            data = plan()
            data["captions"] = "source.srt"
            (base / "plan.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            cli = Path(__file__).resolve().parents[1] / "skills/lizicut/scripts/lizicut.py"
            run([sys.executable, "-X", "utf8", "-B", str(cli), "roughcut", str(base / "plan.json"), "--output-dir", str(base / "video"), "--render"])
            cut = read_json(base / "video/timeline.json")
            self.assertEqual(cut["project"]["duration_ms"], 4800)
            self.assertEqual(read_srt(base / "video/captions.srt")[1]["start_ms"], 1040)
            output_map = read_json(base / "video/roughcut-map.json")
            self.assertEqual(output_map["pending_reviews"][0]["output_end_ms"], 2400)
            # The removed red source interval must not survive in the output.
            frame = subprocess.run([ffmpeg, "-v", "error", "-ss", "1.24", "-i", str(base / "video/roughcut.mp4"), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], check=True, capture_output=True).stdout
            self.assertGreater(frame[1], frame[0] + 40)
            invalid = copy.deepcopy(data)
            invalid["decisions"][3]["start_ms"] = 3920
            with self.assertRaisesRegex(LizicutError, "intersects protect"):
                prepare(invalid, base, base / "unwritten", render_now=True)
            self.assertFalse((base / "unwritten").exists())
            truncated = copy.deepcopy(data)
            truncated["source_duration_ms"] = 5800
            with self.assertRaisesRegex(LizicutError, "silently discarding the tail"):
                prepare(truncated, base, base / "truncated", render_now=True)
            self.assertFalse((base / "truncated").exists())
            run([ffmpeg, "-v", "error", "-nostdin", "-y", "-i", str(base / "source.mp4"), "-vn", "-c:a", "pcm_s16le", str(base / "source.wav")])
            data["source"].update(path="source.wav", kind="audio")
            del data["video"]
            result = prepare(data, base, base / "audio", render_now=True)
            self.assertTrue(result["media"]["decoded"])
            with wave.open(str(base / "audio/roughcut.wav"), "rb") as audio:
                self.assertEqual(audio.getnframes(), 48000 * 4800 // 1000)
            self.assertEqual(read_json(base / "audio/cuts.json"), read_json(base / "video/cuts.json"))
            with self.assertRaisesRegex(LizicutError, "already exists"):
                prepare(data, base, base / "audio")


if __name__ == "__main__":
    unittest.main()
