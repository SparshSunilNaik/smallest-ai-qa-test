"""Execute official documentation examples *verbatim* under a network shim.

The shim (a generated sitecustomize.py) patches `requests` and `httpx` so that:
- offline mode: every call is answered from canned responses (recorded live bodies or synthetic), no network;
- live mode: calls to api.smallest.ai are reserved in the shared ledger *before* being sent (same caps);
  github.com sample downloads are allowed but are not Smallest API calls; every other host is blocked.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .config import REPO_ROOT
from .redact import redact_text, scrub_paths

EXAMPLES_DIR = REPO_ROOT / "docs" / "examples"

_SHIM = r'''
import base64, json, os, time
from urllib.parse import urlparse
MODE = os.environ["QA_SHIM_MODE"]
LOG = os.environ["QA_SHIM_LOG"]
API = "api.smallest.ai"
AUX = {"github.com", "raw.githubusercontent.com", "objects.githubusercontent.com"}
CANNED = json.load(open(os.environ["QA_SHIM_CANNED"])) if os.environ.get("QA_SHIM_CANNED") else {}

def _log(rec):
    with open(LOG, "a") as fh:
        fh.write(json.dumps(rec) + "\n")

def _decide(url):
    host = urlparse(url).hostname or ""
    if host == API:
        return "api"
    if host in AUX:
        return "aux"
    return "blocked"

def _reserve(method, url):
    from smallest_qa.budget import RequestLedger
    from smallest_qa.config import PHASE_REQUEST_CAPS, PHASE_USD_CAPS
    led = RequestLedger(__import__("pathlib").Path(os.environ["QA_LEDGER"]), int(os.environ["QA_LEDGER_MAX"]),
                        phase_caps=PHASE_REQUEST_CAPS, phase_usd_caps=PHASE_USD_CAPS)
    return led.reserve(run_id=os.environ["QA_RUN_ID"], case_id=os.environ["QA_CASE_ID"], method=method,
                       path=urlparse(url).path, phase=int(os.environ["QA_PHASE"]), batch=os.environ["QA_BATCH"],
                       protocol="http", est_tts_chars=int(os.environ.get("QA_EST_CHARS", "0")),
                       est_stt_seconds=float(os.environ.get("QA_EST_STT", "0")))

def _canned(kind):
    c = CANNED.get(kind)
    if c is None:
        raise ConnectionError(f"QA shim offline: no canned response for {kind}")
    return c["status"], c.get("headers", {}), base64.b64decode(c["body_b64"])

try:
    import requests
    from requests.adapters import HTTPAdapter
    from requests.structures import CaseInsensitiveDict
    _orig_send = HTTPAdapter.send

    def _send(self, request, **kw):
        kind = _decide(request.url)
        rec = {"lib": "requests", "method": request.method, "url_path": urlparse(request.url).path,
               "host_kind": kind, "body_bytes": len(request.body or b"") if not isinstance(request.body, str) else len(request.body),
               "query": urlparse(request.url).query, "timeout": str(kw.get("timeout"))}
        if kind == "blocked":
            rec["blocked"] = True; _log(rec)
            raise requests.exceptions.ConnectionError("blocked by QA shim")
        t0 = time.perf_counter()
        if MODE == "offline":
            status, headers, body = _canned(kind)
            resp = requests.models.Response()
            resp.status_code, resp._content, resp.url, resp.request = status, body, request.url, request
            resp.headers = CaseInsensitiveDict(headers)
        else:
            if kind == "api":
                rec["ledger_seq"] = _reserve(request.method, request.url)
            resp = _orig_send(self, request, **kw)
        rec.update({"status": resp.status_code, "ms": round((time.perf_counter() - t0) * 1000, 1),
                    "resp_headers": {k: v for k, v in resp.headers.items() if k.lower() in
                                     ("content-type", "content-length", "x-request-id")},
                    "resp_excerpt": (resp.content[:400].decode("utf-8", "replace")
                                     if resp.content[:1] in (b"{", b"[") else f"<{len(resp.content)} bytes>")})
        _log(rec)
        return resp
    HTTPAdapter.send = _send
except ImportError:
    pass

try:
    import httpx
    _orig_handle = httpx.HTTPTransport.handle_request

    def _handle(self, request):
        url = str(request.url)
        kind = _decide(url)
        rec = {"lib": "httpx", "method": request.method, "url_path": request.url.path, "host_kind": kind,
               "query": request.url.query.decode() if isinstance(request.url.query, bytes) else str(request.url.query)}
        if kind == "blocked":
            rec["blocked"] = True; _log(rec)
            raise httpx.ConnectError("blocked by QA shim", request=request)
        t0 = time.perf_counter()
        if MODE == "offline":
            status, headers, body = _canned(kind)
            resp = httpx.Response(status, headers=headers, content=body, request=request)
        else:
            if kind == "api":
                rec["ledger_seq"] = _reserve(request.method, url)
            resp = _orig_handle(self, request)
            resp.read()
        rec.update({"status": resp.status_code, "ms": round((time.perf_counter() - t0) * 1000, 1),
                    "resp_headers": {k: v for k, v in resp.headers.items() if k.lower() in
                                     ("content-type", "content-length", "x-request-id")}})
        _log(rec)
        return resp
    httpx.HTTPTransport.handle_request = _handle
except ImportError:
    pass
'''


@dataclass
class ExampleRun:
    example: str
    mode: str
    exit_code: int | None
    stdout: str
    stderr_tail: str
    calls: list[dict] = field(default_factory=list)
    files: list[dict] = field(default_factory=list)
    timed_out: bool = False

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def canned(status: int, body: bytes, content_type: str) -> dict:
    return {"status": status, "headers": {"content-type": content_type}, "body_b64": base64.b64encode(body).decode()}


def run_example(example: str, *, mode: str, api_key: str, workdir: Path, canned_responses: dict | None = None,
                ledger_env: dict[str, str] | None = None, input_files: dict[str, bytes] | None = None,
                timeout_s: float = 180.0) -> ExampleRun:
    if mode == "live" and not ledger_env:
        raise ValueError("live mode requires ledger_env so every API call is reserved")
    src = EXAMPLES_DIR / example
    workdir.mkdir(parents=True, exist_ok=True)
    for name, data in (input_files or {}).items():
        (workdir / name).write_bytes(data)
    with tempfile.TemporaryDirectory() as shim_dir:
        shim = Path(shim_dir)
        (shim / "sitecustomize.py").write_text(_SHIM)
        log = shim / "calls.jsonl"
        env = {k: v for k, v in os.environ.items() if not k.startswith(("SMALLEST", "QA_"))}
        env.update({"PYTHONPATH": f"{shim}{os.pathsep}{REPO_ROOT / 'src'}", "SMALLEST_API_KEY": api_key,
                    "SMALLESTAI_TELEMETRY": "0", "QA_SHIM_MODE": mode, "QA_SHIM_LOG": str(log),
                    "PYTHONDONTWRITEBYTECODE": "1"})
        if canned_responses:
            (shim / "canned.json").write_text(json.dumps(canned_responses))
            env["QA_SHIM_CANNED"] = str(shim / "canned.json")
        env.update(ledger_env or {})
        script = workdir / example
        shutil.copyfile(src, script)
        timed_out = False
        try:
            proc = subprocess.run([sys.executable, example], cwd=workdir, env=env, capture_output=True, text=True,
                                  timeout=timeout_s)
            code, out, err = proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as exc:
            timed_out, code = True, None
            out, err = (exc.stdout or "") if isinstance(exc.stdout, str) else "", "timeout"
        calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    files = []
    for p in sorted(workdir.iterdir()):
        if p.name == example or p.name in (input_files or {}):
            continue
        head = p.read_bytes()[:16]
        kind = "wav" if head[:4] == b"RIFF" else "json-text" if head[:1] in (b"{", b"[") else "other"
        files.append({"name": p.name, "bytes": p.stat().st_size, "starts_as": kind})
    secrets = (api_key,)
    return ExampleRun(example, mode, code, scrub_paths(redact_text(out[-800:], secrets)),
                      scrub_paths(redact_text(err[-800:], secrets)), calls, files, timed_out)


def offline_suite(evidence_dir: Path, work_root: Path) -> list[dict]:
    """Run every saved example offline against canned responses built from *recorded live* bodies where
    available (the 401 body is from Phase 1 AUTH-03). No network; zero ledger entries."""
    run1 = json.loads((evidence_dir / "runs" / "20261122T163926Z" / "results.json").read_text(encoding="utf-8"))
    by_case = {c["case_id"]: c for c in run1["cases"]}
    body_401 = by_case["AUTH-03"]["requests"][0]["body_excerpt"].encode()
    stt_ok = by_case["STT-01"]["requests"][0]["body_excerpt"].encode()
    wav = (REPO_ROOT / "fixtures" / "audio" / "stt_en_16k.wav")
    wav_bytes = wav.read_bytes() if wav.exists() else b"RIFF\x00\x00\x00\x00WAVE"
    j = "application/json; charset=utf-8"
    scenarios = [
        ("tts_quickstart_requests.py", "recorded live 401 (invalid key)", {"api": canned(401, body_401, j)}, None),
        ("tts_quickstart_sdk.py", "recorded live 401 (invalid key)", {"api": canned(401, body_401, j)}, None),
        ("stt_transcribe_page_example.py", "any (fails before request)", {"api": canned(200, stt_ok, j)},
         {"call.wav": wav_bytes}),
        ("stt_transcribe_page_sdk_block.py", "synthetic 200 (to observe what is sent)",
         {"api": canned(200, stt_ok, j)}, None),
        ("stt_quickstart_requests.py", "recorded live 200 body; synthetic sample download",
         {"api": canned(200, stt_ok, j), "aux": canned(200, wav_bytes, "audio/wav")}, None),
        ("cookbook_transcribe_python.py", "recorded live 200 body", {"api": canned(200, stt_ok, j)}, None),
    ]
    out = []
    for example, scenario, responses, inputs in scenarios:
        r = run_example(example, mode="offline", api_key="sk_test_offline_doc", workdir=work_root / example[:-3],
                        canned_responses=responses, input_files=inputs)
        out.append({"scenario": scenario, **r.to_dict()})
    return out
