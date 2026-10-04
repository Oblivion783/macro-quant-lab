"""Central Bank Decoder (Project 2): redline a statement against the previous one and score its tone.

Usage
  python -m mql.decoder --check-feeds                       # daily job: new Fed statements
  python -m mql.decoder --bank boe --url <page> --date YYYY-MM-DD
  python -m mql.decoder --evaluate                          # agreement with your hand labels

Outputs
  data/statements/<bank>/<date>.txt   statement text with its source URL on the first line
  docs/decoder/<bank>-<date>.md       redline, tone score and the changed sentences
  docs/decoder/index.md               list of all decodes

Statements are published by the central banks; the redline quotes only changed sentences and links the source.
"""
from __future__ import annotations

import argparse
import csv
import difflib
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

from . import config

SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"'])")


# ---------------------------------------------------------------- text
def clean_html(html: str | bytes) -> str:
    """Statement text from a web page. Pass bytes when you can: BeautifulSoup then reads the page's
    declared charset (servers often omit it from headers, which garbles dashes and quotes)."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
        t.decompose()
    article = soup.find(id="article") or soup.find("article") or soup.find("main")
    root = article or soup
    paras = [p.get_text(" ", strip=True) for p in root.find_all("p")]
    paras = [p for p in paras if len(p) > 40]
    text = "\n\n".join(paras) if paras else root.get_text(" ", strip=True)
    return re.sub(r"[ \t]+", " ", text).strip()


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    return [s.strip() for s in SENT.split(text) if len(s.strip()) > 3]


def word_diff(old: str, new: str) -> str:
    a, b = old.split(), new.split()
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if op == "equal":
            out.append(" ".join(a[i1:i2]))
        if op in ("delete", "replace"):
            out.append("~~" + " ".join(a[i1:i2]) + "~~")
        if op in ("insert", "replace"):
            out.append("**" + " ".join(b[j1:j2]) + "**")
    return " ".join(x for x in out if x)


def redline(old_sents: list[str], new_sents: list[str], pair_cutoff: float = 0.5) -> list[dict]:
    """Sentence-level diff. Replaced blocks are paired into 'changed' when similar enough."""
    ops: list[dict] = []
    sm = difflib.SequenceMatcher(None, old_sents, new_sents, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            ops += [{"op": "same", "text": s} for s in new_sents[j1:j2]]
            continue
        olds, news = list(old_sents[i1:i2]), list(new_sents[j1:j2])
        for n in news:
            best, score = None, 0.0
            for o in olds:
                r = difflib.SequenceMatcher(None, o, n).ratio()
                if r > score:
                    best, score = o, r
            if best is not None and score >= pair_cutoff:
                ops.append({"op": "changed", "old": best, "text": n, "diff": word_diff(best, n), "similarity": round(score, 2)})
                olds.remove(best)
            else:
                ops.append({"op": "added", "text": n})
        ops += [{"op": "removed", "text": o} for o in olds]
    return ops


# ---------------------------------------------------------------- tone
def tone(text: str, lexicon: dict) -> dict:
    t = text.lower()
    hits = {"hawkish": {}, "dovish": {}}
    totals = {}
    for side in ("hawkish", "dovish"):
        total = 0
        for phrase, w in (lexicon.get(side) or {}).items():
            n = len(re.findall(r"\b" + re.escape(phrase.lower()) + r"\b", t))
            if n:
                hits[side][phrase] = n
                total += n * w
        totals[side] = total
    h, d = totals["hawkish"], totals["dovish"]
    score = 0.0 if h + d == 0 else round((h - d) / (h + d), 3)
    return {"hawkish": h, "dovish": d, "score": score, "hits": hits}


def label_from_delta(delta: float, band: float = 0.1) -> str:
    return "hawkish" if delta > band else "dovish" if delta < -band else "neutral"


# ---------------------------------------------------------------- storage
def bank_dir(bank: str) -> Path:
    return config.STATEMENTS / bank


def save_statement(bank: str, day: str, url: str, text: str) -> Path:
    p = bank_dir(bank) / f"{day}.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"Source: {url}\n\n{text}\n", encoding="utf-8")
    return p


def load_statement(p: Path) -> tuple[str, str]:
    raw = p.read_text(encoding="utf-8")
    first, _, body = raw.partition("\n")
    return first.replace("Source:", "").strip(), body.strip()


def previous(bank: str, day: str) -> Path | None:
    files = sorted(f for f in bank_dir(bank).glob("*.txt") if f.stem < day)
    return files[-1] if files else None


# ---------------------------------------------------------------- render
def render(bank_name: str, bank: str, day: str, url: str, prev_day: str | None, prev_url: str | None,
           ops: list[dict], t_new: dict, t_old: dict | None) -> str:
    changed = [o for o in ops if o["op"] != "same"]
    delta = None if t_old is None else round(t_new["score"] - t_old["score"], 3)
    lines = [f"# {bank_name} · {day}", "",
             f"Source: [{url}]({url})" + (f" · compared with [{prev_day}]({prev_url})" if prev_day else ""), ""]
    lines += ["| | This statement | Previous | Change |", "|---|---:|---:|---:|"]
    lines.append(f"| Tone score (−1 dovish … +1 hawkish) | {t_new['score']:+.2f} | "
                 f"{'–' if t_old is None else format(t_old['score'], '+.2f')} | {'–' if delta is None else format(delta, '+.2f')} |")
    lines.append(f"| Sentences changed | {len(changed)} | | |")
    lines += ["", f"**Read:** {'first statement on file' if delta is None else label_from_delta(delta)} versus the previous statement "
              "(lexicon score; check it against your own reading).", ""]
    if changed:
        lines += ["## What changed", "", "~~struck~~ = removed, **bold** = added", ""]
        for o in changed:
            if o["op"] == "changed":
                lines.append(f"- {o['diff']}")
            elif o["op"] == "added":
                lines.append(f"- **Added:** {o['text']}")
            else:
                lines.append(f"- ~~Removed: {o['text']}~~")
    hits = ", ".join(f"{k} ×{v}" for k, v in {**t_new["hits"]["hawkish"]}.items()) or "none"
    dhits = ", ".join(f"{k} ×{v}" for k, v in {**t_new["hits"]["dovish"]}.items()) or "none"
    lines += ["", "## Words behind the score", "", f"- Hawkish: {hits}", f"- Dovish: {dhits}", "",
              "## Market reaction", "", "_Fill in after the release: 2-year yield, curve and currency moves "
              "(from the monitor), and what was priced the day before._", ""]
    return "\n".join(lines)


def decoder_index(docs_dir: Path) -> str:
    files = sorted((p for p in docs_dir.glob("*-20*.md")), key=lambda p: p.stem.split("-", 1)[1], reverse=True)
    lines = ["# Central Bank Decoder", "", "Each page redlines a statement against the previous one and scores its tone. "
             "Method and evaluation: see the repo README.", ""]
    lines += [f"- [{p.stem}]({p.name})" for p in files]
    return "\n".join(lines) + "\n"


def decode(bank: str, day: str, url: str, text: str | None = None, cfg: dict | None = None,
           docs_dir: Path | None = None, publish: bool = True) -> dict:
    cfg = cfg or config.load_yaml("decoder.yaml")
    if text is None:
        from .sources import _get

        text = clean_html(_get(url).content)
    save_statement(bank, day, url, text)
    prev = previous(bank, day)
    lex = cfg["lexicon"]
    t_new = tone(text, lex)
    result = {"bank": bank, "date": day, "url": url, "tone": t_new["score"], "previous": None}
    if prev:
        prev_url, prev_text = load_statement(prev)
        t_old = tone(prev_text, lex)
        ops = redline(split_sentences(prev_text), split_sentences(text))
        result.update(previous=prev.stem, delta=round(t_new["score"] - t_old["score"], 3),
                      changed=sum(1 for o in ops if o["op"] != "same"))
    else:
        prev_url, t_old, ops = None, None, [{"op": "added", "text": s} for s in split_sentences(text)]
    if publish:
        docs_dir = docs_dir or (config.DOCS / "decoder")
        docs_dir.mkdir(parents=True, exist_ok=True)
        md = render(cfg["banks"][bank]["name"], bank, day, url, prev.stem if prev else None, prev_url, ops, t_new, t_old)
        (docs_dir / f"{bank}-{day}.md").write_text(md, encoding="utf-8")
        (docs_dir / "index.md").write_text(decoder_index(docs_dir), encoding="utf-8")
    return result


# ---------------------------------------------------------------- feeds
def parse_feed(xml_text: str | bytes) -> list[dict]:
    if isinstance(xml_text, str):
        xml_text = xml_text.lstrip("\ufeff \r\n\t").encode("utf-8")
    root = ET.fromstring(xml_text.lstrip(b"\xef\xbb\xbf \r\n\t"))
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = it.findtext("pubDate")
        try:
            d = parsedate_to_datetime(pub).date().isoformat() if pub else None
        except (TypeError, ValueError):
            d = None
        items.append({"title": title, "link": link, "date": d})
    return items


def check_feeds(cfg: dict | None = None, publish: bool = True) -> list[dict]:
    from .sources import _get

    cfg = cfg or config.load_yaml("decoder.yaml")
    done = []
    for bank, b in cfg["banks"].items():
        if not b.get("feed"):
            continue
        items = [i for i in parse_feed(_get(b["feed"]).content)
                 if b.get("title_match", "").lower() in i["title"].lower() and i["date"]]
        for i in sorted(items, key=lambda x: x["date"]):
            if not (bank_dir(bank) / f"{i['date']}.txt").exists():
                done.append(decode(bank, i["date"], i["link"], cfg=cfg, publish=publish))
    return done


# ---------------------------------------------------------------- evaluation
def evaluate(labels_csv: Path | None = None, cfg: dict | None = None) -> dict:
    """Compare the lexicon's read with your hand labels (bank,date,label: hawkish|neutral|dovish)."""
    cfg = cfg or config.load_yaml("decoder.yaml")
    labels_csv = labels_csv or (config.STATEMENTS / "labels.csv")
    with open(labels_csv, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    agree, total, misses = 0, 0, []
    for r in rows:
        cur = bank_dir(r["bank"]) / f"{r['date']}.txt"
        prev = previous(r["bank"], r["date"])
        if not cur.exists() or prev is None:
            continue
        d = tone(load_statement(cur)[1], cfg["lexicon"])["score"] - tone(load_statement(prev)[1], cfg["lexicon"])["score"]
        model = label_from_delta(d)
        total += 1
        if model == r["label"].strip().lower():
            agree += 1
        else:
            misses.append({"bank": r["bank"], "date": r["date"], "you": r["label"], "model": model, "delta": round(d, 3)})
    return {"labelled": total, "agree": agree, "agreement": round(agree / total, 3) if total else None, "misses": misses}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Central Bank Decoder")
    ap.add_argument("--check-feeds", action="store_true")
    ap.add_argument("--bank")
    ap.add_argument("--url")
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--evaluate", action="store_true")
    ap.add_argument("--no-publish", action="store_true", help="store and score only; do not write docs/")
    a = ap.parse_args()
    if a.evaluate:
        print(evaluate())
    elif a.check_feeds:
        import json
        from datetime import timezone

        status = {"ran": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        try:
            status["decoded"] = check_feeds(publish=not a.no_publish)
        except Exception as e:  # recorded so failures are visible without the Actions log
            status["error"] = f"{type(e).__name__}: {e}"[:500]
        config.LATEST.mkdir(parents=True, exist_ok=True)
        (config.LATEST / "decoder_status.json").write_text(json.dumps(status, indent=1))
        print(status)
        if "error" in status:
            raise SystemExit(1)
    elif a.bank and a.url:
        datetime.strptime(a.date, "%Y-%m-%d")
        print(decode(a.bank, a.date, a.url, publish=not a.no_publish))
    else:
        ap.print_help()
