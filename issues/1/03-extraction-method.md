# 4. Extraction method

This is the main cost/complexity driver. Two sub-decisions: **how to
enumerate** the catalog, and **how to extract fields** from each entry.

## Enumeration

| Option | Manning | O'Reilly |
|---|---|---|
| Sitemap XML | `manning.com` publishes sitemaps listing product URLs | `oreilly.com` sitemaps exist but cover a subset |
| Catalog/browse pagination | topic & catalog pages with page params | search results (gated for full catalog) |
| Underlying JSON API | Manning's site calls a JSON catalog/search endpoint | O'Reilly has `api.oreilly.com` search — auth-gated for full results |

**Recommendation:** prefer **sitemap → product URLs**, fall back to browse
pagination. Investigate each site's JSON API during the first implementation
issue; use it if it's stable and unauthenticated.

## Field extraction — three approaches

| Approach | Pros | Cons |
|---|---|---|
| A. Direct HTML parse (BeautifulSoup / selectors) | free, fast, deterministic; catalog pages are structured and stable | one set of selectors per site; breaks on redesign |
| B. Site JSON API | cleanest data, no HTML parsing | may need auth (O'Reilly); undocumented, can change |
| C. Per-page LLM fragment (reuse `SmartScraperGraph`) | resilient to markup changes; matches existing pattern | cost + latency per page across a whole catalog; needs `LLM_PROVIDER` configured; overkill for structured data |

**Recommendation:** **A (direct HTML parse)** as the primary method, because
title/author/category are plain structured fields on these catalog pages —
unlike Amazon BSR, which is buried and noisy. Keep C available as a
per-record fallback only when a page fails the selector parse. Avoid running
the LLM across the full catalog.

## If LLM is used anyway
- Which provider? `LLM_PROVIDER` currently defaults to `ollama` (local, free
  but slow). A full catalog run (Manning ≈ 1000+ titles) on a paid API
  needs a rough budget sign-off.
- Feed only a small fragment per page (same tactic as
  `extract_bsr_html_fragment`), never the full page.

## Do we still need Playwright?
- Manning / O'Reilly listing pages: check whether server-rendered HTML is
  enough (likely yes) — plain `httpx` is cheaper than driving a browser.
- **Recommendation:** try `httpx` + parser first; fall back to Playwright
  (headless, no login) only for pages that require JS. The persisted
  Amazon login session is not relevant here.

## Rate limiting
- Reuse a `REQUEST_DELAY`-style politeness gap between requests (config
  already has `REQUEST_DELAY = 2.0`). Decide the value for these sites.
