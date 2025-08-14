
# IG Daily Report Telegram Bot (AI Vision) — VS Code Edition

Production-ready Telegram bot to parse Instagram screenshots and send daily reports in a fixed order. 
Now with **clear structure**, **rich comments**, and **VS Code** configs.

## Setup

```bash
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env  # fill in your keys
python src/main.py
```

## Format & Lint
- `black . && isort .`
- `pytest` to run tests
