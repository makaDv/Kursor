"""Collect the full license texts of every third-party component we distribute.

Apache-2.0, BSD and (L)GPL require shipping the license text (and notices) with
binaries, a list of names is not enough. Run before every release build:

    server/.venv/Scripts/python scripts/collect_licenses.py

Writes:
  client/public/licenses.txt                     shown in the apps (Altro > Licenze)
  docs/legal/licenses/windows-third-party.txt    bundled with the Windows program
"""

from __future__ import annotations

import importlib.metadata as md
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NODE = ROOT / "client" / "node_modules"
SEP = "\n" + "=" * 78 + "\n"

# Java/Kotlin libraries compiled into the Android app (see padlink-native/android/build.gradle).
ANDROID_APACHE = [
    ("OkHttp", "Copyright 2019 Square, Inc."),
    ("Okio", "Copyright 2013 Square, Inc."),
    ("Kotlin Standard Library (OkHttp dependency)", "Copyright 2010-2024 JetBrains s.r.o. and Kotlin Programming Language contributors."),
    ("ZXing core", "Copyright 2007-2024 ZXing authors"),
    ("zxing-android-embedded", "Copyright (C) 2012-2024 ZXing authors, Journey Mobile"),
    ("AndroidX libraries (appcompat, core, activity, fragment, webkit, biometric, ...)", "Copyright The Android Open Source Project"),
    ("Google Play In-App Review", "Copyright Google LLC"),
]


def _license_files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.is_file() and re.match(r"(?i)(licen[sc]e|copying|notice)", p.name))


# ---- JavaScript / native app --------------------------------------------------------------
def _npm_tree(names: list[str]) -> list[str]:
    seen: list[str] = []
    stack = list(names)
    while stack:
        name = stack.pop()
        if name in seen or name == "padlink-native":
            continue
        pkg = NODE / name / "package.json"
        if not pkg.exists():
            continue
        seen.append(name)
        stack.extend(json.loads(pkg.read_text(encoding="utf-8")).get("dependencies", {}))
    return sorted(seen)


def app_licenses(apache_text: str) -> str:
    deps = json.loads((ROOT / "client" / "package.json").read_text(encoding="utf-8"))["dependencies"]
    # tailwindcss: its preflight CSS is compiled into the bundle.
    names = _npm_tree(list(deps) + ["tailwindcss"])
    out = ["PadLink app: third-party software notices", "",
           "This app includes the following open-source software, under the licenses reproduced below."]
    for name in names:
        folder = NODE / name
        meta = json.loads((folder / "package.json").read_text(encoding="utf-8"))
        files = _license_files(folder)
        out.append(SEP + f"{name} {meta.get('version', '')}  ({meta.get('license', 'see below')})\n")
        out.extend(f.read_text(encoding="utf-8", errors="replace").strip() + "\n" for f in files)
    out.append(SEP + "Android libraries (Apache License 2.0)\n")
    out.extend(f"- {n}: {c}" for n, c in ANDROID_APACHE)
    out.append("\n" + apache_text.strip())
    return "\n".join(out) + "\n"


# ---- Python / Windows program -------------------------------------------------------------
def _req_names(path: Path) -> list[str]:
    names = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if line:
            names.append(re.split(r"[<>=!~\[; ]", line)[0])
    return names


def _py_tree(roots: list[str]) -> list[md.Distribution]:
    seen: dict[str, md.Distribution] = {}
    stack = list(roots)
    while stack:
        name = stack.pop().lower().replace("_", "-")
        if name in seen or name in ("pyinstaller", "pyinstaller-hooks-contrib", "altgraph", "pefile",
                                    "setuptools", "packaging", "pywin32-ctypes"):
            continue
        try:
            dist = md.distribution(name)
        except md.PackageNotFoundError:
            continue
        seen[name] = dist
        for req in dist.requires or []:
            if "extra ==" in req:
                continue
            marker = req.split(";", 1)[1] if ";" in req else ""
            if "sys_platform" in marker and "win32" not in marker and "!=" not in marker:
                continue
            stack.append(re.split(r"[<>=!~\[; (]", req.strip())[0])
    return sorted(seen.values(), key=lambda d: d.metadata["Name"].lower())


def windows_licenses() -> str:
    roots = _req_names(ROOT / "server" / "requirements.txt") + _req_names(ROOT / "server" / "requirements-desktop.txt")
    out = ["PadLink for Windows: third-party software notices", "",
           "This program bundles the following open-source software, under the licenses reproduced below.",
           "LGPL components (pynput, pystray, zeroconf) are unmodified and kept as separate replaceable modules;",
           "source: https://github.com/moses-palmer/pynput , https://github.com/moses-palmer/pystray , "
           "https://github.com/python-zeroconf/python-zeroconf"]
    py_license = Path(sys.base_prefix) / "LICENSE.txt"
    if py_license.exists():
        out.append(SEP + f"Python {sys.version.split()[0]} (PSF License)\n")
        out.append(py_license.read_text(encoding="utf-8", errors="replace").strip())
    for tk in sorted((Path(sys.base_prefix) / "tcl").glob("t*[0-9]*/license.terms"))[:2]:
        out.append(SEP + f"{tk.parent.name} (Tcl/Tk license)\n")
        out.append(tk.read_text(encoding="utf-8", errors="replace").strip())
    for dist in _py_tree(roots):
        meta = dist.metadata
        lic = meta.get("License-Expression") or (meta.get("License") or "").splitlines()[0:1]
        lic = lic if isinstance(lic, str) else (lic[0] if lic else "")
        out.append(SEP + f"{meta['Name']} {dist.version}  ({lic[:60] or 'see below'})\n")
        files = [f for f in (dist.files or []) if re.search(r"(?i)(licen[sc]e|copying|notice|authors)", f.name)
                 and ".dist-info" in str(f)]
        for f in files:
            try:
                out.append(f"--- {f.name}\n" + Path(dist.locate_file(f)).read_text(encoding="utf-8", errors="replace").strip())
            except OSError:
                pass
    return "\n".join(out) + "\n"


def main() -> None:
    apache = md.distribution("cryptography")
    apache_file = next(f for f in apache.files or [] if f.name == "LICENSE.APACHE")
    apache_text = Path(apache.locate_file(apache_file)).read_text(encoding="utf-8")

    app = ROOT / "client" / "public" / "licenses.txt"
    app.write_text(app_licenses(apache_text), encoding="utf-8")
    win = ROOT / "docs" / "legal" / "licenses" / "windows-third-party.txt"
    win.parent.mkdir(parents=True, exist_ok=True)
    win.write_text(windows_licenses(), encoding="utf-8")
    print(f"{app} ({app.stat().st_size // 1024} KB)\n{win} ({win.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
