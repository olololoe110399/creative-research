# Archived AI Copilot concept — not part of Research Intelligence v3

The original design exposed manual **AI Investigate**, **AI Challenge**,
**AI Draft Playbook** and **AI Stress Test** buttons. That interface has been
retired in favor of **automatically materialized research**.

**Important:** The Operator Intelligence Lab no longer exposes any Copilot
buttons, even optional ones. It never loads the old \`ai_ui.js\` module,
checks \`/api/ai/status\`, or starts a Gemini request when the researcher
navigates Research Intelligence, Creative Library or Operator Playbook.

## Active workflow

1. The researcher explicitly confirms the operator/account grouping before scrape.
2. Canonical scraping, Vision, family clustering and analysis produce the evidence.
3. The Lab automatically displays **Observed / Inferred / Unknown** and
   machine-generated family-quality diagnostics.
4. Operator Playbook automatically presents evidence-linked experiment
   candidates. The researcher can put ideas into **My Experiments** and
   record first-party results; no truth-certification gate exists.

Read [RESEARCH_INTELLIGENCE_V3.md](RESEARCH_INTELLIGENCE_V3.md).

## Historical technical implementation

The repository still contains the private/local, opt-in
\`creative_research.ai_research\` engine and guarded \`/api/ai/*\` endpoints as
**legacy developer-only infrastructure**. They are not wired to the Lab UI.
They are not necessary to use the Lab, do not run in the standard
\`lab --open\` invocation, and must not be presented as a normal product
workflow.

That engine uses deterministic JSON evidence packets, strict source ID
validation, operator scoping, a bounded allowlist of models, output schemas,
a per-process call cap, and private cached proposal reports. Historic
reports stay under \`data/07_knowledge/ai_research\` and are not promoted
to observed facts or trusted knowledge.

The producer still treats captions/creative descriptions as untrusted
model input. Source ref validation checks identity, but it cannot prove
that the model's interpretation is semantically correct. Gemini is
opt-in and chargeable if the legacy API is explicitly enabled and used
by a separate developer client.

For the normal workflow, any optional semantic adjudication belongs in the
upstream calibrated family-judge stage, not a button shown to the researcher.

## Quality gate

- No \`Investigate further with AI (optional)\` or \`Explore playbook
  further with AI\` buttons in generated HTML, research cards or drawers.
- No \`ai_ui.js\` in the generated workspace or Python wheel.
- No AI status, model or report requests during ordinary Lab navigation.
- The retired module is removed from older exported workspaces on rebuild.
- Tests enforce these invariants alongside Python source-lineage checks.

A real-operator acceptance test is still required for multilingual family
quality, media playback and usability; CI success alone does not establish
research truth.
