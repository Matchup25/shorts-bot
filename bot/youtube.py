"""Agent 6 – the publisher: talks to the official YouTube Data API."""
import collections
import datetime as dt
import re

import requests

from .util import env, log

TOKEN_URI = "https://oauth2.googleapis.com/token"
CATEGORY_IDS = {  # YouTube category numbers
    "science": "28", "space": "28", "tech": "28", "health": "28", "nature": "15",
    "world": "25", "business": "25", "weird": "24", "culture": "24", "education": "27",
}


def service(token_env: str = "YT_REFRESH_TOKEN"):
    """YouTube API for one channel: YT_REFRESH_TOKEN = World in a Shot, YT2_REFRESH_TOKEN = explainer channel."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(
        token=None,
        refresh_token=env(token_env),
        client_id=env("YT_CLIENT_ID"),
        client_secret=env("YT_CLIENT_SECRET"),
        token_uri=TOKEN_URI,
        # no fixed scopes: the token keeps whatever permissions were granted when it was made
    )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def granted_scopes(token_env: str = "YT_REFRESH_TOKEN") -> list:
    """Which YouTube permissions the saved token has (to know if comments/analytics are allowed)."""
    try:
        r = requests.post(TOKEN_URI, timeout=20, data={
            "grant_type": "refresh_token", "refresh_token": env(token_env),
            "client_id": env("YT_CLIENT_ID"), "client_secret": env("YT_CLIENT_SECRET")})
        return r.json().get("scope", "").split() if r.ok else []
    except Exception:
        return []


def comment(yt, video_id: str, text: str):
    """Post a top-level comment on our own video (needs the youtube.force-ssl permission)."""
    body = {"snippet": {"videoId": video_id, "topLevelComment": {"snippet": {"textOriginal": text}}}}
    res = yt.commentThreads().insert(part="snippet", body=body).execute()
    return res.get("id")


def analytics_retention(video_ids: list, start: str, end: str) -> dict:
    """Average % watched and seconds watched per video (needs yt-analytics.readonly). {} if not allowed."""
    if not video_ids:
        return {}
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(token=None, refresh_token=env("YT_REFRESH_TOKEN"), client_id=env("YT_CLIENT_ID"),
                        client_secret=env("YT_CLIENT_SECRET"), token_uri=TOKEN_URI)
    try:
        ya = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
        res = ya.reports().query(ids="channel==MINE", startDate=start, endDate=end, dimensions="video",
                                 metrics="views,averageViewPercentage,averageViewDuration",
                                 filters="video==" + ",".join(video_ids[:200]), maxResults=200).execute()
    except Exception as exc:
        detail = getattr(exc, "reason", "") or str(exc)[-200:]
        log(f"  retention numbers not available: {detail}")
        return {}
    out = {}
    for row in res.get("rows", []) or []:
        out[row[0]] = {"views": row[1], "avg_pct": round(row[2], 1), "avg_sec": round(row[3], 1)}
    return out


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


def shorts_demand(yt, query: str, hours: int = 48) -> dict | None:
    """How much people are watching Shorts about this topic right now:
    the views of the 5 most watched Shorts on it published in the last `hours`."""
    since = (dt.datetime.utcnow() - dt.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        found = yt.search().list(
            part="id", q=query, type="video", videoDuration="short", order="viewCount",
            publishedAfter=since, maxResults=10, relevanceLanguage="en",
        ).execute()
        ids = [item["id"]["videoId"] for item in found.get("items", []) if item.get("id", {}).get("videoId")]
        views = []
        if ids:
            stats = yt.videos().list(part="statistics", id=",".join(ids)).execute()
            views = sorted((int(i.get("statistics", {}).get("viewCount", 0)) for i in stats.get("items", [])), reverse=True)
        return {"query": query, "videos": len(views), "views": sum(views[:5]), "top": views[0] if views else 0}
    except Exception as exc:
        log(f"  YouTube demand check failed for '{query}': {exc}")
        return None


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
           privacy: str, ai_disclosure: bool, publish_at: str | None = None) -> str:
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
            # a scheduled video stays private until YouTube publishes it at publish_at
            "privacyStatus": "private" if publish_at else privacy,
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": bool(ai_disclosure),
        },
    }
    if publish_at:
        body["status"]["publishAt"] = publish_at
    media = MediaFileUpload(video_path, mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            log(f"  uploading… {int(status.progress() * 100)}%")
    return response["id"]
