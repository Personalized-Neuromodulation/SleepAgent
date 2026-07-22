EVIDENCE_VERIFICATION_PROMPT = """You are verifying rule-extracted sleep science evidence.
Use only the provided source_text. Do not add external knowledge.
Return valid JSON with verified_claims. If source_text does not report a finding, set should_include=false.

source_text:
{source_text}

candidate:
{candidate_json}
"""
