"""Error-contract comparison: observed JSON error bodies vs the schema each endpoint documents.

Documented schemas (re-verified 2026-11-22):
- TTS sync (synthesize-speech): 400/401/500 bodies are {error?: string, message?: string}.
- STT (transcribe): all error statuses share one optional-field schema (see STT_ERROR_SCHEMA).
- SSE TTS, get_voices: no error body schema documented.
"""

from __future__ import annotations

from typing import Any

from . import docs_refs as D

TTS_ERROR_SCHEMA: dict[str, tuple[type, ...]] = {"error": (str,), "message": (str,)}
STT_ERROR_SCHEMA: dict[str, tuple[type, ...]] = {
    "error": (str,), "status": (str,), "message": (str,), "error_code": (str,), "code": (str,),
    "language": (str,), "detected_language": (str,), "language_confidence": (int, float), "region": (str,),
    "request_id": (str,), "errors": (list, str),
}
SCHEMAS = {"tts": (TTS_ERROR_SCHEMA, D.TTS_SYNC), "stt": (STT_ERROR_SCHEMA, D.STT_TRANSCRIBE)}


def type_name(v: Any) -> str:
    if isinstance(v, list):
        inner = sorted({type_name(x) for x in v}) or ["empty"]
        return f"list[{'|'.join(inner)}]"
    if isinstance(v, dict):
        return "object{" + ",".join(sorted(v)) + "}"
    return {str: "string", bool: "boolean", int: "number", float: "number", type(None): "null"}.get(type(v),
                                                                                                 type(v).__name__)


def signature(body: Any) -> str:
    """Stable shape signature, e.g. `{error:list[object{code,message,path}]}`."""
    if not isinstance(body, dict):
        return type_name(body)
    return "{" + ",".join(f"{k}:{type_name(body[k])}" for k in sorted(body)) + "}"


def conformance(body: Any, product: str) -> tuple[bool, list[str]]:
    """True when every documented field present has its documented type and at least one human-readable
    message string exists. Undocumented extra fields are reported but not counted as violations."""
    schema, _ = SCHEMAS[product]
    if not isinstance(body, dict):
        return False, [f"body is {type_name(body)}, expected a JSON object"]
    problems = []
    for key, value in body.items():
        if key in schema and not isinstance(value, schema[key]):
            problems.append(f"`{key}` is {type_name(value)}; documented as "
                            f"{'/'.join(t.__name__ for t in schema[key])}")
    if not any(isinstance(body.get(k), str) and body.get(k) for k in ("error", "message")):
        problems.append("no human-readable `error`/`message` string")
    return not problems, problems


def undocumented_fields(body: Any, product: str) -> list[str]:
    schema, _ = SCHEMAS[product]
    return sorted(k for k in body if k not in schema) if isinstance(body, dict) else []


def human_message(body: Any) -> str | None:
    """What a typical client would show: first string message found in the common places."""
    if not isinstance(body, dict):
        return None
    for key in ("message", "error"):
        if isinstance(body.get(key), str) and body[key]:
            return body[key]
    for key in ("error", "errors"):
        val = body.get(key)
        if isinstance(val, list) and val and isinstance(val[0], dict) and isinstance(val[0].get("message"), str):
            return val[0]["message"]
        if isinstance(val, str) and val:
            return val
    return None
