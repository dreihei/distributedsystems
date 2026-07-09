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

`DOUBLE`

Verdoppelt den Einsatz der aktiven Hand und gibt genau eine Karte. Nur mit genau zwei Karten und ausreichendem Guthaben erlaubt.

```json
{"table_id": "main", "player_id": "p1"}
```

`SPLIT`

Teilt ein Paar in zwei Haende. Nur mit Paar auf den ersten beiden Karten und ausreichendem Guthaben erlaubt.

```json
{"table_id": "main", "player_id": "p1"}
```

`REFILL_BALANCE`

Fuellt das Guthaben eines Spielers auf (Standard: 1000).

```json
{"table_id": "main", "player_id": "p1", "amount": 1000}
```

### Fehlerantworten

Verletzt eine Aktion die Spielregeln oder den Tabellenzustand, antwortet der Server mit einem Fehler und dem aktuellen Snapshot:

```json
{"error": "round already running", "table": {...}}
```

Wichtige Faelle:

- `unknown table ...`: Die Tabelle existiert auf diesem Server nicht. Tabellen werden nur ueber `JOIN_TABLE` erzeugt (und nur auf dem Cluster-Koordinator; andere Server leiten den Join dorthin weiter).
- `not your turn`: Ein anderer Spieler ist am Zug.
- `cannot change the bet during a round`, `round already running`, `round in progress; join again after this round`: Phasen-Verstoesse.

### Snapshot-Felder (Auszug)

Jede Antwort mit `table` enthaelt u.a.:

- `state_version`: steigt bei jeder Zustandsaenderung.
- `lineage`: UUID des Tabellen-Erzeugungsereignisses. Versionen sind nur innerhalb derselben Lineage vergleichbar.
- `turn_remaining`: verbleibende Sekunden des aktuellen Zuges (vom Server berechnet, unabhaengig von der Client-Uhr).
- `turn_deadline` / `turn_timeout`: Unix-Timestamp und konfigurierte Dauer (Standard 30s) des Turn-Timers.

## Server zu Server

`SERVER_ANNOUNCE`

Ein Server stellt sich einem Peer vor. Die Antwort enthaelt den lokalen Peer und alle bekannten Tabellen.

`HEARTBEAT`

Lebensmeldung zwischen Servern, zugleich Anti-Entropy-Kanal. Payload:

```json
{
  "peer": {"server_id": 1, "host": "...", "server_port": 9101, "client_port": 9001},
  "tables": {"main": {"lineage": "...", "version": 12}}
}
```

Die Antwort enthaelt volle Snapshots aller Tabellen, fuer die der Antwortende Game Master ist und bei denen der Sender eine aeltere Version (oder eine andere Lineage) gemeldet hat. Verpasste `STATE_SYNC`-Nachrichten heilen sich dadurch selbst. Peers ohne Heartbeat-Antwort werden nach dem Timeout aus der Peer-Liste entfernt.

`STATE_SYNC`

Game Master repliziert den vollstaendigen Tabellenzustand (inklusive Deck, `lineage`, `created_at`, `state_version`). Der Empfaenger uebernimmt ihn nur, wenn er nach den Lineage-Regeln gewinnt (gleiche Lineage: hoehere Version; Fork: aeltere `created_at`).

`GET_TABLES`

Liefert alle lokalen Tabellenzustaende. Der Wahlsieger nutzt das fuer Read-Repair, bevor er sich als neuer Game Master meldet.

`ELECTION`

Teil des normalen Bully-Algorithmus.

`COORDINATOR`

Gewinner der Election teilt die neue Game Master ID mit. Der neue Master erhoeht die `state_version` und re-synct alle Tabellen.
