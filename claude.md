# Project conventions for Claude

## Python — repository / service classes

- **Always call class methods directly** on an instance of the class (e.g. `BookRepo().load_active_books()`).
- Do **not** wrap class methods in module-level helper functions just to shorten the call site.
- If a caller needs a shared instance, let it create and hold its own (or receive one via dependency injection) — do not create a module-level singleton in the library module.
