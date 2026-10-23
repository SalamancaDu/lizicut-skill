from __future__ import annotations

import copy
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/lizicut/scripts"))
from render_media import ensure_output, render
from timeline import LizicutError, read_json, read_srt, retime, stream_duration_ms, validate, write_srt


def sample() -> dict:
    return {
        "version": "lizicut.timeline.v1",
        "project": {"title": "测试", "width": 320, "height": 180, "fps": 25, "duration_ms": 2000, "timing_basis": "fixed", "audio_mode": "silent"},
        "assets": {"board": {"path": "board.png", "kind": "image", "source_type": "designed", "source_ref": "原创测试示意", "usage": "illustration", "license": "original"}},
        "shots": [{"id": "s1", "start_ms": 0, "end_ms": 2000, "asset_id": "board", "carrier": "graphic", "information_shape": "comparison", "purpose": "看清差异", "decision": "同板比较"}],
        "audio": [],
    }


class TimelineTests(unittest.TestCase):
    def test_silent_fixed_duration_is_a_valid_clock(self):
        self.assertEqual(validate(sample(), Path.cwd()), [])

    def test_gap_overlap_and_off_frame_boundary_are_rejected(self):
        for change in ({"start_ms": 40}, {"end_ms": 1960}, {"end_ms": 1999}):
            with self.subTest(change=change), self.assertRaises(LizicutError):
                data = sample()
                data["shots"][0].update(change)
                validate(data, Path.cwd())

    def test_estimated_timing_cannot_render_final_even_before_media_exists(self):
        data = sample()
        data["project"]["timing_basis"] = "estimated"
        self.assertTrue(validate(data, Path.cwd()))
        with self.assertRaisesRegex(LizicutError, "estimated timing"):
            render(data, Path.cwd(), Path("unwritten.mp4"))

    def test_generated_image_is_not_evidence(self):
        data = sample()
        data["assets"]["board"].update(source_type="generated", usage="evidence")
        with self.assertRaisesRegex(LizicutError, "cannot be factual evidence"):
            validate(data, Path.cwd())

    def test_illustration_cannot_be_referenced_as_evidence(self):
        data = sample()
        data["shots"][0]["evidence_refs"] = ["board"]
        with self.assertRaisesRegex(LizicutError, "cannot serve as factual evidence"):
            validate(data, Path.cwd())

    def test_narrated_project_requires_an_explicit_sound_track(self):
        data = sample()
        data["project"]["audio_mode"] = "narrated"
        with self.assertRaisesRegex(LizicutError, "requires at least one narration"):
            validate(data, Path.cwd())

    def test_mistyped_render_effect_is_not_silently_ignored(self):
        data = sample()
        data["shots"][0]["motion"] = "make it cinematic"
        with self.assertRaisesRegex(LizicutError, "unsupported fields"):
            validate(data, Path.cwd())

    def test_trimmed_loop_requires_prepared_asset(self):
        data = sample()
        data["assets"]["board"]["kind"] = "video"
        data["shots"][0].update(loop=True, source_in_ms=500)
        with self.assertRaisesRegex(LizicutError, "trimmed loop asset"):
            validate(data, Path.cwd())

    def test_nonfinite_gains_and_excessive_fades_are_rejected(self):
        for change in ({"gain": float("nan")}, {"gain": float("inf")}, {"fade_in_ms": 1600, "fade_out_ms": 1000}):
            with self.subTest(change=change), self.assertRaises(LizicutError):
                data = sample()
                data["project"]["audio_mode"] = "narrated"
                data["assets"]["voice"] = {**data["assets"]["board"], "path": "voice.wav", "kind": "audio"}
                data["audio"] = [{"id": "v1", "asset_id": "voice", "role": "narration", "start_ms": 0, "end_ms": 2000, **change}]
                validate(data, Path.cwd())

    def test_asset_paths_are_relative_to_timeline_not_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            data = sample()
            with self.assertRaisesRegex(LizicutError, re.escape(str((Path(directory) / "board.png").resolve()))):
                validate(data, Path(directory), media=True)

    def test_input_cannot_be_overwritten_even_with_overwrite_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.mp4"
            path.write_bytes(b"original")
            with self.assertRaisesRegex(LizicutError, "replace an input"):
                ensure_output(path, [path], True)
            self.assertEqual(path.read_bytes(), b"original")

    def test_duplicate_json_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text('{"assets":{},"assets":{}}', encoding="utf-8")
            with self.assertRaisesRegex(LizicutError, "Duplicate JSON key"):
                read_json(path)

    def test_stream_duration_does_not_borrow_a_longer_sibling_or_container(self):
        info = {"format": {"duration": "10"}, "streams": [{"codec_type": "video", "duration": "10"}, {"codec_type": "audio", "duration": "2"}]}
        self.assertEqual(stream_duration_ms(info, "audio"), 2000)
        del info["streams"][1]["duration"]
        self.assertIsNone(stream_duration_ms(info, "audio"))
        info["streams"][1].update(duration_ts=96000, time_base="1/48000")
        self.assertEqual(stream_duration_ms(info, "audio"), 2000)

    def test_zero_gain_does_not_satisfy_required_voice(self):
        data = sample()
        data["project"]["audio_mode"] = "narrated"
        data["assets"]["voice"] = {**data["assets"]["board"], "kind": "audio", "path": "voice.wav"}
        data["audio"] = [{"id": "v", "asset_id": "voice", "role": "narration", "start_ms": 0, "end_ms": 2000, "gain": 0}]
        with self.assertRaisesRegex(LizicutError, "requires at least one narration"):
            validate(data, Path.cwd())

    def test_text_led_film_can_have_music_without_forcing_narration(self):
        data = sample()
        data["project"]["audio_mode"] = "nonverbal"
        data["assets"]["music"] = {**data["assets"]["board"], "kind": "audio", "path": "music.wav"}
        data["audio"] = [{"id": "bgm", "asset_id": "music", "role": "bgm", "start_ms": 0, "end_ms": 2000, "gain": 0.1}]
        self.assertEqual(validate(data, Path.cwd()), [])
        data["audio"][0]["role"] = "narration"
        with self.assertRaisesRegex(LizicutError, "nonverbal project requires"):
            validate(data, Path.cwd())

    def test_overlay_contract_rejects_off_frame_outside_or_unsupported_masks(self):
        for change in ({"start_ms": 1}, {"x": 300}, {"end_ms": 2400}, {"fade_in_ms": 1600, "fade_out_ms": 600}, {"mask": "circle"}):
            with self.subTest(change=change), self.assertRaises(LizicutError):
                data = sample()
                data["overlays"] = [{"id": "o1", "asset_id": "board", "role": "element", "start_ms": 0, "end_ms": 2000, "x": 10, "y": 10, "width": 100, "height": 80, "purpose": "主体", "decision": "按关键词出现", **change}]
                validate(data, Path.cwd())


class CaptionTests(unittest.TestCase):
    def test_retime_removes_deleted_cues_and_maps_source_to_output(self):
        cues = [{"start_ms": 100, "end_ms": 800, "text": "保留甲"}, {"start_ms": 1200, "end_ms": 1800, "text": "删掉"}, {"start_ms": 2200, "end_ms": 2800, "text": "保留乙"}]
        original = copy.deepcopy(cues)
        cuts = {"source_duration_ms": 3000, "kept_ranges": [{"start_ms": 0, "end_ms": 1000}, {"start_ms": 2000, "end_ms": 3000}]}
        output = retime(cues, cuts)
        self.assertEqual([cue["text"] for cue in output], ["保留甲", "保留乙"])
        self.assertEqual((output[1]["start_ms"], output[1]["end_ms"]), (1200, 1800))
        self.assertEqual(cues, original)

    def test_cross_cut_caption_is_not_duplicated_or_guessed(self):
        cuts = {"source_duration_ms": 3000, "kept_ranges": [{"start_ms": 0, "end_ms": 1000}, {"start_ms": 2000, "end_ms": 3000}]}
        with self.assertRaisesRegex(LizicutError, "cue 1 crosses a cut"):
            retime([{"start_ms": 800, "end_ms": 2300, "text": "需要根据声音拆分的整句"}], cuts)

    def test_touching_kept_ranges_do_not_create_a_false_cut(self):
        cuts = {"source_duration_ms": 2000, "kept_ranges": [{"start_ms": 0, "end_ms": 1000}, {"start_ms": 1000, "end_ms": 2000}]}
        cue = {"start_ms": 800, "end_ms": 1200, "text": "连续语句"}
        self.assertEqual(retime([cue], cuts), [cue])

    def test_unsorted_and_overlapping_kept_ranges_are_rejected(self):
        cuts = {"source_duration_ms": 3000, "kept_ranges": [{"start_ms": 500, "end_ms": 2000}, {"start_ms": 1500, "end_ms": 2500}]}
        with self.assertRaises(LizicutError):
            retime([], cuts)

    def test_srt_round_trip_preserves_chinese_and_explicit_linebreaks(self):
        cues = [{"start_ms": 0, "end_ms": 1120, "text": "营收与利润\n不是同一个指标"}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "中文字幕.srt"
            write_srt(cues, path)
            self.assertEqual(read_srt(path), cues)
            self.assertFalse(path.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_invalid_clocks_and_overlap_include_cue_context(self):
        for content in ("1\n00:70:00,000 --> 00:70:01,000\n错", "1\n00:00:00,000 --> 00:00:02,000\n甲\n\n2\n00:00:01,000 --> 00:00:03,000\n乙"):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "invalid.srt"
                path.write_text(content, encoding="utf-8")
                with self.assertRaises(LizicutError):
                    read_srt(path)


if __name__ == "__main__":
    unittest.main()
