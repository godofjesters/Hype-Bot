"""Small YouTube Data API client and channel URL resolver."""
from __future__ import annotations

from urllib.parse import urlparse

import httpx

API_ROOT = "https://www.googleapis.com/youtube/v3"


class YouTubeError(Exception):
    pass


def channel_reference(value: str) -> tuple[str, str]:
    value = value.strip()
    if not value:
        raise YouTubeError("Enter a YouTube channel URL, handle, or channel ID.")
    if value.startswith("UC") and len(value) == 24:
        return "id", value
    if value.startswith("@"):
        return "forHandle", value[1:]
    if "youtube.com" not in value:
        return "forHandle", value
    parsed = urlparse(value if "://" in value else "https://" + value)
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        raise YouTubeError("That URL does not identify a YouTube channel.")
    if parts[0].startswith("@"):
        return "forHandle", parts[0][1:]
    if parts[0] == "channel" and len(parts) > 1:
        return "id", parts[1]
    if parts[0] == "user" and len(parts) > 1:
        return "forUsername", parts[1]
    raise YouTubeError("Use a channel URL, @handle, or /user/username URL.")


class YouTubeClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def get(self, resource: str, **params):
        try:
            response = httpx.get(
                f"{API_ROOT}/{resource}", params={**params, "key": self.api_key}, timeout=20
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            try:
                message = exc.response.json().get("error", {}).get("message", "YouTube API request failed")
            except ValueError:
                message = "YouTube API request failed"
            raise YouTubeError(message[:240]) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise YouTubeError("Could not reach the YouTube Data API.") from exc

    def resolve_channel(self, value: str) -> dict:
        key, reference = channel_reference(value)
        result = self.get("channels", part="snippet,contentDetails", **{key: reference})
        items = result.get("items", [])
        if not items:
            raise YouTubeError("YouTube did not find that channel.")
        channel = items[0]
        return {
            "channel_id": channel["id"],
            "title": channel["snippet"]["title"],
            "uploads_playlist": channel["contentDetails"]["relatedPlaylists"]["uploads"],
        }

    def scan(self, channel_id: str, uploads_playlist: str) -> list[dict]:
        # search.list has a separate 100-call daily bucket. One per channel/hour
        # keeps four channels within 96 calls/day; playlistItems and videos.list
        # use the shared quota for the other API methods.
        search = self.get(
            "search", part="id", channelId=channel_id, type="video", order="date", maxResults=50
        )
        videos = {item.get("id", {}).get("videoId") for item in search.get("items", [])}
        uploads = self.get("playlistItems", part="contentDetails,snippet", playlistId=uploads_playlist, maxResults=50)
        for item in uploads.get("items", []):
            video_id = item.get("contentDetails", {}).get("videoId")
            if video_id:
                videos.add(video_id)
        if not videos:
            return []
        video_ids = sorted(videos)
        found = []
        for offset in range(0, len(video_ids), 50):
            result = self.get(
                "videos", part="snippet,liveStreamingDetails",
                id=",".join(video_ids[offset:offset + 50]),
            )
            found.extend(result.get("items", []))
        return found

