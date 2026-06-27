# TELUS Maps Quality Rating — Quick Reference Cheat Sheet

## Rating Scale

| Rating | Description |
|--------|-------------|
| **Navigational** | Perfect result — user navigates directly here. Exact match, best possible answer. |
| **Excellent** | Highly relevant — fully satisfies the query intent with minor gaps. |
| **Good** | Relevant — satisfies the query but not the ideal result. |
| **Acceptable** | Marginally relevant — barely satisfies the query. |
| **Off Topic** | Not relevant — no meaningful connection to the query. |
| **Couldn't Evaluate** | Cannot rate — insufficient information to determine relevance. |

---

## Query Types & Governing Sections

| Query Type | Section | Key Rule |
|-----------|---------|---------|
| Transit Query | 5.16.1 | Exact station → Nav; Same locality → Excellent; Neighboring → Good; Farther → Acceptable |
| Chain Business (no modifier) | 10.6.2 | Closest chain, fresh viewport → Nav/Excellent; closer exist → Good/Acceptable |
| Chain + General Modifier | 10.6.3 | In specified area → Excellent; adjacent → Good; wrong area → Acceptable |
| Chain + Specific Modifier | 10.6.3 | Exact address → Nav; closest to address → Excellent |
| Business + Full Address | 8.3.2 | Exact match → Nav; same block → Excellent; same street → Good |
| Non-Specific Address | 10.2 | Best street interpretation → Excellent; valid but non-prominent → Good |
| Point of Interest | 8.3.2 | Exact POI → Nav; same category same area → Excellent; same city → Good |
| Famous Landmark | 8.3.2 | Exact landmark → Nav; same location different entity → Excellent |
| Near Me | 10.6.2 | Nearest to user → Nav; close but not nearest → Good |
| Locality Query | — | Exact locality → Nav; sub-locality → Excellent; adjacent → Good |
| Address | 10.2 | Exact → Nav; same block → Excellent; same street → Good; different street → Off Topic |
| Street | 10.2 | Exact street → Nav; parallel/nearby → Good |
| Closed Business | 5.14 | Recently closed, shows location → Acceptable; long closed → Off Topic |
| Transit POI | 5.16.1 | POI inside/at station → Nav; accessible from station → Excellent |
| Unexpected Result | 5.14 | Clear alias/rebranding → Excellent; weak connection → Acceptable; none → Off Topic |

---

## Decision Tree: Transit Query (§5.16.1)

```
Query is for a transit station/stop
        │
        ▼
Is the result the EXACT station queried?
   │
   ├─ YES → NAVIGATIONAL
   │
   └─ NO → Is the station in the SAME LOCALITY?
              │
              ├─ YES → EXCELLENT
              │
              └─ NO → Is it in a NEIGHBORING LOCALITY?
                         │
                         ├─ YES → GOOD
                         │
                         └─ NO → Is it the same transit system, just farther?
                                    │
                                    ├─ YES → ACCEPTABLE
                                    │
                                    └─ NO → OFF TOPIC
```

---

## Decision Tree: Chain Business (§10.6.2)

```
Query is for a chain business (no location modifier)
        │
        ▼
Is the result the CORRECT CHAIN?
   │
   ├─ NO → OFF TOPIC
   │
   └─ YES → Is the VIEWPORT FRESH?
               │
               ├─ YES (Fresh) → Are there CLOSER LOCATIONS of this chain in viewport?
               │                    │
               │                    ├─ NO (this is closest) → NAVIGATIONAL
               │                    │
               │                    ├─ YES, 1-2 closer → GOOD
               │                    │
               │                    └─ YES, 3+ closer → ACCEPTABLE
               │
               └─ NO (Stale) → Is the result the best available match?
                                   │
                                   ├─ YES → EXCELLENT
                                   │
                                   └─ NO → GOOD / ACCEPTABLE
```

---

## Decision Tree: Chain Business + General Location Modifier (§10.6.3)

```
Query: "[Chain] in/near [General Area]"
        │
        ▼
Is the result the CORRECT CHAIN?
   │
   ├─ NO → OFF TOPIC
   │
   └─ YES → Is the result in the SPECIFIED AREA?
               │
               ├─ YES → EXCELLENT
               │
               └─ NO → Is it in an ADJACENT/NEIGHBORING area?
                           │
                           ├─ YES → GOOD
                           │
                           └─ NO → Is it in the same city, different area?
                                      │
                                      ├─ YES → ACCEPTABLE
                                      │
                                      └─ NO → OFF TOPIC
```

---

## Decision Tree: Chain Business + Specific Location Modifier (§10.6.3)

```
Query: "[Chain] at/on [Specific Address]"
        │
        ▼
Is the result the CORRECT CHAIN?
   │
   ├─ NO → OFF TOPIC
   │
   └─ YES → Does it match the EXACT ADDRESS?
               │
               ├─ YES → NAVIGATIONAL
               │
               └─ NO → Is it the CLOSEST location to that address?
                           │
                           ├─ YES → EXCELLENT
                           │
                           └─ NO → Is it in the same neighborhood?
                                      │
                                      ├─ YES → GOOD
                                      │
                                      └─ NO → ACCEPTABLE
```

---

## Decision Tree: Point of Interest (§8.3.2)

```
Query is for a specific POI
        │
        ▼
Is the result the EXACT POI (same name & location)?
   │
   ├─ YES → NAVIGATIONAL
   │
   └─ NO → Is it the SAME PLACE with a different name (alias/colloquial)?
               │
               ├─ YES → NAVIGATIONAL
               │
               └─ NO → Is it the SAME CATEGORY in the SAME AREA?
                           │
                           ├─ YES → EXCELLENT
                           │
                           └─ NO → Is it the same category, same CITY?
                                      │
                                      ├─ YES → GOOD
                                      │
                                      └─ NO → ACCEPTABLE / OFF TOPIC
```

---

## Key Concepts

### Distance Demotion (Chain Business)
When a chain business appears in the results but closer locations of the same chain exist in the viewport:
- **0 closer** → No demotion (Navigational/Excellent)
- **1–2 closer** → Demote to **Good**
- **3+ closer** → Demote to **Acceptable**

### Fresh vs. Stale Viewport
- **Fresh**: The viewport was recently moved/centered — location is reliable for distance calculations
- **Stale**: The viewport hasn't been updated — less reliable for distance-based ratings
- Fresh viewport criteria are generally stricter than stale viewport criteria

### User Inside Viewport
- When user location is **inside** the viewport, distance calculations are relative to the user
- When user is **outside** the viewport, distance calculations are relative to viewport center
- Near Me queries require the user to be inside the viewport for full accuracy

### USPS Address Verification
- USPS findings can confirm or contradict address validity
- If USPS confirms an address doesn't exist, adjust rating downward
- If USPS confirms address is valid but different, use USPS data as authoritative

### Official Website Verification
- Official website can confirm business location, hours, and whether still open
- If official website shows different address than map pin, investigate further
- Permanently closed confirmation from official website → rate as Closed Business

---

## Common Exceptions

1. **Airports**: Treated as major landmarks; only the queried airport rates Navigational
2. **Chain with single location in area**: Always Navigational regardless of distance
3. **POI with multiple entrances**: Any official entrance rates Navigational
4. **Rebranded businesses**: Former name in description → Excellent; no mention → Acceptable
5. **Temporarily closed**: Rate based on expected re-opening; Permanent closure → Acceptable
6. **Ambiguous locality names**: Use most prominent interpretation; note in reasoning
7. **Address typos in query**: If result clearly matches intended address, rate as if exact
