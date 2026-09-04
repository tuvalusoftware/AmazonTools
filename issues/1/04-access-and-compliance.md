# 5. Access, auth, compliance, affiliate links

## O'Reilly access
- Full O'Reilly catalog requires a **paid learning subscription** login.
- Decision needed (open question 3): do we have an account we are
  **authorized** to use for automated scraping?
  - If **yes** — get written OK from the manager, store creds via
    pydantic-settings like `AMAZON_EMAIL` / `AMAZON_PASSWORD`, use a
    dedicated persisted session file (not the Amazon one).
  - If **no** — O'Reilly scope drops to the public subset (see
    `01-purpose-and-scope.md` D2 option a), or O'Reilly is deferred.
- **Recommendation:** do not build against an authenticated O'Reilly session
  unless the manager explicitly authorizes a specific account.

## Manning access
- Appears fully public — confirm no login is needed for catalog + product
  pages.

## robots.txt / ToS / rate limits
- Check `manning.com/robots.txt` and `oreilly.com/robots.txt` before
  implementing; honor `Disallow` and any `Crawl-delay`.
- Decision: are we comfortable proceeding given each site's Terms of
  Service? Flag to the manager that this is publisher-site scraping, not a
  public API.
- Agree a politeness delay (≥ 2 s/request suggested) and a single-threaded
  crawl.

## Affiliate link handling
- The manager's Manning link carries affiliate / `utm_source` params.
- Decision: when we store `product_url`, do we
  - (a) store the **clean canonical URL**, or
  - (b) append the affiliate tag so links in any delivered report are
    monetized?
- **Recommendation:** store the clean canonical URL in the DB; if a
  delivered report needs affiliate links, add the tag at export time from a
  configurable `MANNING_AFFILIATE_PARAMS` setting. Keeps stored data clean
  and the affiliate scheme swappable.

## PII
- None expected (author names are public bibliographic data), but do not
  scrape user reviews / reviewer names.
