"""
Helper_Lookup_Asin — LLM vision helpers for the ASIN-lookup pipeline.

Contains:
- Raw LLM API calls (Gemini / OpenAI)
- Vision helpers: best-match card selection, swatch-state check, ASIN-from-URL
"""

from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Any

from config import settings
from utils.logger import get_logger

log = get_logger(__name__)


# --------------------------------------------------------------------------- #
# LLM raw calls                                                                #
# --------------------------------------------------------------------------- #

def ask_gemini_raw(prompt: str, images_b64: list[str]) -> str:
    import google.generativeai as genai  # type: ignore

    genai.configure(api_key=settings.GOOGLE_API_KEY)

    raw_model = settings.GEMINI_MODEL
    model_name = raw_model.split("/", 1)[-1] if "/" in raw_model else raw_model
    model = genai.GenerativeModel(model_name)

    parts: list[Any] = [prompt]
    for b64 in images_b64:
        if b64:
            parts.append({"mime_type": "image/png", "data": b64})

    return model.generate_content(parts).text.strip()


def ask_openai_raw(prompt: str, images_b64: list[str]) -> str:
    from openai import OpenAI  # type: ignore

    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    content: list[Any] = [{"type": "text", "text": prompt}]
    for b64 in images_b64:
        if b64:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            })

    resp = client.chat.completions.create(
        model=settings.OPENAI_MODEL.split("/", 1)[-1],
        messages=[{"role": "user", "content": content}],
        max_tokens=10,
    )
    return resp.choices[0].message.content or ""


# --------------------------------------------------------------------------- #
# LLM vision helpers                                                           #
# --------------------------------------------------------------------------- #

def parse_llm_choice(raw: str, n_images: int) -> int:
    """Parse the LLM's card-number reply into a 0-based index.

    Returns
    -------
    int
        0-based index of the chosen card, or -1 when the LLM replied "0"
        (no match) or when the response contains no digit at all.
    """
    log.info("LLM vision response: %r", raw)
    m = re.search(r"\d+", raw)
    if not m:
        return -1
    card_number = int(m.group())
    if card_number == 0:
        return -1
    idx = card_number - 1
    return max(0, min(idx, n_images - 1))


def ask_llm_best_match(title: str, screenshots: list[Path]) -> int:
    """Send *screenshots* to the configured vision LLM and return the 0-based
    index of the card that best matches *title*.

    Returns
    -------
    int
        0-based index of the best-matching card, or -1 when the LLM says
        none of the cards match (or on any API/parse error).
    """
    provider = settings.LLM_PROVIDER.lower()

    images_b64: list[str] = []
    for p in screenshots:
        try:
            images_b64.append(base64.b64encode(p.read_bytes()).decode())
        except Exception as exc:
            log.warning("Could not read screenshot %s: %s", p, exc)
            images_b64.append("")

    prompt = (
        f"I searched Amazon for the book titled: \"{title}\"\n\n"
        f"Below are {len(screenshots)} search result cards (numbered 1–{len(screenshots)}).\n"
        "Each image shows one result card from the Amazon search results page.\n\n"
        "Which card number (1–" + str(len(screenshots)) + ") best matches the book I searched for?\n"
        "Consider the title, author, and cover image.\n"
        "If NONE of the cards match the book, reply with 0.\n"
        "Reply with ONLY a single integer (0 means no match), nothing else."
    )

    try:
        if provider == "gemini":
            return parse_llm_choice(ask_gemini_raw(prompt, images_b64), len(images_b64))
        elif provider == "openai":
            return parse_llm_choice(ask_openai_raw(prompt, images_b64), len(images_b64))
        else:
            log.warning(
                "LLM provider %r does not support vision in this helper — "
                "falling back to first candidate",
                provider,
            )
            return 0
    except Exception as exc:
        log.warning("LLM vision call failed (%s) — falling back to first candidate", exc)
        return 0


def ask_llm_first_item_selected(swatch_screenshot: Path) -> bool:
    """Ask the vision LLM whether the first item in the #tmmSwatchesList
    fragment is currently selected/active.

    Returns True when the LLM confirms it is selected, False otherwise
    (including on any API/parse error — caller will click to be safe).
    """
    try:
        b64 = base64.b64encode(swatch_screenshot.read_bytes()).decode()
    except Exception as exc:
        log.warning("Could not read swatch screenshot %s: %s", swatch_screenshot, exc)
        return False

    prompt = (
        "This image shows a list of Amazon book format/edition options "
        "(e.g. Kindle, Hardcover, Paperback, Audible).\n\n"
        "Is the FIRST item in the list currently selected or active? "
        "A selected item is typically highlighted, bolded, has a border, "
        "or is visually distinct from the others.\n\n"
        "Reply with ONLY 'YES' or 'NO', nothing else."
    )
    images_b64 = [b64]
    provider = settings.LLM_PROVIDER.lower()

    try:
        if provider == "gemini":
            raw = ask_gemini_raw(prompt, images_b64)
        elif provider == "openai":
            raw = ask_openai_raw(prompt, images_b64)
        else:
            log.warning(
                "LLM provider %r does not support vision — assuming first item NOT selected",
                provider,
            )
            return False
    except Exception as exc:
        log.warning("LLM swatch check failed (%s) — assuming first item NOT selected", exc)
        return False

    log.info("LLM swatch-selected response: %r", raw)
    return raw.strip().upper().startswith("YES")


def ask_llm_asin_from_url(url: str) -> str:
    """Ask the LLM to extract the ASIN from an Amazon product URL.

    Returns the 10-character ASIN string, or an empty string on failure.
    As a fast-path, a regex match on the /dp/ segment is tried first; the
    LLM is only called when the regex produces no result.
    """
    m = re.search(r"/dp/([A-Z0-9]{10})", url)
    if m:
        asin = m.group(1)
        log.info("lookup_asin: extracted ASIN %s from URL via regex", asin)
        return asin

    prompt = (
        f"The following is an Amazon product page URL:\n{url}\n\n"
        "Extract the ASIN (Amazon Standard Identification Number) from the URL.\n"
        "The ASIN is a 10-character alphanumeric code, usually found after '/dp/' in the path.\n"
        "Reply with ONLY the 10-character ASIN, nothing else. "
        "If you cannot find it, reply with an empty string."
    )
    provider = settings.LLM_PROVIDER.lower()
    try:
        if provider == "gemini":
            raw = ask_gemini_raw(prompt, [])
        elif provider == "openai":
            raw = ask_openai_raw(prompt, [])
        else:
            log.warning("LLM provider %r not supported for ASIN extraction", provider)
            return ""
    except Exception as exc:
        log.warning("LLM ASIN-from-URL call failed (%s)", exc)
        return ""

    log.info("LLM ASIN-from-URL response: %r (url=%s)", raw, url)
    candidate = raw.strip().upper()
    if re.fullmatch(r"[A-Z0-9]{10}", candidate):
        return candidate
    log.warning("lookup_asin: LLM returned invalid ASIN %r from URL %s", raw, url)
    return ""


