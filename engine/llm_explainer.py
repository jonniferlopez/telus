"""
LLM explanation module.

The LLM's role is strictly limited to EXPLAINING a decision that was
already made deterministically by the rule engine. The LLM NEVER
determines or changes the rating.

Requires an OpenAI API key in the environment (OPENAI_API_KEY).
Falls back to a template-based explanation if no key is available.
"""

from __future__ import annotations

import os
import textwrap


def _template_explanation(
    query: str,
    query_type: str,
    guideline_section: str,
    rule_title: str,
    decision_path: list[dict],
    rating: str,
    confidence: str,
) -> str:
    """Generate a rule-based template explanation without using an LLM."""
    steps_text = "\n".join(
        f"  • {s['question']} → {s['answer']}" for s in decision_path
    )

    rating_context = {
        "Navigational": "This is the best possible rating — the result is the perfect, exact answer to the query.",
        "Excellent": "This is a high-quality result that fully satisfies the query intent with only minor gaps.",
        "Good": "The result is relevant and useful but is not the ideal match for the query.",
        "Acceptable": "The result is marginally relevant — it partially addresses the query but with notable limitations.",
        "Off Topic": "The result has no meaningful connection to the query and should not be shown for this search.",
        "Couldn't Evaluate": "Insufficient information was available to determine a rating.",
    }
    rating_desc = rating_context.get(rating, "")

    return textwrap.dedent(f"""\
        **Query:** {query}
        **Detected Type:** {query_type}
        **Guideline:** §{guideline_section} — {rule_title}

        **Decision path:**
        {steps_text}

        **Rating: {rating}**
        {rating_desc}

        *(Template explanation — add an OpenAI API key for AI-generated explanations.)*
    """).strip()


def _llm_explanation(
    query: str,
    query_type: str,
    guideline_section: str,
    rule_title: str,
    decision_path: list[dict],
    rating: str,
    confidence: str,
    api_key: str,
    model: str,
) -> str:
    """Call the OpenAI API to generate a natural-language explanation."""
    try:
        from openai import OpenAI  # type: ignore

        steps_text = "\n".join(
            f"  - {s['question']} → {s['answer']}" for s in decision_path
        )

        system_prompt = (
            "You are an assistant that explains map search result rating decisions made by a "
            "deterministic rule engine. Your ONLY job is to explain the reasoning behind an "
            "already-determined rating. Do NOT suggest a different rating. Do NOT invent new rules. "
            "Be concise — 2 to 4 sentences."
        )

        user_prompt = textwrap.dedent(f"""\
            A TELUS Maps Quality rater has evaluated a search result using the guidelines.
            Please explain in 2–4 sentences why the rating is correct.

            Query: {query}
            Detected Query Type: {query_type}
            Applicable Guideline Section: §{guideline_section} — {rule_title}

            Decision path taken:
            {steps_text}

            Final Rating: {rating}
            Confidence: {confidence}

            Explain why this rating was assigned based on the decision path and guideline.
            Do not suggest changing the rating.
        """)

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=300,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()

    except ImportError:
        return (
            "OpenAI library not installed. Install it with: pip install openai\n\n"
            + _template_explanation(
                query, query_type, guideline_section, rule_title, decision_path, rating, confidence
            )
        )
    except Exception as exc:
        return (
            f"LLM explanation unavailable ({exc}).\n\n"
            + _template_explanation(
                query, query_type, guideline_section, rule_title, decision_path, rating, confidence
            )
        )


def get_explanation(
    query: str,
    query_type: str,
    guideline_section: str,
    rule_title: str,
    decision_path: list[dict],
    rating: str,
    confidence: str,
    api_key: str | None = None,
) -> str:
    """
    Return a plain-language explanation of the rating decision.

    Uses the OpenAI API if an API key is available; otherwise falls
    back to a deterministic template explanation.

    Parameters
    ----------
    query : str
        The original user query.
    query_type : str
        Detected query type.
    guideline_section : str
        Applicable guideline section.
    rule_title : str
        Title of the applied rule.
    decision_path : list[dict]
        List of {"question": str, "answer": str} steps.
    rating : str
        The final rating.
    confidence : str
        The confidence level.
    api_key : str | None
        OpenAI API key. Falls back to OPENAI_API_KEY env var.

    Returns
    -------
    str
        Explanation text (markdown).
    """
    key = api_key or os.environ.get("OPENAI_API_KEY", "")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    if key:
        return _llm_explanation(
            query=query,
            query_type=query_type,
            guideline_section=guideline_section,
            rule_title=rule_title,
            decision_path=decision_path,
            rating=rating,
            confidence=confidence,
            api_key=key,
            model=model,
        )

    return _template_explanation(
        query=query,
        query_type=query_type,
        guideline_section=guideline_section,
        rule_title=rule_title,
        decision_path=decision_path,
        rating=rating,
        confidence=confidence,
    )
