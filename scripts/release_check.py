"""Pre-release gate: run before every store upload (build.ps1 -Release runs it too).

    server/.venv/Scripts/python scripts/release_check.py [--skip-audit]

Fails (exit 1) when:
  * a public file still contains a placeholder ([EMAIL DI CONTATTO], example.com, ...);
  * versions differ (client/package.json, server, Windows installer);
  * the Android app is debuggable-by-WebView, allows backups or cleartext traffic;
  * signing keys or keystore.properties are tracked by git;
  * npm audit / pip-audit report known vulnerabilities (skip offline with --skip-audit).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_FILES = [
    "docs/legal/PRIVACY.md", "docs/legal/TERMS.md", "SECURITY.md",
    "client/src/components/Help.tsx", "site/template.html", "site/index.body.html", "site/faq.body.html",
]
PLACEHOLDER = re.compile(r"\[(?:NOME|NAME|EMAIL|CONTACT|URL)[^\]]*\]|example\.com|<URL[^>]*>|href=\"#\">(?:Google Play|App Store|Microsoft Store)")

problems: list[str] = []
warnings: list[str] = []


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def check_placeholders() -> None:
    for rel in PUBLIC_FILES:
        for n, line in enumerate(read(rel).splitlines(), 1):
            if m := PLACEHOLDER.search(line):
                problems.append(f"{rel}:{n}: placeholder {m.group(0)!r} (fill release.json, run apply_release_info.py)")
    rel = json.loads(read("release.json"))
    for key, value in rel.items():
        if not key.startswith("_") and isinstance(value, str) and value.startswith("["):
            problems.append(f"release.json: {key} not filled")


def check_versions() -> None:
    v = json.loads(read("client/package.json"))["version"]
    found = {
        "server/kursor/__init__.py": re.search(r'__version__ = "([^"]+)"', read("server/kursor/__init__.py")),
        "packaging/windows/kursor.iss": re.search(r'#define AppVersion "([^"]+)"', read("packaging/windows/kursor.iss")),
        "packaging/windows/version_info.txt": re.search(r"'ProductVersion', '([^']+)'", read("packaging/windows/version_info.txt")),
    }
    for rel, m in found.items():
        if not m or m.group(1) != v:
            problems.append(f"{rel}: version {m.group(1) if m else '?'} != client/package.json {v}")
    if "appVersion" not in read("client/android/app/build.gradle"):
        problems.append("client/android/app/build.gradle: versionName/versionCode not derived from package.json")


def check_android() -> None:
    cap = read("client/capacitor.config.ts")
    if re.search(r"webContentsDebuggingEnabled:\s*true", cap):
        problems.append("client/capacitor.config.ts: webContentsDebuggingEnabled must be false")
    manifest = read("client/android/app/src/main/AndroidManifest.xml")
    if 'android:allowBackup="false"' not in manifest:
        problems.append("AndroidManifest.xml: android:allowBackup must be false")
    if 'android:usesCleartextTraffic="false"' not in manifest:
        problems.append("AndroidManifest.xml: android:usesCleartextTraffic must be false")
    if "minifyEnabled true" not in read("client/android/app/build.gradle"):
        warnings.append("client/android/app/build.gradle: R8 (minifyEnabled) is off for release")


def check_secrets_not_tracked() -> None:
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.splitlines()
    for f in tracked:
        if re.search(r"(keystore\.properties|\.jks|\.keystore|\.p12|\.pfx|\.p8|secret\.key)$", f):
            problems.append(f"{f}: signing key / secret tracked by git")


def check_audits() -> None:
    npm = subprocess.run("npm audit --omit=dev --audit-level=low", cwd=ROOT / "client", shell=True,
                         capture_output=True, text=True)
    if npm.returncode != 0:
        problems.append("npm audit: vulnerabilities found (cd client; npm audit --omit=dev)")
    py = ROOT / "server" / ".venv" / "Scripts" / "python.exe"
    if not py.exists():
        py = Path(sys.executable)
    pip = subprocess.run([str(py), "-m", "pip_audit", "-r", str(ROOT / "server" / "requirements.lock")],
                         capture_output=True, text=True)
    if "No module named pip_audit" in pip.stderr:
        problems.append("pip-audit not installed: server/.venv/Scripts/python -m pip install pip-audit")
    elif pip.returncode != 0:
        problems.append("pip-audit: vulnerabilities found (" + (pip.stdout.strip().splitlines() or ["?"])[-1] + ")")


def check_updates() -> None:
    text = read("server/kursor/updates.py")
    if re.search(r"^UPDATE_URL: str \| None = None", text, re.M):
        warnings.append("server/kursor/updates.py: signed updates for the website installer are off (UPDATE_URL)")


def main() -> int:
    check_placeholders()
    check_versions()
    check_android()
    check_secrets_not_tracked()
    check_updates()
    if "--skip-audit" not in sys.argv:
        check_audits()
    for w in warnings:
        print("WARN ", w)
    for p in problems:
        print("FAIL ", p)
    print("RELEASE CHECK:", "FAILED" if problems else "OK")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
