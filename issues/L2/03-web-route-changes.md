# 3. Route changes — `/register` and `/pending`

> Parent overview: [Issue 2 — Async register flow](./main.md)

## What was done

### `POST /register` in `web/app.py`

Signature now injects `BackgroundTasks`:

```python
@app.post("/register", response_class=HTMLResponse)
async def register(
    request: Request,
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    title: str = Form(...),
    profit_pct: str = Form(...),
    current_price: str = Form(...),
):
```

After validation passes, the route enqueues the service and returns
`pending.html` immediately (< 1 s):

```python
background_tasks.add_task(
    RegisterService(email.strip(), title.strip(), profit_val, price_val).run
)
return _render(request, "pending.html")
```

Removed from the route: `asyncio.to_thread(search_asin, ...)`,
`repo.register_book(...)`, duplicate-check branch, `RedirectResponse`.

### New template — `web/templates/pending.html`

Amber/spinner page styled with Tailwind CDN, same layout as `registered.html`.
No template variables — always renders identically.

Key UI copy:
- Heading: "We've received your request"
- Body: lookup in progress, confirmation email coming within a minute.
- CTA: "Register another book" → `/`

### `GET /registered` — kept unchanged

Renders `registered.html` with `?title=` query param. No longer reached by the
normal form flow, but kept for backward compatibility (bookmarks, potential
future email links).
