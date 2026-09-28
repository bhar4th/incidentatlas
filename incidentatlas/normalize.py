"""Bounded ingestion for normalized events and an explicit OTLP/JSON subset.

Accepted OTLP: spans, log records, gauge/sum number data points and explicit
histograms (represented as observation-count and average, never guessed p95).
Unknown metric variants are reported as invalid, not silently synthesized.
"""
from __future__ import annotations
import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any

MAX_EVENTS = 100_000
KINDS = {"log", "span", "metric", "deployment"}
SEVERITIES = {"debug", "info", "warning", "error", "critical"}


def timestamp(value: Any) -> str:
    if isinstance(value, bool) or value is None:
        raise ValueError("timestamp is required")
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ValueError("timestamp must be finite")
        dt = datetime.fromtimestamp(value, timezone.utc)
    elif isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ValueError("timestamp must contain timezone")
        dt = dt.astimezone(timezone.utc)
    else:
        raise ValueError("timestamp must be ISO string or epoch seconds")
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def epoch(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def finite(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric")
    n = float(value)
    if not math.isfinite(n):
        raise ValueError(f"{name} must be finite")
    return n


def normalize_event(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("event must be an object")
    kind = raw.get("kind", "log")
    if kind not in KINDS:
        raise ValueError("kind must be log, span, metric or deployment")
    service = raw.get("service")
    if not isinstance(service, str) or not service.strip() or len(service) > 200:
        raise ValueError("service is required and limited to 200 characters")
    severity = str(raw.get("severity", "info")).lower()
    if severity == "warn":
        severity = "warning"
    if severity not in SEVERITIES:
        raise ValueError("unsupported severity")
    attrs = raw.get("attributes", {})
    if not isinstance(attrs, dict) or len(attrs) > 100:
        raise ValueError("attributes must be an object with at most 100 fields")
    clean_attrs = {}
    for k, v in attrs.items():
        if not isinstance(k, str) or len(k) > 200:
            raise ValueError("invalid attribute key")
        if not (v is None or isinstance(v, (str, int, float, bool))):
            raise ValueError("normalized attributes must have scalar values")
        if isinstance(v, float) and not math.isfinite(v):
            raise ValueError("attributes cannot contain nonfinite numbers")
        if isinstance(v, str) and len(v) > 8192:
            raise ValueError("attribute value exceeds 8192 characters")
        clean_attrs[k] = v
    event = {"timestamp": timestamp(raw.get("timestamp")), "service": service.strip(),
             "kind": kind, "severity": severity, "name": str(raw.get("name", kind))[:500],
             "message": str(raw.get("message", ""))[:8192], "attributes": clean_attrs}
    for key in ("trace_id", "span_id", "parent_span_id", "unit"):
        if raw.get(key) is not None:
            event[key] = str(raw[key])[:200]
    for key in ("duration_ms", "value"):
        if raw.get(key) is not None:
            event[key] = finite(raw[key], key)
    if event.get("duration_ms", 0) < 0:
        raise ValueError("duration_ms cannot be negative")
    if kind == "metric" and "value" not in event:
        raise ValueError("metric requires value")
    provided_id = raw.get("id")
    if provided_id is not None:
        if not isinstance(provided_id, str) or not provided_id.strip() or len(provided_id) > 250:
            raise ValueError("id must be a nonempty string of at most 250 characters")
        event["id"] = provided_id
    else:
        event["id"] = "ev_" + hashlib.sha256(canonical(event).encode()).hexdigest()[:24]
    return event


def canonical(event: dict) -> str:
    return json.dumps({k: v for k, v in event.items() if k not in {"late", "ingested_at"}}, sort_keys=True, separators=(",", ":"), allow_nan=False)


def otlp_value(value: dict) -> Any:
    for key in ("stringValue", "boolValue", "intValue", "doubleValue"):
        if key in value:
            return int(value[key]) if key == "intValue" else value[key]
    if "arrayValue" in value or "kvlistValue" in value or "bytesValue" in value:
        return json.dumps(value, sort_keys=True)
    return None


def attributes(values: list) -> dict:
    return {x["key"]: otlp_value(x.get("value", {})) for x in values if isinstance(x, dict) and isinstance(x.get("key"), str)}


def nanos(value: Any) -> str:
    # Integer division before float conversion avoids losing the entire subsecond.
    n = int(value)
    return timestamp(n // 1_000_000_000 + (n % 1_000_000_000) / 1_000_000_000)


def otlp_events(payload: dict):
    for resource in payload.get("resourceSpans", []):
        resource_attrs = attributes(resource.get("resource", {}).get("attributes", []))
        service = resource_attrs.get("service.name", "unknown-service")
        for scope in resource.get("scopeSpans", []):
            for span in scope.get("spans", []):
                try:
                    attrs = {**resource_attrs, **attributes(span.get("attributes", []))}
                    kinds = {1: "internal", 2: "server", 3: "client", 4: "producer", 5: "consumer"}
                    attrs["span.kind"] = kinds.get(span.get("kind"), str(span.get("kind", "internal")).lower().replace("span_kind_", ""))
                    status = span.get("status", {}).get("code", 0)
                    trace, sid = span.get("traceId", ""), span.get("spanId", "")
                    if not trace or not sid:
                        raise ValueError("OTLP span requires traceId and spanId")
                    yield {"id": f"span:{trace}:{sid}", "service": service, "timestamp": nanos(span["startTimeUnixNano"]),
                           "kind": "span", "name": span.get("name", "span"), "message": span.get("status", {}).get("message", ""),
                           "severity": "error" if status in (2, "STATUS_CODE_ERROR") else "info",
                           "duration_ms": (int(span["endTimeUnixNano"]) - int(span["startTimeUnixNano"])) / 1e6,
                           "trace_id": trace, "span_id": sid, "parent_span_id": span.get("parentSpanId", ""), "attributes": attrs}
                except (KeyError, ValueError, TypeError) as exc:
                    yield {"_normalization_error": f"invalid OTLP span: {exc}"}
    for resource in payload.get("resourceLogs", []):
        resource_attrs = attributes(resource.get("resource", {}).get("attributes", []))
        service = resource_attrs.get("service.name", "unknown-service")
        for scope in resource.get("scopeLogs", []):
            for log in scope.get("logRecords", []):
                try:
                    number = int(log.get("severityNumber", 9))
                    level = "critical" if number >= 21 else "error" if number >= 17 else "warning" if number >= 13 else "info" if number >= 9 else "debug"
                    yield {"service": service, "timestamp": nanos(log.get("timeUnixNano") or log["observedTimeUnixNano"]), "kind": "log", "severity": level,
                           "name": log.get("eventName", "log"), "message": otlp_value(log.get("body", {})) or "",
                           "trace_id": log.get("traceId", ""), "span_id": log.get("spanId", ""),
                           "attributes": {**resource_attrs, **attributes(log.get("attributes", []))}}
                except (KeyError, ValueError, TypeError) as exc:
                    yield {"_normalization_error": f"invalid OTLP log: {exc}"}
    for resource in payload.get("resourceMetrics", []):
        resource_attrs = attributes(resource.get("resource", {}).get("attributes", []))
        service = resource_attrs.get("service.name", "unknown-service")
        for scope in resource.get("scopeMetrics", []):
            for metric in scope.get("metrics", []):
                variant = next((k for k in ("gauge", "sum", "histogram") if k in metric), None)
                if not variant:
                    yield {"_normalization_error": "unsupported OTLP metric variant (supports gauge, sum, histogram)"}
                    continue
                for point in metric[variant].get("dataPoints", []):
                    try:
                        attrs = {**resource_attrs, **attributes(point.get("attributes", []))}
                        name = metric.get("name", "metric")
                        if variant == "histogram":
                            count = int(point["count"])
                            if count <= 0 or "sum" not in point:
                                raise ValueError("histogram needs positive count and sum for average")
                            value = float(point["sum"]) / count
                            name += ".mean"
                            attrs["observation_count"] = count
                            attrs["aggregation"] = "histogram_mean"
                        else:
                            value = point.get("asDouble", point.get("asInt"))
                            if value is None:
                                raise ValueError("number data point needs asDouble or asInt")
                        yield {"service": service, "timestamp": nanos(point["timeUnixNano"]), "kind": "metric", "severity": "info",
                               "name": name, "value": value, "unit": metric.get("unit", ""), "attributes": attrs}
                    except (KeyError, ValueError, TypeError, ZeroDivisionError) as exc:
                        yield {"_normalization_error": f"invalid OTLP metric: {exc}"}


def normalize_payload(payload: Any) -> tuple[list[dict], list[dict]]:
    if isinstance(payload, list):
        raw_events = payload
    elif isinstance(payload, dict) and "events" in payload:
        raw_events = payload["events"]
        if not isinstance(raw_events, list):
            raise ValueError("events must be an array")
    elif isinstance(payload, dict) and any(k in payload for k in ("resourceSpans", "resourceLogs", "resourceMetrics")):
        try:
            raw_events = list(otlp_events(payload))
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError, OSError) as exc:
            raise ValueError("malformed OTLP resource/scope structure") from exc
    else:
        raise ValueError("expected events array or OTLP JSON resourceSpans/resourceLogs/resourceMetrics")
    if len(raw_events) > MAX_EVENTS:
        raise ValueError(f"event count exceeds {MAX_EVENTS}")
    accepted, errors, seen = [], [], {}
    for index, raw in enumerate(raw_events):
        try:
            if isinstance(raw, dict) and "_normalization_error" in raw:
                raise ValueError(raw["_normalization_error"])
            event = normalize_event(raw)
            if event["id"] in seen and canonical(event) != seen[event["id"]]:
                raise ValueError("conflicting duplicate id in payload")
            seen[event["id"]] = canonical(event)
            accepted.append(event)
        except (ValueError, TypeError, OverflowError, OSError) as exc:
            errors.append({"index": index, "error": str(exc)})
    return accepted, errors
