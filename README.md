# Iran Crisis Monitor

A real-time intelligence dashboard for monitoring the Iran crisis - built with the kind of analytical framework used by world-class intelligence analysts.

## Live

- **Vercel**: [iran-crisis-monitor.vercel.app](https://iran-crisis-monitor.vercel.app/)

## Features

- **Live Monitoring** - Real-time news feed from OSINT accounts, Iran International, Reuters, Al Jazeera, Bellingcat, and defense analysis outlets. X/OSINT-first sourcing philosophy.
- **Polymarket Odds** - Live prediction market data with historical trend charts via CLOB API (`interval=max`).
- **Situation Overview** - Current threat level, key indicators, strategic context.
- **Order of Battle** - US, Israeli, and Iranian force dispositions.
- **Scenarios & Watch** - Probabilistic scenario analysis with key indicators to watch.
- **Economic Impact** - Oil markets, sanctions, shipping disruption analysis.
- **Analytical Frameworks** - Comparative case analysis (Iraq 2003, Libya 2011, Syria 2017), Kissinger / Brzezinski strategic frameworks, nuclear breakout timeline.
- **Situation Room Chat** - Real-time analyst chat with random CIA-style codenames. Facebook Messenger-style collapsed bar UI.

## Architecture

```
iran-dashboard/          # Perplexity hosting (CGI-bin backend)
+-- index.html           # Single-file frontend (~4200 lines)
+-- cgi-bin/
    +-- live.py          # Live data: RSS feeds + Polymarket API + CLOB history
    +-- chat.py          # Chat system: sessions, messages, heartbeat, online users

iran-vercel/             # Vercel deployment
+-- vercel.json          # Routing config
+-- api/
    +-- live.py          # BaseHTTPRequestHandler class (Vercel Python runtime)
    +-- chat.py          # Query-param routing (?action=session|messages|heartbeat|online)
+-- public/
    +-- index.html       # Frontend with Vercel-specific chatUrl() routing helper
```

## Data Sources

### News Feeds (RSS)
- Iran International (`iranintl.com/en/feed`)
- Google News (Iran-filtered)
- Reuters World News
- Al Jazeera
- Middle East Eye
- Times of Israel / Jerusalem Post
- Bellingcat
- Breaking Defense
- War on the Rocks

### OSINT Quick Links
- [@AuroraIntel](https://x.com/AuroraIntel)
- [@sentdefender](https://x.com/sentdefender)
- [@IntelCrab](https://x.com/IntelCrab)
- [@Faytuks](https://x.com/Faytuks)
- [@LOABORINGWAR](https://x.com/LOABORINGWAR)

### Prediction Markets
- Polymarket Gamma API (live odds)
- Polymarket CLOB API (price history with `interval=max&fidelity=120`)

## Design

- **Fonts**: IBM Plex Sans (display/body), JetBrains Mono (data/mono)
- **Theme**: Light mode default. Single red accent `#c41e1e`. Max-width 1440px.
- **Charts**: Chart.js 4.4.0 + chartjs-adapter-date-fns

## Local Development

The Perplexity version uses CGI-bin scripts. For the Vercel version:

```bash
cd iran-vercel
vercel dev
```

## Deployment

### Vercel
```bash
python3 deploy_vercel.py
```

## License

MIT
