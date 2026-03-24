╔══════════════════════════════════════════════════════╗
║          DevOps Job Hub — Setup Guide                ║
╚══════════════════════════════════════════════════════╝

REQUIREMENTS
  • Node.js installed (free from https://nodejs.org)
    Download the LTS version and install it

HOW TO START
  Mac:     Double-click  START.command
  Windows: Double-click  START.bat
  Manual:  Open terminal, cd to this folder, run: node server.js

FIRST-TIME SETUP (takes 2 minutes)
  1. Start the server (above)
  2. Browser opens automatically at http://localhost:3747
  3. Click "Setup" in the nav bar
  4. Get a free API key at https://console.anthropic.com
       → Sign up / Log in → API Keys → Create key → Copy it
  5. Paste the key in the "Anthropic API key" box and click Save
  6. Paste your resume text in the "Your resume" box and click Save
  7. Click "Today's Jobs" and press "Generate resume" on any card!

FEATURES
  ✦ Top 5 DevOps jobs scraped from LinkedIn (Ireland, entry/associate)
  ✦ Generate ATS-tailored resume for each job — Claude AI writes it
  ✦ Download tailored resume as a .txt file
  ✦ Click Apply ↗ to open the direct application page
  ✦ Track every application: stage, date, resume used, result
  ✦ Pipeline board (Saved → Applied → Interview → Offer)
  ✦ Timeline view of all applications
  ✦ Schedule daily 8am refresh

YOUR DATA
  • Applications saved in your browser (localStorage) — private to you
  • Resume saved in browser localStorage
  • API key saved in config.json (on your computer only)
  • Nothing is sent to any server except the Anthropic API for resume generation

TROUBLESHOOTING
  • Green dot in top-right nav = API ready
  • Red dot = API key missing or wrong — re-enter in Setup
  • "Server offline" = Node.js server isn't running — start it first
  • Port already in use? Edit config.json, change "port" to e.g. 3748
