# Security policy

PadLink controls a computer remotely, so we take security reports seriously.

## Reporting a vulnerability

Report it privately through GitHub: **[Report a vulnerability](https://github.com/makaDv/Kursor/security/advisories/new)** (Security tab of the repository). Please include:
- a description of the issue and its impact;
- the steps to reproduce it (versions of the PC program and of the app);
- if possible, a proof of concept.

Please do not disclose the issue publicly until a fix is available. We acknowledge reports within **7 days** and aim to release a fix within **90 days**. We credit reporters who wish to be named.

## Supported versions

Only the latest version published on the stores, and the latest installer of the Windows program, receive security fixes.

## Scope

- In scope: pairing and authentication, TLS and certificate pinning, the WebSocket protocol, input handling, the Windows program, and the Android and iOS apps.
- Out of scope: attacks that require an already-paired device or full control of the user's PC, physical access to an unlocked phone, and social engineering.
