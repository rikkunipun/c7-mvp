# Token Optimization Hackathon — Submission

Repo: Siddhant-Goswami/c7-mvp, branch `mcp`, file `c7-mcp/diagnoser.py`
Representative query used throughout (search_web + get_calendar_events + estimate_time_saved):

> "I open Jira, pick a priority task, write a status report, and Slack it to my manager
> every morning — it takes 40 minutes a day, 5 days a week. Diagnose this workflow, check
> my calendar between 2026-08-03 and 2026-08-07 for meetings related to this Jira/manager
> reporting routine, and suggest current tools to automate it. How many hours a year would
> automating it save me?"

## 1. App + repo link

`c7-mcp/diagnoser.py` on branch `mcp` — see repo link (to be added once pushed; see note below).

## 2. BEFORE — naive/unoptimized tool call

Peak payload (messages sent to the model, right after the raw tool dumps land in context),
counted with `tiktoken` (`cl100k_base` — an approximation, since no public tokenizer exists
for `qwen/qwen3.6-27b`; consistent within this comparison, but won't exactly match Groq's
real billed count, which ran ~14% higher in one observed case):

| tool | raw result tokens |
|---|---|
| `search_web` (8 results) | 3,075 |
| `get_calendar_events` (10 events) | 679 |
| `estimate_time_saved` | 10 |
| **Peak payload** | **5,309** |

Total input tokens across the full interaction (all 4 API calls in the loop, since Groq
bills each call for its full growing context): **14,807**.

## 3. AFTER — same query, through the retrieval pipeline

Same representative query, same tools, after wiring `filter_relevant()` (keyword-count
filter, no embeddings, no vector DB) into `run_tools()`:

| tool | raw tokens | filtered tokens |
|---|---|---|
| `search_web` (8 → top 5) | 3,075 | 1,923 |
| `get_calendar_events` (10 → top 5) | 679 | 365 |
| `estimate_time_saved` (unfiltered) | 10 | 10 |
| **Peak payload** | **5,309** | **3,795** |

**Compression: 5,309 / 3,795 = 1.40x** (peak payload). Total input tokens across the full
interaction: 10,864 (vs. 14,807 before) — same 1.36x-1.40x range.

Answer quality held up: the filtered run still correctly named all 5 genuinely relevant
calendar events by date/time and gave equivalent tool recommendations to the unfiltered run.

## 4. Index design

See `c7-mcp/index.json`. Summary: each tool's output is already naturally chunked (one
search result = one chunk, one calendar event = one chunk — no further splitting needed).
Metadata kept per chunk: `title`+`content` for search results, `title`+`description` for
calendar events (used for filtering); other keys (`url`, `score`, `date`, `attendees`, etc.)
are present in the raw data but not currently used by the filter.

**Key discovered after seeing a real query:** Tavily's raw search results already include a
`score` relevance field that the filter never uses — ranking is currently pure keyword-hit
count, which can misrank near-duplicate-topic items. Observed concretely: the filter kept
"Sprint Planning" over "Sprint Retrospective" for a query that never contained the word
"sprint" at all — "Sprint Planning" only won because its description incidentally also
matched the unrelated keyword "priority." Combining keyword-hit count with the existing
`score` field would likely improve ranking without adding embeddings.

## 5. Cost projection

Pricing (Groq, `qwen/qwen3.6-27b`, listed as a Preview model — evaluation pricing, not
guaranteed stable for production): **$0.60 / 1M input tokens, $3.00 / 1M output tokens.**

| | BEFORE | AFTER |
|---|---|---|
| Total input tokens (4 calls) | 14,807 | 10,864 |
| Output tokens (final answer) | 450 | 755 |
| Total cost per query | $0.01023 | $0.00878 |

Output length varies naturally between runs (unrelated to the optimization, which only
targets input/tool-output tokens) — the 1.40x input compression is the reliable, repeatable
number; the blended total-cost savings in any single run will vary with how long the model's
answer happens to be.

**Projection at personal scale** (1 query per workday, 260/year — matching this assignment's
own "40 min/day, 5 days/week" framing):

| | BEFORE | AFTER | savings |
|---|---|---|---|
| Daily | $0.01023 | $0.00878 | $0.00145 |
| Monthly (~21.7 workdays) | $0.222 | $0.190 | $0.032 |
| Yearly (260 workdays) | $2.66 | $2.28 | **$0.38** |

**Verdict: at personal scale, this does not pay for itself in dollar terms.** $0.38/year
saved does not justify the engineering time spent building the retrieval pipeline. The real
payoff at this scale isn't cost — it's reliability: the naive, unfiltered version hit Groq's
8,000 TPM rate limit and failed outright (413 errors) at points during development, and the
optimized version doesn't. If this were ever deployed to more than one person, the same
1.40x input compression scales linearly with usage while the naive version's risk of hitting
the rate limit only gets worse — so the "worth it" answer flips from no to yes well before
reaching production-app-scale volume.

---

## Notes on methodology / known limitations

- `tiktoken` (`cl100k_base`) is an approximation of `qwen/qwen3.6-27b`'s real tokenizer —
  used consistently for before/after comparison, but not exact against Groq's actual billing.
- The keyword extractor does light punctuation stripping (commas, periods, em dash) but
  missed the `/` in "Jira/manager," producing one merged token — didn't affect this query's
  results since "jira" and "manager" both also appeared as separate tokens elsewhere in the
  sentence, but is a known gap for future queries.
- `get_calendar_events` currently ignores its own `start_date`/`end_date` arguments and
  always returns the full mock week — date-range filtering was out of scope for this pass
  (bulk-first, correctness-later was the deliberate order of work).
