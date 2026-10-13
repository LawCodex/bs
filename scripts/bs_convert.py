#!/usr/bin/env python3
"""Convert downloaded consolidated Acts of The Bahamas (_raw/bs) to Markdown."""
import datetime, json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bs_pdfmd as pm

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
RAW = os.path.abspath(os.path.join(ROOT, "..", "_raw", "bs"))
BASE = "https://laws.bahamas.gov.bs"
PAGE = BASE + "/cms/legislation/acts_only/by-alphabetical-order.html"
JUNK = [r"^STATUTE LAW OF THE BAHAMAS$", r"^\[Original Service \d{4}\]$", r"^LRO \d+/\d{4}$", r"^[–—_-]{10,}$",
        r"^\[(Original Service|Issue) .{0,30}\]$"]


def slugify(s):
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:80].strip("-")


def q(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def front(d):
    out = ["---"]
    for k, v in d.items():
        if v is None or v == "":
            continue
        out.append(f"{k}: {v if isinstance(v, (int, float)) or k in ('date', 'last_amended', 'retrieved', 'type', 'jurisdiction', 'language', 'status') else q(v)}")
    out.append("---")
    return "\n".join(out) + "\n\n"


def pdate(s):
    try:
        return datetime.datetime.strptime(s.strip(), "%A, %d %B %Y").date().isoformat()
    except Exception:
        return None


def pdf_ok(path):
    if not os.path.exists(path):
        return False
    with open(path, "rb") as f:
        head = f.read(5)
        f.seek(max(0, os.path.getsize(path) - 4096))
        tail = f.read()
    return head == b"%PDF-" and b"%%EOF" in tail and \
        subprocess.run(["pdfinfo", path], capture_output=True).returncode == 0


def main():
    retrieved = datetime.date.today().isoformat()
    for d in ("chapters", "constitution", "acts"):
        os.makedirs(os.path.join(ROOT, d), exist_ok=True)
    items = json.load(open(os.path.join(RAW, "list.json")))
    report = {"converted": [], "gaps": []}
    used = set()
    for it in items:
        fn = it["href"].split("/")[-1]
        pdf = os.path.join(RAW, "pdf", fn)
        title = it["title"]
        if not pdf_ok(pdf):
            report["gaps"].append({"title": title, "reason": "PDF not downloadable / incomplete", "source": BASE + it["href"]})
            continue
        body, st = pm.pdf_to_md(pdf, extra_header_patterns=JUNK, anywhere_patterns=JUNK, tmpdir=RAW)
        if st["chars_per_page"] < 150:
            report["gaps"].append({"title": title, "reason": "PDF has no text layer (scan)", "source": BASE + it["href"]})
            continue
        p1 = subprocess.run(["pdftotext", "-l", "3", pdf, "-"], capture_output=True, text=True).stdout
        cm = re.search(r"\bCHAPTER\s+(\d+)([A-Z]?)\b", p1) or re.search(r"\[CH\.\s*(\d+)([A-Z]?)\b", p1)
        is_const = title.strip().lower() == "the constitution"
        if cm and not is_const:
            cap = f"{int(cm.group(1))}{cm.group(2)}"
            fname = f"ch-{int(cm.group(1)):03d}{cm.group(2).lower()}-{slugify(title)}"
            d = "chapters"
        else:
            cap = None
            fname = f"{it['number'].lower()}-{slugify(title)}" if it.get("number") else slugify(title)
            d = "constitution" if is_const else "acts"
        while (d, fname) in used:
            fname += "-2"
        used.add((d, fname))
        rel = f"{d}/{fname}.md"
        fm = {
            "title": "The Constitution of The Commonwealth of The Bahamas" if is_const else title,
            "identifier": f"Ch. {cap}" if cap else None,
            "legislation_number": it.get("number"),
            "type": "constitution" if is_const else "act",
            "jurisdiction": "bs", "language": "en",
            "date": pdate(it.get("commencement", "")),
            "status": "in_force",
            "long_title": it.get("long_title") or None,
            "category": it.get("category") or None,
            "source": PAGE,
            "source_pdf": BASE + it["href"],
            "pages": st["pages"],
            "retrieved": retrieved,
        }
        with open(os.path.join(ROOT, rel), "w", encoding="utf-8") as f:
            f.write(front(fm) + f"# {fm['title']}\n\n" + body)
        report["converted"].append({"title": title, "file": rel, "quality": st["quality"]})
        print(rel, st["quality"], flush=True)
    json.dump(report, open(os.path.join(RAW, "convert_report.json"), "w"), indent=1)
    print(len(report["converted"]), "converted;", len(report["gaps"]), "gaps")


if __name__ == "__main__":
    main()
