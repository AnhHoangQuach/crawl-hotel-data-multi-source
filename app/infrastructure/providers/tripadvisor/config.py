import re

HOMEPAGE_URL = "https://www.tripadvisor.com/"

# --- IMPORTANT: selectors below are best-effort, UNVERIFIED guesses -------
# Every attempt to load tripadvisor.com while building this (direct, via
# headless/non-headless Playwright, and via 10 free proxies) was blocked by
# a DataDome CAPTCHA wall before any real page ever rendered, so none of
# these could be checked against the live DOM. Each field lists several
# plausible selectors (joined with CSS's "," == "or") instead of one single
# guess, so a fix is "add/replace an entry in this list" rather than a
# scraper-logic change. Re-verify all of these against real page HTML before
# relying on this provider's output.
#
# The one part of this file that *is* reliable: TripAdvisor's hotel detail
# URLs have followed the stable, long-standing pattern
# `/Hotel_Review-g<geoId>-d<hotelId>-Reviews-...html` for over a decade --
# that's a URL/routing convention, not a CSS class, so it doesn't rot the
# way hashed class names do. The flow below leans on it wherever possible.

HOTEL_REVIEW_URL_RE = re.compile(r"/Hotel_Review-g(\d+)-d(\d+)-")

COOKIE_ACCEPT_SELECTOR = (
    "#onetrust-accept-btn-handler, button[id*='accept' i], button[class*='cookie' i]"
)

SEARCH_INPUT_SELECTOR = (
    "#mainSearch, input[data-test-target='search-input'], "
    "input[placeholder*='places to go' i], input[placeholder*='search' i]"
)
SEARCH_SUBMIT_SELECTOR = (
    "button[data-test-target='search-submit'], #SUBMIT_HOTELS, button[type='submit']"
)

# Autocomplete suggestion rows. Restricted to ones whose own link already
# points at a hotel page, same purpose as the old RapidAPI provider's
# `place_type == "HOTEL"` filter -- keeps city/attraction suggestions out of
# the fuzzy-match candidate pool.
SUGGESTION_ITEM_SELECTOR = (
    "div[data-test-target='autosuggest-result'], li[data-test-target='autosuggest-result'], "
    "[class*='autosuggest' i] a"
)

# Hotel result cards on a search/listing page, after submitting the search.
HOTEL_CARD_LINK_SELECTOR = "a[href*='/Hotel_Review-']"
HOTEL_CARD_NAME_SELECTOR = "div[data-automation*='hotel' i] [class*='name' i], a[href*='/Hotel_Review-']"
HOTEL_CARD_LOCATION_SELECTOR = "div[data-automation*='hotel' i] [class*='location' i]"

# Detail page fallbacks for fields not present in the page's JSON-LD (see
# extraction.extract_json_ld) -- JSON-LD is preferred wherever available
# since it's schema.org-shaped structured data TripAdvisor exposes for
# Google's hotel rich results, and is much slower-changing than CSS classes.
DETAIL_NAME_SELECTOR = "h1#HEADING, h1"
DETAIL_TYPE_SELECTOR = "[data-automation*='poiType' i], [class*='hotelClass' i]"
DETAIL_STAR_RATING_SELECTOR = "svg[class*='star' i] title, [aria-label*='star' i]"
DETAIL_RATING_SUMMARY_SELECTOR = "[data-automation*='rating' i], [class*='reviewCount' i]"
DETAIL_ADDRESS_SELECTOR = "[data-automation*='address' i], span[class*='address' i]"
DETAIL_DESCRIPTION_SELECTOR = "div[data-automation*='aboutTab' i], div[class*='about' i]"
DETAIL_AMENITIES_SELECTOR = "div[data-automation*='amenit' i] [class*='amenity' i], div[class*='amenit' i]"

REVIEW_TEXT_SELECTOR = "[data-automation*='reviewText' i] span, q[class*='review' i]"
MAX_REVIEW_BLOCKS = 30

# Photo CDN domain pattern is far more stable than any CSS class -- TripAdvisor
# serves all gallery/listing photos from this media subdomain regardless of
# the surrounding page markup.
PHOTO_CDN_HOSTS = ("media-cdn.tripadvisor.com", "dynamic-media-cdn.tripadvisor.com")
MAX_PHOTOS = 30
