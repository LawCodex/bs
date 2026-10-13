#!/usr/bin/env python3
"""Fetch the current consolidated Acts of The Bahamas from laws.bahamas.gov.bs
(Office of the Attorney General / Law Revision Centre).

For each letter A-Z, posts the "Acts by alphabetical order" point-in-time form
(today's date), collects the principal Act rows (current consolidated PDF link,
legislation number, long title, category, commencement), downloads the PDFs
into _raw/bs/pdf/.
"""
import datetime, json, os, re, string, subprocess, sys, time, html as htmlmod
import requests
from bs4 import BeautifulSoup

BASE = "https://laws.bahamas.gov.bs"
PAGE = BASE + "/cms/legislation/acts_only/by-alphabetical-order.html"
UA = "LawCodex/1.0 (+https://github.com/LawCodex)"
RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "_raw", "bs")
DELAY = 1.0
s = requests.Session()
s.headers["User-Agent"] = UA


def req(method, url, **kw):
    for i in range(5):
        try:
            r = s.request(method, url, timeout=300, **kw)
            if r.status_code in (200, 404, 403):
                return r
        except requests.RequestException as e:
            print("  retry", url, e, file=sys.stderr)
        time.sleep(5 * (i + 1))
    raise RuntimeError("failed " + url)


def pdf_ok(path):
    if not os.path.exists(path):
        return False
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        head = f.read(5)
        f.seek(max(0, size - 4096))
        tail = f.read()
    if head != b"%PDF-" or b"%%EOF" not in tail:
        return False
    return subprocess.run(["pdfinfo", path], capture_output=True).returncode == 0


def download(url, path):
    """Stream to path.part, resuming with HTTP Range after broken connections."""
    part = path + ".part"
    total = None
    for attempt in range(8):
        have = os.path.getsize(part) if os.path.exists(part) else 0
        headers = {"Range": f"bytes={have}-"} if have else {}
        try:
            with s.get(url, headers=headers, stream=True, timeout=300) as r:
                if r.status_code == 200:
                    have = 0
                    total = int(r.headers.get("content-length", 0)) or None
                    mode = "wb"
                elif r.status_code == 206:
                    m = re.search(r"/(\d+)$", r.headers.get("content-range", ""))
                    total = int(m.group(1)) if m else total
                    mode = "ab"
                elif r.status_code == 416:
                    break
                else:
                    return r.status_code
                with open(part, mode) as f:
                    for chunk in r.iter_content(1 << 16):
                        f.write(chunk)
            if total is None or os.path.getsize(part) >= total:
                break
        except requests.RequestException as e:
            print("  resume", url, e, file=sys.stderr, flush=True)
            time.sleep(10 * (attempt + 1))
    if os.path.exists(part) and (total is None or os.path.getsize(part) == total):
        os.replace(part, path)
        return 200
    return -1


def popover(td):
    d = td.find(attrs={"data-bs-content": True}) if td else None
    return d["data-bs-content"] if d else ""


def parse(html):
    soup = BeautifulSoup(html, "lxml")
    out = []
    for tr in soup.select("tbody.tablebg > tr, tbody.tablebg tr"):
        a = tr.find("a", class_="npWrap", href=re.compile(r"/LEGISLATION/PRINCIPAL/"))
        if not a or tr.find_parent("tr"):
            continue
        notes = popover(tr.find("td", class_="displayNotes"))
        num = re.search(r"Legislation Number:\s*([\w-]+)", notes)
        lt = notes.split("<hr class='notes'>", 1)[1] if "<hr" in notes else ""
        cat = BeautifulSoup(popover(tr.find("td", class_="category")), "lxml").get_text("; ", strip=True)
        com = popover(tr.find("td", class_="commencement"))
        out.append({"title": a.get_text(" ", strip=True).replace("\xa0", " ").strip(),
                    "href": a["href"], "number": num.group(1) if num else "",
                    "long_title": BeautifulSoup(lt, "lxml").get_text(" ", strip=True),
                    "category": cat, "commencement": BeautifulSoup(com, "lxml").get_text(" ", strip=True)})
    return out


def main():
    os.makedirs(os.path.join(RAW, "pdf"), exist_ok=True)
    lp = os.path.join(RAW, "list.json")
    if os.path.exists(lp):
        items = json.load(open(lp))
    else:
        today = datetime.date.today().isoformat() + " 00:00:00"
        req("GET", PAGE)
        items, seen = [], set()
        for L in string.ascii_uppercase:
            r = req("POST", PAGE, data={"pointintime_post": today, "submit4": L,
                                        "pointintime_post_alpha": today})
            rows = parse(r.text)
            for x in rows:
                if x["href"] not in seen:
                    seen.add(x["href"])
                    items.append(x)
            print(L, len(rows), flush=True)
            time.sleep(DELAY)
        json.dump(items, open(lp, "w"), indent=1)
    print(len(items), "items", flush=True)
    for n, it in enumerate(items):
        fn = it["href"].split("/")[-1]
        p = os.path.join(RAW, "pdf", fn)
        if pdf_ok(p):
            continue
        code = download(BASE + it["href"], p)
        print(n, fn, pdf_ok(p), code, flush=True)
        time.sleep(DELAY)


if __name__ == "__main__":
    main()
