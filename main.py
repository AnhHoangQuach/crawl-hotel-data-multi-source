import asyncio
import random
import sys

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, ProxyConfig

from traveloka.config import HOMEPAGE_URL
from traveloka.csv_io import read_hotels_csv, write_results_json
from traveloka.proxy import get_working_proxies
from traveloka.scraper import HotelScraper, empty_result

DEFAULT_INPUT_CSV = "hotels.csv"
DEFAULT_OUTPUT_JSON = "hotels_result.json"


async def crawl_all(hotels, proxy_configs):
    browser_cfg = BrowserConfig(headless=True, viewport_width=1400, viewport_height=900)
    run_cfg = CrawlerRunConfig(
        proxy_config=proxy_configs if proxy_configs else None,
        # The proxy list already ends with a "direct" fallback entry, so one
        # pass through it is enough -- max_retries would multiply the whole
        # list (very slow once most free proxies are dead).
        max_retries=0,
        wait_until="domcontentloaded",
        page_timeout=60000,
    )

    scraper = HotelScraper()
    results = []

    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        crawler.crawler_strategy.set_hook("after_goto", scraper.after_goto_hook)

        for name, address in hotels:
            print(f"Dang crawl: {name} ({address or 'khong ro dia chi'})...")
            scraper.target_name = name
            scraper.target_address = address
            scraper.result = None

            try:
                await crawler.arun(url=HOMEPAGE_URL, config=run_cfg)
            except Exception as e:
                data = empty_result(name, address)
                data["error"] = str(e)
                results.append(data)
                print(f"  -> FAIL: {e}")
                continue

            data = scraper.result or empty_result(name, address)
            if not data.get("name"):
                print("  -> Khong lay duoc, thu lai 1 lan...")
                scraper.result = None
                try:
                    await crawler.arun(url=HOMEPAGE_URL, config=run_cfg)
                    data = scraper.result or data
                except Exception as e:
                    data["error"] = data.get("error") or str(e)

            if data.get("name"):
                status = "OK"
            elif data.get("low_confidence"):
                status = "SKIP"
            else:
                status = "FAIL"
            label = data.get("name") or data.get("error")
            match_score = data.get("match_score")
            print(f"  -> {status}: {label} (match_score={match_score})")
            results.append(data)

            await asyncio.sleep(random.uniform(3, 6))

    return results


async def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_INPUT_CSV
    try:
        hotels = read_hotels_csv(csv_path)
    except FileNotFoundError:
        print(f"Khong tim thay file CSV: {csv_path}")
        print("Dinh dang CSV can co cot 'name' (ten khach san) va 'address' (dia chi).")
        return
    except ValueError as e:
        print(str(e))
        return

    if not hotels:
        print("CSV khong co khach san nao de crawl.")
        return

    print("Dang tim proxy free cong khai de du phong...")
    proxies = await get_working_proxies()
    if proxies:
        print(f"Tim duoc {len(proxies)} proxy con song.")
        # Try direct first: a human-like search flow (see traveloka/scraper.py)
        # has proven far more reliable than free proxies, which often "work"
        # at the network level (HTTP 200) but render too slowly/incompletely
        # for the page's JS to finish hydrating. Proxies are kept only as a
        # fallback for the case where Traveloka does serve a real block page.
        proxy_configs = ["direct"] + [ProxyConfig(server=f"http://{p}") for p in proxies]
    else:
        print("Khong co proxy free nao con song luc nay, se chay truc tiep.")
        proxy_configs = None

    results = await crawl_all(hotels, proxy_configs)

    write_results_json(results, DEFAULT_OUTPUT_JSON)

    ok = sum(1 for r in results if r.get("name"))
    print(f"\nHoan tat: {ok}/{len(results)} khach san lay duoc du lieu.")
    print(f"Da luu vao {DEFAULT_OUTPUT_JSON}")


if __name__ == "__main__":
    asyncio.run(main())
