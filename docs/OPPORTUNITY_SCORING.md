# Opportunity Scoring — Methodology

`scripts/score_opportunities.py` turns the five raw tables into a ranked,
explained list of sellers the Ads Sales team should prioritize. It reads
only the public CSV output of `scripts/generate_data.py` — the same tables a
real analyst would query — never the generator's internal latent variables.

## The four pillars, as sub-scores

Each of the platform's four pillars becomes one 0–100 sub-score per seller:

| Sub-score | Pillar | What it measures |
|---|---|---|
| `marketplace_score` | Marketplace | Organic demand/traction, **category-normalized** |
| `advertising_gap_score` | Advertising | How under-monetized they are relative to peers |
| `seller_score` | Seller | Readiness/trustworthiness as a sales target |
| `sales_gap_score` | Opportunity (sales activity) | How overdue they are for outreach |

### `marketplace_score` — organic demand

Built from `listing_metrics` rolled up through `listings` to the seller:

```
demand_raw = views·1 + clicks·4 + chats_started·8 + phone_reveals·8 + favorites_added·3
```

Deeper-funnel actions (a chat, a phone reveal) count for more than a passive
view, since they signal real buyer intent. `demand_raw` is then converted to
a **percentile rank within the seller's `primary_category`** — comparing a
Property seller only against other Property sellers, not against Fashion —
because raw view counts differ by an order of magnitude across categories
for reasons that have nothing to do with how good a lead someone is.

### `advertising_gap_score` — under-monetization

```
if total_ad_spend == 0:        gap = 100
else:                          gap = 60 × (1 − spend_percentile_within_category)
```

Never having advertised gets the ceiling score (100) directly, rather than
just ranking at the bottom of the spenders — that keeps "never advertised"
and "advertised a little" visibly distinct populations. Existing advertisers
still get a shrinking gap score as their relative spend grows, so upsell
potential doesn't vanish entirely.

### `seller_score` — readiness/trustworthiness

```
25 × is_verified + 10 × phone_verified + 25 × (rating_avg / 5)
+ 25 × (response_rate_pct / 100) + 15 × min(tenure_years / 2, 1)
```

A weighted composite of trust and engagement signals. This isn't demand —
it's "if the sales team calls, is this someone worth calling."

### `sales_gap_score` — outreach coverage gap

Derived from the most recent row per seller in `sales_activities`:

| Situation | Gap score |
|---|---|
| Never contacted | 100 |
| Deal `closed_won` | 5 (already converted) |
| Deal `closed_lost` / last outcome `not_interested` | 15 (recently declined) |
| Open `next_follow_up_date` in the future | 10 (already being worked — don't double-flag) |
| Contacted, stalled, no active follow-up | `days_since_last_contact / 1.8`, clipped to [10, 100] (re-surfaces stale leads) |

## Combining into `opportunity_score`

**This is the part that matters most, and the first version of it was wrong.**
A naive weighted *sum* of the four sub-scores — e.g.
`0.4·marketplace + 0.25·advertising_gap + 0.2·seller + 0.15·sales_gap` —
inflates almost everyone: most sellers have never advertised (gap=100) and
have never been contacted (gap=100), so those two terms alone contribute
`0.25×100 + 0.15×100 = 40` points to nearly 80% of the seller base regardless
of whether they have any organic traction at all. An average-traction,
never-touched seller ends up in the "Warm" tier next to a genuinely
high-potential one — the score stops discriminating.

Opportunity is a **conjunction**, not a sum: *high traction* **and**
*nobody's monetizing it* **and** *nobody's called them*. So `marketplace_score`
(the actual size of the prize) is the base, and the other three pillars each
apply a **multiplicative dampener** in a bounded range instead of an
independent additive term:

```
advertising_dampener = 0.30 + 0.70 × (advertising_gap_score / 100)   # range [0.30, 1.00]
sales_dampener       = 0.25 + 0.75 × (sales_gap_score / 100)          # range [0.25, 1.00]
readiness_dampener   = 0.40 + 0.60 × (seller_score / 100)             # range [0.40, 1.00]

opportunity_score = marketplace_score × advertising_dampener × sales_dampener × readiness_dampener
```

Properties this gives:
- **Zero traction stays near zero**, no matter how neglected or unmonetized
  a seller is — being ignored isn't itself an opportunity if there's nothing
  to unlock.
- **A top-traction seller who's already a heavy advertiser and being
  actively worked gets pulled back down** (dampeners near their floors),
  correctly deprioritizing accounts sales already has.
- **A top-traction seller who's never advertised and never been
  contacted keeps close to their full `marketplace_score`** — the ideal lead.
- Every dampener has a floor above zero, so no single pillar can *erase* a
  strong marketplace signal on its own — a great lead who happens to have a
  middling `seller_score` is discounted, not disqualified.

Sellers are bucketed into `priority_tier`: **Hot** (≥70), **Warm** (45–69),
**Cool** (20–44), **Low** (<20).

## Validating the result

On the current dataset (seed 42): mean score 26.7, median 21.7, with a long
right tail up to 92.2 — 62 sellers (4.1%) land in Hot, 698 (46.5%) in Low.
Spot checks confirm the intended behavior:

- A seller with **top-1% traction, already spending heavily on ads, and
  currently being worked by a rep** scores **6.8** (Low) — correctly
  deprioritized.
- A seller with **top-1% traction, zero ad spend, verified, never
  contacted** scores **92.2** (Hot) — the platform's ideal lead.
- Several of the sellers this script ranks in the top 20 are the same ones
  flagged in `scripts/audit_data.py` check #4 (top-quartile traction, zero
  ads, zero contact) — confirming the score is *discovering* that segment
  from the four pillars, not being handed it.

## Explanations

Each seller gets a one-sentence `reason` built from whichever pillar
readings are actually notable for them (top-percentile traction, "zero ad
spend to date," verification/rating/response-rate callouts, contact-gap
description) — not a fixed template, so a Hot lead and a Low one read
differently and the reason always traces back to real column values.

## Running it

```bash
python scripts/score_opportunities.py            # reads data/raw/, writes data/processed/opportunity_scores.csv
python scripts/score_opportunities.py --top 50    # print more leads to console
```

Output columns: full pillar breakdown (`marketplace_score`,
`advertising_gap_score`, `seller_score`, `sales_gap_score`), the composite
`opportunity_score` and `priority_tier`, supporting raw metrics
(`total_views`, `total_ad_spend`, `touch_count`, `days_since_last_contact`,
...), and the `reason` string — ranked descending by `opportunity_score`.
