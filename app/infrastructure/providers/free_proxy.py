import asyncio
import random
import re

import httpx

FREE_PROXY_SOURCES = [
    "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/protocols/http.txt",
    "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/protocols/https.txt",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=5000&country=all&ssl=all&anonymity=all",
]
# Must be https:// -- Traveloka is HTTPS-only, and a lot of free "http"
# proxies forward plain HTTP fine but don't support CONNECT tunneling for
# HTTPS at all (they'd pass a plain-HTTP check yet still fail every real
# request with ERR_TUNNEL_CONNECTION_FAILED).
PROXY_TEST_URL = "https://httpbin.org/ip"
PROXY_IP_PORT_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}:\d{2,5}$")


async def _fetch_source(client, src):
    try:
        resp = await client.get(src, timeout=10)
        return resp.text
    except Exception:
        return ""


async def fetch_candidate_proxies(limit=120):
    candidates = []
    async with httpx.AsyncClient() as client:
        texts = await asyncio.gather(*(_fetch_source(client, src) for src in FREE_PROXY_SOURCES))

    for text in texts:
        for line in text.splitlines():
            line = line.strip()
            if PROXY_IP_PORT_RE.match(line):
                candidates.append(line)

    # de-duplicate while preserving order
    seen = set()
    unique = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique[:limit]


async def validate_proxy(proxy, timeout=6.0):
    try:
        async with httpx.AsyncClient(proxy=f"http://{proxy}", timeout=timeout) as client:
            resp = await client.get(PROXY_TEST_URL)
            return resp.status_code == 200
    except Exception:
        return False


async def get_working_proxies(max_count=6, pool_size=120, concurrency=40):
    candidates = await fetch_candidate_proxies(pool_size)
    if not candidates:
        return []
    random.shuffle(candidates)

    sem = asyncio.Semaphore(concurrency)
    working = []
    stop = asyncio.Event()

    async def worker(proxy):
        if stop.is_set():
            return
        async with sem:
            if stop.is_set():
                return
            if await validate_proxy(proxy):
                working.append(proxy)
                if len(working) >= max_count:
                    stop.set()

    await asyncio.gather(*(worker(p) for p in candidates), return_exceptions=True)
    return working[:max_count]
