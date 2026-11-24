"""Builds the public website (site/dist): landing page, privacy, terms, FAQ.

    server/.venv/Scripts/python scripts/build_site.py

Upload site/dist to any static host (GitHub Pages of a separate PUBLIC repo,
Netlify, Cloudflare Pages...). The store listings need the privacy URL:
<your-site>/privacy.html. The private source repository is never published.
"""

from __future__ import annotations

import html
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "site"
OUT = SRC / "dist"


def inline(text: str) -> str:
    t = html.escape(text, quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![*\w])_(.+?)_(?!\w)", r"<em>\1</em>", t)
    t = re.sub(r"\*(.+?)\*", r"<em>\1</em>", t)
    t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
    t = re.sub(r"\[(.+?)\]\((https?://[^)]+)\)", r'<a href="\2" rel="noopener">\1</a>', t)
    return t


def md_to_html(md: str) -> str:
    """Small Markdown subset used by docs/legal: headings, paragraphs, lists, tables, quotes."""
    out: list[str] = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.strip() == "---":
            if line.strip() == "---":
                out.append("<hr>")
            i += 1
            continue
        if line.startswith("> "):
            i += 1  # authoring notes ("Prima di pubblicare...") are not published
            continue
        m = re.match(r"^(#{1,4}) (.+)", line)
        if m:
            level = len(m.group(1))
            out.append(f"<h{level}>{inline(m.group(2))}</h{level}>")
            i += 1
            continue
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                if not re.match(r"^\|[\s:|-]+\|$", lines[i]):
                    rows.append([c.strip() for c in lines[i].strip("|").split("|")])
                i += 1
            head, *body = rows
            out.append("<div class='table'><table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head)
                       + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in body)
                       + "</tbody></table></div>")
            continue
        if re.match(r"^\s*([-*]|\d+\.) ", line):
            ordered = bool(re.match(r"^\s*\d+\.", line))
            items = []
            while i < len(lines) and re.match(r"^\s*([-*]|\d+\.) ", lines[i]):
                items.append(re.sub(r"^\s*([-*]|\d+\.) ", "", lines[i]))
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items) + f"</{tag}>")
            continue
        para = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#|\||>|\s*[-*] |\s*\d+\. |---)", lines[i]):
            para.append(lines[i])
            i += 1
        out.append(f"<p>{inline(' '.join(para))}</p>")
    return "\n".join(out)


def page(title: str, body: str) -> str:
    tpl = (SRC / "template.html").read_text(encoding="utf-8")
    return tpl.replace("{{title}}", html.escape(title)).replace("{{body}}", body)


def main() -> None:
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    shutil.copy(SRC / "style.css", OUT / "style.css")
    icon = ROOT / "client" / "public" / "icons" / "icon.svg"
    if icon.exists():
        shutil.copy(icon, OUT / "icon.svg")
    (OUT / "index.html").write_text(page("PadLink", (SRC / "index.body.html").read_text(encoding="utf-8")), encoding="utf-8")
    (OUT / "faq.html").write_text(page("PadLink · FAQ", (SRC / "faq.body.html").read_text(encoding="utf-8")), encoding="utf-8")
    for name, title in (("PRIVACY", "PadLink · Privacy"), ("TERMS", "PadLink · Termini d'uso")):
        md = (ROOT / "docs" / "legal" / f"{name}.md").read_text(encoding="utf-8")
        (OUT / f"{name.lower()}.html").write_text(page(title, md_to_html(md)), encoding="utf-8")
    print("Site written to", OUT)


if __name__ == "__main__":
    main()
