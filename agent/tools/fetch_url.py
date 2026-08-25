"""
Tool : fetch_url
Récupère le contenu à ingérer à partir d'une URL (mode "url" du formulaire de feedback).

Deux chemins :
- App Store : flux RSS officiel Apple (un avis = un feedback, plusieurs avis par URL).
- Générique : extraction du texte principal de n'importe quelle page statique (un feedback).

G2, Trustpilot et Play Store ne sont pas supportés : leurs avis sont chargés en JavaScript
côté client, invisibles à un simple fetch HTTP (nécessiterait un navigateur headless, hors
périmètre pour l'instant).
"""

import re

import httpx
from bs4 import BeautifulSoup

_HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; feedbackai-agent/1.0)"}
_APPSTORE_URL_RE = re.compile(r"apps\.apple\.com/(\w{2})/app/[^/]+/id(\d+)")


def is_appstore_url(url: str) -> bool:
    return bool(_APPSTORE_URL_RE.search(url))


async def fetch_appstore_reviews(url: str, limit: int = 20) -> list[str]:
    """Récupère les avis les plus récents d'une app via le flux RSS officiel Apple."""
    match = _APPSTORE_URL_RE.search(url)
    if not match:
        raise ValueError(f"URL App Store non reconnue : {url!r}")
    country, app_id = match.groups()

    feed_url = f"https://itunes.apple.com/{country}/rss/customerreviews/id={app_id}/sortby=mostrecent/json"
    async with httpx.AsyncClient(timeout=10.0, headers=_HTTP_HEADERS) as http:
        resp = await http.get(feed_url)
        resp.raise_for_status()
        data = resp.json()

    entries = data.get("feed", {}).get("entry", [])
    reviews = [
        e["content"]["label"].strip()
        for e in entries
        if "content" in e and "im:rating" in e and e["content"].get("label", "").strip()
    ]
    return reviews[:limit]


async def fetch_generic_page_text(url: str) -> str:
    """Récupère et nettoie le texte principal d'une page statique quelconque."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=10.0, headers=_HTTP_HEADERS) as http:
        resp = await http.get(url)
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript", "svg"]):
        tag.decompose()

    text = re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True)).strip()
    if len(text) < 5:
        raise ValueError("Aucun texte exploitable extrait de la page.")
    return text[:5000]
