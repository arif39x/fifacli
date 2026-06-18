```
______   __     ______   ______     ______     __         __    
/\  ___\ /\ \   /\  ___\ /\  __ \   /\  ___\   /\ \       /\ \   
\ \  __\ \ \ \  \ \  __\ \ \  __ \  \ \ \____  \ \ \____  \ \ \  
\ \_\    \ \_\  \ \_\    \ \_\ \_\  \ \_____\  \ \_____\  \ \_\ 
 \/_/     \/_/   \/_/     \/_/\/_/   \/_____/   \/_____/   \/_/ 
                                                                
```

# fifacli — 2026 FIFA World Cup CLI Streamer

Watch World Cup matches from your terminal. Automatically discovers free streams and launches `mpv` — no browser needed.

## Features

- Auto-detects the current live match from the schedule
- Scrapes streaming sites with a headless browser to find the `.m3u8` URL
- Falls back to official free broadcasters (CazeTV, BFM, ZDF, RTVE)
- Proxy support for geo-unblocking

## Dependencies

### Required

| Tool | Purpose |
|---|---|
| **mpv** | Video player |
| **fzf** | Fuzzy-finder menu |
| **yt-dlp** | Stream extraction for official channels |

```bash
# Linux (Arch)
sudo pacman -S mpv fzf yt-dlp

# Linux (Debian/Ubuntu)
sudo apt install mpv fzf yt-dlp

# macOS (Homebrew)
brew install mpv fzf yt-dlp

# Windows (scoop)
scoop install mpv fzf yt-dlp
```

### Optional

| Tool | Purpose |
|---|---|
| **streamlink** | Fallback stream extractor |
| **Python 3.14+** | Required for the auto-scraper |
| **Playwright** | Headless browser engine (installed automatically) |

## Installation

### Linux / macOS

```bash
# Clone the repo
git clone https://github.com/yourusername/wc-cli.git
cd wc-cli

# Make it executable
chmod +x fifacli

# Set up the Python scraper (one-time)
python3 -m venv scrapers/venv
scrapers/venv/bin/pip install playwright
scrapers/venv/bin/playwright install chromium

# Run it
./fifacli
```

### Windows (PowerShell)

```powershell
# Clone the repo
git clone https://github.com/yourusername/wc-cli.git
cd wc-cli

# Set up the Python scraper (one-time)
python -m venv scrapers\venv
scrapers\venv\Scripts\pip install playwright
scrapers\venv\Scripts\playwright install chromium

# Run it with Git Bash or WSL
.\fifacli
```

> **Note:** On Windows, run from Git Bash, WSL, or Cygwin — Bash is required.

## Usage

```bash
./fifacli
```

### Menu

1. Select a channel:
   - **Português (CazeTV)** — YouTube live
   - **Français (BFM)** — French stream
   - **Deutsch (ZDF)** — German stream
   - **Español (RTVE)** — Spanish stream
   - **Stream (scrape)** — Auto-discover from trickscorner (see below)
2. The match plays in `mpv`
3. Press Enter to return to the menu

### Auto-scrape mode

Select **Stream (scrape)** and it will:

1. Detect the current live match from the built-in schedule
2. Visit `trickscorner.xyz` with a headless Chromium
3. Scrape all match links from the page
4. Match the live match name against the links (fuzzy)
5. Follow the player redirect chain
6. Extract the raw `.m3u8` CDN URL
7. Play it in `mpv`

If no match is live, it prompts for a match name manually.

### Proxy / VPN

Set a proxy in `~/.config/wc-cli/config`:

```
HTTP_PROXY=socks5://127.0.0.1:1080
```

### Change the streaming site

Edit `~/.config/wc-cli/config`:

```
SCRAPE_BASE_URL=https://www.trickscorner.xyz
```

## How it works

```
┌──────────┐     ┌──────────────────┐     ┌─────────────────┐     ┌─────┐
│  fifacli │───▶ │  Playwright      │───▶ │  Streaming CDN │────▶│ mpv │
│  (bash)  │     │  headless Chrome │     │  .m3u8 stream   │     │     │
└──────────┘     └──────────────────┘     └─────────────────┘     └─────┘
       │                    │
       │ find_matches()     │ discover_matches()
       │ from schedule      │ + extract_stream()
       ▼                    ▼
  "Portugal vs          trickscorner.xyz
   Congo DR"            → /2026/06/...portugal-vs-dr-congo.html
                        → playerdpku.blogspot.com?id=...
                        → cloudfront.net/...chunklist.m3u8
```

The scraper uses Playwright (headless Chromium) to:

1. **Discover** — visit the base URL, find all match links
2. **Match** — fuzzy-match the schedule entry to the correct link
3. **Extract** — intercept network requests for `.m3u8` / `.mpd` files
4. **Follow** — if a player wrapper page is found, navigate into it
5. **Play** — return the direct CDN `.m3u8` URL to `mpv`

## Files

| File | Purpose |
|---|---|
| `fifacli` | Main script (Bash) |
| `scrapers/extract_stream.py` | Playwright-based stream extractor |
| `scrapers/requirements.txt` | Python dependencies |
| `scrapers/venv/` | Python virtual environment (gitignored) |
| `~/.config/wc-cli/config` | User configuration |
