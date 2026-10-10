# Creative mechanics — topic-independent candidates

**Read [creative taxonomy](creative-taxonomy.md) first.** A core-concept family
asks whether posts express the **same specific idea**. A mechanic candidate asks
whether posts share an **execution structure** across possibly different topics.
Mechanic membership never changes `creative_families.parquet`.

## Investigation

1. Run `mechanic-groups` over the selected population, preferably separately
   for slideshow and video; start with `hook_technique,content_format,cta_type`.
2. Review candidate signatures, distinct topics/accounts, the observed metric
   coverage and both high **and** low examples. A high median is association,
   not a mechanism that caused performance.
3. Run `trace-mechanic` with the returned `MECH-...` ID, the **same** axes,
   and paged members. Review source Vision data and ordered sequence beats.
4. Explain what is truly shared or variable on all seven taxonomy axes:
   topic, hook, narrative, attention, visual, pacing, CTA. Do not silently
   promote a missing/uncertain axis into an observed property.
5. Inspect mechanically similar posts outside the proposed group (for example
   the same hook with a different CTA). Propose a concrete falsification test.

Only **2–3 selected axes** form a deterministic candidate signature. A single
post can match different signatures if the selected axes change; this is not a
canonical clustering model. `mechanic_id` is a hash of the ordered axes and
normalized labels, **not** a persistent identifier across taxonomy revisions.
Narrative/attention list values are descriptive Vision output, not verified
psychological effects. Group size, distinct accounts and median are observations,
not proof of independent replication.

## Review gates

- Compare a stratified sample of matches and non-matches by actual media or
  source sequence evidence where available. Record over-grouping, under-grouping
  and uncertain cases without changing the core family IDs.
- Repeated cross-posts are not independent creative experiments.
- Do not impose a broad topic identity test on mechanic groups: the purpose
  is to expose common execution templates across topics.
- Never claim that two posts share a causal attention mechanism merely because
  they have the same Vision hook label.
- Report insufficient evidence if the group contains only a few posts or
  critical timing/sequence evidence is missing.

The command runs offline over canonical tables only, under the bridge's
source size, timeout and output constraints.
