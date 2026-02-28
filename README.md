# Iran Crisis Monitor

Real-time intelligence dashboard for monitoring the Iran crisis.

**Live**: [iran-crisis-monitor.vercel.app](https://iran-crisis-monitor.vercel.app/)

## Structure

```
api/          # Vercel serverless functions
  live.py     # Live data: RSS feeds + Polymarket API + CLOB history
  chat.py     # Chat system: sessions, messages, heartbeat, online users
public/       # Static assets served by Vercel
  index.html  # Single-file frontend (~4200 lines)
perplexity/   # Perplexity hosting variant (CGI-bin backend)
  cgi-bin/
    live.py
    chat.py
vercel.json   # Vercel routing config
```

## Data Sources

- **News**: Iran International, Google News, Reuters, Al Jazeera, Middle East Eye, Bellingcat, Breaking Defense, War on the Rocks
- **OSINT**: @AuroraIntel, @sentdefender, @IntelCrab, @Faytuks, @LOABORINGWAR
- **Markets**: Polymarket Gamma API (live odds) + CLOB API (price history)

## Deployment

Vercel deployment from CLI:
```bash
python3 deploy_vercel.py
```

To sync `public/index.html` to this repo, run the "Sync HTML from Vercel" GitHub Action from the Actions tab.

## Local Dev (Beginner-Friendly)

This repo can run fully locally. These helper scripts are safe and do not deploy anything:

```bash
# one-time (or whenever you want to refresh from deployed frontend)
./scripts/dev-setup.sh

# start local dev server
./scripts/dev-start.sh
```

Then open `http://localhost:3000`.

Notes:
- `dev-setup.sh` only overwrites `public/index.html` when it still looks like the placeholder.
- If you already changed `public/index.html`, it will skip by default.
- Use `./scripts/dev-setup.sh --force` only when you intentionally want to replace your local HTML.

## Design

- IBM Plex Sans (display/body), JetBrains Mono (data)
- Light mode default, single red accent `#c41e1e`
- Chart.js 4.4.0 + chartjs-adapter-date-fns
- Max-width 1440px
