# PredictFlow — Full Working Project

A Groww‑style dashboard with:
- Pure HTML/CSS UI
- Minimal JS for calling a **secure Flask API proxy**
- Alpha Vantage integration for quotes/search
- Optional Groq AI summary endpoint

## Run locally

1) Install Python 3.10+
2) From the `server` folder:
```
pip install -r requirements.txt
```
3) Add your keys in `.env` (already filled if you downloaded from ChatGPT):
```
ALPHAVANTAGE_KEY=...
GROQ_API_KEY=...
```
4) Start:
```
python app.py
```
5) Open http://localhost:8000

## Notes
- Free tiers have rate limits (Alpha Vantage ~5 req/min). The server has a small in‑memory cache to help.
- Keys are never exposed to the browser; they only live in the server `.env`.
