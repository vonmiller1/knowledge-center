# Model card: Meeting Knowledge Capture (H6)

This is a STARTER model card. It records the model boundary as built and the controls that must be
completed before a managed deployment. The deterministic engine is the system of record; the model
is a bounded, replaceable component.

## What the model does, and does not do

- **Does**: from a redacted transcript it proposes candidate commitments (decisions and actions
  with owner references, due phrases and span citations, slice 3), and it drafts minutes prose that
  restates register entries (slice 5). Both outputs are JSON, schema-validated, and discarded on
  failure.
- **Does NOT**: produce any number or verdict. Owner resolution, SLA / decision-review / retention
  dates, acceptance or rejection, decision state, and the escalation decision are all computed by
  `domain/action_register.py` in pure stdlib. With the generation adapter stubbed the register and
  minutes are byte-identical, so a model change cannot move a figure.

## Boundary and validation

- The transcript is redacted with `pii-kit` BEFORE any model call (`domain/turns.redact_for_model`);
  a spy-adapter test asserts no raw identifier reaches the generation port.
- Extraction output is validated by `domain/candidates.parse_candidates` (malformed candidates are
  discarded, never repaired). Minutes output is grounded by `domain/minutes.draft_minutes` against
  the register; an ungrounded draft is discarded and never published.
- Every consequential result sets `requires_human_review` and is routed to Hrz7 (rule R8) in the
  same call; nothing auto-executes.

## Adapters and profiles

| Profile | Generation adapter | Behaviour |
|---|---|---|
| `local` | `adapters/local/generation.py` | Deterministic stub (scripted per fixture, heuristic fallback). SDK-free. |
| `gcp` | `adapters/gcp/generation.py` | Gemini via the Google GenAI SDK, imported lazily. |
| `onprem` | `adapters/onprem/generation.py` | Fail-fast placeholder for a client-hosted model. |

## Remaining controls (TODO, repo owner)

- **Model id, version and routing** for the `gcp` adapter (P-07): pin the exact model and record it
  here; wire the prompt templates for extraction and narration.
- **Budget and rate controls, and a kill switch** (P-10, P-11): per-tenant token budget, request
  rate limit, and a switch that forces deterministic-only operation with the model disabled.
- **Evaluation of the live model**: the offline eval scores the deterministic stub pipeline against
  the golden oracle. Add a managed-profile eval run (Hrz4 promotion gate) that scores real
  extraction F1 and minutes groundedness against the same golden meetings.
- **Prompt-injection screening** on the transcript before generation, via the Hrz1 guardrail
  adapter, failing closed to deterministic-only on screen-unavailable.

Until these are complete the system is safe to run offline (deterministic engine plus stub model)
and the managed model path is not production-cleared.
