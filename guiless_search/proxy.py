"""Proxy resolution: explicit URL or standard env vars → Chromium flags."""

import logging
import os
import urllib.parse
import urllib.request

log = logging.getLogger("guiless-search")


def _normalize(url: str, *, strict: bool) -> str | None:
    p = urllib.parse.urlsplit(url)
    if p.scheme not in ("http", "https") or not p.netloc:
        if strict:
            raise ValueError(f"invalid proxy URL: {url}")
        log.warning("Ignoring invalid proxy URL: %s", url)
        return None
    return f"{p.scheme}://{p.netloc}"


def apply_proxy(explicit: str = "") -> str:
    """Inject proxy flags into QTWEBENGINE_CHROMIUM_FLAGS.

    *explicit* wins; otherwise standard http_proxy/https_proxy/all_proxy
    env vars are used.  Returns a summary of the active proxy, "" if none.
    """
    proxies: dict[str, str] = {}
    if explicit:
        url = _normalize(explicit, strict=True)
        assert url is not None
        proxies = {"http": url, "https": url}
        no_proxy = os.environ.get("NO_PROXY") or os.environ.get("no_proxy", "")
    else:
        env = urllib.request.getproxies_environment()
        for scheme in ("http", "https"):
            url = env.get(scheme) or env.get("all")
            if url:
                norm = _normalize(url, strict=False)
                if norm:
                    proxies[scheme] = norm
        no_proxy = env.get("no", "")
    if not proxies:
        return ""

    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    additions: list[str] = []
    server = ";".join(f"{s}={u}" for s, u in proxies.items())
    if "--proxy-server" not in flags:
        additions.append(f"--proxy-server={server}")
    bypass = ";".join(x.strip() for x in no_proxy.split(",") if x.strip())
    if bypass and "--proxy-bypass-list" not in flags:
        additions.append(f"--proxy-bypass-list={bypass}")
    if additions:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
            f"{flags} {' '.join(additions)}"
        ).strip()
    return server
