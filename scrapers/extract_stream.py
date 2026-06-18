#!/usr/bin/env python3
import asyncio
import sys
import argparse
import time
import re
import json
from urllib.parse import urlparse, parse_qs, urljoin
from playwright.async_api import async_playwright

KNOWN_SITES = [
    "https://www.goatsports.xyz",
    "https://mpdwc5.blogspot.com",
    "https://socowc5.blogspot.com",
    "https://cswc5.blogspot.com",
    "https://siiirwc5.blogspot.com",
    "https://youtwc5.blogspot.com",
    "https://livewc5.blogspot.com",
]

SOURCE_PAGES = [
    "https://www.goatsports.xyz/p/why-is-maradonas-goal-called-hand-of.html",
]

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
    path = urlparse(url).path.lower()
    return ".m3u8" in path or ".mpd" in path

async def extract_blogspot_links(page):
    links = []
    try:
        buttons = await page.query_selector_all("button.live-btn")
        for b in buttons:
            onclick = await b.get_attribute("onclick") or ""
            m = re.search(r"href='([^']+)'", onclick)
            if m:
                text = await b.inner_text() or ""
                links.append((m.group(1), text.strip()))
    except Exception:
        pass
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
            if any(k in path for k in ("/p/match", "/match", "/stream", "/live")):
                links.append((href, text))
    except Exception:
        pass
    return links

async def extract_from_page(page, url):
    html = await page.content()
    iframe_src = None
    if 'streamFrame' in html:
        m = re.search(r'id="streamFrame"[^>]*src="([^"]*)"', html)
        if m:
            iframe_src = m.group(1)
            m2 = re.search(r'src="([^"]*)"[^>]*id="streamFrame"', html)
            if m2:
                iframe_src = m2.group(1)
    if not iframe_src and 'streamFrame' in html:
        m = re.search(r'"gm\d+"\s*:\s*"(https?://[^"]+)"', html)
        if m:
            iframe_src = m.group(1)
    if iframe_src and not iframe_src.startswith("http"):
        iframe_src = urljoin(url, iframe_src)
    return iframe_src

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
        matches = await extract_blogspot_links(page)
        if not matches and base_url in SOURCE_PAGES:
            matches = await extract_blogspot_links(page)
        if not matches:
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

        if not stream_url:
            iframe_src = await extract_from_page(page, url)
            if iframe_src:
                try:
                    await page.goto(iframe_src, wait_until="commit", timeout=10000)
                except Exception:
                    pass
                deadline2 = time.time() + min(timeout, 8)
                while time.time() < deadline2 and not stream_url:
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
                src = await page.eval_on_selector_all(
                    "[src]",
                    "els => els.map(e => e.getAttribute('src')).filter(s => s && (s.includes('.m3u8') || s.includes('.mpd')))"
                )
                for s in src:
                    stream_url = s if s.startswith("http") else urljoin(url, s)
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

    if stream_url:
        return stream_url
    if extracted_stream:
        return extracted_stream
    return "ERROR: No stream URL found"

async def auto_extract(base_url, match_desc, timeout=20, proxy=None):
    sys.stderr.write("Discovering match links...\n")
    sys.stderr.flush()
    try:
        matches = await asyncio.wait_for(
            discover_matches(base_url, proxy), timeout=20
        )
    except Exception as e:
        return f"ERROR: Failed to discover matches: {e}"

    if not matches:
        matches = []
        for site in KNOWN_SITES:
            try:
                m = await asyncio.wait_for(discover_matches(site, proxy), timeout=10)
                matches.extend(m)
            except Exception:
                pass

    if not matches:
        return "ERROR: No match links found on any known site"

    sys.stderr.write(f"Found {len(matches)} match links\n")
    sys.stderr.flush()

    if match_desc:
        scored = []
        for url, txt in matches:
            combined = (url + " " + txt).lower().replace("-", " ").replace("_", " ").replace("/", " ")
            words = re.sub(r'[^a-z0-9\s]', ' ', match_desc.lower()).split()
            score = sum(1 for w in words if len(w) > 2 and w in combined)
            scored.append((score, url, txt))
        scored.sort(key=lambda x: -x[0])
        best_score, best_url, best_text = scored[0]
        sys.stderr.write(f"Best match (score {best_score}): {best_text or best_url}\n")
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
    parser.add_argument("url", nargs="?", help="Match page URL or base streaming site URL")
    parser.add_argument("--match", help="Match description for auto-discovery")
    parser.add_argument("--timeout", type=int, default=20, help="Seconds to wait (default: 20)")
    parser.add_argument("--proxy", help="Proxy server (e.g. socks5://127.0.0.1:1080)", default=None)
    parser.add_argument("--list-sites", action="store_true", help="List known scrape sites and exit")
    args = parser.parse_args()

    if args.list_sites:
        for s in KNOWN_SITES + SOURCE_PAGES:
            print(s)
        return

    if not args.url:
        parser.print_help()
        sys.exit(1)

    if args.match:
        result = await auto_extract(args.url, args.match, args.timeout, args.proxy)
    else:
        result = await extract_stream(args.url, args.timeout, args.proxy)
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
