"""Typed Gemini response contracts; slideshow/video field taxonomies stay distinct."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

LanguageCode = Literal[
    "en",
    "es",
    "pt",
    "fr",
    "de",
    "it",
    "vi",
    "id",
    "ms",
    "tl",
    "th",
    "zh",
    "ja",
    "ko",
    "ar",
    "hi",
    "ru",
    "tr",
    "pl",
    "nl",
    "sv",
    "other",
    "unknown",
]

SlideRole = Literal[
    "hook",
    "problem",
    "body",
    "study_tip",
    "proof",
    "transition",
    "product_reveal",
    "product_demo",
    "cta",
    "other",
    "uncertain",
]

SlideshowVisualType = Literal[
    "real_person_photo",
    "lifestyle_photo",
    "study_desk_photo",
    "notes_or_document",
    "app_screenshot",
    "table_or_chart",
    "illustration_or_infographic",
    "meme_or_graphic",
    "mixed",
    "other",
    "uncertain",
]

AudienceSegment = Literal[
    "general_student",
    "college_student",
    "high_school_student",
    "medical_student",
    "nursing_student",
    "premed_student",
    "healthcare_student",
    "other",
    "uncertain",
]

ContentAngle = Literal[
    "study_method",
    "exam_prep",
    "memorization",
    "active_recall",
    "note_taking",
    "study_motivation",
    "productivity",
    "anatomy_medical_education",
    "nursing_education",
    "app_tool_recommendation",
    "relatable_student_life",
    "other",
    "uncertain",
]

ValueType = Literal[
    "educational_reference",
    "how_to",
    "checklist_or_list",
    "study_resource",
    "motivation",
    "relatable_story",
    "tool_demo",
    "comparison",
    "other",
    "uncertain",
]

HookTechnique = Literal[
    "pattern_interrupt",
    "question",
    "bold_claim",
    "story_tease",
    "curiosity_gap",
    "direct_address",
    "relatable_pain",
    "transformation_preview",
    "list_or_number",
    "pov",
    "how_to",
    "other",
    "uncertain",
]

ContentFormat = Literal[
    "problem_solution",
    "listicle",
    "tutorial",
    "story",
    "before_after",
    "day_in_life",
    "study_routine",
    "tool_demo",
    "educational_explainer",
    "motivation",
    "mixed",
    "other",
    "uncertain",
]

ProductFamily = Literal["none", "single_product", "multiple", "other", "uncertain"]

ProductPlacementStyle = Literal[
    "none", "immediate", "soft_reveal", "late_reveal", "integrated_throughout", "uncertain"
]

CTAType = Literal[
    "none",
    "link_in_bio",
    "download",
    "try_product",
    "follow",
    "save",
    "share",
    "comment",
    "dm",
    "other",
    "uncertain",
]


class TextRegion(BaseModel):
    text: str
    kind: Literal[
        "creative_overlay",
        "embedded_app_ui",
        "embedded_table_chart",
        "embedded_document_notes",
        "brand_logo",
        "other",
    ]
    language_code: LanguageCode = "unknown"


class SlideAnalysis(BaseModel):
    slide_index: int = Field(description="1-based slide number. First slide MUST be 1.")
    role: SlideRole
    primary_overlay_text: str | None = None
    text_regions: list[TextRegion] = Field(default_factory=list)
    visual_type: SlideshowVisualType
    visual_description: str
    product_visible: bool
    product_family_visible: ProductFamily = "none"
    confidence: float = Field(ge=0, le=1)


class SlideshowHookAnalysis(BaseModel):
    text: str | None = None
    slide_index: int | None = None
    technique: HookTechnique
    psychological_trigger: str | None = None
    replicable_formula: str | None = None


class VisualStyle(BaseModel):
    dominant_visual_type: SlideshowVisualType
    aesthetic: str
    image_realism: Literal[
        "appears_real_photo", "appears_ai_generated", "mixed", "uncertain", "not_applicable"
    ]
    pinterest_like_aesthetic: Literal["yes", "no", "uncertain"]
    pinterest_note: str
    text_overlay_style: str
    visual_consistency_across_slides: Literal["high", "medium", "low", "uncertain"]


class SlideshowProductPlacement(BaseModel):
    has_visible_product: bool
    product_family: ProductFamily
    visible_product_name: str | None = None
    first_appearance_slide: int | None = None
    placement_style: ProductPlacementStyle
    evidence: list[str] = Field(default_factory=list)


class SlideshowCTAAnalysis(BaseModel):
    has_visible_cta: bool
    cta_type: CTAType
    text: str | None = None
    slide_index: int | None = None
    evidence: list[str] = Field(default_factory=list)


class SlideshowCreativeAnalysis(BaseModel):
    primary_language_code: LanguageCode
    secondary_language_codes: list[LanguageCode] = Field(default_factory=list)
    mixed_language: bool
    audience_segment: AudienceSegment
    niche: str
    topic: str
    content_angle: ContentAngle
    value_type: ValueType
    pain_point: str | None = None
    desired_outcome: str | None = None
    hook: SlideshowHookAnalysis
    slides: list[SlideAnalysis]
    narrative_structure: list[str]
    content_format: ContentFormat
    visual_style: VisualStyle
    proof_or_credibility: list[str] = Field(default_factory=list)
    product: SlideshowProductPlacement
    cta: SlideshowCTAAnalysis
    creative_formula: str
    attention_mechanisms_used: list[str] = Field(default_factory=list)
    overall_confidence: float = Field(ge=0, le=1)
    uncertainty_notes: list[str] = Field(default_factory=list)


VideoFormat = Literal[
    "talking_head",
    "broll_text_overlay",
    "screen_recording",
    "app_demo",
    "study_routine",
    "tutorial",
    "meme_or_sketch",
    "montage",
    "mixed",
    "other",
    "uncertain",
]

BeatRole = Literal[
    "hook",
    "problem",
    "context",
    "value",
    "tutorial_step",
    "proof",
    "transition",
    "product_reveal",
    "product_demo",
    "cta",
    "ending",
    "other",
    "uncertain",
]

VideoVisualType = Literal[
    "talking_head",
    "real_person_lifestyle",
    "study_desk",
    "notes_or_document",
    "app_screen",
    "screen_recording",
    "table_or_chart",
    "illustration_or_infographic",
    "meme_or_graphic",
    "broll",
    "mixed",
    "other",
    "uncertain",
]


class VideoHookAnalysis(BaseModel):
    start_second: float = Field(ge=0)
    end_second: float = Field(ge=0)
    spoken_text: str | None = None
    overlay_text: str | None = None
    technique: HookTechnique
    psychological_trigger: str | None = None
    replicable_formula: str | None = None


class TimelineBeat(BaseModel):
    start_second: float = Field(ge=0)
    end_second: float = Field(ge=0)
    role: BeatRole
    visual_type: VideoVisualType
    visual_description: str
    spoken_summary: str | None = None
    overlay_text: str | None = None
    product_visible: bool
    product_family_visible: ProductFamily = "none"


class VideoProductPlacement(BaseModel):
    has_visible_or_spoken_product: bool
    product_family: ProductFamily
    visible_or_spoken_name: str | None = None
    first_appearance_second: float | None = None
    placement_style: ProductPlacementStyle
    evidence: list[str] = Field(default_factory=list)


class VideoCTAAnalysis(BaseModel):
    has_explicit_cta: bool
    cta_type: CTAType
    text_or_speech: str | None = None
    timestamp_second: float | None = None
    modality: Literal["spoken", "visual", "both", "none", "uncertain"]
    evidence: list[str] = Field(default_factory=list)


class AudioAnalysis(BaseModel):
    has_speech: bool
    has_background_music: bool
    narration_style: Literal[
        "direct_to_camera", "voiceover", "dialogue", "no_speech", "mixed", "uncertain"
    ]
    pacing: Literal["slow", "medium", "fast", "uncertain"]


class VideoCreativeAnalysis(BaseModel):
    primary_language_code: LanguageCode
    secondary_language_codes: list[LanguageCode] = Field(default_factory=list)
    mixed_language: bool
    audience_segment: AudienceSegment
    niche: str
    topic: str
    content_angle: ContentAngle
    value_type: ValueType
    pain_point: str | None = None
    desired_outcome: str | None = None
    video_format: VideoFormat
    hook: VideoHookAnalysis
    timeline: list[TimelineBeat]
    spoken_transcript: str | None = None
    narrative_structure: list[str]
    dominant_visual_type: VideoVisualType
    visual_aesthetic: str
    text_overlay_style: str
    editing_style: str
    camera_style: str
    face_or_person_present: bool
    audio: AudioAnalysis
    proof_or_credibility: list[str] = Field(default_factory=list)
    product: VideoProductPlacement
    cta: VideoCTAAnalysis
    creative_formula: str
    attention_mechanisms_used: list[str] = Field(default_factory=list)
    overall_confidence: float = Field(ge=0, le=1)
    uncertainty_notes: list[str] = Field(default_factory=list)
