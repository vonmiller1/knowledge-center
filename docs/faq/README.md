# FAQ index

Answers to the questions different teams ask when evaluating, adopting, or reviewing this
repository as a common base for meeting-to-action capture agents. Each file is written for a
specific audience; skim the one that matches your role.

| FAQ | For | Answers |
|---|---|---|
| [security-faq.md](security-faq.md) | AppSec / security review | server-side identity, the redact-before-model boundary, the audit chain and its anchor, secrets, supply chain, what is deliberately not built yet |
| [portability-faq.md](portability-faq.md) | Architecture / cloud / exit planning | the no-lock-in claim, the ten ports and three profiles, which managed adapters are real, on-premises exit, data export |
| [features-faq.md](features-faq.md) | Product / delivery / operations | what the capture pipeline produces, what is deterministic vs model, what is gated on human review, and the boundary with sibling catalog systems |
| [adoption-faq.md](adoption-faq.md) | Engineering leads forking the repo | rename, taking upstream fixes, the kernel split, adding a port, retention packs, versioning |
| [compliance-faq.md](compliance-faq.md) | Compliance / privacy / model risk | regulatory posture, PII and retention, maker-checker, residency enforcement, model-risk evidence |

These FAQs deliberately do **not** re-document capabilities owned by sibling systems in the
[catalog](https://github.com/portable-genai). Where a concern belongs to another repo
(the guardrail gateway, the governed knowledge base, the agent registry, the quality gate, the
observability sink, the human-review console), the FAQ points at it and explains the boundary
rather than duplicating it. See [features-faq.md](features-faq.md) for the full "what this repo
owns vs what it integrates" map, and [`../model-card.md`](../model-card.md) for the model
boundary itself.
