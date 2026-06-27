"""
TELUS Maps Rating Expert System
Streamlit application entry point.

Architecture:
  - Deterministic rule engine (no LLM for rating decisions)
  - LLM used only for natural-language explanation
  - Case library for calibration example lookup
  - Full decision tree tracing
"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="TELUS Maps Rating Expert System",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Imports from engine (after page config)
# ---------------------------------------------------------------------------
from engine.rule_engine import analyze, add_calibration_example  # noqa: E402
from engine.query_detector import QUERY_TYPES, get_additional_questions  # noqa: E402
from engine.case_search import (  # noqa: E402
    get_all_cases,
    search_by_section,
    search_by_query_type,
    search_by_keyword,
    reload_library,
)

# ---------------------------------------------------------------------------
# Rating badge styling
# ---------------------------------------------------------------------------
RATING_COLORS: dict[str, str] = {
    "Navigational": "#FFD700",
    "Excellent": "#28a745",
    "Good": "#17a2b8",
    "Acceptable": "#fd7e14",
    "Off Topic": "#dc3545",
    "Couldn't Evaluate": "#6c757d",
}

RATING_EMOJI: dict[str, str] = {
    "Navigational": "🏆",
    "Excellent": "✅",
    "Good": "👍",
    "Acceptable": "⚠️",
    "Off Topic": "❌",
    "Couldn't Evaluate": "❓",
}

CONFIDENCE_COLORS: dict[str, str] = {
    "High": "#28a745",
    "Medium": "#fd7e14",
    "Low": "#dc3545",
}


def _rating_badge(rating: str) -> str:
    color = RATING_COLORS.get(rating, "#6c757d")
    emoji = RATING_EMOJI.get(rating, "•")
    return (
        f'<span style="background-color:{color};color:{"#000" if rating in ("Navigational",) else "#fff"};'
        f'padding:6px 14px;border-radius:20px;font-weight:bold;font-size:1.1em;">'
        f'{emoji} {rating}</span>'
    )


def _confidence_badge(level: str, score: int) -> str:
    color = CONFIDENCE_COLORS.get(level, "#6c757d")
    return (
        f'<span style="background-color:{color};color:#fff;'
        f'padding:4px 10px;border-radius:12px;font-size:0.95em;font-weight:bold;">'
        f'{level} ({score}/100)</span>'
    )


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("⚙️ Configuration")

    api_key_input = st.text_input(
        "OpenAI API Key (optional)",
        type="password",
        value=os.environ.get("OPENAI_API_KEY", ""),
        help="Required for AI-generated explanations. Ratings are always determined by deterministic rules.",
        key="sidebar_api_key",
    )
    if api_key_input:
        os.environ["OPENAI_API_KEY"] = api_key_input

    st.divider()

    st.markdown("### ℹ️ About")
    st.markdown(
        """
**TELUS Maps Rating Expert System**

A deterministic rule engine for evaluating map search results per TELUS TryRating guidelines.

**Pipeline order (always followed):**
1. Detect Query Type
2. Find Governing Guideline
3. Find Calibration Examples
4. Run Decision Tree
5. Produce Rating
6. Explain Why

**The LLM only explains — it never determines the rating.**
        """
    )

    st.divider()
    st.markdown("### 📋 Quick Reference")
    st.markdown(
        """
| Rating | Meaning |
|--------|---------|
| 🏆 Navigational | Perfect exact match |
| ✅ Excellent | Highly relevant |
| 👍 Good | Relevant, not ideal |
| ⚠️ Acceptable | Marginally relevant |
| ❌ Off Topic | Not relevant |
| ❓ Couldn't Evaluate | Insufficient info |
        """
    )


# ---------------------------------------------------------------------------
# Main title
# ---------------------------------------------------------------------------
st.title("🗺️ TELUS Maps Rating Expert System")
st.caption(
    "Expert-level map result evaluation using deterministic rules, calibration examples, and structured decision trees."
)

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tabs = st.tabs([
    "🎯 Rating Assistant",
    "🔍 Search Case Library",
    "➕ Add Calibration Example",
    "📚 Guidelines Cheat Sheet",
])

# ===========================================================================
# TAB 1 — Rating Assistant
# ===========================================================================
with tabs[0]:
    st.markdown("### Enter Query & Result Details")
    st.info(
        "Fill in as many fields as possible. The more context you provide, "
        "the more accurate the rating and confidence score."
    )

    # -----------------------------------------------------------------------
    # Basic inputs
    # -----------------------------------------------------------------------
    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.markdown("#### 🔍 Query Information")
        query = st.text_input(
            "Query *",
            placeholder="e.g. Wendy's, Davenport Station, 123 Main Street",
            key="query_input",
        )
        viewport_status = st.radio(
            "Viewport Status *",
            options=["Fresh", "Stale"],
            horizontal=True,
            key="viewport_status",
            help="Fresh = viewport was recently moved/centered. Stale = viewport not updated recently.",
        )
        user_inside = st.radio(
            "User Inside Viewport *",
            options=["Yes", "No"],
            horizontal=True,
            key="user_inside",
            help="Is the user's physical location inside the current viewport?",
        )

    with col_right:
        st.markdown("#### 📍 Result Details")
        result_title = st.text_input(
            "Result Title",
            placeholder="e.g. Wendy's Downtown, King Station",
            key="result_title",
        )
        category = st.text_input(
            "Category",
            placeholder="e.g. Fast Food Restaurant, Transit Station",
            key="category",
        )
        address = st.text_input(
            "Address",
            placeholder="e.g. 123 Main Street, Springfield IL",
            key="address",
        )

    # Second row of inputs
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        pin_notes = st.text_area(
            "Pin Notes",
            placeholder="e.g. Permanently Closed, Open 24h",
            height=80,
            key="pin_notes",
        )
    with col_b:
        official_website = st.text_area(
            "Official Website Findings",
            placeholder="e.g. Website confirms closed; Different address shown",
            height=80,
            key="official_website",
        )
    with col_c:
        usps_findings = st.text_area(
            "USPS Findings",
            placeholder="e.g. Address verified; Address not found",
            height=80,
            key="usps_findings",
        )

    manual_notes = st.text_area(
        "Manual Notes",
        placeholder="Any additional context (e.g. 'Two closer Wendy's exist in viewport', 'Station is in same locality')",
        height=80,
        key="manual_notes",
    )

    # -----------------------------------------------------------------------
    # Auto-detect query type
    # -----------------------------------------------------------------------
    if query:
        from engine.query_detector import detect_query_type as _detect

        auto_type, auto_reason = _detect(
            query=query,
            category=category,
            address=address,
            result_title=result_title,
            pin_notes=pin_notes,
        )

        st.divider()
        st.markdown("### Step 1: Detected Query Type")
        col_det, col_over = st.columns([2, 1])

        with col_det:
            st.success(f"**{auto_type}**")
            st.caption(f"*Reason: {auto_reason}*")

        with col_over:
            override_type = st.selectbox(
                "Override (optional)",
                options=["(use detected)"] + QUERY_TYPES,
                key="type_override",
            )

        effective_type = auto_type if override_type == "(use detected)" else override_type

        # -------------------------------------------------------------------
        # Step 2: Guideline Section
        # -------------------------------------------------------------------
        st.divider()
        st.markdown("### Step 2: Applicable Guideline Section")

        from engine.rule_engine import _load_rule

        rule = _load_rule(effective_type)
        if rule:
            section = rule.get("section", "N/A")
            title = rule.get("title", effective_type)
            st.markdown(f"**§{section}** — {title}")

            with st.expander("View Rule Details", expanded=False):
                st.markdown(f"**Description:** {rule.get('description', '')}")
                st.markdown("**Decision Logic:**")
                for step in rule.get("decision_logic", []):
                    cond = step.get("condition", step.get("step", ""))
                    rating_val = step.get("rating", "")
                    st.markdown(f"- {cond} → **{rating_val}**")
                if rule.get("exceptions"):
                    st.markdown("**Exceptions:**")
                    for exc in rule["exceptions"]:
                        st.markdown(f"- {exc}")
        else:
            section = "N/A"
            title = effective_type
            st.warning(f"No specific rule file found for '{effective_type}'.")

        # -------------------------------------------------------------------
        # Step 3: Calibration Examples
        # -------------------------------------------------------------------
        st.divider()
        st.markdown("### Step 3: Relevant Calibration Examples")

        from engine.case_search import search_cases as _search

        cases = _search(
            query_type=effective_type,
            query=query,
            section=section,
            max_results=3,
        )

        if cases:
            for c in cases:
                c_rating = c.get("rating", "")
                c_color = RATING_COLORS.get(c_rating, "#6c757d")
                with st.expander(
                    f"[§{c.get('section','?')}] {c.get('query','?')} → {c_rating}",
                    expanded=False,
                ):
                    st.markdown(f"**Query:** {c.get('query', '')}")
                    st.markdown(f"**Result:** {c.get('result', '')}")
                    if c.get("conditions"):
                        st.markdown("**Conditions:**")
                        for cond in c["conditions"]:
                            st.markdown(f"  - {cond}")
                    st.markdown(
                        f"**Rating:** <span style='color:{c_color};font-weight:bold;'>{c_rating}</span>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(f"**Reasoning:** {c.get('reasoning', '')}")
        else:
            st.info("No close calibration examples found. The engine will rely solely on the decision tree.")

        # -------------------------------------------------------------------
        # Step 4: Additional Questions (Decision Tree Inputs)
        # -------------------------------------------------------------------
        st.divider()
        st.markdown("### Step 4: Decision Tree Inputs")
        st.caption(
            "Answer the questions below so the decision tree can produce an accurate rating. "
            "Leave as 'Unknown' if you cannot determine the answer."
        )

        additional_questions = get_additional_questions(effective_type)
        additional_answers: dict[str, bool | None] = {}

        if additional_questions:
            cols_q = st.columns(min(len(additional_questions), 2))
            for idx, q_item in enumerate(additional_questions):
                col = cols_q[idx % 2]
                with col:
                    choice = st.radio(
                        q_item["text"],
                        options=["Unknown", "Yes", "No"],
                        horizontal=True,
                        key=f"aq_{q_item['key']}",
                    )
                    if choice == "Yes":
                        additional_answers[q_item["key"]] = True
                    elif choice == "No":
                        additional_answers[q_item["key"]] = False
                    else:
                        additional_answers[q_item["key"]] = None
        else:
            st.info("No additional questions required for this query type.")

        # -------------------------------------------------------------------
        # Steps 5 & 6: Run Engine and Display Rating
        # -------------------------------------------------------------------
        st.divider()
        st.markdown("### Steps 5–6: Rating & Confidence")

        result = analyze(
            query=query,
            viewport_fresh=(viewport_status == "Fresh"),
            user_inside_viewport=(user_inside == "Yes"),
            result_title=result_title,
            category=category,
            address=address,
            pin_notes=pin_notes,
            official_website=official_website,
            usps_findings=usps_findings,
            manual_notes=manual_notes,
            query_type_override=effective_type if override_type != "(use detected)" else None,
            additional_answers=additional_answers,
            generate_explanation=False,
        )

        col_rating, col_conf = st.columns([1, 1])
        with col_rating:
            st.markdown("#### Suggested Rating")
            st.markdown(
                _rating_badge(result.rating),
                unsafe_allow_html=True,
            )

        with col_conf:
            st.markdown("#### Confidence")
            st.markdown(
                _confidence_badge(result.confidence.level, result.confidence.score),
                unsafe_allow_html=True,
            )
            st.caption(result.confidence.explanation)

        # Decision tree path
        st.markdown("#### 🌳 Decision Tree Path")
        for i, step in enumerate(result.decision_path, 1):
            answer_color = "#28a745" if step.answer == "Yes" else ("#dc3545" if step.answer == "No" else "#6c757d")
            st.markdown(
                f"**{i}.** {step.question} → "
                f'<span style="color:{answer_color};font-weight:bold;">{step.answer}</span>',
                unsafe_allow_html=True,
            )

        # Confidence factors
        if result.confidence.factors:
            with st.expander("📊 Confidence Factors", expanded=False):
                for f in result.confidence.factors:
                    st.markdown(f"- {f}")

        # Exceptions
        if result.rating_result.exceptions:
            with st.expander("⚠️ Possible Exceptions to Consider", expanded=False):
                for exc in result.rating_result.exceptions:
                    st.markdown(f"- {exc}")

        # -------------------------------------------------------------------
        # Step 7: LLM Explanation (optional, on demand)
        # -------------------------------------------------------------------
        st.divider()
        st.markdown("### Step 7: Explanation")

        col_btn, col_info = st.columns([1, 2])
        with col_btn:
            explain_btn = st.button(
                "🤖 Get AI Explanation",
                key="explain_btn",
                help="Uses OpenAI to explain the reasoning in plain language. Requires an API key.",
                disabled=not bool(os.environ.get("OPENAI_API_KEY", "")),
            )
        with col_info:
            if not os.environ.get("OPENAI_API_KEY", ""):
                st.caption("Add an OpenAI API key in the sidebar to enable AI explanations.")

        if explain_btn or st.session_state.get("explanation_shown", False):
            if explain_btn:
                with st.spinner("Generating explanation..."):
                    explanation = analyze(
                        query=query,
                        viewport_fresh=(viewport_status == "Fresh"),
                        user_inside_viewport=(user_inside == "Yes"),
                        result_title=result_title,
                        category=category,
                        address=address,
                        pin_notes=pin_notes,
                        official_website=official_website,
                        usps_findings=usps_findings,
                        manual_notes=manual_notes,
                        query_type_override=effective_type if override_type != "(use detected)" else None,
                        additional_answers=additional_answers,
                        generate_explanation=True,
                        api_key=os.environ.get("OPENAI_API_KEY"),
                    ).explanation
                st.session_state["last_explanation"] = explanation
                st.session_state["explanation_shown"] = True

            if st.session_state.get("last_explanation"):
                st.markdown(st.session_state["last_explanation"])

        # Always show template explanation as fallback
        if not st.session_state.get("explanation_shown", False):
            from engine.llm_explainer import _template_explanation

            template_exp = _template_explanation(
                query=query,
                query_type=result.query_type,
                guideline_section=result.guideline_section,
                rule_title=result.rule_title,
                decision_path=[
                    {"question": s.question, "answer": s.answer}
                    for s in result.decision_path
                ],
                rating=result.rating,
                confidence=result.confidence.level,
            )
            with st.expander("📝 Template Explanation", expanded=True):
                st.markdown(template_exp)

    else:
        st.info("👆 Enter a query above to begin the analysis.")


# ===========================================================================
# TAB 2 — Search Case Library
# ===========================================================================
with tabs[1]:
    st.markdown("### 🔍 Search Case Library")
    st.markdown(
        f"The case library contains **{len(get_all_cases())} calibration examples**. "
        "Use the filters below to find relevant examples."
    )

    search_col1, search_col2, search_col3, search_col4 = st.columns(4)

    with search_col1:
        search_section = st.text_input(
            "Filter by Section",
            placeholder="e.g. 5.16.1",
            key="search_section",
        )
    with search_col2:
        search_type = st.selectbox(
            "Filter by Query Type",
            options=["(all)"] + QUERY_TYPES,
            key="search_type",
        )
    with search_col3:
        search_keyword = st.text_input(
            "Search by Keyword",
            placeholder="e.g. station, wendy's",
            key="search_keyword",
        )
    with search_col4:
        search_rating = st.selectbox(
            "Filter by Rating",
            options=["(all)", "Navigational", "Excellent", "Good", "Acceptable", "Off Topic"],
            key="search_rating",
        )

    # Build result set
    if search_section:
        results = search_by_section(search_section)
    elif search_type != "(all)":
        results = search_by_query_type(search_type)
    elif search_keyword:
        results = search_by_keyword(search_keyword)
    else:
        results = get_all_cases()

    # Apply rating filter
    if search_rating != "(all)":
        results = [c for c in results if c.get("rating") == search_rating]

    st.markdown(f"**{len(results)} result(s) found**")

    for case in results:
        c_rating = case.get("rating", "")
        c_color = RATING_COLORS.get(c_rating, "#6c757d")
        c_emoji = RATING_EMOJI.get(c_rating, "•")

        with st.expander(
            f"#{case.get('id','?')} | [{case.get('query_type','?')}] "
            f"§{case.get('section','?')} | {case.get('query','?')} → {c_emoji} {c_rating}"
        ):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Query:** {case.get('query', '')}")
                st.markdown(f"**Result:** {case.get('result', '')}")
                st.markdown(f"**Query Type:** {case.get('query_type', '')}")
                st.markdown(f"**Section:** §{case.get('section', '')}")
            with col2:
                st.markdown(
                    f"**Rating:** <span style='color:{c_color};font-weight:bold;'>{c_rating}</span>",
                    unsafe_allow_html=True,
                )
                if case.get("conditions"):
                    st.markdown("**Conditions:**")
                    for cond in case["conditions"]:
                        st.markdown(f"  - {cond}")
                st.markdown(f"**Reasoning:** {case.get('reasoning', '')}")

    if not results:
        st.info("No matching cases found. Try different search criteria.")


# ===========================================================================
# TAB 3 — Add Calibration Example
# ===========================================================================
with tabs[2]:
    st.markdown("### ➕ Add a New Calibration Example")
    st.info(
        "New examples are permanently added to the case library and become searchable immediately. "
        "Use official TELUS calibration examples or well-reasoned edge cases."
    )

    with st.form("add_example_form"):
        add_col1, add_col2 = st.columns(2)

        with add_col1:
            add_query_type = st.selectbox("Query Type *", QUERY_TYPES, key="add_qt")
            add_section = st.text_input("Guideline Section *", placeholder="e.g. 5.16.1", key="add_sec")
            add_query = st.text_input("Query *", placeholder="e.g. Davenport Station", key="add_q")
            add_result = st.text_input(
                "Result (what the map showed) *",
                placeholder="e.g. King Station",
                key="add_r",
            )
            add_rating = st.selectbox(
                "Official Rating *",
                ["Navigational", "Excellent", "Good", "Acceptable", "Off Topic", "Couldn't Evaluate"],
                key="add_rat",
            )

        with add_col2:
            add_conditions = st.text_area(
                "Conditions (one per line) *",
                placeholder="No exact Davenport Station found\nStation is in same locality",
                height=100,
                key="add_cond",
            )
            add_reasoning = st.text_area(
                "Reasoning *",
                placeholder="Explain why this rating was assigned based on the guidelines.",
                height=100,
                key="add_reason",
            )
            add_keywords = st.text_input(
                "Keywords (comma-separated, optional)",
                placeholder="transit, station, same locality",
                key="add_kw",
            )

        submitted = st.form_submit_button("💾 Save to Case Library", type="primary")

        if submitted:
            errors = []
            if not add_query_type:
                errors.append("Query Type is required")
            if not add_section.strip():
                errors.append("Guideline Section is required")
            if not add_query.strip():
                errors.append("Query is required")
            if not add_result.strip():
                errors.append("Result is required")
            if not add_conditions.strip():
                errors.append("Conditions are required")
            if not add_reasoning.strip():
                errors.append("Reasoning is required")

            if errors:
                for err in errors:
                    st.error(f"❌ {err}")
            else:
                conditions_list = [c.strip() for c in add_conditions.split("\n") if c.strip()]
                keywords_list = [k.strip() for k in add_keywords.split(",") if k.strip()]

                success = add_calibration_example(
                    query_type=add_query_type,
                    section=add_section.strip(),
                    query=add_query.strip(),
                    result=add_result.strip(),
                    conditions=conditions_list,
                    rating=add_rating,
                    reasoning=add_reasoning.strip(),
                    keywords=keywords_list,
                )

                if success:
                    reload_library()
                    st.success(
                        f"✅ Calibration example added successfully! "
                        f"The library now contains {len(get_all_cases())} examples."
                    )
                else:
                    st.error("❌ Failed to save the example. Check file permissions.")


# ===========================================================================
# TAB 4 — Guidelines Cheat Sheet
# ===========================================================================
with tabs[3]:
    st.markdown("### 📚 TELUS Maps Quality Rating — Guidelines Cheat Sheet")

    cheat_path = Path(__file__).parent / "data" / "cheat_sheet.md"
    if cheat_path.exists():
        with cheat_path.open("r", encoding="utf-8") as f:
            cheat_content = f.read()
        st.markdown(cheat_content)
    else:
        st.warning("Cheat sheet file not found at data/cheat_sheet.md")

    st.divider()
    st.markdown("### 📖 Rule Files")
    st.markdown("The following rule files are loaded by the engine:")

    rules_dir = Path(__file__).parent / "rules"
    rule_files = sorted(rules_dir.glob("*.json")) if rules_dir.exists() else []

    for rule_file in rule_files:
        try:
            import json as _json

            with rule_file.open() as f:
                rule_data = _json.load(f)
            with st.expander(
                f"§{rule_data.get('section','?')} — {rule_data.get('title','?')} ({rule_file.name})"
            ):
                st.markdown(f"**Applies to:** {rule_data.get('applies_to', 'N/A')}")
                st.markdown(f"**Description:** {rule_data.get('description', '')}")
                st.markdown("**Decision Logic:**")
                for step in rule_data.get("decision_logic", []):
                    cond = step.get("condition", "")
                    rat = step.get("rating", "")
                    if cond and rat:
                        color = RATING_COLORS.get(rat, "#6c757d")
                        st.markdown(
                            f"- {cond} → <span style='color:{color};font-weight:bold;'>{rat}</span>",
                            unsafe_allow_html=True,
                        )
        except Exception:
            st.markdown(f"- {rule_file.name} (could not parse)")
