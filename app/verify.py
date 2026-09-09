import re
from pydantic import ValidationError
from app.schemas import OUTPUT_MODELS

def collect_citations(value):
    found = []
    def walk(v):
        if isinstance(v, dict):
            for key, item in v.items():
                if key == 'citations' and isinstance(item, list):
                    found.extend(c for c in item if isinstance(c, str))
                else:
                    walk(item)
        elif isinstance(v, list):
            for item in v:
                walk(item)
    walk(value)
    return list(dict.fromkeys(found))

def verify(output_type, result, evidence):
    errors = []
    try:
        OUTPUT_MODELS[output_type].model_validate(result)
    except ValidationError as exc:
        errors.extend('.'.join(map(str, e['loc'])) + ': ' + e['msg'] for e in exc.errors(include_input=False))
    valid = {e['evidence_id']: e for e in evidence}
    seen = collect_citations(result)
    invalid = sorted(set(seen) - valid.keys())
    if invalid:
        errors.append('Invented/invalid citation IDs; use only the provided evidence IDs')
    if not evidence:
        errors.append('No source evidence available')
    if output_type == 'advisory' and isinstance(result, dict) and result.get('severity'):
        cited = '\n'.join(valid[c]['content'] for c in seen if c in valid)
        if not re.search(r'(?<!\w)' + re.escape(str(result['severity'])) + r'(?!\w)', cited, re.IGNORECASE):
            errors.append('Severity is not explicitly present in cited evidence; use null')
    return {'passed': not errors, 'errors': errors, 'invalid_citations': invalid,
            'citation_count': len(seen), 'evidence_count': len(evidence),
            'verification_scope': 'schema_and_evidence_ids', 'factual_accuracy_verified': False,
            'warnings': ['Citation IDs and structure checked. Human review is required for factual support.']}
