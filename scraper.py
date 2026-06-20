"""
scraper.py — Scraper de TikTok e Instagram via Apify
Uso: python scraper.py
Guarda resultados en: datos/videos_latest.csv
"""

import os
import re
import pandas as pd
from apify_client import ApifyClient
from dotenv import load_dotenv

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────────────
APIFY_TOKEN = os.getenv("APIFY_KEY") or os.getenv("APIFY_TOKEN", "")

OUTPUT_PATH = "datos/videos_latest.csv"
MAX_VIDEOS  = 20  # por cuenta

# Handles verificados en TikTok (busca el @ exacto en tiktok.com)
TIKTOK_ACCOUNTS    = [
    "icebarrel",
    "thepodcompany",
    "icebathclub",
    "piolet91",
    "subceromx",
    "polarrecovery",
    "ice.bath.recovery.tijuan",
    "tryicebath",
    
]

# URLs completas de Instagram (requerido por apify/instagram-scraper)
INSTAGRAM_ACCOUNTS = [
    "https://www.instagram.com/plunge/", 
    "https://www.instagram.com/mentefria.therapy/",
    "https://www.instagram.com/morozkoforge/",
    "https://www.instagram.com/icebarrel/",
    "https://www.instagram.com/piolet91/",
    "https://www.instagram.com/thecoldplungestore/",
    "https://www.instagram.com/thecoldpod/",
    
  
]

# Apify actors
ACTOR_TIKTOK    = "clockworks/free-tiktok-scraper"
ACTOR_INSTAGRAM = "apify/instagram-scraper"


def _viral_score(df: pd.DataFrame) -> pd.Series:
    """views / promedio_de_views_por_cuenta — cuántas veces supera la media"""
    media_por_cuenta = df.groupby(["platform", "account"])["views"].transform("mean")
    return (df["views"] / media_por_cuenta.replace(0, 1)).round(2)


# ── TikTok ──────────────────────────────────────────────────────────────────
def scrape_tiktok(client: ApifyClient) -> list[dict]:
    print(f"[TikTok] Scrapeando {len(TIKTOK_ACCOUNTS)} cuentas...")

    run = client.actor(ACTOR_TIKTOK).call(run_input={
        "profiles":       [f"@{a}" for a in TIKTOK_ACCOUNTS],
        "resultsPerPage": MAX_VIDEOS,
        "shouldDownloadVideos": False,
        "shouldDownloadCovers": False,
    })

    items = []
    dataset_id = run.default_dataset_id if hasattr(run, "default_dataset_id") else run["defaultDatasetId"]
    for item in client.dataset(dataset_id).iterate_items():
        try:
            hashtags = " ".join(
                f"#{h['name']}" if isinstance(h, dict) else f"#{h}"
                for h in (item.get("hashtags") or [])
            )
            views    = int(item.get("playCount") or item.get("stats", {}).get("playCount") or 0)
            likes    = int(item.get("diggCount") or item.get("stats", {}).get("diggCount") or 0)
            comments = int(item.get("commentCount") or item.get("stats", {}).get("commentCount") or 0)
            shares   = int(item.get("shareCount") or item.get("stats", {}).get("shareCount") or 0)
            duration = int(
                item.get("videoMeta", {}).get("duration")
                or item.get("video", {}).get("duration")
                or 0
            )
            account  = (
                item.get("authorMeta", {}).get("name")
                or item.get("author", {}).get("uniqueId")
                or "unknown"
            )
            eng = round((likes + comments + shares) / views * 100, 2) if views > 0 else 0.0

            items.append({
                "platform":       "TikTok",
                "account":        account,
                "views":          views,
                "likes":          likes,
                "comments":       comments,
                "shares":         shares,
                "engagement_rate": eng,
                "description":    (item.get("text") or "")[:200],
                "hashtags":       hashtags,
                "duration_secs":  duration,
                "url":            item.get("webVideoUrl") or item.get("url") or "",
            })
        except Exception as e:
            print(f"  [warn] item ignorado: {e}")

    print(f"  -> {len(items)} videos obtenidos")
    return items


# ── Instagram ───────────────────────────────────────────────────────────────
def scrape_instagram(client: ApifyClient) -> list[dict]:
    print(f"[Instagram] Scrapeando {len(INSTAGRAM_ACCOUNTS)} cuentas...")

    run = client.actor(ACTOR_INSTAGRAM).call(run_input={
        "directUrls":   INSTAGRAM_ACCOUNTS,
        "resultsLimit": MAX_VIDEOS,
        "resultsType":  "posts",
    })

    items = []
    dataset_id = run.default_dataset_id if hasattr(run, "default_dataset_id") else run["defaultDatasetId"]
    for item in client.dataset(dataset_id).iterate_items():
        try:
            views    = int(item.get("videoViewCount") or item.get("videoPlayCount") or 0)
            likes    = int(item.get("likesCount") or 0)
            comments = int(item.get("commentsCount") or 0)

            # Solo reels/videos tienen views; ignorar fotos sin views
            if views == 0 and item.get("type") not in ("Video", "Reel"):
                continue

            caption  = item.get("caption") or ""
            hashtags = " ".join(re.findall(r"#\w+", caption))
            eng = round((likes + comments) / views * 100, 2) if views > 0 else 0.0

            items.append({
                "platform":       "Instagram",
                "account":        item.get("ownerUsername") or "unknown",
                "views":          views,
                "likes":          likes,
                "comments":       comments,
                "shares":         0,
                "engagement_rate": eng,
                "description":    caption[:200],
                "hashtags":       hashtags,
                "duration_secs":  int(item.get("videoDuration") or 0),
                "url":            item.get("url") or item.get("shortCode") and
                                  f"https://www.instagram.com/p/{item['shortCode']}/" or "",
            })
        except Exception as e:
            print(f"  [warn] item ignorado: {e}")

    print(f"  -> {len(items)} videos obtenidos")
    return items


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    if not APIFY_TOKEN:
        print("[Error] APIFY_KEY no encontrado. Agrega tu token en el .env")
        return

    client = ApifyClient(APIFY_TOKEN)

    filas = []
    filas += scrape_tiktok(client)
    filas += scrape_instagram(client)

    if not filas:
        print("[Error] No se obtuvo ningún video.")
        return

    df = pd.DataFrame(filas)
    df = df[df["views"] > 0].copy()
    df["viral_score"] = _viral_score(df)
    df = df.sort_values("views", ascending=False).reset_index(drop=True)
    df.index += 1
    df.index.name = "rank"

    os.makedirs("datos", exist_ok=True)
    df.to_csv(OUTPUT_PATH)
    print(f"\n[OK] {len(df)} videos guardados en {OUTPUT_PATH}")
    print(df[["platform", "account", "views", "viral_score"]].head(10).to_string())


if __name__ == "__main__":
    main()
