import re

HOMEPAGE_URL = "https://www.traveloka.com/en-vn"

ACCOM_TYPE_PICKER_SELECTOR = "[data-testid='accom-type-picker']"
SEARCH_INPUT_SELECTOR = "input[placeholder='City, hotel, place to go']"
SUGGESTION_ITEM_SELECTOR = "[data-testid^='accom_autocomplete_item_']"
SEARCH_SUBMIT_SELECTOR = "[data-testid='search-submit-button']"
HOTEL_CARD_NAME_SELECTOR = "[data-testid='tvat-hotelName']"
HOTEL_CARD_LOCATION_SELECTOR = "[data-testid='tvat-hotelLocation']"

DISPLAY_NAME_SELECTOR = "[data-testid='display_name_label']"
ACCOM_TYPE_SELECTOR = "[data-testid='header_accom_type']"
STAR_RATING_SELECTOR = "[data-testid='header_star_rating']"
REVIEW_RATING_SELECTOR = "[data-testid='review-rating']"
ADDRESS_SELECTOR = "[data-testid='summary-location']"
AMENITIES_SELECTOR = "[data-testid='summary-facility']"
FACILITIES_SELECTOR = "[data-testid='section-facility']"
DESCRIPTION_SELECTOR = "[data-testid='about-content']"

BIG_THUMBNAIL_SELECTOR = "[data-testid='hotel_detail_imgBigThumbnail']"
SEE_MORE_PHOTOS_SELECTOR = "[data-testid='hotel_detail_imgSeeMore_5']"
PHOTO_LIGHTBOX_SELECTOR = "[data-testid='accom_photo_lightbox']"
PHOTO_LIGHTBOX_CLOSE_SELECTOR = "[data-testid='photo_tab_close_button']"
GALLERY_FALLBACK_SELECTOR = (
    "[data-testid='section-photo-gallery'] img, [data-testid='overview-gallery'] img"
)

REVIEW_TAB_LINK_SELECTOR = "[data-testid='link-REVIEW']"
REVIEW_LIST_CONTAINER_SELECTOR = "[data-testid='review-list-container']"
REVIEW_NEXT_PAGE_SELECTOR = "[data-testid='next-page-btn']"

ROOM_CARD_SELECTOR = "[data-testid='room_inventory_card']"
ROOM_NAME_SELECTOR = "[data-testid='room_inventory_name']"
ROOM_BED_TYPE_SELECTOR = "[data-testid='room_inventory_bed_type']"
ROOM_BREAKFAST_SELECTOR = "[data-testid='room_inventory_breakfast']"
ROOM_PRICE_SUMMARY_SELECTOR = "[data-testid='room_inventory_price_summary']"
ROOM_NUM_LEFT_SELECTOR = "[data-testid='room_inventory_room_num']"
ROOM_CANCELLATION_SELECTOR = "[data-testid='text_cancellation_policy']"

LATLNG_RE = re.compile(
    r'"latitude"\s*:\s*"?(-?\d+\.\d+)"?[^}]{0,80}"longitude"\s*:\s*"?(-?\d+\.\d+)"?'
)

MAX_REVIEW_PAGES = 5
MAX_PHOTOS = 60
MAX_ROOMS = 20

# Below this, the picked hotel card is probably wrong -- either Traveloka's
# autocomplete ranking went off into an unrelated city/country, or the only
# "best" candidate just happens to share a generic location with the query
# (e.g. "Soul Boutique Hotel Phu Quoc" scored 0.46 against query "THE SEA
# PHU QUOC" / "Kien Giang" purely on shared province text). Empirically,
# correct matches in testing scored 0.67-0.74; wrong ones scored 0.28-0.46 --
# 0.5 sits in the gap. The result is still returned but flagged so it isn't
# mistaken for a real match.
MATCH_SCORE_THRESHOLD = 0.5
