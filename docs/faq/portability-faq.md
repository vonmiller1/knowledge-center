# Portability FAQ

For architecture, cloud and exit-planning reviewers who want to know how real the "no lock-in"
claim is, and how an off-cloud or sovereign exit would actually work.

## What is the no-lock-in claim, concretely?

`src/meeting_capture/domain/` and `src/meeting_capture/ports/` import only the standard library
and the workspace kits (`hex-service-kit`, `pii-kit`, `speech-lexicon-kit`, `review-kit`,
`agent-eval-kit`, and the others listed in `tests/unit/test_core_purity.py::ALLOWED_KITS`, all of
which are themselves stdlib-pure). No web framework, no cloud SDK, no HTTP client. The rule is an
allowlist rather than an SDK blocklist, because a blocklist rots the day a vendor renames a
distribution, and `tests/unit/test_core_purity.py` walks the AST of both layers and fails the
build on anything not allowed.

**There is exactly one recorded exception, and it is not a loophole.**
`domain/retention.py` imports `yaml` to load the per-market retention packs. It is listed by name
in `EXEMPT_IMPORTS` with a written reason ("retention rules are parsed inside the core; extraction
to the config boundary is queued"), so it is debt with a name on it rather than an allowance. Any
import not on that list fails the scan. Read the domain claim as "stdlib-only plus the workspace
kits, with one named and queued exception", not as an unqualified purity claim.

## What are the profiles?

One variable, `MEETCAP_PROFILE`, selects the whole adapter stack, and it resolves THREE states at
import into a `ProfileChoice`: unset is NO CHOICE (never a silent `local`), set-and-empty raises,
and an unknown or mis-capitalised value raises. Both raises kill the process before it can serve.

- **`local`** is a real, working, SDK-free offline stack: fixture transcripts, a deterministic
  generation stub, an in-memory corpus and task store, seeded dev personas, and a hash-chained
  audit log. It is the dev, test and CI default and the working proof that the domain runs
  entirely off-cloud.
- **`gcp`** is the managed family, with every cloud SDK imported LAZILY inside the method so the
  other two profiles import the tree with no SDK installed. Proved by BLOCKING the import in a
  fresh interpreter (`tests/contract/_sdk_free_probe.py`) rather than by the SDK happening to be
  absent from the machine.
- **`onprem`** is the exit family: placeholders that satisfy the same Protocols and RAISE rather
  than pretending, so the portability claim cannot be silently false.

## What are the ports?

Ten, all `@runtime_checkable` Protocols re-exported once from `ports/__init__.py` with the
`PORT_PROTOCOLS` map: `audit`, `identity`, `review_router`, `transcription`, `diarization`,
`generation`, `corpus`, `task_router`, `tracer` and `evaluation`. The transcription, diarization,
corpus and task-router ports are specific to this vertical and do not exist in the sibling
services built from the same base.

A port is registered in FIVE places or it runs with no enforcement at all
(`ports/__init__.py`, `config.DEFAULT_BINDINGS`, a `Container` accessor, `config/settings.yaml`,
and a `PortCase` in `tests/contract/canonical.py`), and
`tests/contract/test_port_parity.py` asserts set equality across all five.

## Which managed adapters are actually implemented?

This matters more than the port count, so here is the honest split. Real in the `gcp` family:
`audit.py` (Cloud Logging), `identity.py` (IAP assertion verification), `review_router.py` (`human-review-console`
over `review-kit`), `tracer.py` (OpenTelemetry through the commons), `evaluation.py` (the
`model-quality-gate` promotion client). Deployment-wired stubs that construct the client and then raise
`NotImplementedError` naming [`../runbook.md`](../runbook.md): `transcription.py`,
`diarization.py`, `generation.py`, `corpus.py`, `task_router.py`.

That is deliberate: the lazy-import shape, the settings binding and the contract conformance are
all proved, and the deployment specifics (which recognizer model, which datastore, which queue)
are an adopter decision. It is not a finished managed profile, and this repo does not claim one.

## Is the portability claim tested, or just asserted?

Tested, and bounded. `make portability` (`scripts/portability_demo.py`) runs eight named checks
with a pass or fail each: port-map completeness, adapter construction and Protocol conformance,
the offline family ANSWERING, the exit family REFUSING, in-place rewrite detection, anchored
truncation detection with its control case, the JSON Lines export and foreign reload, and the
no-cloud-SDK check. It prints what it does NOT prove and exits non-zero on any failure.

Alongside it, `tests/contract/test_port_parity.py` proves every port binds in every profile with
the cloud SDKs unimportable, and `tests/contract/test_behavioral_parity.py` proves the same
request behaves the same at each family's boundary: offline answers, on-premises raises, managed
refuses rather than silently succeeding.

## How would a sovereign or on-premises exit actually go?

The `onprem` family is the scaffold: each fail-fast placeholder marks a seam where a client
supplies their own component (their recogniser, their diarizer, their model host, their IdP,
their audit store, their review console, their task system). Because the domain never changes,
the exit is an adapter exercise rather than a rewrite. The audit trail exports to and restores
from JSON Lines, so the data half of the exit is a file copy. The written path is
[`../onprem-migration.md`](../onprem-migration.md), and the operating rules are in
[`../runbook.md`](../runbook.md).

## How is data residency handled?

The region is chosen once (`asia-southeast1` by default) and shared: `GCP_REGION` feeds `region:`
in `config/settings.yaml`, which `/healthz` reports and the agent card prints, so a drifting
deployment is visible. At deploy time `infra/terraform/variables.tf` validates `var.region`
against `var.allowed_regions` at plan time, `org_policy.tf` pins
`constraints/gcp.resourceLocations` to that region's location group, `kms.tf` creates a REGIONAL
key ring (never a multi-region one), and `vpc_sc.tf` draws a dry-run-first perimeter around the
sovereignty-critical APIs. A second market is a tfvars change, not a fork.

## Can the data be exported in an open format?

Yes. The audit trail exports to and reloads from JSON Lines through the commons
`HashChainedAuditLog`, and `scripts/portability_demo.py` performs an export and a FOREIGN reload
as one of its named checks, so the claim is executed rather than described. The register, the
minutes and the citations are frozen dataclasses over plain types, so serialising them needs no
vendor library.

## What is honestly NOT portable?

- **The managed vertical adapters**, as above: five of the ten `gcp` bindings raise today.
- **Tamper-evidence limits.** The in-repo hash chain plus anchor detects edits, reorders,
  deletions and truncation. It is not a substitute for the managed WORM sink (the locked Cloud
  Logging bucket in `logging_worm.tf`, or `agent-observability`) in production, and
  `scripts/portability_demo.py` says so rather than overclaiming.
- **The terraform posture claims** are encoded as mock-provider plan tests in
  `infra/terraform/production_edge.tftest.hcl`, but nothing in this repo runs them: there is no
  `make tf-check` target and no terraform CI job. Treat them as reviewed intent, not as a
  build-guarded invariant.
