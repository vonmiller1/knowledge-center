"""Minimal stdlib CLI: triage a case, or verify the audit chain (argparse, no extra deps)."""

from __future__ import annotations

import argparse
import sys
from datetime import date

from hex_service_kit.logging import configure_logging

from ..config import build_container
from ..domain.capture_service import MeetingCaptureService
from ..domain.models import TriageInput
from ..domain.triage_service import TriageService
from ..packs import load_default_packs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="meeting_capture")
    sub = parser.add_subparsers(dest="command", required=True)

    triage_cmd = sub.add_parser("triage", help="Triage a single case.")
    triage_cmd.add_argument("subject")
    triage_cmd.add_argument("text")
    triage_cmd.add_argument("--actor", default="cli-user@bank.example")
    triage_cmd.add_argument(
        "--tenant", default="", help="Tenant partition asserted to human-review-console."
    )

    capture_cmd = sub.add_parser("capture", help="Capture a meeting into a register and minutes.")
    capture_cmd.add_argument("audio_uri", help="Reference to the meeting audio/transcript.")
    capture_cmd.add_argument("--market", required=True, help="Market code, e.g. SG / AU / JP.")
    capture_cmd.add_argument("--as-of", required=True, help="Meeting date, ISO YYYY-MM-DD.")
    capture_cmd.add_argument("--actor", default="cli-user@bank.example")
    capture_cmd.add_argument(
        "--tenant", default="", help="Tenant partition asserted to human-review-console."
    )

    args = parser.parse_args(argv)
    container = build_container()
    # Idempotent: a process that is both an API app and a CLI configures once.
    configure_logging(container.settings.profile, service="meeting-knowledge-capture")

    if args.command == "triage":
        service = TriageService(container.audit, tracer=container.tracer)
        result = service.triage(TriageInput(subject=args.subject, text=args.text), actor=args.actor)
        print(f"{result.subject}: {result.severity.value} ({result.decision.value})")
        print(f"  requires_human_review: {result.requires_human_review}")
        if result.requires_human_review:
            # Rule R8 on the CLI path too: the same escalation, the same router. A surface that
            # only printed the flag would be a second place for an escalation to stop.
            ref = container.review_router.route(result, maker=args.actor, tenant=args.tenant)
            print(f"  routed to human review: {ref}")
        return 0

    if args.command == "capture":
        capture_service = MeetingCaptureService(
            transcription=container.transcription,
            diarization=container.diarization,
            generation=container.generation,
            corpus=container.corpus,
            task_router=container.task_router,
            review_router=container.review_router,
            audit=container.audit,
            tracer=container.tracer,
            packs=load_default_packs(),
            tenant=args.tenant,
        )
        capture_result = capture_service.capture(
            args.audio_uri,
            market=args.market,
            as_of=date.fromisoformat(args.as_of),
            actor=args.actor,
        )
        digest = capture_result.transcript_digest[:19]
        print(f"{capture_result.meeting_id} [{capture_result.market}]  digest {digest}")
        print(
            f"  accepted={len(capture_result.register.accepted)} "
            f"rejected={len(capture_result.register.rejected)} "
            f"for_review={len(capture_result.register.consequential)} "
            f"minutes_grounded={capture_result.minutes.grounded}"
        )
        for entry in capture_result.register.entries:
            marker = "*" if entry.requires_human_review else " "
            due = entry.sla_due.isoformat() if entry.sla_due else "-"
            reasons = f" ({'; '.join(entry.reasons)})" if entry.reasons else ""
            print(
                f"  {marker} {entry.entry_id} {entry.kind.value:<8} {entry.outcome.value:<8} "
                f"owner={entry.owner or '-'} due={due}{reasons}"
            )
        return 0

    return 2  # pragma: no cover - argparse requires a subcommand


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
