"""ONE canonical request per port, shared by the structural and behavioural contract suites.

Parity means the same request through every implementation, so the request needs a single home.
Retyping it per suite is how two "parity" tests end up asserting different things.

Each :class:`PortCase` answers three questions about one port:

* ``invoke``   : what a single canonical call to this port looks like;
* ``answered`` : what it means for the OFFLINE family to have actually answered (a port that
  returns ``None`` and records nothing has not answered, it has merely not raised);
* ``managed_refusal`` : what the MANAGED family must do when called with no cloud reachable.
  Never a silent success: either it refuses because it is unconfigured, or its lazy SDK import
  fails. Both are honest; returning as if the work happened is not.

Adding a port means adding a case here. ``test_port_parity.py`` fails the build if this table
and the port map ever disagree, so the touch list in ``CONTRIBUTING.md`` is enforced rather than
merely written down.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agent_eval_kit import EvalReport
from hex_service_kit.identity import IdentityError, Principal, RequestContext
from hex_service_kit.observability import TokenUsage

from meeting_capture.adapters.local._fixtures import FIXTURE_MEETINGS
from meeting_capture.domain.kernel import (
    AuditEvent,
    Citation,
    Decision,
    Severity,
)
from meeting_capture.domain.models import (
    TriageResult,
)
from meeting_capture.ports.corpus import CorpusDocument
from meeting_capture.ports.diarization import DiarizationRequest
from meeting_capture.ports.generation import ExtractionRequest
from meeting_capture.ports.task_router import TaskAssignment
from meeting_capture.ports.transcription import AudioRef, TranscriptionRequest

from tests.fixtures import sample_cases

#: A fixture audio reference every ingestion adapter is handed, resolving to the SG meeting.
_FIXTURE_AUDIO = AudioRef(uri=FIXTURE_MEETINGS[0].audio_uri, media_type="audio/wav")
#: The redacted-style transcript handed to the generation adapter (fixture recogniser output).
_FIXTURE_TRANSCRIPT = FIXTURE_MEETINGS[0].transcript()

#: The audit record every audit-port implementation is handed. Already redacted, as the port
#: requires: a raw identifier must never reach a WORM record.
CANONICAL_EVENT = AuditEvent(
    action="triage",
    actor=sample_cases.ACTOR,
    decision=Decision.ESCALATED,
    severity=Severity.HIGH,
    redacted_summary="Acme Holdings (FICTIONAL): triaged high",
    citations=(Citation(source_id="case:acme", title="Case description", snippet="urgent"),),
)

#: The escalated result every review-router implementation is handed (rule R8's payload).
CANONICAL_RESULT = TriageResult(
    subject=sample_cases.ESCALATING_CASE.subject,
    severity=Severity.HIGH,
    decision=Decision.ESCALATED,
    summary=f"{sample_cases.ESCALATING_CASE.subject}: triaged high",
    requires_human_review=True,
    citations=(Citation(source_id="case:acme", title="Case description", snippet="urgent"),),
)

#: The inbound transport context every identity implementation is handed.
CANONICAL_CONTEXT = RequestContext(headers={"x-dev-persona": "auditor"})


@dataclass(frozen=True, slots=True)
class PortCase:
    """One port's canonical call plus the two verdicts the parity suites need."""

    invoke: Callable[[Any], Any]
    answered: Callable[[Any, Any], bool]
    managed_refusal: tuple[type[BaseException], ...]
    detail: str


def _audit_invoke(adapter: Any) -> Any:
    return adapter.record(CANONICAL_EVENT)


def _audit_answered(adapter: Any, _result: Any) -> bool:
    stored = adapter.log.read_all()
    return bool(stored) and stored[-1]["actor"] == sample_cases.ACTOR and adapter.verify().ok


def _identity_invoke(adapter: Any) -> Any:
    return adapter.resolve(CANONICAL_CONTEXT)


def _identity_answered(_adapter: Any, result: Any) -> bool:
    return isinstance(result, Principal) and bool(result.actor)


def _review_invoke(adapter: Any) -> Any:
    return adapter.route(CANONICAL_RESULT, maker=sample_cases.ACTOR, tenant=sample_cases.TENANT)


def _review_answered(adapter: Any, result: Any) -> bool:
    return bool(result) and len(adapter.outbox.pending()) == 1


def _transcription_invoke(adapter: Any) -> Any:
    return adapter.transcribe(
        TranscriptionRequest(request_id="req-1", audio=_FIXTURE_AUDIO, locale="en-SG")
    )


def _transcription_answered(_adapter: Any, result: Any) -> bool:
    return bool(result.transcript.turns)


def _diarization_invoke(adapter: Any) -> Any:
    return adapter.diarize(DiarizationRequest(request_id="req-1", audio=_FIXTURE_AUDIO))


def _diarization_answered(_adapter: Any, result: Any) -> bool:
    return bool(result.segments)


def _generation_invoke(adapter: Any) -> Any:
    return adapter.extract(ExtractionRequest(transcript=_FIXTURE_TRANSCRIPT))


def _generation_answered(_adapter: Any, result: Any) -> bool:
    loaded = json.loads(result)
    return isinstance(loaded, dict) and bool(loaded.get("candidates"))


def _corpus_invoke(adapter: Any) -> Any:
    return adapter.publish(
        CorpusDocument(
            doc_id="doc-can-1",
            title="Minutes (FICTIONAL)",
            market=sample_cases.TENANT,
            body="onboarding pack decision recorded",
        )
    )


def _corpus_answered(adapter: Any, result: Any) -> bool:
    return bool(result) and bool(adapter.retrieve("onboarding"))


def _task_invoke(adapter: Any) -> Any:
    return adapter.create_task(
        TaskAssignment(
            source_entry_id="e1",
            title="Prepare the onboarding pack",
            owner="Wei Lim (FICTIONAL)",
            market="SG",
        )
    )


def _task_answered(adapter: Any, result: Any) -> bool:
    return bool(result) and len(adapter.tasks) == 1


def _tracer_invoke(adapter: Any) -> Any:
    with adapter.span("canonical.unit", action="canonical"):
        adapter.record_token_usage(TokenUsage(input_tokens=7, output_tokens=2), "canonical-model")
    return True


def _tracer_answered(adapter: Any, result: Any) -> bool:
    return bool(result)


def _evaluation_invoke(adapter: Any) -> Any:
    return adapter.evaluate("eval/datasets/canonical.jsonl")


def _evaluation_answered(adapter: Any, result: Any) -> bool:
    return isinstance(result, EvalReport) and result.dataset.endswith("canonical.jsonl")


CANONICAL_CALLS: dict[str, PortCase] = {
    "audit": PortCase(
        invoke=_audit_invoke,
        answered=_audit_answered,
        # The lazy `google.cloud` import is the first thing the managed sink does.
        managed_refusal=(ImportError,),
        detail="write one already-redacted WORM record",
    ),
    "identity": PortCase(
        invoke=_identity_invoke,
        answered=_identity_answered,
        # No IAP assertion header offline, so the managed adapter refuses before importing.
        managed_refusal=(IdentityError,),
        detail="resolve a verified principal from transport context",
    ),
    "review_router": PortCase(
        invoke=_review_invoke,
        answered=_review_answered,
        # Rule R8: with no console configured the managed router must refuse, not swallow.
        managed_refusal=(RuntimeError,),
        detail="route one escalated result to human review",
    ),
    "transcription": PortCase(
        invoke=_transcription_invoke,
        answered=_transcription_answered,
        # The lazy `google.cloud.speech_v2` import is the first thing the managed adapter does.
        managed_refusal=(ImportError,),
        detail="transcribe a fixture meeting into speaker turns",
    ),
    "diarization": PortCase(
        invoke=_diarization_invoke,
        answered=_diarization_answered,
        managed_refusal=(ImportError,),
        detail="segment a fixture meeting by speaker",
    ),
    "generation": PortCase(
        invoke=_generation_invoke,
        answered=_generation_answered,
        # The lazy `google.genai` import is the first thing the managed adapter does.
        managed_refusal=(ImportError,),
        detail="extract candidate commitments as a JSON payload",
    ),
    "corpus": PortCase(
        invoke=_corpus_invoke,
        answered=_corpus_answered,
        managed_refusal=(ImportError,),
        detail="publish one governed document and retrieve it",
    ),
    "task_router": PortCase(
        invoke=_task_invoke,
        answered=_task_answered,
        managed_refusal=(ImportError,),
        detail="create one external task assignment",
    ),
    "tracer": PortCase(
        invoke=_tracer_invoke,
        answered=_tracer_answered,
        # NOTHING. Tracing is not essential to correctness, so the managed adapter must not refuse
        # offline either: with no SDK it degrades to a no-op and the traced body still runs. An
        # adapter that raised here would take a request down over a diagnostic.
        managed_refusal=(),
        detail="open one span and report the cost of a model call",
    ),
    "evaluation": PortCase(
        invoke=_evaluation_invoke,
        answered=_evaluation_answered,
        # The managed gate reaches model-quality-gate over HTTP, which is unreachable offline.
        managed_refusal=(Exception,),
        detail="score one golden dataset through the promotion authority",
    ),
}
