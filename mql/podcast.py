"""Turn the daily brief into a ~3-minute audio episode and a podcast RSS feed.

Audio uses edge-tts (free, no key). Episodes are not committed to git (they would bloat the repo):
the GitHub Actions workflow keeps the last few in the Actions cache and publishes them with the site.
Subscribe in any podcast app with:  <site>/podcast.xml
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import date, datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

from . import config

SPEECH = [
    (r"(\d)\s*bp\b", r"\1 basis points"), (r"\bbp\b", "basis points"), (r"(\d)%", r"\1 percent"),
    (r"\b2s10s\b", "two-tens"), (r"\b5s30s\b", "five-thirties"), (r"\b5s20s\b", "five-twenties"),
    (r"\b5y5y\b", "five-year five-year forward"), (r"(\d+)y\b", r"\1-year"), (r"\bUSD/INR\b", "dollar-rupee"),
    (r"\bEUR/USD\b", "euro-dollar"), (r"\bGBP/USD\b", "sterling-dollar"), (r"\bUSD/JPY\b", "dollar-yen"),
    (r"\bOAS\b", "spread"), (r"(\d\.\d)x\b", r"\1 times"), (r"\bS&P\b", "S and P"), (r"\s+", " "),
]


def speakable(text: str) -> str:
    for pat, rep in SPEECH:
        text = re.sub(pat, rep, text)
    return text.strip()


def script(day: date, narrative: dict) -> str:
    parts = [f"This is Macro Quant Lab, the daily markets brief for {day:%A} {day.day} {day:%B}.",
             f"The headline: {narrative['headline'].rstrip('.')}."]
    parts += [b for b in narrative.get("bullets", [])]
    parts += narrative.get("context", [])
    if narrative.get("india"):
        parts.append("Now India")
        parts += narrative["india"]
    parts.append("That's the brief. Personal research on public data, not investment advice. Have a good day.")
    return speakable(" ".join(p if p.endswith(".") else p + "." for p in parts))


async def _tts(text: str, out: Path, voice: str) -> None:
    import edge_tts  # optional dependency

    await edge_tts.Communicate(text, voice).save(str(out))


def synthesize(text: str, out: Path, voice: str = "en-GB-RyanNeural") -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(_tts(text, out, voice))
    return out


def rss(episodes: list[dict], site_url: str) -> str:
    items = []
    for e in sorted(episodes, key=lambda x: x["date"], reverse=True):
        d = datetime.strptime(e["date"], "%Y-%m-%d").replace(hour=1, tzinfo=timezone.utc)
        url = f"{site_url}/audio/{e['date']}.mp3"
        items.append(
            "<item>"
            f"<title>{escape(e['date'] + ' · ' + e['title'])}</title>"
            f"<description>{escape(e.get('summary', ''))}</description>"
            f"<enclosure url=\"{escape(url)}\" length=\"{e.get('bytes', 0)}\" type=\"audio/mpeg\"/>"
            f"<guid isPermaLink=\"false\">mql-{e['date']}</guid>"
            f"<pubDate>{format_datetime(d)}</pubDate>"
            "</item>")
    return ("<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
            "<rss version=\"2.0\" xmlns:itunes=\"http://www.itunes.com/dtds/podcast-1.0.dtd\"><channel>"
            "<title>Macro Quant Lab · Daily</title>"
            f"<link>{escape(site_url)}/</link>"
            "<language>en</language>"
            "<description>A three-minute daily read of rates, credit, equities and FX, generated from public data. "
            "Personal research, not investment advice.</description>"
            "<itunes:author>Macro Quant Lab</itunes:author><itunes:explicit>false</itunes:explicit>"
            + "".join(items) + "</channel></rss>")


def run(day: date, narrative: dict, audio_dir: Path, keep: int = 7, voice: str = "en-GB-RyanNeural",
        site_url: str = config.SITE_URL) -> Path:
    audio_dir.mkdir(parents=True, exist_ok=True)
    mp3 = synthesize(script(day, narrative), audio_dir / f"{day.isoformat()}.mp3", voice)
    idx_path = audio_dir / "episodes.json"
    eps = json.loads(idx_path.read_text()) if idx_path.exists() else []
    eps = [e for e in eps if e["date"] != day.isoformat()]
    eps.append({"date": day.isoformat(), "title": narrative["headline"], "summary": " ".join(narrative.get("bullets", [])[:3]),
                "bytes": mp3.stat().st_size})
    eps = sorted(eps, key=lambda e: e["date"])[-keep:]
    keep_dates = {e["date"] for e in eps}
    for f in audio_dir.glob("*.mp3"):
        if f.stem not in keep_dates:
            f.unlink()
    idx_path.write_text(json.dumps(eps, indent=1))
    feed = audio_dir / "podcast.xml"
    feed.write_text(rss(eps, site_url), encoding="utf-8")
    return feed


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build today's audio episode and the podcast feed")
    ap.add_argument("--audio-dir", default="audio")
    ap.add_argument("--keep", type=int, default=7)
    ap.add_argument("--voice", default="en-GB-RyanNeural")
    args = ap.parse_args()
    nar = json.loads((config.LATEST / "narrative.json").read_text())
    d = date.fromisoformat(nar["date"])
    print(run(d, nar, Path(args.audio_dir), args.keep, args.voice))
