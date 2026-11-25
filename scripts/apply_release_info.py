"""Writes the public release details from release.json into the files users see.

    server/.venv/Scripts/python scripts/apply_release_info.py

Fill release.json first. Placeholders such as [EMAIL DI CONTATTO] are replaced in
the legal texts, SECURITY.md, the in-app support address and the website. Values
still in [brackets] are left alone, so the script can be run as often as needed;
scripts/release_check.py then refuses to release while any placeholder remains.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _filled(value: str) -> bool:
    return bool(value) and not value.startswith("[")


def main() -> int:
    rel = json.loads((ROOT / "release.json").read_text(encoding="utf-8"))
    name, contact = rel["developer_name"], rel["contact_email"]
    security, support = rel["security_email"], rel["support_email"]

    tokens = {
        "[NOME / RAGIONE SOCIALE]": name,
        "[NAME / COMPANY]": name,
        "[EMAIL DI CONTATTO]": contact,
        "[CONTACT EMAIL]": contact,
        "[EMAIL DI SICUREZZA]": security,
    }
    changed: list[str] = []

    def rewrite(rel_path: str, fn) -> None:
        path = ROOT / rel_path
        text = path.read_text(encoding="utf-8")
        new = fn(text)
        if new != text:
            path.write_text(new, encoding="utf-8", newline="")
            changed.append(rel_path)

    def replace_tokens(text: str) -> str:
        for token, value in tokens.items():
            if _filled(value):
                text = text.replace(token, value)
        # The "replace these before publishing" note goes once nothing is left to replace.
        if not any(t in text for t in tokens):
            text = re.sub(r"^> \*\*Prima di pubblicare:\*\*.*\n\n?", "", text, flags=re.M)
        return text

    for doc in ("docs/legal/PRIVACY.md", "docs/legal/TERMS.md", "SECURITY.md"):
        rewrite(doc, replace_tokens)

    if _filled(support):
        rewrite("client/src/components/Help.tsx",
                lambda t: re.sub(r"export const SUPPORT_EMAIL = '[^']*'", lambda _m: f"export const SUPPORT_EMAIL = '{support}'", t))
        rewrite("site/template.html", lambda t: re.sub(r'href="mailto:[^"]*"', lambda _m: f'href="mailto:{support}"', t))

    links = {"Google Play": rel["play_url"], "Microsoft Store": rel["ms_store_url"],
             "Scarica per Windows": rel["windows_download_url"]}

    def site_links(text: str) -> str:
        for label, url in links.items():
            if _filled(url):
                text = re.sub(rf'href="[^"]*"(>{re.escape(label)}<)', lambda m, u=url: f'href="{u}"{m.group(1)}', text)
        return text

    rewrite("site/index.body.html", site_links)
    print("Updated:", ", ".join(changed) if changed else "nothing (fill release.json first)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
