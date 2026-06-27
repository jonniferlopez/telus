"""
Deterministic decision trees for each TELUS Maps query type.

Each function receives a ``context`` dict containing all user-supplied
inputs (basic fields + additional question answers) and returns a
``RatingResult`` with the rating, decision path, guideline section,
exceptions, and confidence factors.

The LLM is NOT consulted here. All logic is deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DecisionStep:
    """One step in the decision path."""
    question: str
    answer: str  # "Yes" | "No" | "Unknown" | descriptive text


@dataclass
class RatingResult:
    """Full result from a decision tree run."""
    rating: str                          # Navigational / Excellent / Good / Acceptable / Off Topic / Couldn't Evaluate
    guideline_section: str               # e.g. "5.16.1"
    rule_title: str
    decision_path: list[DecisionStep]
    exceptions: list[str]
    confidence_factors: list[str]        # factors that affect confidence

    def to_dict(self) -> dict:
        return {
            "rating": self.rating,
            "guideline_section": self.guideline_section,
            "rule_title": self.rule_title,
            "decision_path": [{"question": s.question, "answer": s.answer} for s in self.decision_path],
            "exceptions": self.exceptions,
            "confidence_factors": self.confidence_factors,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _yn(context: dict, key: str) -> bool | None:
    """Read a yes/no answer from context. Returns True/False/None."""
    val = context.get(key)
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("yes", "true", "y")
    return None


def _step(path: list[DecisionStep], question: str, answer: str | bool | None) -> None:
    """Append a decision step, converting bool answers to Yes/No."""
    if isinstance(answer, bool):
        answer_str = "Yes" if answer else "No"
    elif answer is None:
        answer_str = "Unknown"
    else:
        answer_str = str(answer)
    path.append(DecisionStep(question=question, answer=answer_str))


# ---------------------------------------------------------------------------
# Individual decision trees
# ---------------------------------------------------------------------------

def _transit_tree(context: dict) -> RatingResult:
    path: list[DecisionStep] = []
    exceptions = [
        "Airport queries require the exact airport for Navigational",
        "Route-specific queries require matching route for Navigational",
        "Transit hubs serving the same area may rate Excellent even without exact name match",
    ]

    exact = _yn(context, "exact_station_match")
    _step(path, "Is the result the exact station/stop queried?", exact)

    if exact:
        return RatingResult(
            rating="Navigational",
            guideline_section="5.16.1",
            rule_title="Transit Station Queries",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Exact station match → deterministic Navigational rating"],
        )

    same = _yn(context, "same_locality")
    _step(path, "Is the result in the same locality as the queried station?", same)

    if same:
        return RatingResult(
            rating="Excellent",
            guideline_section="5.16.1",
            rule_title="Transit Station Queries",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Same-locality station — deterministic Excellent rating"],
        )

    neighboring = _yn(context, "neighboring_locality")
    _step(path, "Is the result in a neighboring/adjacent locality?", neighboring)

    if neighboring:
        return RatingResult(
            rating="Good",
            guideline_section="5.16.1",
            rule_title="Transit Station Queries",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Neighboring-locality station — deterministic Good rating"],
        )

    # Farther away but still transit
    _step(path, "Is it the same transit system, just farther away?", "Assumed yes — still a transit result")
    return RatingResult(
        rating="Acceptable",
        guideline_section="5.16.1",
        rule_title="Transit Station Queries",
        decision_path=path,
        exceptions=exceptions,
        confidence_factors=["No locality match found — defaulting to Acceptable for distant transit"],
    )


def _chain_business_tree(context: dict) -> RatingResult:
    path: list[DecisionStep] = []
    exceptions = [
        "A chain with only one location in the area is always Navigational regardless of distance",
        "Temporarily closed locations should be rated Acceptable or lower",
        "User-inside-viewport shifts distance reference point to the user",
    ]

    viewport_fresh: bool = context.get("viewport_fresh", True)
    user_inside: bool = context.get("user_inside_viewport", False)

    correct_chain = _yn(context, "correct_chain")
    _step(path, "Is the result the same chain/brand as queried?", correct_chain)

    if correct_chain is False:
        return RatingResult(
            rating="Off Topic",
            guideline_section="10.6.2",
            rule_title="Chain Business (No Location Modifier)",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Result is a different brand — deterministic Off Topic"],
        )

    _step(path, "Is the viewport fresh?", viewport_fresh)
    _step(path, "Is the user inside the viewport?", user_inside)

    # User-relative or viewport-relative distance logic
    is_closest = _yn(context, "is_closest")
    closer_exist = _yn(context, "closer_exist")
    many_closer_exist = _yn(context, "many_closer_exist")

    if viewport_fresh:
        _step(path, "Is this the closest location of this chain in the viewport?", is_closest)

        if is_closest:
            return RatingResult(
                rating="Navigational",
                guideline_section="10.6.2",
                rule_title="Chain Business (No Location Modifier)",
                decision_path=path,
                exceptions=exceptions,
                confidence_factors=[
                    "Fresh viewport",
                    "Correct chain",
                    "Closest location — deterministic Navigational",
                ],
            )

        _step(path, "Are there 3 or more closer locations not shown first?", many_closer_exist)
        if many_closer_exist:
            return RatingResult(
                rating="Acceptable",
                guideline_section="10.6.2",
                rule_title="Chain Business (No Location Modifier)",
                decision_path=path,
                exceptions=exceptions,
                confidence_factors=[
                    "Fresh viewport",
                    "3+ closer locations exist — heavy distance demotion to Acceptable",
                ],
            )

        _step(path, "Are there 1–2 closer locations not shown first?", closer_exist)
        if closer_exist:
            return RatingResult(
                rating="Good",
                guideline_section="10.6.2",
                rule_title="Chain Business (No Location Modifier)",
                decision_path=path,
                exceptions=exceptions,
                confidence_factors=[
                    "Fresh viewport",
                    "1–2 closer locations exist — distance demotion to Good",
                ],
            )

        # closest unknown
        return RatingResult(
            rating="Excellent",
            guideline_section="10.6.2",
            rule_title="Chain Business (No Location Modifier)",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=[
                "Fresh viewport",
                "Correct chain, distance unknown — defaulting to Excellent",
            ],
        )

    else:  # Stale viewport
        return RatingResult(
            rating="Excellent",
            guideline_section="10.6.2",
            rule_title="Chain Business (No Location Modifier)",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=[
                "Stale viewport — distance criteria relaxed",
                "Correct chain match → Excellent",
            ],
        )


def _chain_general_modifier_tree(context: dict) -> RatingResult:
    path: list[DecisionStep] = []
    exceptions = [
        "If no chain location exists in the specified area, the nearest one may rate Excellent",
        "Ambiguous area names (e.g., 'downtown') require judgment",
    ]

    correct_chain = _yn(context, "correct_chain")
    _step(path, "Is the result the same chain/brand as queried?", correct_chain)

    if correct_chain is False:
        return RatingResult(
            rating="Off Topic",
            guideline_section="10.6.3",
            rule_title="Chain Business + General Location Modifier",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Wrong chain brand — deterministic Off Topic"],
        )

    in_area = _yn(context, "in_specified_area")
    _step(path, "Is the result in the specified general area/city?", in_area)

    if in_area:
        return RatingResult(
            rating="Excellent",
            guideline_section="10.6.3",
            rule_title="Chain Business + General Location Modifier",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Correct chain in correct area — deterministic Excellent"],
        )

    adjacent = _yn(context, "adjacent_area")
    _step(path, "Is the result in an adjacent/neighboring area?", adjacent)

    if adjacent:
        return RatingResult(
            rating="Good",
            guideline_section="10.6.3",
            rule_title="Chain Business + General Location Modifier",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Correct chain in adjacent area — deterministic Good"],
        )

    return RatingResult(
        rating="Acceptable",
        guideline_section="10.6.3",
        rule_title="Chain Business + General Location Modifier",
        decision_path=path,
        exceptions=exceptions,
        confidence_factors=["Correct chain but wrong area — Acceptable (same city, different area)"],
    )


def _chain_specific_modifier_tree(context: dict) -> RatingResult:
    path: list[DecisionStep] = []
    exceptions = [
        "Intersections qualify as exact if result is on one of the specified streets at that crossing",
        "If no chain exists near the address, closest may still rate Excellent",
    ]

    correct_chain = _yn(context, "correct_chain")
    _step(path, "Is the result the same chain/brand as queried?", correct_chain)

    if correct_chain is False:
        return RatingResult(
            rating="Off Topic",
            guideline_section="10.6.3",
            rule_title="Chain Business + Specific Location Modifier",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Wrong chain brand — deterministic Off Topic"],
        )

    exact_addr = _yn(context, "exact_address")
    _step(path, "Does the result match the exact specified address/intersection?", exact_addr)

    if exact_addr:
        return RatingResult(
            rating="Navigational",
            guideline_section="10.6.3",
            rule_title="Chain Business + Specific Location Modifier",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Correct chain at exact specified address — deterministic Navigational"],
        )

    closest = _yn(context, "closest_to_address")
    _step(path, "Is this the closest location of the chain to the specified address?", closest)

    if closest:
        return RatingResult(
            rating="Excellent",
            guideline_section="10.6.3",
            rule_title="Chain Business + Specific Location Modifier",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Correct chain, closest to specified address — deterministic Excellent"],
        )

    same_nb = _yn(context, "same_neighborhood")
    _step(path, "Is the result in the same neighborhood as the specified address?", same_nb)

    if same_nb:
        return RatingResult(
            rating="Good",
            guideline_section="10.6.3",
            rule_title="Chain Business + Specific Location Modifier",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Correct chain, same neighborhood — deterministic Good"],
        )

    return RatingResult(
        rating="Acceptable",
        guideline_section="10.6.3",
        rule_title="Chain Business + Specific Location Modifier",
        decision_path=path,
        exceptions=exceptions,
        confidence_factors=["Correct chain but wrong neighborhood relative to specified address — Acceptable"],
    )


def _business_full_address_tree(context: dict) -> RatingResult:
    path: list[DecisionStep] = []
    exceptions = [
        "USPS or official website data can override address matching",
        "If the business has moved, show the new address; rate new location",
    ]

    correct_biz = _yn(context, "correct_business")
    _step(path, "Is the result the same business as queried (by name)?", correct_biz)

    if correct_biz is False:
        return RatingResult(
            rating="Off Topic",
            guideline_section="8.3.2",
            rule_title="Business + Full Address",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Wrong business name — deterministic Off Topic"],
        )

    exact_addr = _yn(context, "exact_address")
    _step(path, "Does the address match exactly (same number and street)?", exact_addr)

    if exact_addr:
        return RatingResult(
            rating="Navigational",
            guideline_section="8.3.2",
            rule_title="Business + Full Address",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Correct business at exact address — deterministic Navigational"],
        )

    same_block = _yn(context, "same_block")
    _step(path, "Is it on the same block (within ~50 house numbers)?", same_block)

    if same_block:
        return RatingResult(
            rating="Excellent",
            guideline_section="8.3.2",
            rule_title="Business + Full Address",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Correct business, same block — Excellent"],
        )

    same_street = _yn(context, "same_street")
    _step(path, "Is it on the same street (different block range)?", same_street)

    if same_street:
        return RatingResult(
            rating="Good",
            guideline_section="8.3.2",
            rule_title="Business + Full Address",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Correct business, same street different block — Good"],
        )

    return RatingResult(
        rating="Acceptable",
        guideline_section="8.3.2",
        rule_title="Business + Full Address",
        decision_path=path,
        exceptions=exceptions,
        confidence_factors=["Correct business but different street — Acceptable at best"],
    )


def _non_specific_address_tree(context: dict) -> RatingResult:
    path: list[DecisionStep] = []
    exceptions = [
        "Very common street names (Main Street) require the most prominent result",
        "If context clues suggest a specific business, treat as Business query",
    ]

    valid = _yn(context, "valid_interpretation")
    _step(path, "Is the result a valid interpretation of the non-specific address?", valid)

    if valid is False:
        return RatingResult(
            rating="Off Topic",
            guideline_section="10.2",
            rule_title="Non-Specific Address",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Result is not a valid interpretation of the address — Off Topic"],
        )

    prominent = _yn(context, "most_prominent")
    _step(path, "Is it the most prominent/central interpretation (best disambiguation)?", prominent)

    if prominent:
        return RatingResult(
            rating="Excellent",
            guideline_section="10.2",
            rule_title="Non-Specific Address",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Valid and most prominent interpretation — Excellent"],
        )

    return RatingResult(
        rating="Good",
        guideline_section="10.2",
        rule_title="Non-Specific Address",
        decision_path=path,
        exceptions=exceptions,
        confidence_factors=["Valid but not most prominent interpretation — Good"],
    )


def _poi_tree(context: dict) -> RatingResult:
    path: list[DecisionStep] = []
    exceptions = [
        "Well-known POIs have strict Navigational criteria — only the exact POI qualifies",
        "Multiple entrances or buildings of the same POI all rate Navigational",
        "Hospital ER entrance and main entrance both rate Navigational for hospital queries",
    ]

    exact = _yn(context, "exact_poi")
    _step(path, "Is the result the exact POI queried (same name and location)?", exact)

    if exact:
        return RatingResult(
            rating="Navigational",
            guideline_section="8.3.2",
            rule_title="POI Address Queries",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Exact POI match — deterministic Navigational"],
        )

    alias = _yn(context, "alias_same_place")
    _step(path, "Is it an alias, colloquial name, or different entrance for the same physical POI?", alias)

    if alias:
        return RatingResult(
            rating="Navigational",
            guideline_section="8.3.2",
            rule_title="POI Address Queries",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Same physical POI with different name — deterministic Navigational"],
        )

    same_cat_area = _yn(context, "same_category_same_area")
    _step(path, "Is it the same category of POI in the same area/neighborhood?", same_cat_area)

    if same_cat_area:
        return RatingResult(
            rating="Excellent",
            guideline_section="8.3.2",
            rule_title="POI Address Queries",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Same POI category, same area — Excellent"],
        )

    same_cat_city = _yn(context, "same_category_same_city")
    _step(path, "Is it the same category in the same city but different neighborhood?", same_cat_city)

    if same_cat_city:
        return RatingResult(
            rating="Good",
            guideline_section="8.3.2",
            rule_title="POI Address Queries",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Same POI category, same city — Good"],
        )

    return RatingResult(
        rating="Acceptable",
        guideline_section="8.3.2",
        rule_title="POI Address Queries",
        decision_path=path,
        exceptions=exceptions,
        confidence_factors=["Related POI category but different area — Acceptable at best"],
    )


def _famous_landmark_tree(context: dict) -> RatingResult:
    path: list[DecisionStep] = []
    exceptions = [
        "Only the exact landmark qualifies for Navigational — no nearby businesses",
        "Official welcome centers or visitor centers at the landmark may rate Navigational",
    ]

    exact = _yn(context, "exact_landmark")
    _step(path, "Is the result the exact famous landmark queried?", exact)

    if exact:
        return RatingResult(
            rating="Navigational",
            guideline_section="8.3.2",
            rule_title="Famous Landmark",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Exact landmark match — deterministic Navigational"],
        )

    official = _yn(context, "official_entity")
    _step(path, "Is it the official entity/page for this landmark?", official)

    if official:
        return RatingResult(
            rating="Navigational",
            guideline_section="8.3.2",
            rule_title="Famous Landmark",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Official landmark entity — deterministic Navigational"],
        )

    return RatingResult(
        rating="Good",
        guideline_section="8.3.2",
        rule_title="Famous Landmark",
        decision_path=path,
        exceptions=exceptions,
        confidence_factors=["Not the exact landmark or official entity — Good at best"],
    )


def _near_me_tree(context: dict) -> RatingResult:
    path: list[DecisionStep] = []
    exceptions = [
        "If user is not inside the viewport, Near Me is treated as viewport-center-relative",
        "Very large viewports reduce the reliability of 'nearest' calculations",
    ]

    user_inside: bool = context.get("user_inside_viewport", False)
    _step(path, "Is the user inside the viewport?", user_inside)

    nearest = _yn(context, "nearest_result")
    _step(path, "Is this the nearest matching entity to the user's location?", nearest)

    if nearest:
        return RatingResult(
            rating="Navigational",
            guideline_section="10.6.2",
            rule_title="Near Me Query",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=[
                "Nearest result to user — deterministic Navigational" if user_inside
                else "Nearest in viewport (user outside) — Navigational with lower confidence",
            ],
        )

    within_reasonable = _yn(context, "within_reasonable")
    _step(path, "Is the result within a reasonable distance?", within_reasonable)

    if within_reasonable:
        return RatingResult(
            rating="Good",
            guideline_section="10.6.2",
            rule_title="Near Me Query",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Nearby but not nearest — Good"],
        )

    return RatingResult(
        rating="Acceptable",
        guideline_section="10.6.2",
        rule_title="Near Me Query",
        decision_path=path,
        exceptions=exceptions,
        confidence_factors=["Relevant but not nearby — Acceptable"],
    )


def _locality_tree(context: dict) -> RatingResult:
    path: list[DecisionStep] = []
    exceptions = [
        "Ambiguous locality names use most prominent interpretation",
        "Sub-localities (neighborhoods) within queried city may rate Excellent",
    ]

    exact = _yn(context, "exact_locality")
    _step(path, "Is the result the exact locality (city/town/neighborhood) queried?", exact)

    if exact:
        return RatingResult(
            rating="Navigational",
            guideline_section="5.16.1",
            rule_title="Locality Query",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Exact locality match — deterministic Navigational"],
        )

    sub = _yn(context, "sub_locality")
    _step(path, "Is it a sub-locality or neighborhood within the queried area?", sub)

    if sub:
        return RatingResult(
            rating="Excellent",
            guideline_section="5.16.1",
            rule_title="Locality Query",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Sub-locality of queried area — Excellent"],
        )

    adjacent = _yn(context, "adjacent_locality")
    _step(path, "Is it an adjacent or neighboring locality?", adjacent)

    if adjacent:
        return RatingResult(
            rating="Good",
            guideline_section="5.16.1",
            rule_title="Locality Query",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Adjacent locality — Good"],
        )

    return RatingResult(
        rating="Acceptable",
        guideline_section="5.16.1",
        rule_title="Locality Query",
        decision_path=path,
        exceptions=exceptions,
        confidence_factors=["Different but somewhat related locality — Acceptable at best"],
    )


def _address_tree(context: dict) -> RatingResult:
    path: list[DecisionStep] = []
    exceptions = [
        "USPS data is authoritative for address validation",
        "Address typos in queries: rate as if the intended address was queried",
    ]

    exact = _yn(context, "exact_address")
    _step(path, "Does the result match the exact address queried?", exact)

    if exact:
        return RatingResult(
            rating="Navigational",
            guideline_section="10.2",
            rule_title="Address Query",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Exact address match — deterministic Navigational"],
        )

    same_block = _yn(context, "same_block")
    _step(path, "Is it on the same block (within ~50 house numbers)?", same_block)

    if same_block:
        return RatingResult(
            rating="Excellent",
            guideline_section="10.2",
            rule_title="Address Query",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Same block — Excellent"],
        )

    same_street = _yn(context, "same_street")
    _step(path, "Is it on the same street (different block range)?", same_street)

    if same_street:
        return RatingResult(
            rating="Good",
            guideline_section="10.2",
            rule_title="Address Query",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Same street, different block — Good"],
        )

    return RatingResult(
        rating="Off Topic",
        guideline_section="10.2",
        rule_title="Address Query",
        decision_path=path,
        exceptions=exceptions,
        confidence_factors=["Different street — Off Topic"],
    )


def _closed_business_tree(context: dict) -> RatingResult:
    path: list[DecisionStep] = []
    exceptions = [
        "Recently closed (<1 year) businesses may still be Acceptable",
        "Historical closures (chain-wide) are well-known and may warrant Acceptable",
    ]

    same_biz = _yn(context, "is_same_business")
    _step(path, "Is the result the same business that is closed (correct name)?", same_biz)

    if same_biz is False:
        return RatingResult(
            rating="Off Topic",
            guideline_section="5.14",
            rule_title="Closed Business",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Wrong business — Off Topic"],
        )

    recently = _yn(context, "recently_closed")
    _step(path, "Was the business closed recently (within ~1 year)?", recently)

    successor = _yn(context, "successor_shown")
    _step(path, "Is a successor or replacement business shown at the same location?", successor)

    if recently:
        return RatingResult(
            rating="Acceptable",
            guideline_section="5.14",
            rule_title="Closed Business",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Recently closed business — Acceptable (shows historical location)"],
        )

    return RatingResult(
        rating="Acceptable",
        guideline_section="5.14",
        rule_title="Closed Business",
        decision_path=path,
        exceptions=exceptions,
        confidence_factors=["Closed business shown — Acceptable (marginally useful as historical reference)"],
    )


def _transit_poi_tree(context: dict) -> RatingResult:
    path: list[DecisionStep] = []
    exceptions = [
        "POIs directly inside a transit station are always Navigational",
    ]

    inside = _yn(context, "inside_station")
    _step(path, "Is the result physically inside or at the queried transit station?", inside)

    if inside:
        return RatingResult(
            rating="Navigational",
            guideline_section="5.16.1",
            rule_title="Transit POI",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["POI inside transit station — deterministic Navigational"],
        )

    serves = _yn(context, "serves_station")
    _step(path, "Does the result directly serve transit users at that station?", serves)

    if serves:
        return RatingResult(
            rating="Excellent",
            guideline_section="5.16.1",
            rule_title="Transit POI",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["POI serves transit users at queried station — Excellent"],
        )

    return RatingResult(
        rating="Good",
        guideline_section="5.16.1",
        rule_title="Transit POI",
        decision_path=path,
        exceptions=exceptions,
        confidence_factors=["POI near but not directly at/serving the station — Good"],
    )


def _unexpected_result_tree(context: dict) -> RatingResult:
    path: list[DecisionStep] = []
    exceptions = [
        "Rebranded businesses with former name noted may rate Excellent",
        "Parent company results for a subsidiary query may rate Excellent",
    ]

    connection = _yn(context, "any_connection")
    _step(path, "Is there any meaningful connection between query and result (alias, rebranding, address)?", connection)

    if connection:
        user_want = _yn(context, "user_might_want")
        _step(path, "Could the user plausibly have wanted this result?", user_want)

        if user_want:
            return RatingResult(
                rating="Excellent",
                guideline_section="5.14",
                rule_title="Unexpected Result",
                decision_path=path,
                exceptions=exceptions,
                confidence_factors=["Connection exists and user might want this — Excellent"],
            )

        return RatingResult(
            rating="Acceptable",
            guideline_section="5.14",
            rule_title="Unexpected Result",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Weak or indirect connection — Acceptable"],
        )

    return RatingResult(
        rating="Off Topic",
        guideline_section="5.14",
        rule_title="Unexpected Result",
        decision_path=path,
        exceptions=exceptions,
        confidence_factors=["No meaningful connection found — Off Topic"],
    )


def _street_tree(context: dict) -> RatingResult:
    path: list[DecisionStep] = []
    exceptions = [
        "Famous named streets (Rodeo Drive, Wall Street) follow famous landmark rules",
    ]

    exact = _yn(context, "exact_street")
    _step(path, "Does the result match the exact street queried (same name, same city)?", exact)

    if exact:
        return RatingResult(
            rating="Navigational",
            guideline_section="10.2",
            rule_title="Street Query",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Exact street match — deterministic Navigational"],
        )

    same_area = _yn(context, "same_area")
    _step(path, "Is it in the same general area/city?", same_area)

    if same_area:
        return RatingResult(
            rating="Good",
            guideline_section="10.2",
            rule_title="Street Query",
            decision_path=path,
            exceptions=exceptions,
            confidence_factors=["Street in same area but not exact match — Good"],
        )

    return RatingResult(
        rating="Acceptable",
        guideline_section="10.2",
        rule_title="Street Query",
        decision_path=path,
        exceptions=exceptions,
        confidence_factors=["Street in different area — Acceptable"],
    )


def _default_tree(context: dict) -> RatingResult:
    """Fallback tree when no specific tree is matched."""
    return RatingResult(
        rating="Couldn't Evaluate",
        guideline_section="N/A",
        rule_title="Unknown Query Type",
        decision_path=[DecisionStep("Query type recognized?", "No — using fallback")],
        exceptions=["Select the correct query type and re-run"],
        confidence_factors=["Unknown query type — cannot apply deterministic rules"],
    )


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------

_TREE_MAP: dict = {
    "Transit Query": _transit_tree,
    "Chain Business": _chain_business_tree,
    "Chain Business + General Location Modifier": _chain_general_modifier_tree,
    "Chain Business + Specific Location Modifier": _chain_specific_modifier_tree,
    "Business + Full Address": _business_full_address_tree,
    "Non-Specific Address": _non_specific_address_tree,
    "Point of Interest": _poi_tree,
    "Famous Landmark": _famous_landmark_tree,
    "Near Me": _near_me_tree,
    "Locality Query": _locality_tree,
    "Address": _address_tree,
    "Closed Business": _closed_business_tree,
    "Transit POI": _transit_poi_tree,
    "Unexpected Result": _unexpected_result_tree,
    "Street": _street_tree,
}


def run_decision_tree(query_type: str, context: dict) -> RatingResult:
    """
    Run the appropriate decision tree for the given query type.

    Parameters
    ----------
    query_type : str
        One of the recognised TELUS Maps query types.
    context : dict
        All collected inputs: basic fields (viewport_fresh,
        user_inside_viewport, …) plus additional question answers keyed
        by the question ``key`` from ADDITIONAL_QUESTIONS.

    Returns
    -------
    RatingResult
    """
    tree_fn = _TREE_MAP.get(query_type, _default_tree)
    return tree_fn(context)
