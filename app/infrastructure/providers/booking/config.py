import re

HOMEPAGE_URL = "https://www.booking.com/"

# --- Unlike TripAdvisor, every selector below was verified against real,
# organically-fetched page HTML while building this (search -> results ->
# detail). Booking.com's anti-bot is an AWS WAF JS challenge, not an
# interactive CAPTCHA -- it resolves automatically in a real/headless
# browser, so the live DOM was actually reachable for inspection.

SEARCH_INPUT_SELECTOR = "input[name='ss']"
SUGGESTION_ITEM_SELECTOR = "li[id^='autocomplete-result-']"
SUGGESTION_HOTEL_ICON_SELECTOR = "[data-testid='autocomplete-icon-hotel']"
SEARCH_SUBMIT_SELECTOR = "button[type='submit']"

# Selecting a suggestion (even a hotel-type one) and submitting always lands
# on an intermediate city/listing page first, never straight on the
# property's own page -- confirmed directly, so the flow always needs this
# second card-matching stage.
#
# Booking.com serves (at least) two different listing templates depending on
# how the search resolved -- confirmed by hitting both in testing -- with
# different card markup AND different navigation behavior: the "titleLink"
# template navigates the current tab, while "title-link" opens the property
# in a new tab (target="_blank"). The scraper has to handle both.
HOTEL_CARD_LINK_SELECTOR = "a[data-testid='titleLink'], a[data-testid='title-link']"
HOTEL_DETAIL_URL_RE = re.compile(r"/hotel/[a-z]{2}/")

# Detail page. JSON-LD (extraction.extract_json_ld) covers name/address/
# description/rating/a hero image -- these are CSS fallbacks for fields it
# doesn't carry, or extra data it doesn't have at all (coordinates, full
# amenities list).
DETAIL_NAME_SELECTOR = "h2.pp-header__title, #hp_hotel_name"
DETAIL_ADDRESS_SELECTOR = "[data-testid='PropertyHeaderAddressDesktop-wrapper']"
DETAIL_DESCRIPTION_SELECTOR = "[data-testid='property-description']"
ACCOMMODATION_TYPE_SELECTOR = "[data-testid='breadcrumb-current']"
AMENITIES_SELECTOR = "[data-testid='property-most-popular-facilities-wrapper']"
FACILITIES_SELECTOR = "[data-testid='property-facilities-block-container']"
REVIEW_TEXT_SELECTOR = "[data-testid='featuredreview-text'], [data-testid='featuredreviewcard-text']"
# Verified real attribute carrying "lat,lng" -- not in the JSON-LD block.
COORDS_ATTR_SELECTOR = "[data-atlas-latlng]"

# "bstatic.com" alone also matches UI assets (flag icons, design assets),
# not just hotel photos (confirmed while building this) -- require the
# actual hotel-image path prefix too.
PHOTO_CDN_HOSTS = ("bstatic.com",)
PHOTO_PATH_HINT = "/images/hotel/"
MAX_PHOTOS = 30
MAX_REVIEWS = 20

# NOTE: room/price data ("rooms" on HotelResult) requires picking checkin/
# checkout dates through the page's own date-picker widget. Verified that
# passing ?checkin=...&checkout=... in the URL does NOT trigger it, and
# clicking through the picker's day cells didn't reliably either. Left as
# an empty list -- same as the old RapidAPI provider left it "minimal
# pending confirmation" -- a scoped follow-up, not a regression.
