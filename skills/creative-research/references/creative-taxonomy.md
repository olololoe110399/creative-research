# TikTok creative taxonomy — agent methodology v1

Separate **what the creative is about** from **how it tries to attract, hold,
explain and convert attention**. These are investigator judgments over existing
Vision evidence, not calibrated causal effects or a replacement warehouse schema.

Read actual fields in `data/05_master/creative_analysis.parquet` and ordered
`data/05_master/creative_sequence.parquet`. Vision-extracted fields can be uncertain
or wrong. The source media, when available, is stronger than an isolated label.

## Seven orthogonal axes

| Axis | What to identify | Canonical evidence |
| --- | --- | --- |
| **Topic** | Subject, specific pain, audience problem and content angle; separate topic from niche and product | `topic`, `niche`, `pain_point`, `audience_segment`, `content_angle` |
| **Hook** | Opening words/visuals and observable technique; initial video beat or first slide, never unseen seconds | `hook_text`, `hook_technique`, `hook_position`, `hook_replicable_formula`, first sequence beat |
| **Narrative structure** | Ordered setup, stakes, demonstration, proof, reveal, payoff and CTA; not merely format name | `narrative_structure`, `creative_formula`, ordered `creative_sequence.role` with times |
| **Attention mechanism** | Shown curiosity gap, contrast, specificity, novelty, stakes, delayed reveal or proof cue; multiple can coexist | `attention_mechanisms`, `hook_psychological_trigger`, sequence text/visual evidence |
| **Visual format** | Face-camera, screen capture, demonstration, slides/notes, b-roll and text overlays; modality vs aesthetic | `content_type`, `content_format`, `video_format`, `dominant_visual_type`, `visual_aesthetic`, `editing_style`, sequence visuals |
| **Pacing** | Beat density, changes, pauses and allocation of on-screen time, only where visible | `pacing`, `duration_seconds`, sequence `start_second` / `end_second`, slide counts |
| **CTA** | Explicit call, action, position and spoken/visual modality; absent vs unobserved | `has_cta`, `cta_type`, `cta_text`, `cta_position`, `cta_modality`, `cta_evidence`, closing beats |

## Concrete tagging decisions

- **Hook**: retain existing source enum when supported (e.g. `question`,
  `bold_claim`, `story_tease`, `curiosity_gap`, `pattern_interrupt`,
  `direct_address`, `relatable_pain`, `transformation_preview`,
  `list_or_number`, `pov`, `how_to`, `uncertain`). Quote a short observable cue.
  A question in a caption is not necessarily the first-second hook.
- **Narrative**: express as ordered beats such as
  claim → objection → evidence, or problem → demo → proof → CTA.
  If the sequence is incomplete, say so rather than inventing a payoff.
- **Attention**: distinguish a device proposed to attract attention from
  measured watch-time/retention. No mechanism alone proves why viewers stayed.
  Multiple labels may be valid; a single exclusive label can lose meaning.
- **Visual**: a slideshow can tell a story; face-to-camera is not automatically
  a tutorial. Keep medium, editing, camera, and graphics separate.
- **Pacing**: respect `slow`, `medium`, `fast`, `uncertain` labels when present.
  Do not invent cut counts or temporal precision from a qualitative label.
- **CTA**: distinguish visible/spoken instruction, implicit suggestion and
  genuinely unknown content. Lack of a captured beat is not proof of no CTA.

For *every axis* report (1) the value or ordered labels, (2) `post_uid` and
source column/sequence position, (3) provenance
`source_observed | vision_extracted | analyst_inference | unknown`,
and (4) specific uncertainty/alternative explanation. Mark `unknown`
when insufficient; do not infer psychological impact, virality, private
operator intent, ownership or financial outcomes.

## Family-level comparisons

Start with [investigation tools](investigation-tools.md). Use full-population
group summaries; then inspect high/low performers within a family, varied members,
and similar posts outside it. Identify which of the seven axes stay invariant
and which differ. Topic overlap is not proof of identical creative mechanics,
and one repeated post is not independent evidence of a strategy.

Before recommending an original variant, state the mechanism hypothesis,
supporting and disconfirming source IDs, denominator/cohort constraints,
a rival explanation, proposed observable result and experiment design.
Never copy unlicensed music, footage, trademarks, text or creative expression.

Use [Creative Mechanic Audit](../assets/creative-mechanic-audit.md).
It is a reasoning worksheet, not a new canonical schema. The existing report
validator checks numeric source citations, **not** creative interpretation.
