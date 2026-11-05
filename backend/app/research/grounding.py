"""Conservative checks on generated historical claims, beyond source relevance.

These checks reject known unsupported additions; manual approval still matters.
"""
import re
from app.research.claims import CLAIMS
from app.research.verification import classify_risk


def validate_historical_claims(script,context):
    evidence=' '.join(row.get('supported_excerpt') or row.get('summary','') for row in context.get('sources',[]))
    text=script['full_script']
    if not evidence.strip():raise ValueError('Historical script has no supported source excerpts')
    numbers=lambda value:set(re.findall(r'\b\d+(?:[.,]\d+)?\b',value))
    if numbers(text)-numbers(evidence):raise ValueError('Historical script introduces figures/dates absent from the supported claims')
    kinds=lambda value:{key for key,pattern in CLAIMS.items() if re.search(pattern,value,re.I)}
    source_kinds=kinds(evidence);script_kinds=kinds(text)
    # "Won the award" and "was named Player of the Year" express the
    # same award outcome. Do not misclassify that paraphrase as a match result.
    if 'award' in source_kinds and 'award' in script_kinds and 'result' not in source_kinds:
        results=re.findall(CLAIMS['result'],text,re.I)
        if results and all(re.fullmatch(r'wins?|won|victory',word,re.I) for word in results):
            script_kinds.discard('result')
    # "Milestone" alone can describe the significance of an award without
    # asserting a statistical record. Records/figures still need evidence.
    if 'statistics' in script_kinds and not re.search(r'\b(record|statistics?)\b',text,re.I):script_kinds.discard('statistics')
    if script_kinds-source_kinds:raise ValueError('Historical script introduces unsupported claim categories: '+', '.join(sorted(script_kinds-source_kinds)))
    if classify_risk({'title':'','summary':text})[0]=='HIGH' and classify_risk({'title':'','summary':evidence})[0]!='HIGH':
        raise ValueError('Historical script introduces unsupported sensitive claims')
    if re.search(r'\b(because|caused|led to|resulted in|due to)\b',text,re.I) and not re.search(r'\b(because|caused|led to|resulted in|due to)\b',evidence,re.I):
        raise ValueError('Historical script introduces unsupported causal explanations')
    for quote in re.findall(r'["“]([^"”]{8,})["”]',text):
        if quote.casefold() not in evidence.casefold():raise ValueError('Historical script introduces an unsupported quotation')
    if re.search(r'\b(he|she|they)\s+(is|are|plays|works|owns|leads|holds|has)\b',text,re.I):
        raise ValueError('Historical script must not assert unverified present-day personal status')
