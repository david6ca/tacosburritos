# Tacos & Burritos

A faithful open-source implementation of the **Taco vs. Burrito** card game (designed by Alex Butler, published by Blue Wasabi Games), built as a multiplayer web app.

## What it is

- Real card names, real rules, real scoring — a 1:1 reproduction of the published game's mechanics (Meal cards, Order Up cards, Foodie Fun cards, the 5-meal end condition, etc.). Card art and prose are paraphrased to avoid IP.
- Rules reference: see [`spec/SPEC.md`](spec/SPEC.md) for the full ruleset this implementation enforces.
- 2–4 players, mix of humans and AI bots (Easy / Hard difficulty).
- Real-time multiplayer over WebSocket, reconnect-safe via per-player tokens.

## Stack

- **Backend:** Python 3.11+, FastAPI, WebSockets, Pydantic v2
- **Frontend:** Vanilla JS + CSS, no build step
- **Tests:** pytest (58 tests covering engine, AI, and server)

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[test]"
.venv/bin/uvicorn server:app --reload --app-dir src
# open http://127.0.0.1:8000
```

Run tests:

```bash
.venv/bin/pytest
```

## Deployment

Live at **https://example.com/games/tacos/** — deployed on an Azure VM, served by uvicorn behind nginx (TLS via Let's Encrypt), managed as a systemd unit. The app supports being mounted under any sub-path (e.g. `/games/tacos/`) — the client derives its API and WebSocket base from `location.pathname`, so no hardcoded URLs.

## License

MIT. Game design © Alex Butler / Blue Wasabi Games — this is an unofficial fan implementation.
