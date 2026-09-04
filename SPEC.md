# SPEC: Meeting Knowledge Capture (H6)

Locked decisions, pinned stack, contracts. This document is the deepest authority on intent.

## Pinned stack
- Python `>=3.12`; ruff pinned exactly (`0.15.18`); mypy strict; deploy region `asia-southeast1`.
- Commons declared by tag in `pyproject.toml` (`pii-kit@v0.0.1`, `hex-service-kit@v0.0.1`, `agent-eval-kit@v0.0.1`, `review-kit@v0.0.1`, `speech-lexicon-kit@v0.0.1`) and pinned in the lockfiles to the 40-character COMMIT each tag resolved to. A tag can be moved; a commit cannot, so a lockfile that pinned the tag would let what installs change with no diff. `tests/unit/test_repo_artifacts.py` asserts the three-way agreement offline. `speech-lexicon-kit` supplies the transcript, speaker-turn and diarization types and ports (slice 2), so a citation of "turn 4, characters 0..37" means the same thing here as in the sibling speech consumers.
- The `hex-service-kit` pin is a security floor, not a preference: the kit checks the
  service-identity policy before the token, gates the zero-secret local opening on an exact
  profile match, and binds the loopback exposure guard over both HTTP and WebSocket scopes; it
  resolves every environment read in three states, so a variable set to empty fails closed
  instead of inheriting the unset default. Never move this pin backwards.
- Installs are LOCKED: `requirements-dev.lock` and `requirements-gcp.lock` are committed and are
  what `make install`, CI and the container image install. Nothing ships from an uncommitted
  resolve.

## The vertical: meeting to action

The system turns a meeting into a cited action register and grounded minutes. The deterministic
engine is the differentiation; the model only narrates and extracts, schema-validated and
discardable. The pipeline (`domain/capture_service.py`) runs in one security order:

1. **Ingest and assemble (slice 2).** `SpeechToTextPort` and `DiarizationPort` (re-exported from
   `speech-lexicon-kit`) produce a transcript and speaker segments; `domain/turns.assemble` joins
   them with the kit's `merge_diarization` (largest overlap wins, fixed tie-break). Assembly is
   byte-identical across replays, proved with the kit's `digest`.
2. **Redact before the model.** `domain/turns.redact_for_model` masks PII with `pii-kit` and
   strips now-invalid word offsets, and EVERY downstream stage sees only that redacted transcript.
   A spy-adapter test asserts no raw identifier ever reaches the generation port.
3. **Extract candidates (slice 3).** The model returns candidate commitments as JSON;
   `domain/candidates.parse_candidates` validates each structurally and DISCARDS the malformed,
   never repairs them. A survivor is still only a candidate.
4. **The deterministic register (slice 4).** `domain/action_register.py` decides every candidate
   from pure code: the citation span must land in a real turn; an action's owner must resolve to a
   diarized participant (a name that is not a participant is a hallucination and is rejected; `I` /
   `we` with nobody named is unassigned and accepted-but-flagged); a due phrase that was given must
   parse (`domain/dates.py`, no clock, explicit `as_of`). SLA, decision-review and retention dates
   come from the per-market retention pack (`config/packs/{sg,au,jp}.yaml`, data not code, unknown
   field refused). Duplicates are dropped; decisions carry a proposed/agreed/superseded state. An
   accepted commitment that is unowned or externally binding is consequential.
5. **Cited minutes (slice 5).** The model drafts minutes plus structured claims;
   `domain/minutes.draft_minutes` GROUNDS them against the register (every claim must name a real
   accepted entry and repeat its owner and date; no prose date may be absent from the register) and
   DISCARDS an ungrounded draft. Review-approved minutes publish into the `enterprise-knowledge-base` corpus (`CorpusPort`).
6. **Route and dispatch (slices 5 and 6).** Every consequential entry is routed to `human-review-console` under rule
   R8 in the same call. `TaskRouterPort` creates an external task ONLY for a review-approved entry;
   an unapproved consequential entry yields zero downstream calls.

- **Determinism**: the register (owners, dates, states, acceptance, escalation) is pure stdlib and
  replayable. With the generation adapter stubbed, the register and minutes are byte-identical.
- **Independent-oracle eval** (`eval/`): `register_accuracy`, `sla_exactness`, `extraction_f1`,
  `groundedness`, `review_safety` and `pii_safety` score the pipeline against a HAND-COMPUTED golden
  (`eval/datasets/golden_meetings.jsonl`), never against the pipeline's own verdict. Every metric is
  proved able to go red, and `sla_exactness` PER MARKET (`assert_each_can_go_red`).

## Contracts
- **Identity**: a request's actor is a server-verified `Principal`; the client-supplied actor is
  discarded. Local profile resolves a seeded dev persona from `X-Dev-Persona`.
- **Redaction before audit**: the triage service redacts PII (via `pii-kit`) before writing any
  audit record. No raw identifier reaches the WORM store.
- **Determinism**: the severity band and escalation decision are pure stdlib and replayable; an
  LLM may narrate but never produces the band.
- **Maker-checker (P-06) and routing (R8)**: a HIGH/CRITICAL result sets
  `requires_human_review=True` AND is routed through `ReviewRouterPort` to the `human-review-console` in the
  same request. The flag alone is not the escalation. The response carries `review_ref`, so a
  caller can tell a routed escalation from one that stopped here. The managed adapter refuses to
  run with no console configured rather than swallowing the escalation.
- **Profile**: resolved ONCE, at import, into a `ProfileChoice` and never a bare string. Three
  states of `MEETCAP_PROFILE`: UNSET is NO CHOICE (the SDK-free adapters
  still bind, but the seeded personas are refused, no service-to-service scheme is selected, every
  relaxation sees `unconfigured` and the exposure guard refuses every route to a non-loopback
  peer); SET AND EMPTY raises, so it can never inherit the unset behaviour; SET AND UNKNOWN,
  including a mis-capitalised value, raises. Only a deliberately named profile is honoured, and
  both raises happen before the process can serve anything.
- **Two derived postures, opposite directions**: `exposure_profile` drives every RELAXATION (CORS
  allowlist, the `X-Dev-Persona` allowed header, the HSTS baseline, the S2S scheme) and reads
  `unconfigured` when nobody chose; `bind_profile` drives the RESTRICTION (the loopback bound) and
  reads `local` when nobody chose. One string cannot do both without weakening one of them.
  Only `config.py` reads the variable.
- **End-user authentication is a property of the identity BINDING**, declared by the adapter
  (`VERIFIED` / `CLIENT_ASSERTED` / `UNIMPLEMENTED`) and read by the loopback exposure guard. The
  service-to-service secret authenticates a calling SERVICE and no end user, so it takes no part
  in that decision: setting it closes the S2S routes and relaxes nothing.
- **Audit integrity**: the trail is hash-chained AND externally anchored. `audit_anchor_path`
  points at a file on a different volume that every append writes the chain head to; without it
  a truncated tail is undetectable, because the shorter chain still verifies. Once store and
  anchor disagree the service refuses to append rather than re-anchoring, so an ordinary write
  cannot launder a divergence. Re-anchoring is a deliberate operator action.
- **Agent surface**: optional but scaffolded. The A2A card at `/.well-known/agent-card.json` is
  built from the same tool table the runtime binds, so advertised skills and implemented tools
  are the same set. Tool results are masked for personal data before they return, because a tool
  result becomes model context (P-04); an API response to the caller who supplied the text is
  not. Nothing in `agent/` needs a runtime to import; `build_function_tools()` is the only seam.
- **Ports**: a port is registered in five places (`PORT_PROTOCOLS`, `DEFAULT_BINDINGS`, the
  `Container` accessor, `config/settings.yaml`, and the canonical-call table) and the contract
  suite asserts set equality across all five, in both directions.
- **Demo**: the demo is code and it is asserted. `scripts/walkthrough.py` narrates nine steps
  and, at each one, checks that the service actually reached the state the narration claimed;
  `--auto --headless` runs the same steps unattended in CI. A step exists in exactly two places
  (`demo.STEPS` and `walkthrough.CHECKS`) and the two are held equal, so a narrated claim nobody
  verifies cannot exist. The demo needs no browser engine, no network and no cloud.
- **UI identity**: the browser never asserts who it is. Every client-supplied actor, tenant,
  role, ACL and authorization header is discarded before a request is forwarded; identity is
  resolved server-side and the resolved headers are attached afterwards. The service credential
  is read from the server environment only. Framing and CORS are allowlists that refuse a
  wildcard however it is written, and an empty allowlist denies rather than opening up.
- **Eval**: `--mode smoke` is the offline pre-merge check; `--mode gate` is the `model-quality-gate` promotion
  authority. The gate fails closed.
- **Tests**: split into `unit`, `contract` and `integration`. The offline gate runs the first
  two; every integration module is marked, and that marking is itself enforced.

## Metrics and thresholds (smoke)
- `decision_accuracy >= 0.80`
- `pii_safety >= 0.99` (pack scan + pack-independent planted-literal check)
