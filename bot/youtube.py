"""Agent 6 – the publisher: talks to the official YouTube Data API."""
import collections
import datetime as dt
import re

import requests

from .util import env, log

TOKEN_URI = "https://oauth2.googleapis.com/token"
CATEGORY_IDS = {  # YouTube category numbers
    "science": "28", "space": "28", "tech": "28", "health": "28", "nature": "15",
    "world": "25", "business": "25", "weird": "24", "culture": "24",
}


def service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(
        token=None,
        refresh_token=env("YT_REFRESH_TOKEN"),
        client_id=env("YT_CLIENT_ID"),
        client_secret=env("YT_CLIENT_SECRET"),
        token_uri=TOKEN_URI,
        scopes=["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"],
    )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def popular_hashtags(yt, keywords: list) -> list:
    """Hashtags used by the most viewed Shorts of the last 7 days on the same topic."""
    if not keywords:
        return []
    since = (dt.datetime.utcnow() - dt.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    counter = collections.Counter()
    try:
        found = yt.search().list(
            part="id", q=" ".join(keywords[:3]), type="video", videoDuration="short",
            order="viewCount", publishedAfter=since, maxResults=30, relevanceLanguage="en",
        ).execute()
        ids = [item["id"]["videoId"] for item in found.get("items", [])]
        if ids:
            details = yt.videos().list(part="snippet", id=",".join(ids)).execute()
            for item in details.get("items", []):
                snip = item["snippet"]
                text = snip.get("title", "") + " " + snip.get("description", "")
                tags = {t.lower() for t in re.findall(r"#[A-Za-z0-9_]{2,30}", text)}
                counter.update(tags)
    except Exception as exc:
        log(f"  YouTube hashtag search failed: {exc}")
    return counter.most_common(40)


def google_trends() -> list:
    """Today's trending Google searches in the US and UK (free RSS)."""
    terms = []
    for geo in ("US", "GB"):
        try:
            xml = requests.get(f"https://trends.google.com/trending/rss?geo={geo}", timeout=20).text
            terms += re.findall(r"<item>\s*<title>(.*?)</title>", xml, flags=re.DOTALL)[:20]
        except Exception as exc:
            log(f"  Google Trends failed ({geo}): {exc}")
    return [t.strip() for t in terms]


def upload(yt, video_path: str, title: str, description: str, tags: list, category: str,
           privacy: str, ai_disclosure: bool) -> str:
    from googleapiclient.http import MediaFileUpload
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:4900],
            "tags": [t.lstrip("#") for t in tags][:15],
            "categoryId": CATEGORY_IDS.get(category, "25"),
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": bool(ai_disclosure),
        },
    }
    media = MediaFileUpload(video_path, mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            log(f"  uploading… {int(status.progress() * 100)}%")
    return response["id"]
