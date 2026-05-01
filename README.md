# GUI-Less Search

An unofficial multi-backend tool for accessing web search results in environments **without a graphical user interface**, built for personal study and research on headless information retrieval.

In many server, container, or embedded environments there is no desktop or browser available, yet users still need to look up information on the web. This tool wraps Qt6 WebEngine (PySide6) as a headless Chromium engine and exposes a minimal HTTP API so that users can query Google, DuckDuckGo, Sogou, and Bing via `curl` or similar command-line utilities — all from a single service.

Because no result links are fed back to the search engines, the tool does not leak which results the user actually visited, offering a degree of privacy protection compared to using a regular browser.

**Disclaimer:** This tool is an independent, unofficial project created for educational purposes, personal accessibility, and academic research on headless information retrieval. It acts as a local browser wrapper to facilitate personal workflows and interoperability. It is not intended for bulk scraping, commercial use, or any activity that would violate the terms of service of the accessed services. Users are encouraged to respect fair use principles and the terms of service of the websites they access.

## Dependencies

- `python>=3.10.0`
- `pyside6`
- `qt6-webengine`

## Installation on Arch Linux

This package is available on the [AUR](https://aur.archlinux.org/packages/guiless-search). You can install it with an AUR helper such as `paru` or `yay`:

```bash
paru -S guiless-search
# or
yay -S guiless-search
```

After installation, you can edit the configuration file (optional) and then enable the service:

```bash
sudo systemctl enable --now guiless-search
```

The service listens on `127.0.0.1:8565` by default. You can then query it via `curl` as shown in [Usage Examples](#usage-examples).

## Quick Start

```bash
# Start the service (headless, no display needed)
guiless-search

# Enable only Google and DuckDuckGo (exclude Sogou and Bing)
guiless-search --backends google,duckduckgo

# Custom profile directory
guiless-search --profile-dir /path/to/profile
```

## Features

- **Multiple search backends**: Google, DuckDuckGo, Sogou, Bing — all from a single service
- **Fallback mode**: automatically tries the next backend if the previous one returns no results
- **Parallel mode**: queries all enabled backends concurrently, deduplicates and ranks by cross-engine agreement
- **Backend selection**: enable or disable any backend, configure their priority order
- **Unified API**: single HTTP endpoint for all backends
- **MCP support**: Model Context Protocol (JSON-RPC 2.0) for AI agent integration
- **Headless browser normalization**: normalizes browser fingerprint for consistent rendering in offscreen environments
- **Rate limiting**: configurable per-engine intervals with random jitter
- **Privacy-friendly URL handling**: unwraps click-tracking redirects to present the actual destination URLs
- **Memory-efficient lazy loading**: QWebEnginePage instances are created on demand and released after a configurable idle timeout, reducing memory usage when engines are not actively searching

## Usage Examples

Once the service is running, search from the command line:

```bash
# Health check (no auth)
curl http://localhost:8565/health

# Search with default mode (uses SEARCH_MODE, default: parallel)
curl -s -X POST http://localhost:8565/search \
    -H "Content-Type: application/json" \
    -d '{"query": "Python tutorial"}' | python -m json.tool

# Search with a specific backend
curl -s -X POST http://localhost:8565/search/duckduckgo \
    -H "Content-Type: application/json" \
    -d '{"query": "Python tutorial", "count": 3}' | python -m json.tool

# With authentication
curl -s -X POST http://localhost:8565/search \
    -H "Authorization: Bearer mysecretkey" \
    -H "Content-Type: application/json" \
    -d '{"query": "Python tutorial"}' | python -m json.tool
```

Response format:

```json
[
    {"link": "https://...", "title": "...", "snippet": "..."},
    ...
]
```

## Search Modes

### `parallel` (default)

Queries **all enabled backends concurrently**, then aggregates the results:

- **Deduplicate** by normalized URL (tracking parameters are stripped).
- **Rank** primarily by how many distinct engines returned the same URL — cross-engine agreement is the strongest trust signal against garbage results from unreliable sources.
- **Tie-break** using the configured engine order and original position within that engine.

### `fallback`

Tries backends in the order listed in `BACKENDS`. If the first backend returns non-empty results, stops immediately. If it returns empty results, tries the next one in order.

### `single`

Uses only the `DEFAULT_BACKEND`. No fallback or aggregation.

## Backend Selection

You control which backends are active and their fallback priority via the `BACKENDS` setting:

```bash
# Google first, then DuckDuckGo
guiless-search --backends google,duckduckgo --default-backend google

# DuckDuckGo first, then Google
guiless-search --backends duckduckgo,google --default-backend duckduckgo

# Only Google
guiless-search --backends google

# Exclude Bing, keep Sogou as fallback
guiless-search --backends google,duckduckgo,sogou
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `HOST` | `127.0.0.1` | Listen address |
| `PORT` | `8565` | Listen port |
| `BACKENDS` | `google,duckduckgo,sogou,bing` | Enabled backends (comma-separated, order = fallback priority) |
| `DEFAULT_BACKEND` | `google` | Default backend for `/search` |
| `SEARCH_MODE` | `parallel` | `single`, `fallback`, or `parallel` |
| `SEARCH_INTERVAL` | `1` | Minimum seconds between searches per engine; random jitter of 0-50% is added automatically |
| `PARALLEL_TIMEOUT` | `10` | Max seconds to wait for all engines in `parallel` mode |
| `ENGINE_IDLE_TIMEOUT` | `300` | Seconds of inactivity before releasing the QWebEnginePage to free memory; 0 keeps pages alive permanently |
| `USER_AGENT` | (auto) | Custom User-Agent |
| `API_KEY` | (empty) | API key for `Bearer` token auth; if empty, no auth required |
| `GOOGLE_BASE_URL` | `https://www.google.com` | Base URL for Google search |
| `GOOGLE_EXTRA_COOKIES` | (empty) | Extra cookies as JSON, merged with default consent cookies |
| `BING_BASE_URL` | `https://www.bing.com` | Base URL for Bing search |
| `BING_U_COOKIE` | (empty) | Bing `_U` cookie (see [Cookie Troubleshooting](#cookie-troubleshooting)) |
| `BING_EXTRA_COOKIES` | (empty) | Extra cookies as JSON |
| `BING_ENSEARCH` | (auto) | `1`=force international, `0`=force domestic on cn.bing.com, unset=adaptive |
| `DDG_BASE_URL` | `https://html.duckduckgo.com/html` | Base URL for DuckDuckGo search (HTML no-JS endpoint) |
| `DDG_REGION` | (auto) | Region code (e.g. `us-en`, `wt-wt` for global) |
| `SOGOU_BASE_URL` | `https://www.sogou.com` | Base URL for Sogou search |

## Command-Line Options

```
--host HOST                 Listen address (default: 127.0.0.1)
--port PORT                 Listen port (default: 8565)
--backends LIST             Comma-separated backends (default: google,duckduckgo,sogou,bing)
--default-backend NAME      Default backend (default: google)
--search-mode MODE          single, fallback, or parallel (default: parallel)
--search-interval N         Minimum seconds between searches per engine (default: 1)
--parallel-timeout N        Max seconds to wait for all engines in parallel mode (default: 10)
--engine-idle-timeout N     Release QWebEnginePage after N seconds idle (default: 300, 0=never)
--profile-dir DIR           Custom profile directory
--api-key KEY               API key for Bearer token auth (optional)
--user-agent UA             Custom User-Agent string
--ddg-base-url URL          DuckDuckGo base URL
--ddg-region CODE           DuckDuckGo region code
--google-base-url URL       Google base URL
--google-cookies JSON       Extra cookies as JSON
--bing-base-url URL         Bing base URL
--bing-u-cookie COOKIE      Bing _U cookie
--bing-cookies JSON         Extra cookies as JSON
--bing-ensearch VALUE       1=intl, 0=local, auto
--sogou-base-url URL        Sogou base URL
```

## GDPR Consent Handling

Google shows a GDPR consent page ("Before you continue to Google Search") to users in EU/EEA/UK regions. This tool handles it automatically:

1. **Cookie injection**: Default `SOCS` and `CONSENT` cookies are injected into the browser profile to pre-configure consent preferences.
2. **Consent acceptance**: If the consent page still appears, the tool detects it and interacts with the page to accept the terms, then re-navigates to the search URL.

If you experience issues with the consent page, you can supply additional cookies via `--google-cookies` or `GOOGLE_EXTRA_COOKIES`:

```bash
guiless-search --google-cookies '{"NID":"your_nid_cookie_value"}'
```

## Cookie Troubleshooting (Bing)

In certain network environments, accessing `www.bing.com` may redirect to `cn.bing.com` or involve cookie-dependent routing, which can leave the browser profile in a broken state and cause searches to fail or return incorrect results.

If you experience this problem, try one of the following:

1. **Delete the profile directory** to start with a clean state.
2. **Set `--bing-base-url=https://cn.bing.com`** if your network reliably lands on the mainland endpoint.
3. **Set `--bing-u-cookie`** or `--bing-cookies` to supply known-good cookie values.

If your network can reach `bing.com` without issues, you do not need to set any cookie variables.

## Profile Storage

By default, profile data (cookies, local storage) is stored under the platform-appropriate user data directory:

| Platform | Path |
|---|---|
| Linux (User) | `$XDG_DATA_HOME/io.github.wszqkzqk/guiless-search/` (typically `~/.local/share/...`) |
| Linux (systemd with `StateDirectory=`) | `/var/lib/io.github.wszqkzqk/guiless-search/` (via `$STATE_DIRECTORY`) |
| macOS | `~/Library/Application Support/io.github.wszqkzqk/guiless-search/` |
| Windows | `%LOCALAPPDATA%\io.github.wszqkzqk\guiless-search\` |

Override with `--profile-dir` for portability.

## OpenWebUI Integration

While this tool is primarily designed for CLI usage, its standard HTTP JSON interface allows for local interoperability with other tools, such as [OpenWebUI](https://github.com/open-webui/open-webui).

> **Note on Interoperability**
>
> Connecting this tool to local frontends is provided as an example of personal workflow enhancement. This setup is intended for low-frequency, local debugging and study purposes. It is not a replacement for commercial search APIs, and users should ensure their usage respects fair use guidelines.

If you choose to configure this integration, the technical configuration in **Admin Panel > Settings > Web Search** is:

1. **Web Search Engine**: select `external`
2. **External Search URL**: `http://127.0.0.1:8565/search`
3. **External Search API Key**: your `API_KEY` value if configured, or any non-empty string if not

## MCP Integration

> **Note on MCP Integration**
>
> The built-in MCP (Model Context Protocol) endpoint demonstrates local interoperability between headless browsers and AI agents for personal, low-frequency workflows. This integration allows individuals to streamline their daily research tasks in a privacy-respecting manner.
>
> It is provided strictly as an educational example of local agent integration. For any commercial or production-grade automated search workflows, please use official search APIs.

The built-in MCP endpoint (`/mcp`) reuses the same running server process. No extra wrapper process is required. MCP uses the same Bearer authentication as `/search`.

Available MCP tool:
- `query` with input `{ "query": "...", "count": 5, "backend": "auto" }`
  - `backend`: `"auto"`, `"google"`, `"duckduckgo"`, `"sogou"`, or `"bing"`
  - `"auto"` uses the configured `SEARCH_MODE` (default: `parallel`)
- Returns rendered Markdown text with search results

### Claude Code example

```bash
# no auth
claude mcp add --transport http web-search http://127.0.0.1:8565/mcp

# if server uses --api-key
claude mcp add --transport http web-search http://127.0.0.1:8565/mcp \
  --header "Authorization: Bearer mysecretkey"
```

### Configuration files

These files are user-managed and are not auto-created by package installation.

**Project-scoped**: create `.mcp.json` in your project root.

**User-scoped (global)**: configure `~/.claude.json` under `mcpServers`, or run:

```bash
claude mcp add --transport http --scope user web-search http://127.0.0.1:8565/mcp
```

Example `.mcp.json` (project-scoped):

```json
{
  "mcpServers": {
    "web-search": {
      "type": "http",
      "url": "${WEB_SEARCH_MCP_URL:-http://127.0.0.1:8565/mcp}",
      "headers": {
        "Authorization": "Bearer ${WEB_SEARCH_API_KEY:-}"
      }
    }
  }
}
```

OpenCode config (`opencode.json` in project root, or `~/.config/opencode/opencode.json` for global user config):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "web_search": {
      "type": "remote",
      "url": "http://127.0.0.1:8565/mcp",
      "enabled": true,
      "oauth": false,
      "headers": {
        "Authorization": "Bearer {env:WEB_SEARCH_API_KEY}"
      }
    }
  }
}
```

Hardcoded values are also valid in both configs, for example: `"Authorization": "Bearer mysecretkey"`.

When auth is disabled, the `Authorization` header can be omitted.

## systemd Deployment

```bash
sudo $EDITOR /etc/guiless-search.conf
sudo systemctl enable --now guiless-search
```

## Known Limitations

- **Results per page**: Google returns up to 10 organic results per page. DuckDuckGo, Sogou, and Bing support up to 30. Pagination for more results is not yet supported.
- **CAPTCHA**: Search engines may show CAPTCHA challenges for datacenter IPs or high request rates. This cannot be solved automatically.
- **Selector stability**: CSS class names on search result pages are obfuscated and may change with frontend updates. The extraction logic uses multiple fallback selectors to mitigate this.
- **Bing routing**: In some network environments, Bing may return non-search content instead of actual results due to regional routing or cookie-dependent access controls. You can exclude Bing via `--backends` if it is unreliable in your environment.

## Disclaimer

This project is provided **for personal study and research purposes only**. It is intended strictly for manual, interactive use via command-line interfaces (CLI) by individual users. It is not designed, authorized, or intended for automated scraping, bulk data extraction, or any high-frequency programmatic access. Any use of this tool for automated data collection or other purposes that violate the Terms of Service of the target search engine is strictly prohibited.

**For production deployment, automated workflows, or large-scale usage, please use official search APIs or services:**
- Google: [Custom Search JSON API](https://developers.google.com/custom-search/v1/overview)
- DuckDuckGo: Official Instant Answer API or HTML endpoint terms
- Bing: [Grounding with Bing Search API](https://www.microsoft.com/en-us/bing/apis)

This tool is not a substitute for official APIs and should not be used as such.

It is the user's sole responsibility to comply with all applicable laws and the terms of service of any third-party services accessed through this software. The author does **not** encourage or endorse any use that violates the Terms of Service of Google, Duck Duck Go, Inc., Sogou, or Microsoft.

By using this software you agree that **you bear all responsibility** for ensuring your usage complies with applicable terms of service and laws.

### Trademark Disclaimer

- **"Google"** is a registered trademark of Google LLC.
- **"DuckDuckGo"** is a trademark of Duck Duck Go, Inc.
- **"Sogou"** is a registered trademark of Sogou Inc.
- **"Bing"** is a registered trademark of Microsoft Corporation.

This project is an independent, unofficial tool and is **not** affiliated with, authorized, maintained, sponsored, or endorsed by Google LLC, Duck Duck Go, Inc., Sogou Inc., Microsoft Corporation, or any of their affiliates.

## License

This project is licensed under the GNU General Public License v3.0 or later (GPL-3.0-or-later). See the [COPYING](COPYING) file for details.

This program is distributed in the hope that it will be useful, but **WITHOUT ANY WARRANTY**; without even the implied warranty of **MERCHANTABILITY** or **FITNESS FOR A PARTICULAR PURPOSE**. See the [GNU General Public License](https://www.gnu.org/licenses/gpl-3.0.html) for more details.
