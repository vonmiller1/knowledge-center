# Adopting this repo as your base

This repository (H6, Meeting Knowledge Capture) is a **common base** that a bank or other
regulated institution forks to build its own **meeting-to-action capture service**: a service
that ingests a meeting recording or transcript, redacts it before any model sees it, lets a model
propose candidate commitments, and then decides every acceptance, owner, date and escalation in
pure deterministic code before routing the consequential ones to a human reviewer. It ships a
reusable hexagonal core (a stdlib-only domain, ten typed ports, three swappable adapter families,
a green offline gate) plus a fully worked meeting vertical (transcription, diarization, the
action register, grounded minutes, corpus publication and task dispatch) that you can keep,
retune, or replace with your own artifacts.

This guide is the step-by-step for making it yours. It has two halves: a **mechanical rebrand**
(one script) and the **human decisions** the script cannot make for you.

> Related reading: [`ARCHITECTURE.md`](../ARCHITECTURE.md) (the port table and topology),
> [`CONTRIBUTING.md`](../CONTRIBUTING.md) (the file-by-file touch list for adding an adapter or a
> port), [`COMPLIANCE.md`](../COMPLIANCE.md) (principle to control map),
> [`model-card.md`](model-card.md) (the model boundary and the controls still outstanding), and
> the [`faq/`](faq/) directory.

---

## 1. What you keep vs what you rewrite

The core is hexagonal, and the boundary between reusable machinery and this meeting vertical is a
physical module split with an enforced dependency direction (practices-audit check A7).
`domain/kernel.py` holds the vertical-neutral types and imports nothing from `meeting_capture`,
so you can import it without loading a line of meeting logic. `domain/models.py` holds this
vertical's request and result types and imports `kernel`, never the reverse. It does not
re-export the kernel names, so a consumer imports both explicitly and the split stays visible in
every import line.

| Layer | Where | For a new vertical |
|---|---|---|
| **Kernel** (vertical-neutral) | all of `domain/kernel.py`: `utcnow`, the `Severity` and `Decision` `StrEnum` vocabularies, `Citation`, and the already-redacted `AuditEvent`. Plus the ten Protocols in `ports/` with the identity vocabulary in `ports/identity.py`, and the binding and container machinery in `config.py`. | keep untouched |
| **Policy** (your numbers) | the per-market retention packs in `config/packs/*.yaml` (`action_sla_days`, `decision_review_days`, `retention_years`, `external_binding_markers`), loaded and validated by `domain/retention.py`; the `_SEVERITY_KEYWORDS` bands in `domain/triage_service.py`; the `JURISDICTIONS` tuple in `domain/pii.py`; the `THRESHOLDS` map in `eval/run_eval.py`. | change deliberately (see section 4) |
| **Vertical** (the meeting artifacts) | `domain/models.py` (`TriageInput`, `TriageResult`) and `domain/meeting.py` (`SpanCitation`, `Candidate`, `RegisterEntry`, `Register`, `Minutes`, and the `CommitmentKind` / `DecisionState` / `RegisterOutcome` / `OwnerResolution` vocabularies); the engines in `domain/action_register.py`, `domain/candidates.py`, `domain/dates.py`, `domain/minutes.py`; the orchestrators `domain/capture_service.py` and `domain/triage_service.py`; `domain/turns.py`; the local fixtures and the eval golden sets. | rewrite for your artifacts |

If your product is another *transcript to obligation* vertical (a call-centre QA reviewer, a
credit-committee minute taker, a board-pack secretary), most of this transfers directly:
`domain/turns.py` (deterministic assembly plus redact-before-model), the acceptance and owner
resolution pattern in `domain/action_register.py`, the grounding check in `domain/minutes.py`,
the eval gate and the `human-review-console` human-review routing. You replace the artifact models, the retention
packs and the golden set.

**One honest caveat about the stdlib-only domain.** `domain/` is stdlib plus the workspace kits,
with exactly one recorded exception: `domain/retention.py` imports `yaml` to load the retention
packs. That is not an oversight. It is a written exemption in
`tests/unit/test_core_purity.py::EXEMPT_IMPORTS`, with extraction to the configuration boundary
queued, and the scan fails the build on any import that is not listed there. If you move pack
loading to your own configuration layer, delete the exemption row in the same commit.

## 2. Core-vs-adopter-owned files (so upstream merges stay mechanical)

Upstream keeps evolving these; avoid diverging from them so you can pull fixes cleanly:

- **Upstream-owned** (take our changes): `domain/kernel.py`, everything in `ports/`,
  `tests/contract/`, the eval harness mechanics in `eval/run_eval.py` (the `agent_eval_kit`
  scaffold and the smoke / gate split, not the thresholds), the CI workflows, the binding
  machinery in `config.py` (`DEFAULT_BINDINGS`, `Container`), the `infra/terraform/` baseline, and
  the tooling in `scripts/` (`check_docs_links.py`, `lock.py`, `drop_ui.py`).
- **Adopter-owned** (yours; expect to edit): the *values* in `config/settings.yaml`, every
  retention pack in `config/packs/`, `adapters/onprem/*`, the seeded fixtures in
  `adapters/local/_fixtures.py` and `tests/fixtures/sample_cases.py`, `eval/datasets/*` and the
  `THRESHOLDS` map, UI theming in `ui/`, and the jurisdiction rows in `COMPLIANCE.md`.

Track upstream via git tags; rebase your adopter-owned changes onto each release rather than
merging `main` continuously, so conflicts stay in the files you were told to expect.

## 3. The mechanical rebrand (one script)

`scripts/rename_fork.py` rewrites the python package (`meeting_capture`), the console-script name
(`meeting_capture`, which in this repo is the same token as the package), the `MEETCAP` env-var
prefix, the Terraform `name_prefix` stem (`h6-svc`) and the distribution / git id
(`meeting-knowledge-capture`) across the tree in one simultaneous pass. Preview first, then
apply:

```bash
# Preview (writes nothing):
python scripts/rename_fork.py --package acme_meetings --cli acme-meetings \
    --env-prefix ACME --resource acme-meetings --dry-run

# Apply, sweeping the Markdown prose as well:
python scripts/rename_fork.py --package acme_meetings --cli acme-meetings \
    --env-prefix ACME --resource acme-meetings --include-docs --yes

# Then recreate the environment (the distribution name changed) and prove it is green:
python3.12 -m venv .venv && source .venv/bin/activate
make install
make gate
make docs-check
```

`--dist` defaults to the package name with underscores turned into hyphens. Note that this repo's
own git id (`meeting-knowledge-capture`) does **not** follow that rule: the package is
`meeting_capture` while the git id is `meeting-knowledge-capture`. If your git id differs from
the hyphenated package name too, pass `--dist` explicitly. Omit `--include-docs` if you want the
code renamed but the prose reviewed by hand first. The script deliberately does NOT touch the human
decisions below.

## 4. The human decisions (the script cannot make these)

1. **Region and residency.** The region is chosen once and shared: `GCP_REGION` feeds `region:`
   in `config/settings.yaml`, and Terraform takes `var.region` validated against
   `var.allowed_regions` at plan time. Both default to `asia-southeast1`. Set them together, and
   add `var.additional_resource_locations` only if your org policy evaluates the location-less
   global edge objects. See [`runbook.md`](runbook.md) and
   [`onprem-migration.md`](onprem-migration.md).
2. **Identity and your IdP.** This repo owns no login flow. The `gcp` profile verifies the
   IAP-injected assertion against the configured `MEETCAP_IAP_AUDIENCE` (unset or emptied
   REFUSES, because an unverified audience accepts any Google-signed token), `local` uses seeded
   dev personas that refuse to construct unless `local` was chosen deliberately, and `onprem` is a
   client-IdP placeholder that raises. Configure IAP on the deployed service, read the
   `iap_audience` Terraform output after the first apply, and set the variable. The browser-side
   half is in [`../ui/README.md`](../ui/README.md).
3. **The SLA, decision-review and retention windows.** These are the numbers your compliance
   function owns, and this repo really computes with them:
   `RetentionPack.sla_due` (an action's explicit due date, else `as_of` plus `action_sla_days`),
   `RetentionPack.decision_due` (`as_of` plus `decision_review_days`) and
   `RetentionPack.retention_until` (`as_of` plus `retention_years`, with a deterministic
   29 February fallback), all in `domain/retention.py` and applied by
   `ActionRegisterEngine._evaluate` in `domain/action_register.py`. The shipped packs
   (`config/packs/sg.yaml`, `au.yaml`, `jp.yaml`) carry obviously synthetic numbers. Replace them
   per market. `external_binding_markers` is the other consequential list in the same file: a
   commitment whose text names one of those words is externally binding and is escalated to human
   review, so a missing marker is a commitment that ships unreviewed.
4. **The severity bands.** `_SEVERITY_KEYWORDS` in `domain/triage_service.py` is a module
   constant, not a settings block. That is the open B4 item in
   [`practices-audit.md`](practices-audit.md). Change the keywords deliberately and pin your
   values with a test; better still, lift them into a frozen policy dataclass as part of adoption.
5. **The PII jurisdiction set.** `JURISDICTIONS` in `domain/pii.py` selects and ORDERS rows from
   the shared `pii-kit`. Order matters: the national-ID rows run before the universal email and
   phone rows, and a bare-digit account catch-all you add must go last so it does not subsume a
   national id.
6. **Fixtures are fictional, and stay that way.** Three fixture meetings ship (`sg-1`, `au-1`,
   `jp-1`), one per market pack, in `adapters/local/_fixtures.py`, plus the triage cases in
   `tests/fixtures/sample_cases.py`. Every party is obviously fictional and every domain is
   `.example`. Replace them with your own synthetic data. **Do not run against real recordings
   without your own security, privacy and model-risk sign-off.**
7. **The eval golden set.** `eval/datasets/golden_meetings.jsonl` and `golden_cases.jsonl` with
   the six `THRESHOLDS` in `eval/run_eval.py` (`extraction_f1`, `register_accuracy`,
   `sla_exactness`, `groundedness`, `review_safety`, `pii_safety`, all at 0.99) are what
   `make gate` measures. A fork inherits a green gate that measures the WRONG meetings until you
   rebuild them. The bundle name `meeting-knowledge-capture` is what `--mode gate` asks `model-quality-gate`
   about; rename it and register your own.
8. **Deployment posture.** Review the Dockerfile (digest-pinned base, non-root uid 10001,
   `HEALTHCHECK` on `/healthz`) and `infra/terraform/` before you expose anything: the serving
   edge is opt-in (`var.production_edge_enabled` defaults to false), the VPC-SC perimeter starts
   in dry run (`var.vpc_sc_enforce` defaults to false), the WORM bucket lock
   (`var.worm_locked`, default true) is irreversible, and `var.enable_org_policies` needs
   `roles/orgpolicy.policyAdmin`. Decide each one deliberately rather than inheriting it.
9. **The model controls that are still outstanding.** [`model-card.md`](model-card.md) lists them
   and they are yours to close before a managed deployment: pin the model id, version and routing
   for the `gcp` generation adapter and wire the extraction and narration prompts; add a
   per-tenant token budget, a request rate limit and a kill switch that forces deterministic-only
   operation; add a managed-profile eval run that scores the real model rather than the
   deterministic stub; and screen the transcript for prompt injection through the `agent-guardrail-gateway`,
   failing closed to deterministic-only when the screen is unavailable. Until those are closed the
   system is safe to run offline and the managed model path is not production-cleared.

## 5. Do not duplicate the platform

This repo is one system in a catalog of composable GRC systems. Several concerns it *touches* are
owned by sibling platform services, and you should integrate rather than rebuild them. Be
accurate about which are already wired here, because the honest answer is "two of them are, and
the rest are seams":

| Sibling | What it owns | State in this repo |
|---|---|---|
| `human-review-console` human-review and maker-checker console | every `requires_human_review` escalation in the catalog | **Wired.** `ports/review_router.py` with an adapter in all three families; the managed one submits over the shared `review-kit` to `review_url` (`HUMAN_REVIEW_URL`) and REFUSES rather than swallowing an escalation when it is empty. Rule R8 is Covered in `COMPLIANCE.md`. |
| `model-quality-gate` | the promotion verdict and the metric bundle | **Client wired, registration outstanding.** `adapters/gcp/evaluation.py` and `eval/run_eval.py --mode gate` ask `model-quality-gate` for bundle `meeting-knowledge-capture` and refuse to run off the managed profile. Registering the bundle and its thresholds with `model-quality-gate` is the open half (P-08, R5). |
| `agent-observability`, immutable audit and FinOps | shared traces and the WORM audit sink | **Partly.** The tracer exports OTLP to the `agent-observability` collector when `OTEL_EXPORTER_OTLP_ENDPOINT` is set and to Cloud Trace when it is not; the audit trail is hash-chained and anchored locally, with `infra/terraform/logging_worm.tf` providing the locked bucket. Binding the prompt and response record to the shared sink is the open half (R2). |
| `enterprise-knowledge-base` governed knowledge base (RAG with citations) | ACL-aware retrieval over the bank corpus | **Port only.** `ports/corpus.py` exists and the `local` adapter publishes and retrieves in memory, but `adapters/gcp/corpus.py` is a deployment-wired stub that raises. Approved minutes are meant to publish here; wire it before you claim retrieval. |
| `agent-guardrail-gateway` | prompt-injection defence and output filtering | **Not wired.** There is no `GuardrailPort` in `ports/`. Redaction before the model is this repo's own (`domain/turns.redact_for_model`), which is a different control. R1 stays Partial until the gateway is bound. |
| `agent-registry` | agent identity, versioning and entitlements | **Not wired.** The A2A card is published at `/.well-known/agent-card.json` from the same tool table the runtime binds, but nothing registers it. R4 stays Partial. |
| `architecture-validator` architecture and requirements validator | project intake validation | **Not wired, and not code.** R6 is an intake action: record the validation reference in `COMPLIANCE.md` when the project passes. |

The managed transcription, diarization, generation and task-router adapters are in the same
state as the corpus one: the class exists, the SDK import is lazy and correct, and the call
raises `NotImplementedError` naming the runbook. That is deliberate honesty rather than a
finished managed profile, and closing it is deployment work you own.

## 6. Adoption checklist

- [ ] Ran `scripts/rename_fork.py`, recreated the venv, `make gate` and `make docs-check` green.
- [ ] Set `GCP_REGION`, Terraform `var.region` and `var.allowed_regions` to your in-country region.
- [ ] Configured IAP on the deployed service and set `MEETCAP_IAP_AUDIENCE` from the Terraform output.
- [ ] Replaced every retention pack in `config/packs/` with your own SLA, review, retention and external-binding values.
- [ ] Owned the severity bands in `domain/triage_service.py` with your compliance function, and pinned them with a test.
- [ ] Set `JURISDICTIONS` in `domain/pii.py` to the markets you serve, with the catch-all rows ordered last.
- [ ] Replaced the three fixture meetings and every synthetic triage case.
- [ ] Rebuilt the eval golden set, chose your thresholds, and registered your bundle with `model-quality-gate`.
- [ ] Reviewed the deploy posture (Dockerfile, the four Terraform toggles, the loopback bind).
- [ ] Closed or accepted each outstanding model control in [`model-card.md`](model-card.md).
- [ ] Wired your `human-review-console` review endpoint and decided which remaining sibling systems you integrate vs stub.
- [ ] Recorded your baseline upstream tag so you can take future fixes.
