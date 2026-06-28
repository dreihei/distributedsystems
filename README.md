# Blackjack Royale

Ein einfacher, modularer MVP fuer ein verteiltes Online-Blackjack-Spiel.

Die Projektidee stammt aus der Aufgaben-PDF: mehrere Clients, mehrere Server, dynamische Server-Erkennung, Game Master Rolle, State Sync, Heartbeats, Client-Reconnect-Konzept und normaler Bully-Algorithmus fuer die Wahl eines neuen Game Masters.

## Schnellstart

Mit GUI:

```powershell
python -m blackjack_royale.gui
```

In der GUI kannst du Server starten/stoppen, eine Demo-Sequenz ausfuehren und Server 3 stoppen, um den Game-Master-Ausfall zu simulieren.
Die GUI zeigt den Blackjack-Tisch grafisch mit Dealer-, Spieler- und Bot-Karten sowie einer Statuszeile fuer Werte, Einsatz und Kontostand.

Ohne GUI in drei getrennten Terminals:

```powershell
python -m blackjack_royale.server --id 1 --client-port 9001 --server-port 9101
python -m blackjack_royale.server --id 2 --client-port 9002 --server-port 9102
python -m blackjack_royale.server --id 3 --client-port 9003 --server-port 9103
```

Spielaktionen:

```powershell
python -m blackjack_royale.client --port 9003 join --player-id p1 --name Sergej
python -m blackjack_royale.client --port 9003 add-bot --bot-id bot1 --name DealerBot --amount 25
python -m blackjack_royale.client --port 9003 bet --player-id p1 --amount 50
python -m blackjack_royale.client --port 9003 start
python -m blackjack_royale.client --port 9003 hit --player-id p1
python -m blackjack_royale.client --port 9003 stand --player-id p1
python -m blackjack_royale.client --port 9003 new-round --player-id p1 --amount 50
python -m blackjack_royale.client --port 9003 tables
```

## Dokumentation

Die ausfuehrliche technische Dokumentation liegt in [docs/PROJECT_DOCUMENTATION.md](docs/PROJECT_DOCUMENTATION.md).

Eine kurze Testliste zu den Anforderungen liegt in [docs/REQUIREMENT_TESTS.md](docs/REQUIREMENT_TESTS.md).

Die Client-Server-Architektur ist in [docs/CLIENT_SERVER_ARCHITECTURE.md](docs/CLIENT_SERVER_ARCHITECTURE.md) beschrieben.

Server ohne feste IP suchen:

```powershell
python -m blackjack_royale.client discover
```
