# Blackjack Royale - Nachrichtenprotokoll

Alle Nachrichten werden als eine JSON-Zeile ueber TCP gesendet.

## Allgemeines Format

```json
{
  "type": "JOIN_TABLE",
  "sender": "client",
  "payload": {},
  "timestamp": 1710000000.0
}
```

## Client zu Server

`LIST_TABLES`

```json
{"table_id": "main"}
```

`JOIN_TABLE`

`player_id` wird nicht mehr vom Client vergeben, sondern automatisch vom Server (z.B. `p1`, `p2`, ...).

```json
{"table_id": "main", "name": "Sergej"}
```

Die Antwort enthaelt die zugewiesene ID, die fuer alle weiteren Nachrichten (PLACE_BET, HIT, ...) verwendet werden muss:

```json
{"table": {...}, "player_id": "p1"}
```

`ADD_BOT`

Fuegt einen Bot zum Tisch hinzu. Bots ziehen automatisch bis mindestens 16.

```json
{"table_id": "main", "bot_id": "bot1", "name": "DealerBot", "amount": 25}
```

`PLACE_BET`

```json
{"table_id": "main", "player_id": "p1", "amount": 50}
```

`START_ROUND`

```json
{"table_id": "main"}
```

`NEW_ROUND`

Setzt fuer einen Spieler einen neuen Einsatz und startet direkt die naechste Runde.

```json
{"table_id": "main", "player_id": "p1", "amount": 50}
```

`HIT`

```json
{"table_id": "main", "player_id": "p1"}
```

`STAND`

```json
{"table_id": "main", "player_id": "p1"}
```

## Server zu Server

`SERVER_ANNOUNCE`

Ein Server stellt sich einem Peer vor.

`HEARTBEAT`

Lebensmeldung zwischen Servern.

`STATE_SYNC`

Game Master repliziert Tabellenzustand. Enthaelt u.a. `turn_deadline` (Unix-Timestamp, wann der aktuelle
menschliche Spieler automatisch "Stand" gesetzt wird) und `turn_timeout` (konfigurierte Dauer in Sekunden,
Standard 30s).

`ELECTION`

Teil des normalen Bully-Algorithmus.

`COORDINATOR`

Gewinner der Election teilt neue Game Master ID mit.
