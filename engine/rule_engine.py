"""
Main rule engine orchestrator.

Coordinates all modules in the correct order:
  1. Detect Query Type
  2. Find Governing Guideline Section
  3. Find Similar Calibration Examples
  4. Run Decision Tree
  5. Produce Rating
  6. Calculate Confidence
  7. (Optionally) Explain via LLM

The LLM is NEVER consulted for steps 1–6.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .query_detector import detect_query_type, get_additional_questions
from .decision_trees import run_decision_tree, RatingResult
from .case_search import search_cases, add_case
from .confidence import calculate_confidence, ConfidenceResult
from .llm_explainer import get_explanation

_RULES_DIR = Path(__file__).parent.parent / "rules"

# Map query type → rule file
_RULE_FILE_MAP: dict[str, str] = {
    "Transit Query": "5_16_1_transit.json",
    "Transit POI": "5_16_1_transit.json",
    "Chain Business": "10_6_2_chain_business.json",
    "Chain Business + General Location Modifier": "10_6_3_general_modifier.json",
    "Chain Business + Specific Location Modifier": "10_6_3_specific_modifier.json",
    "Non-Specific Address": "10_2_non_specific_address.json",
    "Unexpected Result": "5_14_unexpected_results.json",
    "Closed Business": "5_14_unexpected_results.json",
    "Point of Interest": "8_3_2_POI_addresses.json",
    "Famous Landmark": "8_3_2_POI_addresses.json",
    "Business + Full Address": "8_3_2_POI_addresses.json",
    "Address": "10_2_non_specific_address.json",
    "Street": "10_2_non_specific_address.json",
    "Locality Query": "5_16_1_transit.json",  # closest section
    "Near Me": "10_6_2_chain_business.json",  # uses distance rules
}


def _load_rule(query_type: str) -> dict:
    """Load the JSON rule file for a given query type."""
    filename = _RULE_FILE_MAP.get(query_type)
    if not filename:
        return {}
    rule_path = _RULES_DIR / filename
    if rule_path.exists():
        with rule_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# ---------------------------------------------------------------------------
# Main result data structure
# ---------------------------------------------------------------------------

@dataclass
class EngineResult:
    """Full result from the expert system pipeline."""
    # Step 1
    query_type: str
    type_reasoning: str
    # Step 2
    guideline_section: str
    rule_title: str
    applicable_rule: dict
    # Step 3
    matching_cases: list[dict]
    # Steps 4–5
    rating_result: RatingResult
    # Step 6
    confidence: ConfidenceResult
    # Step 7 (optional)
    explanation: str = ""

    @property
    def rating(self) -> str:
        return self.rating_result.rating

    @property
    def decision_path(self) -> list:
        return self.rating_result.decision_path

    def to_dict(self) -> dict:
        return {
            "query_type": self.query_type,
            "type_reasoning": self.type_reasoning,
            "guideline_section": self.guideline_section,
            "rule_title": self.rule_title,
            "rating": self.rating,
            "decision_path": [
                {"question": s.question, "answer": s.answer}
                for s in self.decision_path
            ],
            "matching_cases": self.matching_cases,
            "confidence_level": self.confidence.level,
            "confidence_score": self.confidence.score,
            "confidence_factors": self.confidence.factors,
            "exceptions": self.rating_result.exceptions,
            "explanation": self.explanation,
        }


# ---------------------------------------------------------------------------
# Engine functions
# ---------------------------------------------------------------------------

def analyze(
    query: str,
    viewport_fresh: bool = True,
    user_inside_viewport: bool = False,
    result_title: str = "",
    category: str = "",
    address: str = "",
    pin_notes: str = "",
    official_website: str = "",
    usps_findings: str = "",
    manual_notes: str = "",
    query_type_override: str | None = None,
    additional_answers: dict | None = None,
    generate_explanation: bool = False,
    api_key: str | None = None,
) -> EngineResult:
    """
    Run the full expert system pipeline.

    Parameters
    ----------
    query : str
        The map search query to evaluate.
    viewport_fresh : bool
        Whether the viewport is fresh (recently positioned).
    user_inside_viewport : bool
        Whether the user's location is inside the viewport.
    result_title : str
        Title of the map result being evaluated.
    category : str
        Category of the result (e.g. "Restaurant", "Transit Station").
    address : str
        Address shown on the map pin.
    pin_notes : str
        Notes from the map pin (e.g. hours, status).
    official_website : str
        Findings from checking the official website.
    usps_findings : str
        Findings from USPS address verification.
    manual_notes : str
        Additional notes from the rater.
    query_type_override : str | None
        If set, skip auto-detection and use this query type.
    additional_answers : dict | None
        Answers to the additional questions (keyed by question key).
    generate_explanation : bool
        Whether to call the LLM for a natural-language explanation.
    api_key : str | None
        OpenAI API key for LLM explanations.

    Returns
    -------
    EngineResult
    """
    # ------------------------------------------------------------------
    # Step 1: Detect Query Type
    # ------------------------------------------------------------------
    if query_type_override:
        query_type = query_type_override
        type_reasoning = f"Query type manually set to: {query_type_override}"
    else:
        query_type, type_reasoning = detect_query_type(
            query=query,
            category=category,
            address=address,
            result_title=result_title,
            pin_notes=pin_notes,
        )

    # ------------------------------------------------------------------
    # Step 2: Find Governing Guideline Section
    # ------------------------------------------------------------------
    applicable_rule = _load_rule(query_type)
    guideline_section = applicable_rule.get("section", "N/A")
    rule_title = applicable_rule.get("title", query_type)

    # ------------------------------------------------------------------
    # Step 3: Find Similar Calibration Examples
    # ------------------------------------------------------------------
    matching_cases = search_cases(
        query_type=query_type,
        query=query,
        section=guideline_section,
        max_results=3,
    )

    # ------------------------------------------------------------------
    # Step 4: Run Decision Tree
    # ------------------------------------------------------------------
    context = {
        # Basic inputs
        "query": query,
        "viewport_fresh": viewport_fresh,
        "user_inside_viewport": user_inside_viewport,
        "result_title": result_title,
        "category": category,
        "address": address,
        "pin_notes": pin_notes,
        "official_website": official_website,
        "usps_findings": usps_findings,
        "manual_notes": manual_notes,
    }
    if additional_answers:
        context.update(additional_answers)

    rating_result = run_decision_tree(query_type, context)

    # ------------------------------------------------------------------
    # Step 5: Rating is embedded in rating_result
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Step 6: Calculate Confidence
    # ------------------------------------------------------------------
    additional_questions = get_additional_questions(query_type)
    confidence = calculate_confidence(
        matching_cases=matching_cases,
        decision_path=rating_result.decision_path,
        rating=rating_result.rating,
        context=context,
        additional_questions=additional_questions,
    )

    # ------------------------------------------------------------------
    # Step 7: (Optional) LLM Explanation
    # ------------------------------------------------------------------
    explanation = ""
    if generate_explanation:
        explanation = get_explanation(
            query=query,
            query_type=query_type,
            guideline_section=guideline_section,
            rule_title=rule_title,
            decision_path=rating_result.to_dict()["decision_path"],
            rating=rating_result.rating,
            confidence=confidence.level,
            api_key=api_key,
        )

    return EngineResult(
        query_type=query_type,
        type_reasoning=type_reasoning,
        guideline_section=guideline_section,
        rule_title=rule_title,
        applicable_rule=applicable_rule,
        matching_cases=matching_cases,
        rating_result=rating_result,
        confidence=confidence,
        explanation=explanation,
    )


def add_calibration_example(
    query_type: str,
    section: str,
    query: str,
    result: str,
    conditions: list[str],
    rating: str,
    reasoning: str,
    keywords: list[str] | None = None,
) -> bool:
    """
    Add a new calibration example to the case library.

    Returns True if saved successfully.
    """
    case = {
        "query_type": query_type,
        "section": section,
        "query": query,
        "result": result,
        "conditions": conditions,
        "rating": rating,
        "reasoning": reasoning,
        "keywords": keywords or [],
    }
    return add_case(case)
