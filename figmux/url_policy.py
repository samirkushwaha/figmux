from __future__ import annotations

from urllib.parse import urlparse

GOOGLE_OAUTH_HOSTS = {
    "accounts.google.com",
    "accounts.youtube.com",
    "oauth2.googleapis.com",
    "apis.google.com",
}
GOOGLE_AUTH_RELAY_SUFFIX = ".googleusercontent.com"
FIGMA_AUTH_PATH_PREFIXES = ("/login", "/signup", "/oauth")
ABOUT_BLANK = "about:blank"


def parse_https_url(value: str | None):
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme != "https":
        return None
    return parsed


def is_about_blank_url(value: str | None) -> bool:
    return not value or value == ABOUT_BLANK or value.startswith(f"{ABOUT_BLANK}#")


def is_google_auth_domain(hostname: str) -> bool:
    host = (hostname or "").lower()
    return (
        host in GOOGLE_OAUTH_HOSTS
        or host == "google.com"
        or host.endswith(".google.com")
        or (
            ".google." in host
            and (
                host.startswith("accounts.")
                or host.startswith("oauth2.")
                or host.startswith("apis.")
            )
        )
        or host.endswith(GOOGLE_AUTH_RELAY_SUFFIX)
    )


def is_figma_url(value: str | None) -> bool:
    parsed = parse_https_url(value)
    if not parsed:
        return False
    host = parsed.hostname or ""
    return host == "figma.com" or host.endswith(".figma.com")


def is_figma_auth_url(value: str | None) -> bool:
    parsed = parse_https_url(value)
    if not parsed or not is_figma_url(value):
        return False
    return any(parsed.path.startswith(prefix) for prefix in FIGMA_AUTH_PATH_PREFIXES)


def is_oauth_url(value: str | None) -> bool:
    parsed = parse_https_url(value)
    if not parsed:
        return False
    host = parsed.hostname or ""
    if is_google_auth_domain(host):
        return True
    return is_figma_auth_url(value)


def is_allowed_auth_or_figma_url(value: str | None) -> bool:
    return is_figma_url(value) or is_oauth_url(value)


def should_open_auth_popup(url: str | None, referrer_url: str | None) -> bool:
    if is_oauth_url(url) or is_about_blank_url(url):
        return True
    return is_oauth_url(referrer_url) and parse_https_url(url) is not None


def can_restore_url(value: str | None) -> bool:
    return is_figma_url(value) or is_oauth_url(value)
