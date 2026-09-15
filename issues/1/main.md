# Plan: Scrape Manning & O'Reilly publisher catalogs (decisions first)

> GitHub issue: https://github.com/tuvalusoftware/AmazonTools/issues/1
>
> Note: `issues/L1`–`issues/L4` are older local-only plans that predate the
> GitHub remote and have no GitHub issue number. This folder (`issues/1`) is
> the first plan tracked against a real GitHub issue.

## Context

The manager asked to "use the scraping tool" to scrape the
**Manning** (`https://www.manning.com/`) and **O'Reilly**
(`https://www.oreilly.com/products/books-videos.html`) publisher sites and
produce a dataset with **book title, author name, and category**.

The existing codebase is an **Amazon BSR & price tracker**, not a catalog
crawler:

- `jobs/scrape_bsr.py` iterates a fixed ASIN list from
  `BookRepo().load_active_books()`, one product page per ASIN.
- `utils/browser.py` fetches each page through a **persisted Playwright
  login session** (`data/browser_state.json`, Amazon-specific) and parses
  price straight from the buybox DOM.
- BSR rank/category is extracted by feeding a ~5 KB HTML fragment to an LLM
  via `scrapegraphai.SmartScraperGraph`, configured by
  `config.build_graph_config()` (`LLM_PROVIDER` = ollama/openai/groq/gemini).
- Storage is SQLite (`config.settings.DB_PATH`) through `*Repo` classes in
  `utils/` (`BookRepo`, `SnapshotRepo`, `Repo_CronRunLog`, …), always called
  directly on an instance (per `CLAUDE.md`).

Crawling a publisher catalog is a different problem: there is no ASIN list to
drive it (the catalog must be *enumerated*), the two sites have unrelated
HTML and category taxonomies, O'Reilly's real catalog sits behind a paid
login, and running an LLM extraction on every product page of a full catalog
is a genuine cost/time concern.

**This issue is intentionally scoped to producing agreed decisions — no code
yet.** Implementation will be split into follow-up issues once the decisions
below (and the manager's answers to the open questions) are settled.

**Scope decisions (to be filled in as they are made)**:

1. **D1 DECIDED (2026-09-04)** — this is a **standalone dataset**, separate
   from the Amazon BSR tracker. It does not feed `tracked_books` or join to
   any existing table; keep a self-contained store + exporter. Details in
   `01-purpose-and-scope.md`.
2. Definitely **not** in this issue: any implementation, BSR/sales-rank
   tracking for publisher titles, price-history charting for them, or any
   integration with the Amazon tracker (ASIN lookup, cross-referencing).

## Decisions to make

Each item links to a detail doc with the concrete options and a
recommendation.

- [x] [1. Purpose & relationship to the existing tracker](./01-purpose-and-scope.md) — **standalone dataset**
- [ ] [2. Catalog scope (which titles, which formats, how deep)](./01-purpose-and-scope.md)
- [ ] [3. Fields & schema (what to capture, dedup key, category handling)](./02-fields-and-schema.md)
- [ ] [4. Extraction method (HTML parse vs site API vs per-page LLM)](./03-extraction-method.md)
- [ ] [5. Access, auth, robots/ToS, affiliate-link handling](./04-access-and-compliance.md)
- [ ] [6. Storage & code layout (table(s), repo class, job vs script)](./05-storage-and-layout.md)
- [ ] [7. Delivery / output format — needs manager input](./06-delivery-and-scheduling.md)
- [ ] [8. Scheduling (one-off vs recurring, full vs incremental)](./06-delivery-and-scheduling.md)

## Open questions for the manager

1. What is the end use of this data, and in what format do you want it
   delivered (CSV/Excel, web page, emailed report, queryable DB, JSON)?
2. Full catalog, or a subset (new releases only / specific topics)?
3. Is there an O'Reilly account we are authorized to use for scraping? If
   not, only the publicly reachable subset is possible.
4. Any fields beyond title / author / category (ISBN, price, publication
   date, format, cover, description)?
5. Run once, or refresh on a schedule?

## Related work considered but out of scope

- Actual scraper implementation — separate follow-up issue(s) per site.
- Looking up ASINs for publisher titles and folding them into the BSR
  tracker — possible D1 outcome, but its own issue if chosen.
- Price-history / charts for publisher titles.

## Manual test

- Not applicable — this issue produces a decision record, not code. It is
  "done" when every decision above is resolved in its detail doc and the
  manager's open questions are answered.

## Verification

- No commands to run. Review is: the manager (or team lead) signs off on the
  decisions captured in the `NN-*.md` docs before any implementation issue is
  opened.
