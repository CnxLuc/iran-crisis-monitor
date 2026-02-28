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

## Design

- IBM Plex Sans (display/body), JetBrains Mono (data)
- Light mode default, single red accent `#c41e1e`
- Chart.js 4.4.0 + chartjs-adapter-date-fns
- Max-width 1440px
