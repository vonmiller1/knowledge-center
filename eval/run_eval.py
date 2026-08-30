#!/usr/bin/env python3
"""Evaluation gate for Meeting Knowledge Capture (H6).

Two named layers via ``--mode`` (the scaffold is ``agent_eval_kit.eval_main``):

* **smoke** (default) - the offline pre-merge check CI runs on every change: it drives the real
  ``MeetingCaptureService`` with SDK-free local adapters over the golden meetings and scores the
  register engine, the minutes grounding and the review-safety property against the dataset's OWN
  hand-computed ``expected_*`` fields. Those expectations are an INDEPENDENT oracle: the SLA dates
  and consequential sets are derived from the market packs by hand, NEVER read back from the
  pipeline, so a metric that passes is agreeing with a value the pipeline did not produce.
* **gate** - the promotion verdict from the shared Hrz4 authority (requires the ``gcp`` profile),
  via ``agent_eval_kit.PromotionGateClient``.

Every metric here can be driven red; ``tests/unit/test_eval_metrics_go_red.py`` proves it, per
market for the SLA metric (``assert_each_can_go_red``). A metric that cannot go red is not a
metric.

Exit is ``0`` iff every metric meets its threshold (and, in gate mode, the authority agrees).
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any

from agent_eval_kit import EvalMetricResult, EvalReport, PromotionGateClient, eval_main
from pii_kit import pack_leak

from meeting_capture.config import Settings, build_container
from meeting_capture.domain.capture_service import CaptureResult, MeetingCaptureService
from meeting_capture.domain.pii import PII_PATTERNS
from meeting_capture.packs import load_default_packs

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = _REPO_ROOT / "eval" / "datasets" / "golden_meetings.jsonl"

THRESHOLDS: dict[str, float] = {
    "extraction_f1": 0.99,
    "register_accuracy": 0.99,
    "sla_exactness": 0.99,
    "groundedness": 0.99,
    "review_safety": 0.99,
    "pii_safety": 0.99,
}
#: The registered Hrz4 metric bundle for this vertical (Hrz4 owns the metrics + thresholds).
_BUNDLE = "meeting-knowledge-capture"


def _load(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cases.append(json.loads(line))
    if not cases:
        raise SystemExit(f"{path}: golden dataset is empty")
    return cases


def _mean(scores: list[float]) -> float:
    return round(sum(scores) / len(scores), 4) if scores else 0.0


def _f1(predicted: int, expected: int) -> float:
    if expected == 0 and predicted == 0:
        return 1.0
    if predicted == 0 or expected == 0:
        return 0.0
    matched = min(predicted, expected)
    precision = matched / predicted
    recall = matched / expected
    return 2 * precision * recall / (precision + recall)


def _register_accuracy(result: CaptureResult, case: dict[str, Any]) -> float:
    expected_sla: dict[str, str] = case["expected_sla"]
    expected_owners: dict[str, str] = case.get("expected_owners", {})
    accepted_ids = {e.entry_id for e in result.register.accepted}
    if accepted_ids != set(expected_sla):
        return 0.0
    if len(result.register.rejected) != int(case["expected_rejected"]):
        return 0.0
    by_id = {e.entry_id: e for e in result.register.accepted}
    for entry_id, owner in expected_owners.items():
        if by_id[entry_id].owner != owner:
            return 0.0
    return 1.0


def _sla_exactness(result: CaptureResult, case: dict[str, Any]) -> float:
    expected_sla: dict[str, str] = case["expected_sla"]
    by_id = {e.entry_id: e for e in result.register.accepted}
    hits = 0
    for entry_id, iso in expected_sla.items():
        entry = by_id.get(entry_id)
        if entry is not None and entry.sla_due is not None and entry.sla_due.isoformat() == iso:
            hits += 1
    return hits / len(expected_sla) if expected_sla else 1.0


def _review_safety(result: CaptureResult, case: dict[str, Any]) -> float:
    expected = set(case["expected_consequential"])
    got = {e.entry_id for e in result.register.consequential}
    return 1.0 if got == expected else 0.0


def run_smoke(dataset: Path) -> EvalReport:
    cases = _load(dataset)
    container = build_container(Settings(profile="local", audit_path=":memory:", tenant="eval"))
    audit = container.audit
    service = MeetingCaptureService(
        transcription=container.transcription,
        diarization=container.diarization,
        generation=container.generation,
        corpus=container.corpus,
        task_router=container.task_router,
        review_router=container.review_router,
        audit=audit,
        tracer=container.tracer,
        packs=load_default_packs(),
        tenant="eval",
    )

    extraction: list[float] = []
    register: list[float] = []
    sla: list[float] = []
    grounded: list[float] = []
    review: list[float] = []
    minutes_bodies: list[str] = []
    planted: list[str] = []

    for case in cases:
        result = service.capture(
            str(case["audio_uri"]),
            market=str(case["market"]),
            as_of=date.fromisoformat(str(case["as_of"])),
            actor="eval-bot",
        )
        extraction.append(_f1(len(result.register.entries), int(case["expected_candidates"])))
        register.append(_register_accuracy(result, case))
        sla.append(_sla_exactness(result, case))
        grounded.append(1.0 if result.minutes.grounded else 0.0)
        review.append(_review_safety(result, case))
        minutes_bodies.append(result.minutes.body)
        if case.get("planted"):
            planted.append(str(case["planted"]))

    records = [str(e.get("redacted_summary", "")) for e in audit.log.read_all()]
    surfaces = records + minutes_bodies
    pack_leaked = any(pack_leak(text, PII_PATTERNS) for text in surfaces)
    literal_leaked = any(token in text for token in planted for text in surfaces)
    pii_safety = 0.0 if (pack_leaked or literal_leaked) else 1.0

    results = (
        EvalMetricResult.scored("extraction_f1", _mean(extraction), THRESHOLDS["extraction_f1"]),
        EvalMetricResult.scored(
            "register_accuracy", _mean(register), THRESHOLDS["register_accuracy"]
        ),
        EvalMetricResult.scored("sla_exactness", _mean(sla), THRESHOLDS["sla_exactness"]),
        EvalMetricResult.scored("groundedness", _mean(grounded), THRESHOLDS["groundedness"]),
        EvalMetricResult.scored("review_safety", _mean(review), THRESHOLDS["review_safety"]),
        EvalMetricResult.scored("pii_safety", pii_safety, THRESHOLDS["pii_safety"]),
    )
    return EvalReport(dataset=str(dataset), results=results, n_examples=len(cases))


def run_gate(dataset: Path) -> tuple[EvalReport, bool]:
    settings = Settings.load()
    if settings.profile != "gcp":
        raise SystemExit(
            "--mode gate is the promotion authority and requires "
            f"MEETCAP_PROFILE=gcp (got {settings.profile!r}); "
            "run --mode smoke for the offline pre-merge check."
        )
    client = PromotionGateClient(
        os.environ.get("MEETCAP_QUALITY_URL", "http://localhost:8084"),
        bundle=_BUNDLE,
        model="gemini-3.5-flash",
    )
    return client.evaluate(str(dataset)), client.gate(str(dataset))


if __name__ == "__main__":
    raise SystemExit(
        eval_main(
            smoke=run_smoke,
            gate=run_gate,
            default_dataset=DEFAULT_DATASET,
            description="Offline / Hrz4 evaluation gate for H6.",
        )
    )
