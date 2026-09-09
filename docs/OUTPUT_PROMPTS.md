# Output prompts

See [OUTPUT_FORMATS.md](OUTPUT_FORMATS.md) for the final contracts and
`app/prompts.py` for the complete prompt definitions. Each format has separate
rules; Pydantic emits the schema sent to Ollama. The backend issues and validates
evidence IDs. Prompt instructions are not a substitute for validation or human
review of factual support.
