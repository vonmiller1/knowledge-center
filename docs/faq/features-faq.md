# Features FAQ

For product, delivery and operations teams: what this agent does, what is deterministic vs
model-produced, and where its responsibilities **stop** and a sibling catalog system takes over.
Cross-references: [`../../README.md`](../../README.md), [`../../DEMO.md`](../../DEMO.md),
[`../../SPEC.md`](../../SPEC.md), [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md).

### What does H6 actually produce?

Two cited artifacts from one meeting: an **action register** and **grounded minutes**.

The register is a list of `RegisterEntry` rows, one per candidate commitment, each accepted or
rejected with a recorded reason, each carrying the owner it resolved to, the decision state, the
span citation back into the transcript turn it came from, and, when accepted, an SLA due date and
a retention horizon computed from the market's retention pack. The minutes are prose that
restates the register and is discarded if it cannot be grounded against it.

Three fixture meetings ship, one per market pack (`sg-1`, `au-1`, `jp-1`), and the flagship path
is one command: `meeting_capture capture fixture://meetings/sg-1 --market SG --as-of 2026-08-03`.

### What is the pipeline, in order?

`MeetingCaptureService.capture` in `domain/capture_service.py` is the one place it is wired, and
the order is the security order:

1. **Ingest** through `SpeechToTextPort` and `DiarizationPort`.
2. **Assemble** the turns deterministically (`domain/turns.assemble`, largest-overlap wins with a
   fixed tie-break, so the same audio yields the same speaker labels every run).
3. **Redact** (`domain/turns.redact_for_model`) BEFORE the model is ever called.
4. **Extract** candidate commitments through `GenerationPort`.
5. **Validate** them with `domain/candidates.parse_candidates`; a malformed candidate is discarded,
   never repaired.
6. **Decide** with `ActionRegisterEngine` in `domain/action_register.py`.
7. **Draft and ground** the minutes (`domain/minutes.draft_minutes`); an ungrounded draft is
   discarded and never published.
8. **Audit** an already-redacted record.
9. **Route** every consequential entry to human review under rule R8.

### What is deterministic vs done by the model?

The model proposes; the engine decides. `ActionRegisterEngine` is pure stdlib and replayable: it
computes every acceptance and rejection, every owner resolution, every date and every escalation
from the candidate, the diarized transcript and the market retention pack with an explicit
`as_of`. Given the same inputs it returns the same register byte for byte, forever.

Concretely, the engine owns:

- **Acceptance.** The citation span must land in a real turn, an action's owner must resolve to a
  participant, a due phrase that was given must parse, and a duplicate is rejected. A failing
  candidate is REJECTED with the reason recorded, not repaired.
- **Owner resolution**, with three outcomes so a hallucination is not mistaken for a genuine gap:
  a name that IS a participant resolves; `I` or `we` with nobody named is unassigned (accepted and
  flagged); a name that is NOT a participant is unresolvable and rejected, because the model
  attributed the commitment to somebody who was never in the room.
- **The dates.** `sla_due` (the explicit due date if given, else `as_of` plus the pack's
  `action_sla_days`), `decision_due` (`as_of` plus `decision_review_days`) and `retention_until`
  (`as_of` plus `retention_years`), all from `domain/retention.py`.
- **The escalation.** An accepted commitment sets `requires_human_review` when it is an unassigned
  action, when its resolved owner has the `third_party` channel role, or when its text names one
  of the pack's `external_binding_markers`.

The model only extracts candidates and drafts minutes prose. With the generation adapter stubbed
the register and minutes are byte-identical, so a model change cannot move a figure. See
[`../model-card.md`](../model-card.md) for the model boundary and the controls still outstanding.

### Is anything auto-executed?

No, and two follow-on actions are gated in code rather than in a policy document:

- `publish_minutes` REFUSES to publish minutes into the corpus while they carry an unresolved
  consequential entry.
- `dispatch_task` REFUSES to create an external task for a consequential entry that has no review
  reference, so an unapproved commitment yields ZERO downstream calls.

`tests/unit/test_capture_pipeline.py` covers both, and `tests/unit/test_review_routing.py` proves
the escalation is ROUTED (to Hrz7, through `ReviewRouterPort`) in the same call that produced the
result, on the API, CLI and agent paths alike, rather than merely flagged.

### What ports does this repo have that its siblings do not?

`transcription`, `diarization`, `corpus` and `task_router`. Most services built from the same
common base have the audit, identity, review-router, tracer and evaluation ports only. These four
are what makes H6 a meeting service rather than a case-triage service, and they are the ones an
adopter is most likely to rebind to their own recogniser, datastore and task system.

### How does a result reach a person?

Three surfaces, all routing escalations the same way: the HTTP API (`POST /v1/capture` and
`POST /v1/triage`), the CLI (`meeting_capture capture` and `meeting_capture triage`), and the
agent tool table (`triage_case`, `capture_meeting`, `verify_audit_trail`), which is also what the
A2A discovery card at `/.well-known/agent-card.json` is built from, so the card cannot advertise a
skill the service does not implement. There is also an embeddable `ui/` micro-frontend.

### Which capabilities does this repo own vs integrate from the catalog?

It **owns** the meeting-capture domain logic and its artifacts. It **integrates** cross-cutting
concerns owned by sibling platform systems. Do not rebuild these in a fork, and note the
integration state, because two of them are wired and the rest are seams:

| Concern | Owned by (catalog id / repo) | H6's role today |
|---|---|---|
| Human review and maker-checker console | **Hrz7** `human-review-console` | **wired**: every escalation is routed over the shared `review-kit` (rule R8), and the managed router refuses rather than swallowing one |
| AI-quality, eval and model-risk promotion gate | **Hrz4** `model-quality-gate` | **client wired**: `--mode gate` asks it for bundle `meeting-knowledge-capture`; registering the bundle is the open half |
| Observability, immutable WORM audit and FinOps | **Hrz5** `agent-observability` | **partly**: spans go OTLP to its collector when `OTEL_EXPORTER_OTLP_ENDPOINT` is set; the shared audit sink is the open half |
| Governed RAG knowledge base with citations | **Hrz2** `enterprise-knowledge-base` | **port only**: approved minutes are meant to publish here; the managed corpus adapter is a deployment-wired stub |
| Runtime guardrail: prompt-injection defence, output screening | **Hrz1** `agent-guardrail-gateway` | **not wired**: there is no guardrail port yet; redaction is a different control |
| Agent registry, versioning, identity, entitlements | **Hrz3** `agent-registry` | **not wired**: the card is published but nothing registers it |
| Project intake validation | **Rsk3** `architecture-validator` | **not code**: an intake action, recorded in `COMPLIANCE.md` when the project passes |

So the guardrail, the knowledge base, the eval platform, the audit sink and the review console are
*dependencies*, not features of this repo. The full row-by-row status is in
[`../../COMPLIANCE.md`](../../COMPLIANCE.md).

### Can I use this for something other than meetings?

Yes, if the shape matches: a transcript or conversation in, a deterministic register of
obligations out, under human review. The reusable half is the hexagon, the redact-before-model
ordering, the acceptance and owner-resolution pattern, the grounding check, the eval gate and the
Hrz7 routing. The vertical half (the artifact models, the retention packs, the fixtures, the
golden set) is what you replace. See [`../ADOPTING.md`](../ADOPTING.md) and
[adoption-faq.md](adoption-faq.md).

### How do I see it working?

Everything runs offline on synthetic data, with no cloud project, no credentials and no browser
engine:

```bash
make demo             # presenter-paced: nine steps, narrated on the terminal, waits for you
make demo-selftest    # the same arc headless and unattended, asserting every step
make demo-static      # writes demo.json plus out/index.html and out/step-*.html for screenshots
make portability      # the executable portability claim, pass or fail per named check
```

The arc opens the stack, triages a routine case and a consequential one, captures a meeting,
plants a national identifier and proves it is masked before the audit write, shows the reviewer's
queue, verifies and exports the audit trail, rewrites a record and detects it, then swaps to the
exit profile and watches every seam refuse. A step lives in `demo.STEPS` and in
`walkthrough.CHECKS`, and `tests/unit/test_demo_surface.py` holds the two equal, so a claim the
demo makes but nobody verifies cannot exist.
