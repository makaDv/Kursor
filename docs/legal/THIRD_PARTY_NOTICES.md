# Third-party notices

PadLink includes the following open-source components. Each one remains under its own license, and the full license texts are distributed with the respective packages.

## Phone apps (Android / iOS) and web app

| Component | License |
|---|---|
| React, React DOM | MIT |
| Capacitor (core, android, ios) | MIT |
| Tailwind CSS | MIT |
| OkHttp, Okio (Android) | Apache-2.0 |
| ZXing core, zxing-android-embedded (Android) | Apache-2.0 |
| AndroidX libraries incl. biometric (Android) | Apache-2.0 |
| Google Play In-App Review (Android) | Apache-2.0 / Play Core terms |

## Windows program

| Component | License | Note |
|---|---|---|
| CPython | PSF License | Bundled runtime |
| FastAPI, Starlette, Pydantic | MIT | |
| Uvicorn | BSD-3-Clause | |
| websockets | BSD-3-Clause | |
| PyJWT | MIT | |
| cryptography | Apache-2.0 / BSD-3-Clause | Includes OpenSSL (Apache-2.0) |
| mss | MIT | |
| Pillow | MIT-CMU (HPND) | |
| qrcode | BSD-3-Clause | |
| **zeroconf** | **LGPL-2.1-or-later** | mDNS announcement; see the LGPL note below |
| ifaddr | MIT | |
| **pynput** | **LGPL-3.0** | See the LGPL note below |
| **pystray** | **LGPL-3.0** | See the LGPL note below |
| Tcl/Tk (tkinter) | Tcl/Tk License (BSD-style) | |

### LGPL components (pynput, pystray, zeroconf)

These libraries are used without modification. The Windows installer uses PyInstaller's *one-folder* layout. Under the LGPL, the user may replace these libraries with a modified version. To do so, swap the corresponding modules in the installation folder, or rebuild with `packaging/windows/build.ps1`.

- Source code: https://github.com/moses-palmer/pynput and https://github.com/moses-palmer/pystray
- License text: https://www.gnu.org/licenses/lgpl-3.0.html

PadLink's own source code is licensed under the Apache License 2.0 (see `LICENSE`) and is not covered by the LGPL.

> Regenerate the full list before every release:
> `pip-licenses --with-urls --format=markdown` (Python) and `npx license-checker --summary` (client).
