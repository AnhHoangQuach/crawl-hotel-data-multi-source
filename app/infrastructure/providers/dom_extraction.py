import random


async def human_delay(page, min_seconds: float = 1.0, max_seconds: float = 10.0):
    """Pause for a random span after a web action (click/type/navigate).

    A scraper that waits the exact same number of milliseconds after every
    click is itself a detectable pattern -- every real interaction across
    all three providers goes through this instead of a fixed-duration wait.
    """
    await page.wait_for_timeout(random.uniform(min_seconds, max_seconds) * 1000)


async def safe_inner_text(locator):
    try:
        if await locator.count():
            return (await locator.inner_text()).strip()
    except Exception:
        pass
    return None


async def extract_text(page, selector):
    return await safe_inner_text(page.locator(selector).first)


async def extract_all_texts(page, selector):
    out = []
    try:
        loc = page.locator(selector)
        for i in range(await loc.count()):
            text = await safe_inner_text(loc.nth(i))
            if text is not None:
                out.append(text)
    except Exception:
        pass
    return out


def first_working_selector(selector_candidates):
    """Join a list of candidate CSS selectors into one Playwright selector
    that matches whichever candidate is present (`,` is "or" in CSS).

    Used for sites where the real selector can't be confirmed ahead of time
    (e.g. unverified TripAdvisor markup) -- callers list every plausible
    selector and this tries them all at once instead of picking one blindly.
    """
    return ", ".join(selector_candidates)
