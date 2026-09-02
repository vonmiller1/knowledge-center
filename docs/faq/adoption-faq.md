# Adoption FAQ

For an engineering lead forking this repo as their institution's meeting-capture base. The
step-by-step is [`../ADOPTING.md`](../ADOPTING.md); this answers the "will it hurt later?"
questions.

### How do I rebrand it for my organisation?

`scripts/rename_fork.py` rewrites the package name (`meeting_capture`), the console-script name,
the `MEETCAP` env prefix, the Terraform `name_prefix` stem (`h6-svc`) and the distribution / git
id (`meeting-knowledge-capture`) in one simultaneous pass. Preview with `--dry-run`, apply
with `--yes`, add `--include-docs` to sweep Markdown prose too. Then recreate the venv,
`make install`, and run `make gate`.

Two things to know about this repo specifically. First, the console-script name IS the package
name here (`[project.scripts]` in `pyproject.toml` reads
`meeting_capture = "meeting_capture.cli.main:main"`), which is why the script applies every rule
in one pass rather than sequentially: a sequential replace would rename the command twice.
Second, the distribution id does NOT track the package name (`meeting-knowledge-capture` vs
`meeting_capture`), so `--dist` defaults to the hyphenated package and you should pass it
explicitly if your git id differs from that.

### If several teams fork this, how does each take upstream fixes?

Track upstream via git tags. The repo declares a core-vs-adopter-owned boundary
([`../ADOPTING.md`](../ADOPTING.md) section 2): upstream owns `domain/kernel.py`, `ports/`,
`tests/contract/`, the eval harness mechanics, the CI workflows, the binding machinery in
`config.py` and the Terraform baseline; you own the `config/settings.yaml` values, the retention
packs, `adapters/onprem/*`, the fixtures, the golden set and the jurisdiction rows in
`COMPLIANCE.md`. Rebase your adopter-owned changes onto each release rather than merging `main`
continuously, so conflicts stay in files you were told to expect.

### Is there a separate kernel module I keep untouched?

Yes, and it is a real physical split rather than a described one. `domain/kernel.py` holds the
vertical-neutral machinery (`utcnow`, the `Severity` and `Decision` vocabularies, `Citation`,
`AuditEvent`) and imports nothing from `meeting_capture`. `domain/models.py` holds this vertical's
`TriageInput` and `TriageResult` and imports `kernel`, never the reverse; the meeting artifacts
live one module along in `domain/meeting.py`. Practices-audit check A7 is a PASS on that basis.

Note that `models.py` does **not** re-export the kernel names, so a consumer imports both
explicitly. That is deliberate: the split stays visible in every import line.

### How do I add a new outbound dependency (a new port)?

There is a fixed touch list and the contract test enforces it. A port must be registered in FIVE
places or it runs with no enforcement at all:

1. `ports/__init__.py` (the re-export and the `PORT_PROTOCOLS` map),
2. `config.DEFAULT_BINDINGS`,
3. a `Container` accessor,
4. `config/settings.yaml` under `adapters:`,
5. a `PortCase` in `tests/contract/canonical.py`.

Then bind it in all three families. `tests/contract/test_port_parity.py` asserts set equality
across all five, and `tests/unit/test_settings_file.py` fails the build if
`DEFAULT_BINDINGS` and the settings file disagree. The file-by-file walkthrough is in
[`../../CONTRIBUTING.md`](../../CONTRIBUTING.md).

### How do I add a new adapter to an existing port?

The class under `adapters/<family>/` with one constructor shape, `Adapter(settings)`, and any
cloud import INSIDE the method; the same `module:Class` target in both `config.DEFAULT_BINDINGS`
and `config/settings.yaml`; and any new variable in `.env.example`. The lazy-import rule is not a
style preference: `tests/contract/_sdk_free_probe.py` blocks the SDK import in a fresh interpreter
and the other two profiles must still construct.

### How do I change the policy numbers without touching engine code?

Partly today, and this is worth knowing before you plan the work.

The **retention and escalation numbers are already configuration**: `config/packs/*.yaml` carries
`action_sla_days`, `decision_review_days`, `retention_years` and `external_binding_markers` per
market, loaded and validated by `domain/retention.py`, which REFUSES a pack carrying an unknown
field (a key the engine does not understand is a policy it is not applying). Adding a market is a
new pack file, not an engine edit, and the engine fails closed on a market it has no pack for.

The **severity keyword bands are not**: `_SEVERITY_KEYWORDS` in `domain/triage_service.py` is a
module constant. That is the open B4 item in [`../practices-audit.md`](../practices-audit.md).
Retuning today means editing that tuple; lifting it into a frozen policy dataclass with a
`policy:` block in `config/settings.yaml` is a small addition worth planning as part of adoption
if your compliance function must own those words as configuration.

### How do I change the taxonomy?

The vocabularies (`Severity`, `Decision`, `CommitmentKind`, `DecisionState`, `RegisterOutcome`,
`OwnerResolution`) are `LenientStrEnum` from the shared commons, so a member IS its wire value and
an unknown value from a future release does not crash the reader. Extend a vocabulary without
editing engine code; replace one wholesale by editing the enum in `domain/kernel.py` (neutral) or
`domain/meeting.py` (this vertical) and the label maps in `ui/`.

### Will the eval gate mean anything after I diverge?

Not until you rebuild it, and that is an explicit adoption step rather than a silent pass.
`eval/run_eval.py --mode smoke` runs in `make gate` and scores six metrics against
`eval/datasets/golden_meetings.jsonl`, all at a 0.99 threshold: `extraction_f1`,
`register_accuracy`, `sla_exactness`, `groundedness`, `review_safety` and `pii_safety`. Every one
of them can be driven red, and `tests/unit/test_eval_metrics_go_red.py` proves it per market for
the SLA metric, because a metric that cannot go red is not a metric. But the golden meetings are
the reference ones: a fork inherits a green gate that measures the wrong meetings until it
replaces them. `--mode gate` is the promotion half and delegates the verdict to Hrz4 under the
bundle name `meeting-knowledge-capture`; rename the bundle and register your own.

### Will the demo rot after I diverge?

It is guarded from inside the gate. A step lives in `demo.STEPS` and its expectation lives in
`walkthrough.CHECKS`, and `tests/unit/test_demo_surface.py` holds the two sets equal AND drives
the whole nine-step arc through the real services, applying each check, so a claim the demo makes
that nobody verifies cannot exist. The same script runs headless in the hosted check.
Keep the pattern when you add a step: put the numbers a check reads in the step's `facts` dict,
never only in the rendered rows, because a check that parses prose breaks on a wording change.

### Does the offline gate run for my fork out of the box?

Yes. `make gate` is `ruff check`, `ruff format --check`, `mypy src`, `pytest -m 'not integration'`
and the eval smoke run. It needs no network, no cloud SDK, no project and no credentials, and the
workflow references no `secrets.`. Anything that needs a live service lives in
`tests/integration/` and is deselected by the marker;
`tests/unit/test_test_layout.py` fails the build if such a module is not marked. The one step
that needs network is `make audit` (`pip-audit` over both lockfiles), which is separate locally
and a hard-failing job in CI.

### What do I need to do before any deploy?

Read [`../ADOPTING.md`](../ADOPTING.md) section 4 in full, but the short list is: your region in
both `config/settings.yaml` and tfvars, your IAP audience, your retention packs, your fixtures and
golden set, and a decision on each of the four Terraform toggles (`enable_org_policies`,
`enable_vpc_sc`, `vpc_sc_enforce`, `worm_locked`). The model controls in
[`../model-card.md`](../model-card.md) are the other gate: until they are closed the managed model
path is not production-cleared.
