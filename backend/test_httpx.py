import asyncio
import httpx
import feedparser

CONFLICT_KEYWORDS = [
    # English
    "israel", "iran", "hamas", "hezbollah", "idf", "netanyahu",
    "beirut", "gaza", "lebanon", "houthi", "ukraine",
    "strike", "airstrike", "drone", "missile", "attack",
    "war", "military", "troops", "ceasefire", "sanctions",
    "nuclear", "irgc", "mossad", "centcom", "pentagon",
    "tehran", "tel aviv", "rafah", "west bank", "jerusalem",
    "syria", "iraq", "yemen", "red sea", "hormuz", "naval",
    "qatar", "bahrain", "doha", "manama", "al udeid",
    "saudi", "riyadh", "aramco", "jeddah", "dhahran",
    "uae", "abu dhabi", "dubai", "al dhafra",
    "kuwait", "oman", "muscat",
    "gulf", "persian gulf", "strait of hormuz",
    "pakistan", "afghanistan", "islamabad", "kabul",
    
    # Arabic roots/plurals for robust matching
    "إسرائيل", "اسرائيل", "إيران", "ايران", "حماس", "حزب الله", "جيش", "نتنياهو", "جيش الدفاع",
    "بيروت", "غزة", "لبنان", "الحوثي", "حوثي",
    "غارة", "غارات", "قصف", "مسيرة", "مسيرات", "صاروخ", "صواريخ", "هجوم", "هجمات", "انفجار", "انفجارات",
    "حرب", "حروب", "عسكري", "قوات", "وقف إطلاق النار", "عقوبات", "مقتل", "قتلى", "شهداء", "شهيد",
    "نووي", "الحرس الثوري", "الموساد", "البنتاغون",
    "طهران", "تل أبيب", "رفح", "الضفة", "القدس",
    "سوريا", "العراق", "اليمن", "البحر الأحمر", "هرمز", "بحري",
    
    # Generic for dev testing
    "عاجل", "العالم", "الشرق", "أمريكا", "امريكا", "أوروبا", "روسيا", "اقتصاد", "يحدث الآن"
]

RSS_FEEDS_AR = [
    {
        "name": "Al Jazeera (AR)",
        "url": "https://www.aljazeera.net/aljazeerarss/a7c186be-1baa-4bd4-9d80-a84db769f779/73d0e1b4-532f-45ef-b135-bfdff8b8cab9",
        "source": "Al Jazeera (AR)",
    },
    {
        "name": "France24 Arabic",
        "url": "https://www.france24.com/ar/rss",
        "source": "France24 (AR)",
    },
    {
        "name": "BBC Arabic",
        "url": "http://feeds.bbci.co.uk/arabic/rss.xml",
        "source": "BBC Arabic",
    }
]

def is_relevant(entry) -> bool:
    text = (
        getattr(entry, "title", "") + " " +
        getattr(entry, "summary", "") + " " +
        getattr(entry, "description", "")
    ).lower()
    for kw in CONFLICT_KEYWORDS:
        if kw in text:
            return True
    return False

async def main():
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        for feed_cfg in RSS_FEEDS_AR:
            print(f"Fetching {feed_cfg['name']}...")
            try:
                resp = await client.get(feed_cfg["url"])
                print(f"Status: {resp.status_code}")
                if resp.status_code != 200:
                    continue
                parsed = feedparser.parse(resp.text)
                print(f"Entries found: {len(parsed.entries)}")
                relevant = 0
                for entry in parsed.entries:
                    if is_relevant(entry):
                        relevant += 1
                        print(f"  [Match] {entry.title}")
                print(f"Relevant entries: {relevant}/{len(parsed.entries)}")
            except Exception as e:
                print(f"Error: {e}")

asyncio.run(main())
