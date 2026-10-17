"""Small, isolated HTTP integrations for notification destinations."""
from __future__ import annotations

import os
from urllib.parse import urlencode

import httpx

META_GRAPH_VERSION = os.environ.get("META_GRAPH_VERSION", "v26.0").strip()


class DestinationError(Exception):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


def render_message(template: str, values: dict[str, str]) -> str:
    try:
        return template.format_map({key: value or "" for key, value in values.items()})
    except (KeyError, ValueError) as exc:
        raise DestinationError("Template contains an unknown field or invalid format.") from exc


def _request_error(response: httpx.Response, provider: str) -> DestinationError:
    retryable = response.status_code in (408, 425, 429) or response.status_code >= 500
    # Deliberately discard provider response bodies; they can contain sensitive values.
    return DestinationError(f"{provider} returned HTTP {response.status_code}.", retryable)


def discord_send(webhook: str, message: str) -> None:
    if not webhook:
        raise DestinationError("Discord webhook is not configured.")
    try:
        response = httpx.post(webhook, json={"content": message[:2000]}, timeout=20)
    except httpx.HTTPError as exc:
        raise DestinationError("Could not reach Discord.", True) from exc
    if response.status_code not in (200, 204):
        raise _request_error(response, "Discord")


def facebook_send(page_id: str, token: str, message: str) -> str:
    if not page_id or not token:
        raise DestinationError("Facebook Page is not configured.")
    try:
        response = httpx.post(
            f"https://graph.facebook.com/{META_GRAPH_VERSION}/{page_id}/feed",
            data={"message": message, "access_token": token}, timeout=20,
        )
        if response.status_code >= 400:
            raise _request_error(response, "Facebook")
        return str(response.json().get("id", ""))
    except (httpx.HTTPError, ValueError) as exc:
        raise DestinationError("Could not reach Facebook.", True) from exc


# OAuth helpers accept config from caller to keep secrets out of module globals.
def meta_authorize_url(app_id: str, redirect_uri: str, state: str) -> str:
    query = urlencode({"client_id": app_id, "redirect_uri": redirect_uri, "state": state,
                       # business_management is needed for /me/accounts to include
                       # Pages linked to a Meta business portfolio.
                       "scope": "pages_show_list,pages_manage_posts,business_management",
                       "response_type": "code"})
    return f"https://www.facebook.com/{META_GRAPH_VERSION}/dialog/oauth?{query}"


def meta_exchange_code(app_id: str, app_secret: str, redirect_uri: str, code: str) -> str:
    try:
        response = httpx.get(f"https://graph.facebook.com/{META_GRAPH_VERSION}/oauth/access_token", params={
            "client_id": app_id, "client_secret": app_secret, "redirect_uri": redirect_uri, "code": code,
        }, timeout=20)
        if response.status_code >= 400:
            raise _request_error(response, "Meta authorization")
        return response.json()["access_token"]
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise DestinationError("Meta authorization could not be completed.") from exc


def meta_pages(user_token: str) -> list[dict[str, str]]:
    try:
        url = f"https://graph.facebook.com/{META_GRAPH_VERSION}/me/accounts"
        params: dict[str, str | int] = {
            "fields": "id,name,access_token", "access_token": user_token, "limit": 100,
        }
        pages: list[dict[str, str]] = []
        seen_cursors: set[str] = set()
        for _ in range(100):
            response = httpx.get(url, params=params, timeout=20)
            if response.status_code >= 400:
                raise _request_error(response, "Meta Pages")
            payload = response.json()
            pages.extend(
                {"id": str(row["id"]), "name": str(row["name"]), "token": str(row["access_token"])}
                for row in payload.get("data", [])
            )
            paging = payload.get("paging", {})
            next_cursor = paging.get("cursors", {}).get("after")
            if not paging.get("next") or not next_cursor:
                return pages
            if next_cursor in seen_cursors:
                raise DestinationError("Meta returned an invalid Page list.")
            seen_cursors.add(next_cursor)
            params["after"] = next_cursor
        raise DestinationError("Meta returned too many Page list results.")
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise DestinationError("Could not load managed Facebook Pages.") from exc
