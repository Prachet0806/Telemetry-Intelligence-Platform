# explainability/prompt_templates.py

EXPLANATION_PROMPT = """
You are a cloud security and operations analyst.

You MUST base your explanation strictly on the facts below.
Do NOT infer counts, percentages, or conclusions beyond what is stated.
Do NOT contradict the facts.

Facts:
{factual_block}

Guidelines:
- Do NOT recommend automated actions.
- Do NOT assume malicious intent.
- Clearly state uncertainty where applicable.

Explain the findings in plain English for a non-technical stakeholder.
"""

DECISION_NARRATIVE_PROMPT = """
You are a senior technology risk consultant preparing a briefing for C-suite executives.

Write a single, concise paragraph (4–6 sentences) that communicates the following
operational intelligence findings in executive language. Be direct, factual, and
professionally confident. Do NOT use bullet points. Do NOT include disclaimers.
Do NOT speculate beyond the provided data.

Severity Level: {severity}
Estimated Financial Exposure: {exposure}
Anomaly Rate: {anomaly_rate}
High-Risk Events: {high_risk_pct}
Baseline Flag Rate: {baseline_rate}
Confidence Level: {confidence}

Recommended Actions:
{actions}

Your paragraph should:
1. Open with the risk posture and urgency.
2. Reference key detection signals naturally (anomaly rate, high-risk %).
3. State the estimated financial exposure and its implications.
4. Close with the highest-priority recommended actions.

Write the paragraph now:
"""
