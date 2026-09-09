# Output contracts

Pydantic models in `app/schemas.py` are the authoritative schemas. Unknown fields
are rejected. Required textual content is stripped and must be non-empty. Every
citation value must match an evidence ID supplied for that generation. Empty
citation arrays are rejected so outputs remain traceable on both routes.

| Output key | Exact top-level fields | Additional checks | Delivered format |
| --- | --- | --- | --- |
| `executive_summary` | title, summary, key_points, citations | Non-empty summary and key points | Readable UI and Markdown |
| `linkedin` | hook, body, takeaway, hashtags, citations | Non-empty body; at most 8 well-formed hashtags | Readable UI and Markdown |
| `x_post` | posts, citations | 1–20 posts, each 1–280 Unicode code points | Thread cards and Markdown |
| `email` | subject, greeting, body, call_to_action, sign_off, citations | CTA may be empty; body cannot be empty | Email layout and Markdown |
| `advisory` | title, optional severity, summary, affected, sections, recommendations, citations | Severity omitted unless it appears in cited evidence; array items are strings | Advisory layout and Markdown |
| `infographic` | title, headline, key_points, visual_elements, layout, citations | Meaningful content and layout specification | Content specification, not a generated image |
| `presentation` | slides | Each slide has title, bullets, speaker_notes, citations | Slide cards and outline Markdown, not PPTX |
| `video` | title, scenes | 4–6 sequential scenes with narration, caption, visual_keywords, citations | MP4 plus stored plan/timing metadata |

The model receives only the schema for the chosen output, plus its format-specific
rules. A LinkedIn result containing slides, scenes or key_points fails validation.
A video scene must include a narration, a caption no longer than 220 characters,
one or more media keywords and citations. Durations come from measured WAV audio,
never from the LLM.

Generation returns a complete contract or an explicit failure after one repair.
Partial results from a multi-output request appear in `outputs`, with failures in
`errors`; successful outputs are immediately available in history.

All outputs preserve IDs unchanged while the language control requests generated
text in the operator's selected language. Multilingual factual/grammatical accuracy
still depends on the local model. The server does not certify translation quality.
