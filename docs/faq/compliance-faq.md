# Compliance FAQ

For compliance, privacy and model-risk teams assessing this repo's regulatory posture.
Cross-references: [`../../COMPLIANCE.md`](../../COMPLIANCE.md) (the full P-01 to P-13 and R1 to R8
map with an evidence file per row, plus the adopter-owned crosswalk),
[`../../SPEC.md`](../../SPEC.md), and [`../model-card.md`](../model-card.md) for the model
boundary, which this FAQ points at rather than restates.

### Is this making decisions autonomously?

No. It is a decision-support service, and the separation is structural rather than a policy
statement. Every consequential value comes from `domain/action_register.py`, which is pure stdlib
and replayable: acceptance and rejection, owner resolution, the SLA and retention dates, the
decision state and the escalation flag. The model proposes candidate commitments and drafts
minutes prose; it never produces a number or a verdict. With the generation adapter stubbed the
register and the minutes are byte-identical, so a model change cannot move a figure.

Anything consequential (an unassigned action, one whose resolved owner carries the `third_party`
channel role, or one whose text names an external-binding marker in the market's retention pack)
sets `requires_human_review` and is
ROUTED to the Hrz7 human-review console in the same call that produced it, over the shared
`review-kit` (dependency rule R8). Setting the flag and calling the router is one act, not
two. The managed router REFUSES when no console is configured rather than swallowing the
escalation, and two follow-on actions are gated in code: minutes will not publish to the corpus
while an unresolved consequential entry remains, and no external task is created for a
consequential entry with no review reference.

### How is personal data handled?

This service processes meeting transcripts, so unlike some sibling systems it has a real PII
surface and real controls rather than an omitted-by-design declaration.

Redaction happens at three boundaries in this order: before ANY model call
(`domain/turns.redact_for_model`), before the audit write (`domain/triage_service.py`), and before
the review payload leaves the process (`adapters/_review_payload.py`, against every
jurisdiction's rows because the console is a shared sink). The pattern rows come from the shared
`pii-kit` with the selection and ORDER owned by `domain/pii.JURISDICTIONS` (SG, HK, JP, AU as
shipped): national-ID rows run first, universal email and phone rows last.

The first boundary is the one adopters ask about, and it is asserted rather than asserted-about:
a spy generation adapter in `tests/unit/test_capture_pipeline.py` fails the build if a planted
national identifier reaches the generation port.

### How long is data kept, and who decides?

You do. `config/packs/{sg,au,jp}.yaml` carries `retention_years` per market alongside
`action_sla_days` and `decision_review_days`, loaded and validated by `domain/retention.py`, and
`RegisterEntry.retention_until` is computed from it with an explicit `as_of`. The shipped numbers
are obviously synthetic reference values, not a recommendation. Separately, the WORM audit bucket
in `infra/terraform/logging_worm.tf` has its own `var.retention_days` with a 180-day floor and an
IRREVERSIBLE lock, so that window is a deliberate decision made once.

The legal basis for the audit trail and the institution's own retention schedule are
adopter-owned; `COMPLIANCE.md` says so explicitly in its closing section.

### How is the work auditable and reproducible?

Every capture writes an already-redacted `AuditEvent` whose actor is the verified principal, never
a client-supplied value. The trail is append-only and SHA-256 hash-chained, and it is externally
ANCHORED (`MEETCAP_AUDIT_ANCHOR`), because a hash chain alone cannot detect a truncated tail.
`tests/unit/test_audit_anchor.py` proves the detection AND proves the control case goes undetected
without the anchor.

Every register entry carries a span citation back into the transcript turn it came from, and the
engine is deterministic, so a reviewer can recompute the whole register from the same transcript,
the same candidates, the same pack and the same `as_of`. The enterprise WORM sink is Hrz5 and the
locked Cloud Logging bucket; the in-repo chain is the offline stand-in, with its limits stated in
[security-faq.md](security-faq.md) rather than glossed.

### What is the model-risk story?

There is a model card at [`../model-card.md`](../model-card.md) and it is the authority here: it
records what the model does and does not do, the validation applied to its output, the adapter per
profile, and the controls still outstanding before a managed deployment. Read it rather than this
paragraph.

The gate half: `eval/run_eval.py --mode smoke` runs in `make gate` on every change and scores six
metrics at a 0.99 threshold against a golden set of meetings, including a `pii_safety` metric
scored two independent ways. `tests/unit/test_not_falsely_green.py` and
`tests/unit/test_eval_metrics_go_red.py` prove the metrics can go red. `--mode gate` delegates the
promotion verdict to Hrz4 under the bundle `meeting-knowledge-capture` and refuses to run off
the managed profile, because a repo that scored itself and promoted itself would be a gate in name
only. Registering that bundle and its thresholds with Hrz4 is an open item (P-08 and R5).

### Is data residency enforced, or only documented?

Enforced at deploy time, and the terraform is the enforcement rather than the description. The
region is chosen once and shared between the runtime (`GCP_REGION` feeding `region:` in
`config/settings.yaml`, reported by `/healthz` and printed on the agent card) and Terraform, where
`var.region` is validated against `var.allowed_regions` at plan time so an unvetted region fails
before apply. On top of that, `org_policy.tf` applies a `constraints/gcp.resourceLocations`
allowlist pinned to the selected region's location group, `kms.tf` creates a REGIONAL CMEK key
ring and key with 90-day rotation and per-service-agent bindings, `vpc_sc.tf` draws a
dry-run-first VPC Service Controls perimeter around the sovereignty-critical APIs, and
`logging_worm.tf` puts the locked audit bucket in the same region under the same key.

Two honest qualifications. The org-policy and perimeter layers are gated on
`var.enable_org_policies` and `var.enable_vpc_sc` (both default true) with an explicitly
documented, explicitly non-compliant quick-evaluation path that turns them off. And nothing in
this repo's own gate runs the terraform posture tests: `production_edge.tftest.hcl` exists, but
there is no `make tf-check` target and no terraform CI job, so those assertions are reviewed
intent rather than a build-guarded invariant.

### Which regulators does this map to?

`COMPLIANCE.md` maps the catalog's own principles (P-01 to P-13) and platform rules (R1 to R8) to
a control and a named evidence file, aligned to MAS TRM, APRA CPS 234 and CPS 230, HKMA and
PDPA-class regimes. The mapping from those rows to a specific regulation, and the judgement that a
control is SUFFICIENT for it, is deliberately **adopter-owned**: it depends on the institution's
risk appetite, its regulator, its licence conditions and its existing control library. No row in
that file should be quoted as regulatory assurance.

### What is still open, honestly?

The rows to raise at a risk forum, all named in `COMPLIANCE.md` and
[`../practices-audit.md`](../practices-audit.md):

- **Guardrail (R1).** No Hrz1 binding, so there is no prompt-injection defence or output filtering
  on the model boundary yet. Redaction is a different control.
- **Grounding (P-05) and retrieval (R3).** The corpus port exists and the offline adapter works,
  but the managed adapter is a deployment-wired stub, so there is no live governed retrieval.
- **Shared observability (R2).** Traces reach the Hrz5 collector when the OTLP endpoint is set;
  the prompt and response record does not yet land in the shared sink.
- **Registration (R4) and promotion (R5).** The A2A card is published and the promotion client is
  wired, but neither is registered with Hrz3 or Hrz4.
- **Resilience (P-10) and cost control (P-11).** No timeouts, circuit breaker, documented kill
  switch, token budget or cache; the CPS 230 recovery objectives are not yet recorded in the
  runbook.
- **Object-level authorisation.** No queryable store yet, so tenant isolation is carried on
  outbound reviews only.
- **Intake validation (R6).** An action, not a control: record the Rsk3 reference when the project
  passes.

### Can we run it against real meetings today?

Not without your own legal, privacy, security and model-risk sign-off. Every fixture and the whole
golden set use obviously fictional parties and `.example` domains, the one national identifier in
the fixtures exists solely so a redaction check has an independent literal to look for, and the
managed model path is not production-cleared while the model-card controls remain open. The
adoption checklist in [`../ADOPTING.md`](../ADOPTING.md) lists what must precede any live use.
