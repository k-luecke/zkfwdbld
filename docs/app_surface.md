# App Surface

## Goal
Provide a lightweight local application surface for zkfwdbld that can be run today and later wrapped into a downloadable desktop shell.

## Current Shape
- Node server: `app/server.mjs`
- Static UI: `app/static/`
- Snapshot builder: `app/generate_packet_json.mjs`
- Tauri shell: `src-tauri/`
- Default data source: `artifacts/polsia-demo-packet`
- Primary API: `GET /api/packet`

## Why This Exists
The repo already produces good packet and bundle artifacts, but reading raw markdown and JSON file-by-file creates friction during demos and operator review.
This app adds:
- a stable browser entrypoint
- packet-level navigation
- handoff-first browsing
- per-item report and artifact inspection
- a Tauri-compatible static snapshot for desktop packaging

## Local Run
```sh
npm run app:dev
```

Or rebuild the packet and then launch the viewer:
```sh
npm run app:packet
```

The default URL is `http://127.0.0.1:4173`.

## Tauri Desktop Shell

Generate the packet snapshot used by the desktop shell:
```sh
npm run app:sync
```

Run the Tauri desktop app in development mode:
```sh
npm run tauri:dev
```

The desktop shell uses:
- static frontend assets from `app/static`
- generated packet snapshot at `app/static/generated/packet.json`
- Tauri configuration in `src-tauri/tauri.conf.json`

Build the release desktop binary and Debian package:
```sh
npm run tauri:build
```

On Ubuntu/WSL, Tauri needs the GTK/WebKit development stack installed:
```sh
sudo apt-get install -y pkg-config pkgconf libwebkit2gtk-4.1-dev build-essential curl wget file libxdo-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev
```

## Downloadable Path
This app is intentionally thin.
The browser and desktop modes now share the same UI contract, and Tauri can use
the generated packet snapshot directly. That gives the repo a clean path toward:
- desktop builds
- native installers
- richer local data-loading flows later
