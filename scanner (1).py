#!/usr/bin/env python3
"""Daily tender scanner (free version).
Source 1: Government Advertising Agency (GAA) "All Tenders" page.
Writes docs/tenders.json, which the dashboard (docs/index.html) reads.
More sources are added as separate functions that return the same kind of items."""
import datetime as dt, hashlib, io, json, re, time
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

OUT = Path("docs/tenders.json")
GAA = "https://gaa.go.ke/index.php/all-tenders"
BASE = "https://gaa.go.ke/"   # document links on GAA are relative to the site root
UA = {"User-Agent": "TenderTracker/1.0 (daily check of public tender notices)"}
EAT = dt.timezone(dt.timedelta(hours=3))
NOW = dt.datetime.now(EAT)
MON = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
MAX_NEW_PDFS = 30   # notices read per run
KEEP_DAYS = 30      # keep closed tenders this long


def get(url):
    r = requests.get(url, headers=UA, timeout=45)
    r.raise_for_status()
    return r


def parse_dates(text):
    found = set()
    pats = [(r"(\d{1,2})(?:st|nd|rd|th)?[\s,]+(?:of\s+)?([A-Za-z]{3,9})[\s,]+(\d{4})", "dmy"),
            (r"([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", "mdy")]
    for pat, order in pats:
        for a, b, y in re.findall(pat, text):
            d, m = (a, b) if order == "dmy" else (b, a)
            mm = MON.get(m[:3].lower())
            if not mm:
                continue
            try:
                found.add(dt.date(int(y), mm, int(d)))
            except ValueError:
                pass
    return sorted(found)


def find_time(text):
    t = re.sub(r"\s+", " ", text)
    for m in re.finditer(r"clos|deadline|opening", t, re.I):
        seg = t[m.start(): m.start() + 250]
        x = re.search(r"(\d{1,2})\s*[.:]\s*(\d{2})\s*([ap])\.?\s*m", seg, re.I)
        if x:
            h, mi, ap = int(x.group(1)), int(x.group(2)), x.group(3).lower()
            return h % 12 + (12 if ap == "p" else 0), mi
        x = re.search(r"\b(\d{2})(\d{2})\s*hours", seg, re.I)
        if x:
            return int(x.group(1)), int(x.group(2))
    return None


def classify(text):
    """Work out AGPO eligibility from the notice text."""
    t = re.sub(r"\s+", " ", text.lower())

    def reserved(word):
        return bool(re.search(r"(reserved|exclusive\w*|set aside|restricted)[^.;]{0,70}" + word, t)
                    or re.search(word + r"[^.;()]{0,25}\(agpo\)", t)
                    or re.search(r"agpo[^.;]{0,50}" + word, t))
    women = reserved(r"\bwomen\b")
    youth = reserved(r"\byouth")
    pwd = reserved(r"persons? with disabilit|\bpwds?\b")
    is_open = bool(re.search(r"open (national|tender|competitive|international)|national open", t))
    el = "Women" if women else "Youth" if youth else "PWD" if pwd else "Open" if is_open else "Unknown"
    tags = []
    if women and is_open:
        tags.append("Mixed eligibility")
    if el in ("Open", "Unknown") and "agpo" in t:
        tags.append("AGPO mentioned")
    return el, tags


def pdf_text(url):
    from pypdf import PdfReader
    r = get(url)
    if len(r.content) > 6_000_000:
        return ""
    rd = PdfReader(io.BytesIO(r.content))
    return " ".join((p.extract_text() or "") for p in rd.pages[:6])


def find_ref(text):
    t = re.sub(r"\s+", " ", text)
    for m in re.finditer(r"(?:tender|ref(?:erence)?|rfq|rfp|eoi)\s*(?:no\.?|number|ref\.?)?\s*[:.\-]?\s*([A-Z0-9][A-Z0-9/\-._]{5,45})", t, re.I):
        g = m.group(1).rstrip(".-_")
        if re.search(r"\d", g) and re.search(r"[/\-]", g):
            return g
    return ""


def kind_tags(title, entity):
    tags, s = [], (title + " " + entity).lower()
    if re.search(r"registration of suppliers|pre-?qualification|e-registration", s):
        tags.append("Supplier registration")
    if re.search(r"expression of interest|consultan|request for proposal", s):
        tags.append("Consultancy")
    if re.search(r"school|college|universit|institute|polytechnic|academy", s):
        tags.append("Education")
    return tags


def scrape_gaa(pages=3):
    items = []
    for p in range(pages):
        url = GAA if p == 0 else f"{GAA}?page={p}"
        soup = BeautifulSoup(get(url).text, "html.parser")
        table = soup.find("table")
        if not table:
            break
        heads = [th.get_text(" ", strip=True).lower() for th in table.find_all("th")]

        def col(*keys):
            for i, h in enumerate(heads):
                if any(k in h for k in keys):
                    return i
        ci = {"desc": col("description"), "ent": col("entity"), "docs": col("notice", "document"), "date": col("closing")}
        if None in ci.values():
            raise RuntimeError(f"GAA table layout changed, columns found: {heads}")
        for tr in table.find_all("tr"):
            td = tr.find_all("td")
            if len(td) <= max(ci.values()):
                continue
            links = [(a.get_text(" ", strip=True), urljoin(BASE, a["href"].strip())) for a in td[ci["docs"]].find_all("a", href=True)]
            notice = next((u for t, u in links if re.search(r"notice|advert|invitation", t, re.I)), links[0][1] if links else "")
            items.append({"title": td[ci["desc"]].get_text(" ", strip=True),
                          "entity": td[ci["ent"]].get_text(" ", strip=True),
                          "notice": notice, "date_text": td[ci["date"]].get_text(" ", strip=True),
                          "docs": len(links),
                          "links": [{"name": t, "url": u} for t, u in links]})
        time.sleep(1)
    return items


def main():
    old = json.loads(OUT.read_text()) if OUT.exists() else {"tenders": []}
    prev = {t["id"]: t for t in old.get("tenders", [])}
    sources, fresh = {}, {}
    try:
        items = scrape_gaa()
        sources["GAA"] = {"ok": True, "count": len(items)}
    except Exception as e:
        items, sources["GAA"] = [], {"ok": False, "error": str(e)[:300]}
    pdfs = 0
    for it in items:
        tid = "GAA-" + hashlib.sha1((it["entity"] + "|" + it["title"][:150]).encode()).hexdigest()[:8]
        dates = parse_dates(it["date_text"])
        upcoming = [d for d in dates if d >= NOW.date()]
        day = upcoming[0] if upcoming else (dates[-1] if dates else None)
        old_t = prev.get(tid)
        el, tags, tm = (old_t["el"], [t for t in old_t.get("tags", []) if t not in kind_tags(old_t["title"], old_t["entity"]) and t != "Closing time not stated"], None) if old_t else ("Unknown", [], None)
        summary, ref = (old_t.get("summary", ""), old_t.get("ref", "")) if old_t else ("", "")
        need = (not old_t or (not old_t.get("summary") and "Picture notice, not read" not in old_t.get("tags", []))) and it["notice"] and pdfs < MAX_NEW_PDFS
        if need:
            try:
                text = pdf_text(it["notice"])
                el, tags = classify(text)
                if not text.strip():
                    tags = ["Picture notice, not read"]
                tm = find_time(text)
                summary = re.sub(r"\s+", " ", text).strip()[:1500]
                ref = find_ref(text)
                pdfs += 1
                time.sleep(1)
            except Exception:
                tags = ["Notice not read"]
        if old_t and old_t.get("time_known"):
            h, m = map(int, old_t["close"][11:16].split(":"))
            tm = (h, m)
        if day:
            h, m = tm or (10, 0)
            close = dt.datetime(day.year, day.month, day.day, h, m, tzinfo=EAT).isoformat()
        else:
            close = None
        if not close:
            continue
        all_tags = kind_tags(it["title"], it["entity"]) + tags + ([] if tm else ["Closing time not stated"])
        fresh[tid] = {"id": tid, "title": it["title"], "entity": it["entity"], "el": el, "close": close,
                      "time_known": bool(tm), "src": "GAA", "url": GAA, "notice": it["notice"],
                      "tags": all_tags, "docs_list": it["links"], "summary": summary, "ref": ref, "first_seen": old_t["first_seen"] if old_t else NOW.date().isoformat()}
    merged = dict(prev) if not items else {k: v for k, v in prev.items() if k not in fresh}
    merged.update(fresh)
    cutoff = (NOW - dt.timedelta(days=KEEP_DAYS)).isoformat()
    tenders = sorted((t for t in merged.values() if t["close"] >= cutoff), key=lambda t: t["close"])
    OUT.parent.mkdir(exist_ok=True)
    out = json.dumps({"generated": NOW.isoformat(timespec="minutes"), "sources": sources,
                      "tenders": tenders}, indent=1, ensure_ascii=False)
    out = out.replace("gaa.go.ke/index.php/sites/", "gaa.go.ke/sites/")   # repair links saved by the earlier version
    OUT.write_text(out)
    print(f"Saved {len(tenders)} tenders. Sources: {sources}")


if __name__ == "__main__":
    main()
