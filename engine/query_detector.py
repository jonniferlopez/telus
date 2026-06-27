"""
Query type detection module.

Detects the type of a map search query based on the query text,
category, address, result title, and pin notes. Returns both the
detected type and a plain-language reasoning string.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Static reference data
# ---------------------------------------------------------------------------

CHAIN_BUSINESSES: set[str] = {
    "mcdonalds", "mcdonald's", "wendy's", "wendys", "burger king",
    "starbucks", "subway", "dunkin", "dunkin donuts", "dunkin'",
    "tim hortons", "pizza hut", "dominos", "domino's", "kfc",
    "taco bell", "chipotle", "panera", "panera bread", "panda express",
    "chick-fil-a", "chick fil a", "in-n-out", "in n out", "five guys",
    "shake shack", "popeyes", "arby's", "arbys", "sonic",
    "jack in the box", "hardee's", "carl's jr", "target", "walmart",
    "costco", "home depot", "lowes", "lowe's", "cvs", "walgreens",
    "rite aid", "7-eleven", "circle k", "best buy", "autozone",
    "advance auto", "o'reilly auto", "chase bank", "bank of america",
    "wells fargo", "citibank", "ups store", "fedex office",
    "holiday inn", "marriott", "hilton", "sheraton", "westin",
    "comfort inn", "hampton inn", "courtyard", "dollar tree",
    "dollar general", "family dollar", "ross", "tj maxx", "marshalls",
    "burlington", "whole foods", "trader joe's", "kroger", "safeway",
    "albertsons", "publix", "wegmans", "aldi", "lidl", "h&m", "zara",
    "gap", "old navy", "banana republic", "forever 21", "nordstrom",
    "macy's", "jcpenney", "kohl's", "dillard's", "pizza pizza",
    "boston pizza", "swiss chalet", "harvey's", "a&w", "dairy queen",
    "dq", "baskin robbins", "cold stone", "orange julius",
}

TRANSIT_KEYWORDS: set[str] = {
    "station", "metro", "subway", "bus stop", "bus terminal",
    "train station", "rail", "railway", "terminal", "transit",
    "tube", "underground", "bart", "mta", "cta", "mbta",
    "tram", "light rail", "commuter rail", "amtrak", "greyhound",
    "platform", "depot", "streetcar",
}

FAMOUS_LANDMARKS: set[str] = {
    "eiffel tower", "big ben", "statue of liberty", "golden gate bridge",
    "empire state building", "times square", "central park",
    "white house", "capitol building", "lincoln memorial", "space needle",
    "cn tower", "buckingham palace", "notre dame cathedral", "colosseum",
    "sagrada familia", "taj mahal", "great wall", "sydney opera house",
    "burj khalifa", "chrysler building", "rockefeller center",
    "niagara falls", "grand canyon", "mount rushmore",
    "hollywood sign", "brooklyn bridge", "manhattan bridge",
    "tower of london", "louvre", "notre dame", "parthenon",
    "stonehenge", "machu picchu", "angkor wat",
}

STREET_TYPE_SUFFIXES: tuple[str, ...] = (
    " street", " st", " avenue", " ave", " boulevard", " blvd",
    " road", " rd", " drive", " dr", " lane", " ln",
    " place", " pl", " court", " ct", " way", " parkway",
    " pkwy", " highway", " hwy", " circle", " terrace",
    " crescent", " trail", " grove", " close",
)

LOCALITY_KEYWORDS: tuple[str, ...] = (
    "city", "town", "village", "neighborhood", "district",
    "county", "borough", "municipality", "suburb", "region",
    "downtown", "uptown", "midtown", "quarter", "ward",
)

POI_CATEGORIES: tuple[str, ...] = (
    "museum", "park", "hospital", "clinic", "school", "university",
    "college", "church", "hotel", "restaurant", "bar", "cafe",
    "coffee", "library", "theater", "cinema", "stadium", "arena",
    "mall", "shopping", "market", "gym", "fitness", "spa", "salon",
    "bank", "pharmacy", "supermarket", "airport",
)

# All supported query types (ordered for display)
QUERY_TYPES: list[str] = [
    "Chain Business",
    "Chain Business + General Location Modifier",
    "Chain Business + Specific Location Modifier",
    "Business + Full Address",
    "Transit Query",
    "Locality Query",
    "Point of Interest",
    "Famous Landmark",
    "Street",
    "Address",
    "Non-Specific Address",
    "Near Me",
    "Closed Business",
    "Transit POI",
    "Unexpected Result",
]

# ---------------------------------------------------------------------------
# Additional questions asked after query type is detected
# ---------------------------------------------------------------------------

ADDITIONAL_QUESTIONS: dict[str, list[dict]] = {
    "Transit Query": [
        {
            "key": "exact_station_match",
            "text": "Is the result the exact station/stop that was queried (same name and location)?",
        },
        {
            "key": "same_locality",
            "text": "Is the result in the same locality (city / neighborhood) as the queried station?",
        },
        {
            "key": "neighboring_locality",
            "text": "Is the result in a neighboring or adjacent locality?",
        },
    ],
    "Chain Business": [
        {
            "key": "correct_chain",
            "text": "Is the result the same chain/brand as queried (not a different brand)?",
        },
        {
            "key": "is_closest",
            "text": "Is this the closest location of this chain in the current viewport?",
        },
        {
            "key": "closer_exist",
            "text": "Are there 1–2 closer locations of this chain in the viewport that are NOT shown first?",
        },
        {
            "key": "many_closer_exist",
            "text": "Are there 3 or more closer locations of this chain in the viewport not shown first?",
        },
    ],
    "Chain Business + General Location Modifier": [
        {
            "key": "correct_chain",
            "text": "Is the result the same chain/brand as queried?",
        },
        {
            "key": "in_specified_area",
            "text": "Is the result located in the specified general area/city (the modifier in the query)?",
        },
        {
            "key": "adjacent_area",
            "text": "Is the result in an adjacent or neighboring area (just outside the modifier)?",
        },
    ],
    "Chain Business + Specific Location Modifier": [
        {
            "key": "correct_chain",
            "text": "Is the result the same chain/brand as queried?",
        },
        {
            "key": "exact_address",
            "text": "Does the result match the specific address or intersection in the query exactly?",
        },
        {
            "key": "closest_to_address",
            "text": "Is this the closest location of the chain to the specified address?",
        },
        {
            "key": "same_neighborhood",
            "text": "Is the result in the same neighborhood as the specified address?",
        },
    ],
    "Business + Full Address": [
        {
            "key": "correct_business",
            "text": "Is the result the same business (by name) as queried?",
        },
        {
            "key": "exact_address",
            "text": "Does the address in the result match exactly (same number and street)?",
        },
        {
            "key": "same_block",
            "text": "Is it on the same block (within ~50 house numbers on the same street)?",
        },
        {
            "key": "same_street",
            "text": "Is it on the same street (but farther away on different block range)?",
        },
    ],
    "Non-Specific Address": [
        {
            "key": "valid_interpretation",
            "text": "Is the result a valid interpretation of the queried non-specific address?",
        },
        {
            "key": "most_prominent",
            "text": "Is it the most prominent/central interpretation (e.g., busiest segment, most well-known city)?",
        },
    ],
    "Point of Interest": [
        {
            "key": "exact_poi",
            "text": "Is the result the exact POI queried (same name and location)?",
        },
        {
            "key": "alias_same_place",
            "text": "Is it an alias, colloquial name, or different entrance for the same physical POI?",
        },
        {
            "key": "same_category_same_area",
            "text": "Is it the same category of POI (e.g., another museum, another park) in the same area?",
        },
        {
            "key": "same_category_same_city",
            "text": "Is it the same category in the same city but a different neighborhood?",
        },
    ],
    "Famous Landmark": [
        {
            "key": "exact_landmark",
            "text": "Is the result the exact famous landmark queried?",
        },
        {
            "key": "official_entity",
            "text": "Is it the official entity/page for the landmark (not just a nearby business)?",
        },
    ],
    "Near Me": [
        {
            "key": "nearest_result",
            "text": "Is this the nearest matching entity to the user's location?",
        },
        {
            "key": "within_reasonable",
            "text": "Is the result within a reasonable distance (not unreasonably far)?",
        },
    ],
    "Locality Query": [
        {
            "key": "exact_locality",
            "text": "Is the result the exact locality (city, town, neighborhood) queried?",
        },
        {
            "key": "sub_locality",
            "text": "Is it a sub-locality or neighborhood within the queried area?",
        },
        {
            "key": "adjacent_locality",
            "text": "Is it an adjacent or neighboring locality?",
        },
    ],
    "Address": [
        {
            "key": "exact_address",
            "text": "Does the result match the exact address queried (same number, same street)?",
        },
        {
            "key": "same_block",
            "text": "Is it on the same block (within ~50 house numbers)?",
        },
        {
            "key": "same_street",
            "text": "Is it on the same street but farther away (different block range)?",
        },
    ],
    "Closed Business": [
        {
            "key": "is_same_business",
            "text": "Is the result the same business as queried (just currently closed)?",
        },
        {
            "key": "recently_closed",
            "text": "Was the business closed recently (within approximately the past year)?",
        },
        {
            "key": "successor_shown",
            "text": "Is a successor or replacement business shown at the same location?",
        },
    ],
    "Transit POI": [
        {
            "key": "inside_station",
            "text": "Is the result physically inside or at the queried transit station?",
        },
        {
            "key": "serves_station",
            "text": "Does the result directly serve transit users at that station (e.g., taxi stand, bike share)?",
        },
    ],
    "Unexpected Result": [
        {
            "key": "any_connection",
            "text": "Is there any meaningful connection between the query and the result (alias, rebranding, same address)?",
        },
        {
            "key": "user_might_want",
            "text": "Could the user plausibly have wanted this result based on the query?",
        },
    ],
    "Street": [
        {
            "key": "exact_street",
            "text": "Does the result represent the exact street queried (same name, same city)?",
        },
        {
            "key": "same_area",
            "text": "Is it in the same general area/city as expected?",
        },
    ],
}


# ---------------------------------------------------------------------------
# Detection logic
# ---------------------------------------------------------------------------

def _has_street_type(text: str) -> bool:
    """Return True if the text contains a street-type suffix."""
    t = text.lower()
    return any(t.endswith(s) or (s + " ") in t or (s + ",") in t for s in STREET_TYPE_SUFFIXES)


def _is_chain(text: str) -> bool:
    """Return True if the text contains a known chain business name."""
    t = text.lower()
    return any(chain in t for chain in CHAIN_BUSINESSES)


def _is_transit(text: str) -> bool:
    """Return True if the text contains a transit keyword as a whole word."""
    t = text.lower()
    for kw in TRANSIT_KEYWORDS:
        # Use word boundary check: the keyword must appear as a whole word
        # (preceded and followed by a non-word character or string boundary)
        pattern = r"(?<![a-z])" + re.escape(kw) + r"(?![a-z])"
        if re.search(pattern, t):
            return True
    return False


def detect_query_type(
    query: str,
    category: str = "",
    address: str = "",
    result_title: str = "",
    pin_notes: str = "",
) -> tuple[str, str]:
    """
    Detect the query type from the provided inputs.

    Returns
    -------
    (query_type, reasoning)
        query_type : one of QUERY_TYPES
        reasoning  : plain-language explanation of why this type was detected
    """
    q = query.lower().strip()
    cat = (category or "").lower()
    pin = (pin_notes or "").lower()
    rt = (result_title or "").lower()

    # ------------------------------------------------------------------
    # 1. Near Me — highest priority pattern
    # ------------------------------------------------------------------
    if re.search(r"\bnear me\b|\bnearby me\b|\bclose to me\b|\bnearest to me\b", q):
        return "Near Me", "Query contains a 'near me' phrase — user wants closest result to their location."

    # ------------------------------------------------------------------
    # 2. Closed Business
    # ------------------------------------------------------------------
    closed_terms = ("closed", "permanently closed", "out of business", "shutdown", "shuttered")
    if any(t in pin for t in closed_terms) or any(t in rt for t in ("(closed)", "permanently closed")):
        return "Closed Business", "Pin notes or result title indicate the business is closed."

    # ------------------------------------------------------------------
    # 3. Transit
    # ------------------------------------------------------------------
    transit_in_query = _is_transit(q)
    transit_in_cat = any(kw in cat for kw in ("transit", "train", "bus", "metro", "subway", "rail", "station"))
    if transit_in_query or transit_in_cat:
        result_is_transit = result_title and _is_transit(rt)
        if result_title and not result_is_transit:
            return (
                "Transit POI",
                "Query involves transit but the result appears to be a POI near (not at) a transit station.",
            )
        return "Transit Query", "Query contains transit keywords (station, metro, subway, rail, etc.)."

    # ------------------------------------------------------------------
    # 4. Chain Business — checked BEFORE address patterns so that
    #    "Burger King at 400 W 42nd St" is not mis-classified as
    #    Non-Specific Address just because it contains " st".
    # ------------------------------------------------------------------
    if _is_chain(q):
        # Specific modifier: address-like text.
        # Use a safe word-split check instead of a potentially slow regex.
        q_words = q.split()
        _has_num_word = any(
            w.rstrip(".,") .isdigit() and idx + 1 < len(q_words)
            for idx, w in enumerate(q_words)
        )
        has_specific = _has_num_word or _has_street_type(q)

        # General modifier: city/area/direction word
        general_terms = (" in ", " near ", " at ", " downtown", " uptown", " north ", " south ",
                         " east ", " west ", " midtown", " by the ", " around ")
        has_general = (not has_specific) and any(t in (" " + q + " ") for t in general_terms)

        if has_specific:
            return (
                "Chain Business + Specific Location Modifier",
                "Query is a chain business name with a specific address or location (e.g., street address, intersection).",
            )
        if has_general:
            return (
                "Chain Business + General Location Modifier",
                "Query is a chain business name with a general area modifier (city, neighborhood, directional).",
            )
        return "Chain Business", "Query is a chain/franchise business name without a location modifier."

    # ------------------------------------------------------------------
    # 5. Specific street address — starts with a house number
    # ------------------------------------------------------------------
    if re.match(r"^\d+\s+[a-z]", q):
        return "Address", "Query begins with a street number — interpreted as a specific address query."

    # ------------------------------------------------------------------
    # 6. Non-specific address — street type without a house number
    # ------------------------------------------------------------------
    if _has_street_type(q) and not re.match(r"^\d+\s+[a-z]", q):
        return (
            "Non-Specific Address",
            "Query mentions a street type (Street, Ave, Blvd…) without a specific house number.",
        )

    # ------------------------------------------------------------------
    # 7. Famous Landmark
    # ------------------------------------------------------------------
    if any(lm in q for lm in FAMOUS_LANDMARKS):
        return "Famous Landmark", "Query matches a known world-famous landmark."

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    if address and re.match(r"^\d+", address.strip()):
        return (
            "Business + Full Address",
            "A business name was queried and a full street address is provided in the address field.",
        )

    # ------------------------------------------------------------------
    # 9. Locality
    # ------------------------------------------------------------------
    if any(kw in q for kw in LOCALITY_KEYWORDS) or any(kw in cat for kw in ("city", "town", "locality", "neighborhood", "region")):
        return "Locality Query", "Query refers to a city, town, neighborhood, or other administrative locality."

    # ------------------------------------------------------------------
    # 10. Point of Interest (by category)
    # ------------------------------------------------------------------
    if cat and any(p in cat for p in POI_CATEGORIES):
        return "Point of Interest", f"The category '{category}' indicates a specific type of place (POI)."

    # ------------------------------------------------------------------
    # 11. POI keywords in query
    # ------------------------------------------------------------------
    if any(kw in q for kw in POI_CATEGORIES):
        return "Point of Interest", "Query contains keywords associated with a specific type of place (POI)."

    # ------------------------------------------------------------------
    # 12. Street (short query that is a street name)
    # ------------------------------------------------------------------
    words = q.split()
    if len(words) <= 4 and _has_street_type(q):
        return "Street", "Query appears to be a street name without a specific house number."

    # ------------------------------------------------------------------
    # 13. Unexpected Result heuristic
    # ------------------------------------------------------------------
    if result_title and q:
        q_words = {w for w in q.split() if len(w) > 3}
        r_words = {w for w in rt.split() if len(w) > 3}
        if len(q_words) > 1 and not q_words.intersection(r_words):
            return (
                "Unexpected Result",
                "The result title shares no significant words with the query — may be an unexpected or mismatched result.",
            )

    # ------------------------------------------------------------------
    # Default fallback
    # ------------------------------------------------------------------
    return "Point of Interest", "Default classification — no specific pattern matched; treating as a general POI query."


def get_additional_questions(query_type: str) -> list[dict]:
    """Return the list of additional follow-up questions for a given query type."""
    return ADDITIONAL_QUESTIONS.get(query_type, [])
