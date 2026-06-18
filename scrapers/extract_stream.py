#!/usr/bin/env python3
import asyncio
import sys
import argparse
import time
import re
from urllib.parse import urlparse, parse_qs
from playwright.async_api import async_playwright


def is_player_wrapper(url):
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    for key in ("id", "url", "src", "source", "u", "data", "file"):
        if key in params and params[key]:
            val = params[key][0]
            if ".m3u8" in val or ".mpd" in val:
                return True, val
    return False, None


def is_direct_stream(url):
    parsed = urlparse(url)
    path = parsed.path.lower()
    if ".m3u8" in path or ".mpd" in path:
        return True
    return False


def match_score(match_desc, url, link_text):
    combined = (url + " " + link_text).lower()
    combined = combined.replace("-", " ").replace("_", " ").replace("/", " ")
    words = re.sub(r'[^a-z0-9\s]', ' ', match_desc.lower()).split()
    score = sum(1 for w in words if w in combined and len(w) > 2)
    return score


async def discover_matches(base_url, proxy=None):
    matches = []
    async with async_playwright() as p:
        launch_opts = {"headless": True}
        if proxy:
            launch_opts["proxy"] = {"server": proxy}
        browser = await p.chromium.launch(**launch_opts)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        try:
            await page.goto(base_url, wait_until="domcontentloaded", timeout=15000)
        except Exception:
            pass
        await page.wait_for_timeout(3000)
        try:
            all_links = await page.eval_on_selector_all(
                "a",
                "els => els.map(e => ({href: e.href, text: e.textContent.trim()})).filter(e => e.href.startsWith('http'))"
            )
            seen = set()
            for link in all_links:
                href = link["href"]
                text = link["text"]
                if href in seen:
                    continue
                seen.add(href)
                path = urlparse(href).path.lower()
                if any(k in path for k in ("/2026/", "/match", "/stream", "/live")):
                    matches.append((href, text))
        except Exception:
            pass
        await browser.close()
    return matches


async def extract_stream(url, timeout=15, proxy=None):
    stream_url = None
    player_wrapper_url = None
    extracted_stream = None

    async with async_playwright() as p:
        launch_opts = {"headless": True}
        if proxy:
            launch_opts["proxy"] = {"server": proxy}

        browser = await p.chromium.launch(**launch_opts)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        async def on_response(response):
            nonlocal stream_url, player_wrapper_url, extracted_stream
            if stream_url:
                return
            u = response.url
            if is_direct_stream(u):
                stream_url = u
                return
            is_wrapper, extracted = is_player_wrapper(u)
            if is_wrapper and not player_wrapper_url:
                player_wrapper_url = u
                extracted_stream = extracted

        page.on("response", on_response)

        try:
            await page.goto(url, wait_until="commit", timeout=10000)
        except Exception:
            pass

        deadline = time.time() + timeout
        while time.time() < deadline and not stream_url and not player_wrapper_url:
            await asyncio.sleep(1)

        if not stream_url and player_wrapper_url:
            try:
                await page.goto(player_wrapper_url, wait_until="domcontentloaded",
                                timeout=min(timeout, 10) * 1000)
            except Exception:
                pass
            deadline2 = time.time() + min(timeout, 8)
            while time.time() < deadline2 and not stream_url:
                await asyncio.sleep(1)

        if not stream_url and extracted_stream:
            stream_url = extracted_stream

        if not stream_url:
            try:
                src = await page.eval_on_selector_all(
                    "video, source",
                    "els => els.map(e => e.src || e.getAttribute('src')).filter(Boolean)"
                )
                for s in src:
                    if s and (".m3u8" in s or ".mpd" in s):
                        stream_url = s
                        break
            except Exception:
                pass

        if not stream_url:
            try:
                iframes = await page.query_selector_all("iframe")
                for iframe in iframes:
                    src = await iframe.get_attribute("src")
                    if src and src.startswith("http"):
                        result = await extract_stream(src, timeout=min(timeout, 8))
                        if result and not result.startswith("ERROR"):
                            stream_url = result
                            break
            except Exception:
                pass

        try:
            await browser.close()
        except Exception:
            pass

    return stream_url or "ERROR: No stream URL found"


async def auto_extract(base_url, match_desc, timeout=20, proxy=None):
    sys.stderr.write("Discovering match links...\n")
    sys.stderr.flush()
    try:
        matches = await asyncio.wait_for(
            discover_matches(base_url, proxy), timeout=20
        )
    except Exception:
        return "ERROR: Failed to discover matches"

    if not matches:
        return "ERROR: No match links found on page"

    sys.stderr.write(f"Found {len(matches)} match links\n")
    sys.stderr.flush()

    if match_desc:
        scored = [(match_score(match_desc, url, txt), url, txt) for url, txt in matches]
        scored.sort(key=lambda x: -x[0])
        best_score, best_url, best_text = scored[0]
        sys.stderr.write(f"Best match ({best_score}): {best_text or best_url}\n")
        sys.stderr.flush()
        return await extract_stream(best_url, timeout, proxy)
    else:
        for url, txt in matches:
            result = await extract_stream(url, timeout, proxy)
            if result and not result.startswith("ERROR"):
                return result
        return "ERROR: No working stream found on any match link"


async def main():
    parser = argparse.ArgumentParser(description="Extract HLS stream URL from sports streaming sites")
    parser.add_argument("url", help="Match page URL or base streaming site URL")
    parser.add_argument("--match", help="Match description for auto-discovery")
    parser.add_argument("--timeout", type=int, default=15, help="Seconds to wait (default: 15)")
    parser.add_argument("--proxy", help="Proxy server (e.g. socks5://127.0.0.1:1080)", default=None)
    args = parser.parse_args()

    if args.match:
        result = await auto_extract(args.url, args.match, args.timeout, args.proxy)
    else:
        result = await extract_stream(args.url, args.timeout, args.proxy)
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
