from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/lizicut/scripts"
sys.path.insert(0, str(SCRIPTS))
from materials import acquire, check_plan
import materials
from timeline import LizicutError, read_json, run, validate


def request(key: str = "warehouse", *, local: bool = False) -> dict:
    candidate = {
        "id": "choice-a", "provider": "local-fixture" if local else "HTTP-fixture",
        "query": "仓库 纸箱", "title": "自制色块测试，不是真实仓库素材",
        "page_url": "https://example.org/fixture-source", "source_type": "designed",
        "source_ref": "original synthetic test file; no external source or permission claim",
        "author": "test fixture", "published_at": None,
        "rights": {"status": "cleared", "license": "MIT", "license_url": None,
                   "attribution": "original synthetic test fixture", "basis": "created by this test for disposable local verification",
                   "redistribution": "allowed"},
        "review": {"decision": "accept", "content_checked": True, "source_checked": True,
                   "reason": "authored synthetic fixture with explicitly known dimensions; not a real semantic review"}}
    candidate.update({"local_path": "fixture.png"} if local else {"media_url": "http://127.0.0.1/fixture.png"})
    return {"id": key, "shot_ids": [f"shot-{key}"], "purpose": "verify local acquisition only",
            "kind": "image", "usage": "illustration", "queries": ["仓库 纸箱"],
            "requirements": {"min_width": 96, "min_height": 54}, "selected": "choice-a", "candidates": [candidate]}


def plan(*requests: dict) -> dict:
    return {"version": "lizicut.materials.v1", "title": "素材执行夹具", "requests": list(requests or [request()])}


class CandidateContractTests(unittest.TestCase):
    def test_unchecked_rejected_generated_evidence_and_blocked_usage_are_not_selected(self):
        cases = [({"review": {"decision": "review", "content_checked": True, "reason": "unresolved"}}, "actual content inspection"),
                 ({"review": {"decision": "accept", "content_checked": False, "reason": "not viewed"}}, "actual content inspection"),
                 ({"source_type": "generated"}, "generated media"),
                 ({"review": {"decision": "accept", "content_checked": True, "source_checked": False, "reason": "source missing"}}, "original source"),
                 ({"rights": {"status": "blocked", "redistribution": "unknown"}}, "intended use is blocked")]
        for change, message in cases:
            with self.subTest(change=change), self.assertRaisesRegex(LizicutError, message):
                data = plan()
                item = data["requests"][0]
                item["usage"] = "evidence"
                item["candidates"][0].update(change)
                item["candidates"][0].update({"locator": "fixture frame 1", "supports": "fixture dimensions only"})
                check_plan(data)
        data = plan()
        data["requests"][0].update({"selected": None, "gap": "no verified source", "candidates": []})
        self.assertEqual(check_plan(data)["gaps"][0]["reason"], "no verified source")


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "existing FFmpeg required")
class MaterialAcquisitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix="lizicut materials 中文 '")
        cls.base = Path(cls.folder.name)
        ffmpeg = shutil.which("ffmpeg")
        run([ffmpeg, "-v", "error", "-nostdin", "-f", "lavfi", "-i", "color=c=0x347d65:s=128x72",
             "-frames:v", "1", "-threads", "1", str(cls.base / "fixture.png")])
        run([ffmpeg, "-v", "error", "-nostdin", "-f", "lavfi", "-i", "color=c=0x347d65:s=128x72:r=25:d=0.8",
             "-c:v", "libx264", "-threads", "1", str(cls.base / "fixture.mp4")])
        png = (cls.base / "fixture.png").read_bytes()
        video = (cls.base / "fixture.mp4").read_bytes()
        cls.hits = {}
        hits = cls.hits

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                return None

            def do_GET(self):
                route = self.path.split("?", 1)[0]
                hits[route] = hits.get(route, 0) + 1
                if route in {"/slow-body", "/slow-headers"}:
                    try:
                        if route == "/slow-body":
                            self.send_response(200)
                            self.send_header("Content-Type", "image/png")
                            self.send_header("Content-Length", "100")
                            self.end_headers()
                        else:
                            self.wfile.write(b"HTTP/1.1 200 OK\r\n")
                        for _ in range(10):
                            self.wfile.write(b"x" * 10 if route == "/slow-body" else b"X-Slow: x\r\n")
                            self.wfile.flush()
                            time.sleep(0.22)
                    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                        return  # The timed-out download worker intentionally closed its connection.
                    return
                if route == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", "/fixture.png")
                    self.end_headers()
                    return
                body, mime = (video, "video/mp4") if route.endswith(".mp4") else (png, "image/png")
                if route == "/html":
                    body = b"<!DOCTYPE html><html>not a media file</html>"
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(2 * 1024 * 1024 if route == "/oversize" else len(body) + (64 if route == "/truncated" else 0)))
                self.end_headers()
                self.wfile.write(body)

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.server.daemon_threads = True
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.folder.cleanup()

    def test_cli_download_local_import_dedup_provenance_resume_and_timeline_handoff(self):
        remote, local, footage = request("remote"), request("local", local=True), request("footage")
        remote["candidates"][0]["media_url"] = self.url + "/redirect?token=temporary-fixture-only"
        footage["kind"] = "video"
        footage["requirements"] = {"min_width": 96, "min_height": 54, "duration_ms": 400}
        footage["candidates"][0].update({"media_url": self.url + "/fixture.mp4", "source_in_ms": 200})
        data = plan(remote, local, footage)
        original = copy.deepcopy(data)
        source = self.base / "download-plan.json"
        source.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        output = self.base / "complete"
        result = subprocess.run([sys.executable, "-X", "utf8", "-B", str(SCRIPTS / "lizicut.py"), "materials", str(source),
                                 "--output-dir", str(output), "--download"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue(json.loads(result.stdout)["ready"])
        recorded = read_json(output / "materials.json")
        self.assertEqual(recorded["acquisitions"]["remote"]["path"], recorded["acquisitions"]["local"]["path"])
        self.assertEqual(len(list((output / "files").iterdir())), 2)
        self.assertNotIn("temporary-fixture-only", (output / "materials.json").read_text(encoding="utf-8"))
        self.assertEqual(recorded["plan"]["requests"][0]["candidates"][0]["author"], "test fixture")
        self.assertEqual(recorded["bindings"][2]["source_in_ms"], 200)
        self.assertEqual(data, original)
        hits = dict(self.hits)
        second = acquire(data, self.base, output)
        self.assertTrue(second["ready"])
        self.assertEqual(second["reused_files"], 3)
        self.assertEqual(self.hits, hits)  # Completed downloads need no new network request.
        timeline = {"version": "lizicut.timeline.v1", "project": {"title": "asset handoff fixture", "width": 128, "height": 72,
                    "fps": 25, "duration_ms": 1200, "timing_basis": "fixed", "audio_mode": "silent"},
                    "assets": recorded["assets"], "shots": [], "audio": []}
        for i, binding in enumerate(recorded["bindings"]):
            timeline["shots"].append({"id": binding["shot_ids"][0], "start_ms": i * 400, "end_ms": (i + 1) * 400,
                                     "asset_id": binding["asset_id"], "source_in_ms": binding["source_in_ms"], "fit": "contain",
                                     "carrier": "footage", "information_shape": "illustration", "purpose": "fixture",
                                     "decision": "use acquired material", "evidence_refs": []})
        self.assertEqual(validate(timeline, output, media=True), [])
        self.assertEqual(hashlib.sha256((self.base / "fixture.png").read_bytes()).hexdigest(), recorded["acquisitions"]["local"]["sha256"])

    def test_bad_media_oversize_partial_and_short_stream_remain_failed_without_ready_assets(self):
        requests = []
        for key in ("html", "oversize", "truncated", "short"):
            item = request(key)
            item["candidates"][0]["media_url"] = self.url + ("/fixture.mp4" if key == "short" else f"/{key}")
            if key == "short":
                item.update({"kind": "video", "requirements": {"duration_ms": 1000}})
            requests.append(item)
        output = self.base / "failures"
        report = acquire(plan(*requests), self.base, output, allow_download=True, max_mb=1, timeout=2)
        self.assertFalse(report["ready"])
        self.assertEqual(len(report["gaps"]), 4)
        recorded = read_json(output / "materials.json")
        self.assertEqual(recorded["assets"], {})
        self.assertEqual({entry["status"] for entry in recorded["acquisitions"].values()}, {"failed"})
        self.assertEqual(list((output / "files").iterdir()), [])

    def test_unknown_rights_download_denial_and_changed_result_do_not_claim_readiness(self):
        item = request(local=True)
        item["candidates"][0]["rights"] = {"status": "unknown", "redistribution": "unknown"}
        data, output = plan(item), self.base / "unknown-rights"
        report = acquire(data, self.base, output)
        self.assertFalse(report["ready"])
        recorded = read_json(output / "materials.json")
        self.assertEqual(recorded["assets"], {})
        self.assertEqual(recorded["acquisitions"]["warehouse"]["status"], "acquired")
        with self.assertRaisesRegex(LizicutError, "different plan"):
            changed = copy.deepcopy(data)
            changed["title"] = "new plan"
            acquire(changed, self.base, output)
        path = output / recorded["acquisitions"]["warehouse"]["path"]
        path.write_bytes(b"unexpected edit")
        self.assertFalse(acquire(data, self.base, output)["ready"])
        self.assertEqual(path.read_bytes(), b"unexpected edit")
        remote = request("permission")
        remote["candidates"][0]["media_url"] = self.url + "/fixture.png"
        before = dict(self.hits)
        self.assertFalse(acquire(plan(remote), self.base, self.base / "no-network")["ready"])
        self.assertEqual(self.hits, before)

    def test_interrupted_batch_resumes_completed_file_and_stale_temp_cannot_block_it(self):
        first_source = self.base / "resume-first.png"
        shutil.copyfile(self.base / "fixture.png", first_source)
        first, second = request("resume-first", local=True), request("resume-second", local=True)
        first["candidates"][0]["local_path"] = str(first_source)
        data, output = plan(first, second), self.base / "interrupted"
        measured = materials.measured
        calls = 0

        def interrupted(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise KeyboardInterrupt("fixture cancellation after first completed acquisition")
            return measured(*args)

        with patch.object(materials, "measured", side_effect=interrupted), self.assertRaises(KeyboardInterrupt):
            acquire(data, self.base, output)
        saved = read_json(output / "materials.json")
        self.assertFalse(saved["ready"])
        self.assertEqual(saved["acquisitions"]["resume-first"]["status"], "acquired")
        self.assertNotIn("resume-second", saved["acquisitions"])
        first_source.unlink()  # Resume must use the completed copy, not reread its source.
        stale = output / ".materials.json.tmp"
        stale.write_text("{partial old write", encoding="utf-8")
        report = acquire(data, self.base, output)
        self.assertTrue(report["ready"])
        self.assertGreaterEqual(report["reused_files"], 1)
        self.assertEqual(stale.read_text(encoding="utf-8"), "{partial old write")
        self.assertEqual(len(list((output / "files").iterdir())), 1)
        stale.unlink()
        (output / "materials.json").rename(stale)
        recovered = acquire(data, self.base, output)
        self.assertTrue(recovered["ready"])
        self.assertTrue((output / "materials.json").is_file())
        self.assertEqual(recovered["reused_files"], 2)

    def test_total_timeout_stops_trickling_headers_and_body_and_discards_partial_files(self):
        for route in ("slow-headers", "slow-body"):
            with self.subTest(route=route):
                item = request(route)
                item["candidates"][0]["media_url"] = self.url + "/" + route
                output = self.base / route
                started = time.monotonic()
                report = acquire(plan(item), self.base, output, allow_download=True, timeout=1)
                elapsed = time.monotonic() - started
                self.assertFalse(report["ready"])
                self.assertIn("total timeout", report["gaps"][0]["reason"])
                self.assertLess(elapsed, 1.75, f"1s download budget was not bounded: {elapsed:.3f}s")
                self.assertEqual(list((output / "files").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
