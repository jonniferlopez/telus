"""
Confidence calculation module.

Confidence is determined by three factors:
1. How many matching calibration examples exist (evidence weight)
2. Whether the applied rule is deterministic (rule quality)
3. How many input answers are known (input completeness)

Confidence is NOT derived from the LLM.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConfidenceResult:
    level: str          # "High" | "Medium" | "Low"
    score: int          # 0–100
    explanation: str
    factors: list[str]


def calculate_confidence(
    matching_cases: list[dict],
    decision_path: list,        # list of DecisionStep
    rating: str,
    context: dict,
    additional_questions: list[dict],
) -> ConfidenceResult:
    """
    Calculate confidence based on evidence, rule quality, and input completeness.

    Parameters
    ----------
    matching_cases : list[dict]
        Calibration examples that matched this query.
    decision_path : list[DecisionStep]
        The steps taken through the decision tree.
    rating : str
        The determined rating.
    context : dict
        All input values.
    additional_questions : list[dict]
        The additional questions for this query type.

    Returns
    -------
    ConfidenceResult
    """
    factors: list[str] = []
    score = 0

    # ------------------------------------------------------------------
    # Factor 1: Calibration example support (0–40 points)
    # ------------------------------------------------------------------
    n_cases = len(matching_cases)

    # Bonus: cases with matching rating
    matching_rating_cases = [c for c in matching_cases if c.get("rating", "") == rating]
    n_rating_match = len(matching_rating_cases)

    if n_cases == 0:
        case_score = 0
        factors.append("❌ No matching calibration examples found")
    elif n_rating_match == 0:
        case_score = 10
        factors.append(f"⚠️ {n_cases} related example(s) found but none match the current rating")
    elif n_rating_match == 1:
        case_score = 20
        factors.append(f"✅ 1 calibration example matches this rating")
    elif n_rating_match == 2:
        case_score = 30
        factors.append(f"✅ 2 calibration examples match this rating")
    else:
        case_score = 40
        factors.append(f"✅ {n_rating_match} calibration examples match this rating")

    score += case_score

    # ------------------------------------------------------------------
    # Factor 2: Rule determinism (0–40 points)
    # ------------------------------------------------------------------
    # Check how many steps in the decision path had known (non-Unknown) answers
    total_steps = len(decision_path)
    unknown_steps = sum(
        1 for step in decision_path if getattr(step, "answer", "Unknown") == "Unknown"
    )

    if total_steps == 0:
        rule_score = 10
        factors.append("⚠️ No decision steps recorded")
    elif unknown_steps == 0:
        rule_score = 40
        factors.append("✅ All decision steps had definite answers — fully deterministic")
    elif unknown_steps == 1:
        rule_score = 25
        factors.append("⚠️ 1 decision step had an unknown answer — mostly deterministic")
    else:
        rule_score = max(10, 40 - unknown_steps * 10)
        factors.append(f"⚠️ {unknown_steps} decision steps had unknown answers — partial determinism")

    score += rule_score

    # ------------------------------------------------------------------
    # Factor 3: Input completeness (0–20 points)
    # ------------------------------------------------------------------
    if not additional_questions:
        input_score = 20
        factors.append("✅ No additional questions required for this query type")
    else:
        answered = sum(
            1 for q in additional_questions
            if context.get(q["key"]) is not None
        )
        completeness = answered / len(additional_questions)

        if completeness == 1.0:
            input_score = 20
            factors.append("✅ All additional questions answered")
        elif completeness >= 0.5:
            input_score = 10
            factors.append(f"⚠️ {answered}/{len(additional_questions)} additional questions answered")
        else:
            input_score = 5
            factors.append(f"❌ Only {answered}/{len(additional_questions)} additional questions answered")

    score += input_score

    # ------------------------------------------------------------------
    # Determine level
    # ------------------------------------------------------------------
    if score >= 80:
        level = "High"
    elif score >= 50:
        level = "Medium"
    else:
        level = "Low"

    explanation = _build_explanation(level, n_rating_match, unknown_steps, additional_questions, context)

    return ConfidenceResult(
        level=level,
        score=score,
        explanation=explanation,
        factors=factors,
    )


def _build_explanation(
    level: str,
    n_rating_match: int,
    unknown_steps: int,
    additional_questions: list[dict],
    context: dict,
) -> str:
    parts: list[str] = []

    if level == "High":
        parts.append("High confidence: the rating is backed by matching calibration examples and all decision logic was deterministic.")
    elif level == "Medium":
        if n_rating_match == 0:
            parts.append("Medium confidence: no direct calibration examples match this exact rating.")
        if unknown_steps > 0:
            parts.append(f"Medium confidence: {unknown_steps} decision step(s) had unknown inputs.")
        if not parts:
            parts.append("Medium confidence: partial evidence supports this rating.")
    else:
        parts.append("Low confidence: limited calibration support and/or several unknown inputs.")
        parts.append("Consider providing more details or adding a calibration example.")

    return " ".join(parts)
