from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=12000)]
Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Cite = Annotated[str, StringConstraints(pattern=r'^EVID-[1-9][0-9]*-[0-9]{4,}$')]
Citations = Annotated[list[Cite], Field(min_length=1, max_length=100)]
Paragraphs = Annotated[list[Text], Field(min_length=1, max_length=30)]

class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class LinkedInOutput(Contract):
    hook: Short
    body: Paragraphs
    takeaway: Text
    hashtags: list[Annotated[str, StringConstraints(pattern=r'^#[^\s#]+$', max_length=80)]] = Field(max_length=8)
    citations: Citations

class XPostOutput(Contract):
    posts: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=280)]] = Field(min_length=1, max_length=20)
    citations: Citations

class EmailOutput(Contract):
    subject: Short
    greeting: Short
    body: Paragraphs
    call_to_action: str = Field(max_length=1000)
    sign_off: Short
    citations: Citations

class ExecutiveSummaryOutput(Contract):
    title: Short
    summary: Text
    key_points: Paragraphs
    citations: Citations

class AdvisoryOutput(Contract):
    title: Short
    severity: Short | None = None
    summary: Text
    affected: list[Short] = Field(max_length=50)
    sections: list[Text] = Field(max_length=20)
    recommendations: list[Text] = Field(max_length=30)
    citations: Citations

class InfographicOutput(Contract):
    title: Short
    headline: Short
    key_points: Paragraphs
    visual_elements: list[Short] = Field(min_length=1, max_length=20)
    layout: Text
    citations: Citations

class Slide(Contract):
    title: Short
    bullets: Paragraphs
    speaker_notes: str = Field(max_length=3000)
    citations: Citations

class PresentationOutput(Contract):
    slides: list[Slide] = Field(min_length=1, max_length=20)

class Scene(Contract):
    scene: int = Field(ge=1, le=6)
    narration: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    caption: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=220)]
    visual_keywords: list[Short] = Field(min_length=1, max_length=8)
    citations: Citations

class VideoOutput(Contract):
    title: Short
    scenes: list[Scene] = Field(min_length=4, max_length=6)

    @model_validator(mode='after')
    def scene_order(self):
        if [s.scene for s in self.scenes] != list(range(1, len(self.scenes) + 1)):
            raise ValueError('Scene numbers must be consecutive starting at 1')
        return self

OUTPUT_MODELS = {'linkedin': LinkedInOutput, 'x_post': XPostOutput, 'email': EmailOutput,
                 'executive_summary': ExecutiveSummaryOutput, 'advisory': AdvisoryOutput,
                 'infographic': InfographicOutput, 'presentation': PresentationOutput, 'video': VideoOutput}
OutputType = Literal['linkedin', 'x_post', 'email', 'executive_summary', 'advisory', 'infographic', 'presentation', 'video']

class RouteRequest(Contract):
    source_ids: list[Annotated[int, Field(gt=0)]] = Field(min_length=1, max_length=50)
    persistent_knowledge: bool = False
    retrieval_requested: bool = False

    @model_validator(mode='after')
    def unique_sources(self):
        self.source_ids = list(dict.fromkeys(self.source_ids))
        return self

class TransformRequest(RouteRequest):
    output_types: list[OutputType] = Field(min_length=1, max_length=8)
    audience: Short = 'general'
    tone: Short = 'professional'
    language: Short = 'English'
    content_scope: Literal['public', 'internal'] = 'public'
    image_mode: Literal['auto', 'local'] = 'auto'
    detail_level: Literal['short', 'medium', 'detailed'] = 'medium'
    objective: Short = 'inform'
    style: Short = 'factual'
    retrieval_query: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = None
    user_instruction: str = Field('', max_length=2000)

    @model_validator(mode='after')
    def unique_outputs(self):
        self.output_types = list(dict.fromkeys(self.output_types))
        return self

class ManualEditRequest(Contract):
    result: dict

class RevisionRequest(Contract):
    instruction: str = Field(min_length=1, max_length=2000)
    language: Short | None = None

class DeleteSelection(Contract):
    ids: list[Annotated[int, Field(gt=0)]] = Field(min_length=1, max_length=100)
