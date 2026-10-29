# ChessDep

ChessDep is a Dockerized Russian-language chess and virtual-skins application. The project is editable as a regular Python project in PyCharm. It uses FastAPI, SQLite (in a named Docker volume), SQLAlchemy and python-chess. All currency changes, random case and upgrade results, and legal chess moves are handled on the server.

## Идея игры

ChessDep сочетает классические онлайн-шахматы с ограниченным риском прямо во время партии. Перед своим ходом игрок может потратить один из десяти депов и попытаться усилить любую свою фигуру, кроме короля и ферзя. Пешка тоже может быть источником: например, пешка ценностью 1 может стать ладьёй ценностью 5 с шансом 1/5, то есть 20%. Шанс всегда равен ценности исходной фигуры, делённой на ценность цели: конь → ферзь — 3/9 (33,33%), ладья → ферзь — 5/9 (55,56%). Цель должна быть строго ценнее и того же цвета. При успехе фигура усиливается, при неудаче сгорает и исчезает с доски. За ход разрешён один деп, а за партию — десять.

Между партиями игрок собирает косметические скины фигур и досок: выигрывает их в кейсах, экипирует, обменивает на маркете и вкладывает в апгрейд. Косметика не меняет силу фигур и правила шахмат.

## Start on Windows or Linux

Install Docker Desktop on Windows (with its WSL 2 backend) or Docker Engine plus the Compose plugin on Linux. Nothing else is required on the host. From this directory run:

```text
cp .env.example .env
docker compose up --build
```

PowerShell users can copy the sample with `Copy-Item .env.example .env`; the startup command is still `docker compose up --build`. Open [http://localhost:8080](http://localhost:8080). Stop with `docker compose down`; the named `chessdep-data` volume keeps the SQLite database. `docker compose down -v` removes that data.

An administrator can be assigned only from the container command line:

```text
docker compose exec chessdep python -m app.manage promote LOGIN
```

Role assignment is not exposed through the player API.

## Tests

```text
docker compose run --rm chessdep python -m unittest discover -s tests -v
```

## Current implementation

Implemented: registration and login with Argon2 password hashing; signed HttpOnly sessions; virtual balances and a ledger; daily bonus; Genesis skins and case opening; inventory and equipment; server-randomized upgrade; player market with 5% seller commission; gifts; public leaderboard; admin-only user listing, balance adjustment and action log; a chessboard backed by server-validated legal moves, including castling, en passant, promotion, checkmate and stalemate; server-side dep eligibility, chance, limits, both-outcome check restriction and random result. Dep values are pawn 1, knight/bishop 3, rook 5 and queen 9; any own pawn, knight, bishop or rook can be the source, and queen and king cannot. The UI is responsive down to mobile widths and the app runs in Linux containers hosted by either Windows or Linux Docker.

This is the first runnable foundation and does not yet implement the complete requested product. In particular, live PvP matchmaking/invitations, clocks and timeout adjudication, real-time spectator/chat/replay, full dep animation, collection/case authoring and release workflows, listing history and filters, password changes, complete profile statistics, and comprehensive admin workflows remain to be built. Case reel animation, current settings and some UI actions are also presentation-level stubs. Do not use it as a production economy or public multiplayer service yet.
