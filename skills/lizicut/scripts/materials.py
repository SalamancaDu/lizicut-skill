"""Acquire reviewed material candidates and preserve their editorial provenance."""
from __future__ import annotations

import copy
import hashlib
import http.client
import json
import mimetypes
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from timeline import LizicutError, choice, integer, probe, read_json, stream_window_ms, text


SOURCE_TYPES = {"user", "document", "stock", "generated", "designed", "synthetic_audio"}
IMAGE_CODECS = {"png", "mjpeg", "webp", "gif", "bmp", "tiff", "jpeg2000", "av1"}
EXTENSIONS = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif",
              "image/bmp": ".bmp", "image/tiff": ".tif", "image/avif": ".avif", "video/mp4": ".mp4",
              "video/webm": ".webm", "video/quicktime": ".mov", "video/x-msvideo": ".avi",
              "video/x-matroska": ".mkv", "audio/wav": ".wav", "audio/x-wav": ".wav",
              "audio/mpeg": ".mp3", "audio/flac": ".flac", "audio/x-flac": ".flac", "audio/mp4": ".m4a",
              "audio/ogg": ".ogg", "application/ogg": ".ogg", "audio/aac": ".aac"}


def identifier(value: object, context: str) -> str:
    value = text(value, context)
    if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]{0,63}", value):
        raise LizicutError(f"{context}: use a letter followed by at most 63 letters, digits, _ or -")
    return value


def http_url(value: object) -> str:
    value = text(value, "URL")
    try:
        parts = urllib.parse.urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            raise ValueError("expected HTTP(S) URL without embedded credentials")
        _ = parts.port
    except ValueError as error:
        raise LizicutError("Invalid HTTP(S) URL; embedded credentials are not supported") from error
    return value


def public_url(value: str, *, media: bool = False) -> str:
    """Do not persist signed download query strings or common credential parameters."""
    parts = urllib.parse.urlsplit(value)
    query = [] if media else [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
                              if not re.search(r"token|secret|signature|credential|api.?key|authorization|^key$|^sig$|^policy$|^x-amz-|^x-goog-", k, re.I)]
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), ""))


def checked_object(value: object, context: str, allowed: set[str]) -> dict:
    if not isinstance(value, dict) or set(value) - allowed:
        raise LizicutError(f"{context}: expected object with only {sorted(allowed)}")
    return value


def check_plan(plan: dict) -> dict:
    checked_object(plan, "materials", {"version", "title", "requests"})
    if plan.get("version") != "lizicut.materials.v1":
        raise LizicutError("version: expected lizicut.materials.v1")
    text(plan.get("title"), "title")
    requests = plan.get("requests")
    if not isinstance(requests, list) or not requests:
        raise LizicutError("requests: expected nonempty list")
    ids, selected, gaps = set(), 0, []
    for request in requests:
        checked_object(request, "request", {"id", "shot_ids", "purpose", "usage", "kind", "queries", "requirements", "selected", "gap", "candidates"})
        key = identifier(request.get("id"), "request.id")
        if key in ids:
            raise LizicutError(f"Duplicate request id: {key}")
        ids.add(key)
        text(request.get("purpose"), f"{key}.purpose")
        choice(request.get("usage"), {"evidence", "illustration"}, f"{key}.usage")
        choice(request.get("kind"), {"image", "video", "audio"}, f"{key}.kind")
        shots = request.get("shot_ids")
        if not isinstance(shots, list) or not shots or any(not isinstance(s, str) or not s.strip() for s in shots):
            raise LizicutError(f"{key}.shot_ids: expected target shot ids")
        queries = request.get("queries", [])
        if not isinstance(queries, list) or any(not isinstance(q, str) or not q.strip() for q in queries):
            raise LizicutError(f"{key}.queries: expected query strings; use [] when reusing local material")
        requirements = checked_object(request.get("requirements", {}), f"{key}.requirements", {"min_width", "min_height", "duration_ms"})
        for name, value in requirements.items():
            integer(value, f"{key}.requirements.{name}")
        candidates = request.get("candidates", [])
        if not isinstance(candidates, list):
            raise LizicutError(f"{key}.candidates: expected list")
        by_id = {}
        for candidate in candidates:
            checked_object(candidate, f"{key}.candidate", {"id", "provider", "query", "title", "page_url", "media_url", "preview_url", "local_path", "source_type", "source_ref", "author", "published_at", "locator", "supports", "source_in_ms", "rights", "review"})
            cid = identifier(candidate.get("id"), f"{key}.candidate.id")
            if cid in by_id:
                raise LizicutError(f"{key}: duplicate candidate id {cid}")
            by_id[cid] = candidate
            for name in ("provider", "title", "source_ref"):
                text(candidate.get(name), f"{key}.{cid}.{name}")
            for name in ("query", "local_path", "author", "published_at", "locator", "supports"):
                if candidate.get(name) is not None:
                    text(candidate[name], f"{key}.{cid}.{name}")
            choice(candidate.get("source_type"), SOURCE_TYPES, f"{key}.{cid}.source_type")
            if candidate.get("query") and candidate["query"] not in queries:
                raise LizicutError(f"{key}.{cid}.query: must be one of this request's queries")
            for name in ("page_url", "media_url", "preview_url"):
                if candidate.get(name):
                    http_url(candidate[name])
            review = checked_object(candidate.get("review"), f"{key}.{cid}.review", {"decision", "content_checked", "source_checked", "reason"})
            choice(review.get("decision"), {"accept", "reject", "review"}, f"{key}.{cid}.review.decision")
            text(review.get("reason"), f"{key}.{cid}.review.reason")
            for flag in ("content_checked", "source_checked"):
                if flag in review and type(review[flag]) is not bool:
                    raise LizicutError(f"{key}.{cid}.review.{flag}: expected boolean")
            rights = checked_object(candidate.get("rights"), f"{key}.{cid}.rights", {"status", "license", "license_url", "attribution", "basis", "redistribution"})
            choice(rights.get("status"), {"cleared", "unknown", "blocked"}, f"{key}.{cid}.rights.status")
            choice(rights.get("redistribution", "unknown"), {"allowed", "unknown", "prohibited"}, f"{key}.{cid}.rights.redistribution")
            for name in ("license", "attribution", "basis"):
                if rights.get(name) is not None:
                    text(rights[name], f"{key}.{cid}.rights.{name}")
            if rights.get("license_url"):
                http_url(rights["license_url"])
            if rights["status"] == "cleared":
                text(rights.get("license"), f"{key}.{cid}.rights.license")
                text(rights.get("basis"), f"{key}.{cid}.rights.basis")
            integer(candidate.get("source_in_ms", 0), f"{key}.{cid}.source_in_ms")
        cid = request.get("selected")
        if cid is None:
            gaps.append({"request_id": key, "reason": text(request.get("gap"), f"{key}.gap")})
            continue
        identifier(cid, f"{key}.selected")
        if cid not in by_id:
            raise LizicutError(f"{key}.selected: missing candidate {cid}")
        candidate = by_id[cid]
        if candidate["review"]["decision"] != "accept" or candidate["review"].get("content_checked") is not True:
            raise LizicutError(f"{key}: selected candidate must be accepted after actual content inspection")
        if bool(candidate.get("local_path")) == bool(candidate.get("media_url")):
            raise LizicutError(f"{key}: selected candidate needs exactly one local_path or direct media_url")
        if not candidate.get("local_path") and (not candidate.get("page_url") or not candidate.get("query")):
            raise LizicutError(f"{key}: searched download requires page_url and the actual query")
        if candidate["rights"]["status"] == "blocked":
            raise LizicutError(f"{key}: selected candidate's intended use is blocked")
        if request["usage"] == "evidence":
            if candidate["source_type"] in {"generated", "synthetic_audio"}:
                raise LizicutError(f"{key}: generated media cannot be factual evidence")
            if candidate["review"].get("source_checked") is not True:
                raise LizicutError(f"{key}: factual evidence requires inspection of the original source")
            for name in ("supports", "locator"):
                text(candidate.get(name), f"{key}.{cid}.{name}")
        selected += 1
    return {"valid": True, "selected": selected, "gaps": gaps,
            "boundary": "review/rights fields are authored declarations, not machine proof of meaning or permission"}


class Redirects(urllib.request.HTTPRedirectHandler):
    max_redirections = 5
    max_repeats = 2

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        http_url(newurl)
        if urllib.parse.urlsplit(req.full_url).scheme == "https" and urllib.parse.urlsplit(newurl).scheme != "https":
            raise LizicutError("Refused HTTPS to HTTP download redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def copy_bytes(source, target, max_bytes: int, deadline: float) -> tuple[str, int]:
    digest, size = hashlib.sha256(), 0
    while True:
        chunk = source.read(64 * 1024)
        if time.monotonic() > deadline:
            raise LizicutError("Acquisition exceeded its total timeout; no automatic retry")
        if not chunk:
            break
        size += len(chunk)
        if size > max_bytes:
            raise LizicutError("Material exceeds --max-mb; partial file discarded")
        target.write(chunk)
        digest.update(chunk)
    if not size:
        raise LizicutError("Empty material file")
    return digest.hexdigest(), size


def measured(path: Path, request: dict, candidate: dict) -> dict:
    with path.open("rb") as source:
        header = source.read(128).lstrip().lower()
    if header.startswith((b"<!doctype", b"<html", b"{", b"[", b"#extm3u", b"<svg", b"<?xml")):
        raise LizicutError("Received a page, playlist or text response instead of supported self-contained media")
    info = probe(path)
    kind = request["kind"]
    stream_kind = "audio" if kind == "audio" else "video"
    stream = next((s for s in info.get("streams", []) if s.get("codec_type") == stream_kind), None)
    if stream is None:
        raise LizicutError(f"Material has no {stream_kind} stream")
    if kind == "image":
        with path.open("rb") as source:
            magic = source.read(32)
        is_image = (magic.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a", b"BM", b"II*\x00", b"MM\x00*"))
                    or magic[:4] == b"RIFF" and magic[8:12] == b"WEBP"
                    or magic[4:8] == b"ftyp" and magic[8:12] in {b"avif", b"avis"})
        if not is_image or stream.get("codec_name") not in IMAGE_CODECS:
            raise LizicutError("Expected a supported image, received other media")
        if candidate.get("source_in_ms", 0):
            raise LizicutError("Still images must use source_in_ms=0")
    requirements = request.get("requirements", {})
    width, height = stream.get("width", 0), stream.get("height", 0)
    for name, value in (("min_width", width), ("min_height", height)):
        if value < requirements.get(name, 0):
            raise LizicutError(f"Material {name} requirement not met: {value} < {requirements[name]}")
    window = None if kind == "image" else stream_window_ms(info, stream_kind)
    duration = window[1] - window[0] if window else None
    if kind == "video" and window and candidate.get("source_in_ms", 0) < window[0] - 1:
        raise LizicutError("Requested video range precedes its first frame; prepare a synchronized source master")
    if kind != "image" and (window is None or window[1] < candidate.get("source_in_ms", 0) + requirements.get("duration_ms", 0)):
        raise LizicutError("Selected stream is too short or its usable duration is unknown")
    return {"codec": stream.get("codec_name"), "width": width, "height": height, "duration_ms": duration,
            "source_start_ms": window[0] if window else None,
            "source_end_ms": window[1] if window else None,
            "check": "ffprobe first selected stream on the shared source clock; semantic correctness and full decode are not inferred"}


def fetch_download(url: str, target, max_bytes: int, timeout: int) -> tuple[str, int, str, str]:
    """Worker-side bounded streaming; the parent enforces the hard wall clock."""
    request = urllib.request.Request(http_url(url), headers={"User-Agent": "lizicut-materials/0.1.6", "Accept-Encoding": "identity"})
    deadline = time.monotonic() + timeout
    try:
        with urllib.request.build_opener(Redirects()).open(request, timeout=timeout) as response:
            if response.status != 200 or response.headers.get("Content-Range"):
                raise LizicutError("Expected a complete HTTP 200 media response")
            mime = response.headers.get_content_type()
            if mime not in EXTENSIONS and mime != "application/octet-stream":
                raise LizicutError(f"Unsupported media Content-Type: {mime}; use a real media download or local capture")
            length = response.headers.get("Content-Length")
            if length is not None and (not length.isdigit() or int(length) > max_bytes):
                raise LizicutError("Invalid or oversized Content-Length")
            digest, size = copy_bytes(response, target, max_bytes, deadline)
            if length is not None and size != int(length):
                raise LizicutError("Incomplete download: received size differs from Content-Length")
            return digest, size, mime, public_url(response.geturl(), media=True)
    except urllib.error.HTTPError as error:
        raise LizicutError(f"Download HTTP {error.code}; refresh the original download link or inspect access, no automatic retry") from error
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as error:
        raise LizicutError(f"Download failed ({type(error).__name__}); inspect connectivity or source access, no automatic retry") from error


def download(candidate: dict, target: Path, max_bytes: int, timeout: int) -> tuple[str, int, str, str]:
    # A socket timeout alone can be renewed indefinitely by trickling headers or
    # body bytes. A disposable process also bounds DNS/connect/TLS/header reads.
    job = {"url": http_url(candidate["media_url"]), "target": str(target), "max_bytes": max_bytes, "timeout": timeout}
    try:
        process = subprocess.run([sys.executable, "-X", "utf8", "-B", str(Path(__file__).resolve()), "--download-worker"],
                                 input=json.dumps(job), capture_output=True, text=True, encoding="utf-8", timeout=timeout,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except subprocess.TimeoutExpired as error:
        raise LizicutError(f"Download exceeded total timeout ({timeout}s); worker stopped, no automatic retry") from error
    if process.returncode:
        try:
            message = json.loads(process.stdout)["error"]
        except (json.JSONDecodeError, KeyError, TypeError):
            message = f"Download worker failed ({process.returncode}); no automatic retry"
        raise LizicutError(message)
    try:
        digest, size, mime, final_url = json.loads(process.stdout)["result"]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise LizicutError("Download worker returned invalid metadata") from error
    return digest, size, mime, final_url


def download_worker() -> int:
    try:
        job = json.load(sys.stdin)
        with Path(job["target"]).open("wb") as target:
            result = fetch_download(job["url"], target, job["max_bytes"], job["timeout"])
        print(json.dumps({"result": result}))
        return 0
    except (LizicutError, OSError, ValueError, KeyError) as error:
        print(json.dumps({"error": str(error)}))
        return 2


def fingerprint(plan: dict) -> str:
    return hashlib.sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def stored_plan(plan: dict) -> dict:
    plan = copy.deepcopy(plan)
    for request in plan["requests"]:
        for candidate in request.get("candidates", []):
            for name in ("page_url", "media_url", "preview_url"):
                if candidate.get(name):
                    candidate[name] = public_url(candidate[name], media=name != "page_url")
            if candidate["rights"].get("license_url"):
                candidate["rights"]["license_url"] = public_url(candidate["rights"]["license_url"])
    return plan


def save_manifest(path: Path, result: dict) -> None:
    """Persist only complete checkpoints; unrelated stale temp names cannot block."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent,
                                         prefix=".materials-", suffix=".json.tmp", delete=False) as target:
            temporary = Path(target.name)
            json.dump(result, target, ensure_ascii=False, indent=2)
            target.write("\n")
            target.flush()
            os.fsync(target.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def acquire(plan: dict, base: Path, output: Path, *, allow_download: bool = False, max_mb: int = 128, timeout: int = 20) -> dict:
    validation = check_plan(plan)
    integer(max_mb, "max_mb", 1, 4096)
    integer(timeout, "timeout", 1, 300)
    output = output.resolve()
    plan_hash = fingerprint(plan)
    manifest = output / "materials.json"
    result = {"version": "lizicut.materials.result.v1", "plan_sha256": plan_hash, "plan": stored_plan(plan), "acquisitions": {}}
    if output.exists():
        checkpoint = manifest if manifest.is_file() else output / ".materials.json.tmp"
        if not checkpoint.is_file():
            raise LizicutError("Output directory is not a managed materials result; use a new directory")
        result = read_json(checkpoint)
        if result.get("version") != "lizicut.materials.result.v1" or result.get("plan_sha256") != plan_hash:
            raise LizicutError("Existing result belongs to a different plan; preserve it and use a new output directory")
        if not isinstance(result.get("acquisitions"), dict):
            raise LizicutError("Managed materials checkpoint has invalid acquisitions; preserve it and use a new directory")
    if (output / "files").exists() and (output / "files").resolve() != output / "files":
        raise LizicutError("Output files directory must not redirect to another directory")
    (output / "files").mkdir(parents=True, exist_ok=True)
    result.update({"assets": {}, "bindings": [], "gaps": list(validation["gaps"]), "ready": False})
    save_manifest(manifest, result)
    reused = 0
    for request in plan["requests"]:
        if request.get("selected") is None:
            continue
        key = request["id"]
        candidate = next(c for c in request["candidates"] if c["id"] == request["selected"])
        prior = result["acquisitions"].get(key, {})
        temporary = None
        try:
            if prior.get("status") == "acquired":
                path = (output / text(prior.get("path"), "stored path")).resolve()
                if not path.is_relative_to(output / "files") or not path.is_file() or file_hash(path) != prior.get("sha256"):
                    raise LizicutError("Previously acquired file is missing or changed; preserve the result and use a new output directory")
                measured(path, request, candidate)
                reused += 1
                record = prior
            else:
                descriptor, name = tempfile.mkstemp(dir=output / "files", prefix=".download-", suffix=".part")
                os.close(descriptor)
                temporary = Path(name)
                if candidate.get("local_path"):
                    source = (base / text(candidate["local_path"], "local_path")).resolve()
                    if not source.is_file():
                        raise LizicutError(f"Local material is missing: {source}")
                    with source.open("rb") as opened, temporary.open("wb") as target:
                        digest, size = copy_bytes(opened, target, max_mb * 1024 * 1024, time.monotonic() + timeout)
                    mime = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
                    suffix = source.suffix.lower()
                    final_url = None
                else:
                    if not allow_download:
                        raise LizicutError("Remote acquisition needs --download; use it only within the task's existing download authorization")
                    digest, size, mime, final_url = download(candidate, temporary, max_mb * 1024 * 1024, timeout)
                    suffix = Path(urllib.parse.urlsplit(candidate["media_url"]).path).suffix.lower()
                media = measured(temporary, request, candidate)
                extension = EXTENSIONS.get(mime, suffix if suffix in set(EXTENSIONS.values()) else ".bin")
                matches = sorted((output / "files").glob(f"{digest}.*"))
                path = matches[0] if matches else output / "files" / f"{digest}{extension}"
                if path.exists():
                    if path.is_symlink() or file_hash(path) != digest:
                        raise LizicutError("Existing content-addressed material changed; refusing to replace it")
                    reused += 1
                else:
                    with path.open("xb") as destination:
                        try:
                            with temporary.open("rb") as source:
                                copy_bytes(source, destination, max_mb * 1024 * 1024, time.monotonic() + timeout)
                        except (LizicutError, OSError):
                            destination.close()
                            path.unlink(missing_ok=True)
                            raise
                record = {"status": "acquired", "candidate_id": candidate["id"], "path": path.relative_to(output).as_posix(),
                          "sha256": digest, "bytes": size, "content_type": mime, "final_url": final_url,
                          "acquired_at": datetime.now(timezone.utc).isoformat(), "media": media}
            result["acquisitions"][key] = record
            if candidate["rights"]["status"] != "cleared":
                result["gaps"].append({"request_id": key, "reason": "File acquired for inspection; intended-use rights remain unknown"})
            else:
                asset_id = f"material-{key}"
                provenance = " | ".join(str(v) for v in (candidate["source_ref"], public_url(candidate["page_url"]) if candidate.get("page_url") else None,
                                                         candidate.get("locator"), candidate.get("supports"), f"materials.json request={key}") if v)
                result["assets"][asset_id] = {"path": record["path"], "kind": request["kind"], "source_type": candidate["source_type"],
                                                "source_ref": provenance, "usage": request["usage"], "license": candidate["rights"]["license"],
                                                "note": " | ".join(v for v in (candidate["rights"].get("attribution"), candidate["rights"]["basis"]) if v)}
                result["bindings"].append({"request_id": key, "asset_id": asset_id, "shot_ids": request["shot_ids"], "source_in_ms": candidate.get("source_in_ms", 0)})
        except (LizicutError, OSError) as error:
            result["acquisitions"][key] = {"status": "failed", "candidate_id": candidate["id"], "error": str(error)}
            result["gaps"].append({"request_id": key, "reason": str(error)})
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        result["ready"] = not result["gaps"] and len(result["assets"]) == len(plan["requests"])
        save_manifest(manifest, result)
    return {"ready": result["ready"], "manifest": str(manifest), "ready_assets": len(result["assets"]),
            "reused_files": reused, "gaps": result["gaps"],
            "boundary": "search and editorial selection are performed by the agent's available tools; files are probed, not semantically or legally certified"}


if __name__ == "__main__":
    if sys.argv[1:] != ["--download-worker"]:
        raise SystemExit("Use lizicut.py materials; this module's direct entry is reserved for its download worker")
    raise SystemExit(download_worker())
