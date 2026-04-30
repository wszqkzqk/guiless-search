import json
import logging
import os
import platform

from PySide6.QtNetwork import QNetworkCookie
from PySide6.QtWebEngineCore import QWebEngineProfile
from PySide6.QtWidgets import QApplication

from . import config

log = logging.getLogger("guiless-search")


def default_profile_dir(app_name: str) -> str:
    """Return platform-appropriate user data directory.

    When running under systemd with StateDirectory=, the STATE_DIRECTORY
    environment variable is set automatically and takes precedence.
    """
    state_dir = os.environ.get("STATE_DIRECTORY")
    if state_dir:
        return state_dir
    s = platform.system()
    if s == "Windows":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    elif s == "Darwin":
        base = os.path.join(
            os.path.expanduser("~"), "Library", "Application Support",
        )
    else:
        base = os.environ.get(
            "XDG_DATA_HOME",
            os.path.join(os.path.expanduser("~"), ".local", "share"),
        )
    return os.path.join(base, "io.github.wszqkzqk", app_name)


def build_profile(
    app: QApplication, profile_dir: str = "",
) -> QWebEngineProfile:
    """Create a persistent WebEngine profile shared by all engines."""
    profile = QWebEngineProfile("guiless-search", app)

    storage = profile_dir or default_profile_dir("guiless-search")
    profile.setPersistentStoragePath(storage)
    profile.setCachePath(os.path.join(storage, "cache"))

    if config.USER_AGENT:
        profile.setHttpUserAgent(config.USER_AGENT)

    profile.setPersistentCookiesPolicy(
        QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies,
    )
    log.info("UA: %s", profile.httpUserAgent())
    log.info("Profile: %s", profile.persistentStoragePath())
    return profile


def inject_cookies(
    profile: QWebEngineProfile,
    domain: str,
    cookies: dict[str, str],
    extra_json: str = "",
) -> None:
    """Inject cookies into the profile's cookie store for *domain*."""
    merged = dict(cookies)
    if extra_json:
        try:
            extra = json.loads(extra_json)
            if isinstance(extra, dict):
                merged.update(extra)
        except json.JSONDecodeError:
            log.warning("Extra cookies JSON is invalid, ignored")

    if not merged:
        return

    store = profile.cookieStore()
    for name, value in merged.items():
        c = QNetworkCookie(name.encode(), value.encode())
        c.setDomain(domain)
        c.setPath("/")
        c.setSecure(True)
        store.setCookie(c)
