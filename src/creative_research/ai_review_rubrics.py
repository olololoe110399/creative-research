"""Target-specific research rubrics for the Operator Intelligence Lab.

Keep identity decisions, strategy interpretation, and playbook guidance separate.
The distinction is enforced in prompts AND validated after model inference.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


RUBRIC_VERSION = "review-target-rubrics-v2"
FAMILY_MEMBER_LIMIT = 12
REVIEW_QUESTIONS = {
    "family": "Are the candidate posts executions of the SAME underlying creative concept?",
    "hypothesis": "Is this particular stated strategy hypothesis supported, contradicted or unproven?",
    "playbook_sources": "Can the constituent hypotheses support this exact bundle without bypassing human trust?",
    "operator": "Which evidence-linked actions are worth TESTING, with which measurable safeguards?",
}

FAMILY_IDENTITY_RUBRIC = """REVIEW TARGET = CREATIVE FAMILY MEMBERSHIP ONLY.
Question: Do the listed candidate posts share the same underlying creative
concept? Compare the actual core promise, hook mechanism, audience segmentation,
content/story sequence, CTA/product role, translation/adaptation, and each
member's match-to-origin rationale. Same niche, same product, shared account or
similar broad topic ALONE do not establish identity; identify potential false
merges and specific divergent posts. Similarity/match scores are supporting
algorithmic signals, NOT conclusive human/visual proof.

Do NOT evaluate whether a centralized operator used a testing/scaling system,
who caused whom to publish, or whether reuse improved views or performance.
Those are DIFFERENT strategy questions. They are never grounds to HOLD, APPROVE
or REJECT this family. No strategy/experiment proposals in a family answer.

You have Vision-extracted TEXT and sequence metadata, not the raw images/video.
Do not claim that you inspected the visual media, regardless of media URL.
Set family_assessment.visual_media_inspected to false and report human media
inspection as a remaining verification step.

For APPROVE suggestion: all source member posts must be represented and
checked, with concrete structural overlap in at least two distinct posts;
there must be no unresolved material outlier. Human review still verifies
the media before saving a decision. For HOLD: missing/mixed identity evidence,
ambiguous translation or unresolved outlier. For REJECT: identify specific
posts that differ in the defining core concept, formula or sequence. The
review_rationale and family_assessment.identity_rationale must discuss ONLY
the identity evidence, never reach for performance or causal intent.

Provide family_assessment: core_concept, checked_member_post_refs,
identity_support_post_refs, outlier_post_refs, identity_rationale, and
visual_media_inspected=false. They must be REAL family-member post IDs.
Only member ID matches and explicit evidence can support the decision.
If some member metadata is missing or truncated, HOLD rather than APPROVE.
"""

HYPOTHESIS_RUBRIC = """REVIEW TARGET = EXACT HYPOTHESIS CLAIM.
Distinguish deterministic observations from hypotheses about operator intent.
Performance can challenge performance claims; chronology can support observed
family flows, but not prove internal test→scale directives or causation.
Match your approve/hold/reject suggestion to the precise claim scope,
counterexamples and alternatives. Do not treat similar creative identity as
automatic evidence of performance-based selection.
Do not fabricate internal communication logs or claim they are universally
required if the reviewable claim only describes observed behavior.
Do NOT populate family_assessment (that is only for family identity reviews).
Experiments, if useful, must be explicitly provisional and measurable.
"""

BUNDLE_RUBRIC = """REVIEW TARGET = TRUSTED KNOWLEDGE BUNDLE.
Check the exact constituent hypotheses, their approved/held/rejected status,
lineage and opposing evidence. Do not imply bundle APPROVE without all
components already reviewed/approved by humans. A bundle can remain HOLD
despite a plausible research narrative. Never use rejected/held knowledge
as a recommendation. Do NOT populate family_assessment.
"""

PLAYBOOK_RUBRIC = """REVIEW TARGET = PROPOSED USER-SIDE EXPERIMENTS.
Do not claim these are the operator's documented internal actions.
Only cite evidence-backed steps, preserve rejected/held boundaries, and
specify how to measure and when to stop or recheck. Proposed numeric
thresholds are NOT inferred operator rules, so label them proposed.
Do NOT populate family_assessment.
"""

METRIC_RUBRIC = """METRIC AVAILABILITY:
This Lab contains historical views, views_percentile_account,
views_percentile_operator and post timestamps. It does NOT establish hourly
view-velocity, snapshots at 24/48/72 hours, audience demographics, conversion,
revenue or new-campaign outcomes. If you propose tracking those metrics
you MUST set measurement_plan="new_tracking_required" and describe the new
collection needed. If a proposed cutoff is numeric (e.g. >0.50 percentile,
below 0.30, after 72 hours), distinguish the hypothesis from a proven rule:
set threshold_origin="proposed_experiment" and never represent it as observed.
No causal or numerical win-rate guarantees. If no new numeric cutoff is
proposed, threshold_origin="none".
"""

SOURCE_RUBRICS = {
    "family": FAMILY_IDENTITY_RUBRIC,
    "hypothesis": HYPOTHESIS_RUBRIC,
    "playbook_sources": BUNDLE_RUBRIC,
    "operator": PLAYBOOK_RUBRIC,
}


class FamilyIdentityAssessment(BaseModel):
    core_concept: str = Field(min_length=10, max_length=650)
    checked_member_post_refs: list[str] = Field(min_length=1, max_length=FAMILY_MEMBER_LIMIT)
    identity_support_post_refs: list[str] = Field(min_length=1, max_length=FAMILY_MEMBER_LIMIT)
    outlier_post_refs: list[str] = Field(default_factory=list, max_length=FAMILY_MEMBER_LIMIT)
    identity_rationale: str = Field(min_length=20, max_length=1250)
    visual_media_inspected: Literal[False] = False
