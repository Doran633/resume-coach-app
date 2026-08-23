# Package Experience Prompt

Input:

- target_role
- mode
- packaging_level
- experience_type
- raw_input

Output JSON:

- completeness_score
- confirmed_facts
- missing_questions
- normal_version
- bold_version
- boundary_version
- recommended_version
- claims
- interview_plan
- knowledge_checklist
- resume_sections

Principle:

Give the user useful resume wording first, then explain risk and interview support. Do not block bold packaging when the user selected aggressive mode.
