# Security FAQ

For an AppSec reviewer sizing up this repo. It explains what the attack surface is, where the
evidence lives, and what is deliberately not built yet, because a control claimed before it
exists is worse than a control that is owed.

## What does this system actually process?

Meeting audio references and transcripts, which is to say **content full of personal data**:
speaker names, organisation names, whatever the participants said out loud, and in the shipped
fixtures a planted national identifier. That is the opposite of the aggregate-only posture some
sibling repos have, so every PII control here is a real control rather than an N/A.

The pipeline is `MeetingCaptureService.capture` in `domain/capture_service.py`: ingest through
the transcription and diarization ports, assemble the turns deterministically, **redact**,
extract candidate commitments with the model, schema-validate them, run the deterministic action
register, draft and ground the minutes, write an already-redacted audit record, then route every
consequential entry to human review.

## Where exactly is the redaction boundary?

There are three, and the order is the security order:

1. **Before any model call.** `domain/turns.redact_for_model` masks every turn's text with the
   shared `pii-kit` rows selected by `domain/pii.JURISDICTIONS`, and strips per-word offsets from
   the redacted copy on purpose (masking changes character lengths, so an offset computed on the
   original no longer lines up and a stale offset is worse than an absent one). Every downstream
   stage sees only the redacted transcript.
2. **Before the audit write.** `TriageService.triage` in `domain/triage_service.py` redacts before
   anything reaches the sink, so the WORM record is already-redacted by construction, not
   redacted on read.
3. **Before the wire.** `adapters/_review_payload.py` redacts the review payload against EVERY
   jurisdiction's rows, because the human-review console is a shared sink.

The first one is asserted, not asserted-about: `tests/unit/test_capture_pipeline.py` binds a spy
generation adapter and
`test_the_model_never_sees_an_unredacted_identifier` fails if the planted identifier reaches the
generation port. `test_the_audit_record_is_redacted` covers the second.

## Can a caller spoof the actor?

No. `TriageRequest` carries no `actor` field; the audit actor and the review maker are both the
verified `Principal` the bound `IdentityPort` produced. Under `gcp` that is
`adapters/gcp/identity.py`, which calls `id_token.verify_token` with the configured
`MEETCAP_IAP_AUDIENCE` and with IAP's own key set rather than google-auth's OAuth2 default, and
checks the issuer itself because `verify_token` does not. The audience is read in three states:
unset or emptied REFUSES, because `audience=None` is documented as not verifying the audience at
all and would accept any Google-signed token from any project.

Under `local` the personas are seeded dev identities that refuse to construct unless `local` was
chosen deliberately. Under `onprem` the adapter raises rather than falling back.

## What stops the service serving unauthenticated end-user routes?

A module-scope loopback exposure guard in `api/app.py`, bound at module scope because the
Dockerfile `CMD` and `make run-api` serve the app OBJECT and a bound that lives only in `main()`
never runs in a shipped process. Its posture is derived from the **identity binding** and from
nothing else: the adapter declares `VERIFIED`, `CLIENT_ASSERTED` or `UNIMPLEMENTED`
(`ports/identity.py`), and silence reads as client-asserted. `MEETCAP_S2S_TOKEN` may never enter
that decision, because it authenticates a calling service and no end user.
`tests/unit/test_serving_path_exposure.py` and `tests/unit/test_end_user_auth_posture.py` are the
standing gates, and the IAP verifier has its own crypto matrix
(`tests/unit/test_iap_crypto_matrix.py`) run against a locally minted key in a dedicated CI job.

`/docs`, `/redoc` and `/openapi.json` are registered only when the exposure profile is the
deliberate `local`. Under `gcp` they are ABSENT rather than guarded, because a guard the profile
has switched off is no guard.

## What about outbound service-to-service calls?

The real one is the `human-review-console` review submission (`adapters/gcp/review_router.py`) over the shared
`review-kit`, which is stdlib `urllib` with S2S headers wire-compatible with
`hex-service-kit`'s server verifier. Its credentials are `HUMAN_REVIEW_S2S_TOKEN` and
`HUMAN_REVIEW_S2S_SIGNING_KEY`, deliberately distinct variables from this service's own INBOUND
`MEETCAP_S2S_TOKEN`. The managed router REFUSES when no console URL is configured rather than
swallowing the escalation.

## Are there secrets in the repo?

No literal secret material. `config/settings.yaml` carries variable NAMES and non-secret defaults
with `${VAR:-default}` interpolation; `.env.example` carries names; `.env.secrets.example` carries
placeholders. Practices check C10 covers this.

## What is the supply-chain posture?

Committed `requirements-dev.lock` and `requirements-gcp.lock`, installed with `--no-deps` by
`make install`, CI and the Dockerfile; the catalog commons pinned to 40-character commit shas
rather than tags; a digest-pinned base image; SHA-pinned Actions; dependabot per ecosystem; and
`pip-audit` over both locks as a hard CI failure (`make audit` locally).
`tests/unit/test_repo_artifacts.py` asserts each of these from inside the repo.

## Is the audit trail tamper-evident?

Yes, with an honest limit named and then closed. The trail is append-only and SHA-256
hash-chained, which detects an in-place edit, a deletion and a reorder. It does **not** by itself
detect a truncated tail: dropping the newest rows leaves a shorter chain that verifies perfectly.
So `audit_anchor_path` (`MEETCAP_AUDIT_ANCHOR`) writes the chain head to a file on a different
volume on every append. `tests/unit/test_audit_anchor.py` proves the detection, proves the control
case goes UNDETECTED without an anchor, and proves an append after truncation refuses rather than
re-anchoring. The anchor is empty by default, which is correct for the ephemeral `:memory:` store
and wrong for a durable one.

## What does the deployment stack actually enforce?

`infra/terraform/` is a real stack, not a skeleton: `org_policy.tf` pins
`constraints/gcp.resourceLocations` to the selected region's location group and forbids
service-account key creation, `kms.tf` creates a REGIONAL CMEK key ring and key with 90-day
rotation and per-service-agent bindings, `vpc_sc.tf` stands up a dry-run-first VPC Service
Controls perimeter, `logging_worm.tf` creates the locked WORM log bucket, `iam.tf` creates one
least-privilege serving identity, and `production_edge.tf` sets
`INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER` so the `run.app` URL is not a way in.

The honest limit: `infra/terraform/production_edge.tftest.hcl` encodes those posture claims as
mock-provider plan tests, but nothing in this repo runs it. There is no `make tf-check` target
and no terraform CI job, so the terraform assertions are documentation-grade rather than
build-guarded today. `make gate` is deliberately offline and would not run terraform in any case.

## What is deliberately NOT built yet?

Read this list rather than inferring from the green gate:

- **Prompt-injection defence and output filtering.** There is no `GuardrailPort` and no `agent-guardrail-gateway`
  binding. Redaction is not injection defence. Rule R1 in [`../../COMPLIANCE.md`](../../COMPLIANCE.md)
  stays Partial until the gateway is bound.
- **Resilience controls.** No timeouts, no circuit breaker and no documented kill switch for
  outbound dependencies (P-10). The review path degrades correctly (the outbox retains an
  escalation the console could not take); nothing else does.
- **The model controls.** The model id and routing are not pinned, there is no token budget or
  rate limit, and the managed model is not evaluated against the golden set. They are listed in
  [`../model-card.md`](../model-card.md), which this FAQ does not restate.
- **Object-level authorisation.** There is no queryable store yet, so tenant isolation is carried
  on outbound reviews only (C2, and the Tenant isolation row in `COMPLIANCE.md`).
- **`agent-registry` registration.** The A2A card is published but nothing registers it (R4).

## What is explicitly out of scope for this repo?

The guardrail gateway (`agent-guardrail-gateway`), the governed knowledge base (`enterprise-knowledge-base`), the agent registry (`agent-registry`), the
AI-quality and promotion gate (`model-quality-gate`), the shared observability and WORM audit sink (`agent-observability`), and
the human-review console (`human-review-console`). This repo integrates those through ports rather than
re-implementing them. See [features-faq.md](features-faq.md) for the full boundary map and which
of them are actually wired today.
