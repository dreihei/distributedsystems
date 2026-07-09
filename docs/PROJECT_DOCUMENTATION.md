# Blackjack Royale - Projektdokumentation

## 1. Projektziel

Blackjack Royale ist ein verteilter MVP fuer ein Online-Blackjack-Spiel. Das System besteht aus mehreren Clients und mehreren Serverinstanzen. Pro Blackjack-Tabelle gibt es genau einen Game Master Server. Dieser Game Master ist autoritativ fuer Spielaktionen wie Karten ziehen, Einsaetze verarbeiten und Rundenfortschritt.

Die Backup-Server halten den Spielzustand synchron. Wenn der aktuelle Game Master ausfaellt, erkennen die uebrigen Server den Ausfall ueber Heartbeats und waehlen mit einem normalen Bully-Algorithmus einen neuen Game Master.

Wichtig: Die Election ist nicht die Konsistenzlogik fuer den Game State. Die Election bestimmt nur, welcher Server nach einem Ausfall autoritativ wird. Die eigentliche Wiederherstellung des Spielstands kommt aus der State-Synchronisierung, der Anti-Entropy ueber Heartbeats und dem Read-Repair beim Amtsantritt des neuen Game Masters.

## 2. Aktueller Umfang

Umgesetzt:

- Blackjack-Kernlogik ohne externe Abhaengigkeiten, inklusive Double, Split, 3:2-Blackjack-Auszahlung und Turn-Timer.
- Serverseitige Regeldurchsetzung: unzulaessige Aktionen (z.B. Einsatz aendern waehrend der Runde, Split ohne Paar) werden mit einer Fehlerantwort abgelehnt.
- TCP-Kommunikation fuer Client-Server und Server-Server.
- Mehrere Serverinstanzen auf unterschiedlichen Ports.
- UDP-Broadcast-Discovery, damit Clients Server im LAN ohne feste IP finden.
- Peer-Erkennung zwischen Servern auf benachbarten lokalen Ports.
- Game Master Rolle pro Tabelle; Tabellen werden nur vom Cluster-Koordinator erzeugt.
- State Sync vom Game Master zu Backup-Servern mit Lineage-ID und Versionsnummer.
- Anti-Entropy: Heartbeats reparieren verpasste Syncs automatisch.
- Normaler Bully-Algorithmus fuer Game-Master-Failover mit Read-Repair vor dem Amtsantritt.
- CLI-Client und Tkinter-GUI fuer Demo und Tests.

Noch nicht umgesetzt (naechste Ausbaustufen, siehe Abschnitt 12):

- Persistente Speicherung auf Festplatte.
- Vollstaendige Client-Reconnect-Session mit Token.
- Bot-Ersatz nach Client-Timeout.
- Integrationstests fuer Election und Failover mit mehreren laufenden Serverprozessen.

## 3. Ordnerstruktur

```text
blackjack_royale/
  __init__.py
  blackjack.py     Spiellogik (kein Netzwerk)
  client.py        CLI-Client
  config.py        Laufzeitkonfiguration (Ports, Timeouts)
  discovery.py     UDP-Discovery-Helfer
  gui.py           Tkinter-Oberflaeche
  messages.py      JSON-Zeilen-Protokoll
  server.py        Verteilter Server (Client- und Peer-Port)
  state.py         Clusterzustand, Snapshot-Regeln
docs/
  CLIENT_SERVER_ARCHITECTURE.md
  PROJECT_DOCUMENTATION.md
  PROTOCOL.md
  REQUIREMENT_TESTS.md
  RUNBOOK.md
scripts/
  run_server_1.ps1 / .sh
  run_server_2.ps1 / .sh
  run_server_3.ps1 / .sh
  demo_commands.ps1 / .sh
tests/
  test_blackjack.py
  test_messages.py
  test_server.py
  test_state.py
README.md
Blackjack_Royale_Pipeline.md
```

## 3.1 GUI

Die GUI wird mit folgendem Befehl gestartet:

```powershell
python -m blackjack_royale.gui
```

Sie ist ein lokales Control Panel fuer die Demo. Man kann damit:

- Server 1, 2 und 3 starten und stoppen (`Fail GM` stoppt Server 3 fuer die Failover-Demo).
- Spielbefehle senden: Join Table, Place Bet, Add Bot, Start Round, Hit, Stand, Double, Split, New Round.
- Eine Demo-Sequenz ausfuehren.
- Antworten und Serverlogs in einem Ausgabefeld sehen.

Die GUI verwendet dieselbe Client-Kommunikation wie der CLI-Client. Dadurch bleibt die Spiellogik an einer Stelle und die GUI ist nur eine Bedienoberflaeche. Zusaetzlich pollt die GUI alle 2 Sekunden den Tabellenzustand, damit alle offenen GUIs denselben Stand anzeigen.

## 4. Modul: `blackjack_royale.blackjack`

Dieses Modul enthaelt die reine Spiellogik. Es kennt keine Sockets, keine Server und keine Netzwerk-Nachrichten.

### Regeldurchsetzung

Unzulaessige Aktionen werfen eine `RuleError`-Exception. Der Server uebersetzt sie zentral in eine Fehlerantwort an den Client. Dadurch gelten die Regeln fuer jeden Client, unabhaengig davon, ob die GUI Buttons deaktiviert oder nicht. Beispiele:

- Einsatz aendern waehrend `phase == "playing"`.
- `START_ROUND` waehrend eine Runde laeuft.
- Beitritt neuer Spieler mitten in einer Runde (Reconnect mit bekannter ID bleibt erlaubt).
- Double mit mehr als zwei Karten oder ohne ausreichendes Guthaben.
- Split ohne Paar auf den ersten beiden Karten.

### Wichtige Klassen

`Card`

- Repraesentiert eine einzelne Karte mit Rang und Farbe.
- Hat `label()` fuer lesbare Ausgabe sowie `to_dict()`/`from_dict()` fuer State-Synchronisierung.

`Player`

- Speichert Spieler-ID, Name, Guthaben, Einsatz, Handkarten, Split-Hand und Verbindungsstatus.
- `balance` ist der echte Kontostand; `bet` ist der aktive Einsatz der laufenden Runde.
- `split_hand`, `split_bet`, `split_stood`, `on_split_hand` bilden die zweite Hand nach einem Split ab.
- `connected` ist fuer spaetere Reconnect-Logik vorbereitet.

`Table`

- Repraesentiert eine Blackjack-Tabelle mit Deck, Spielern, Dealer-Hand, Phase, Game Master ID und State-Version.
- `state_version` steigt bei jeder relevanten Zustandsaenderung (`bump()`).
- `lineage` (UUID) und `created_at` identifizieren das Erzeugungsereignis der Tabelle. Zwei Tabellen mit gleicher `table_id` aber verschiedener `lineage` sind unabhaengige Forks; Versionsnummern sind nur innerhalb einer Lineage vergleichbar.
- `turn_deadline` haelt den Zeitpunkt, zu dem der aktive menschliche Spieler automatisch auf Stand gesetzt wird.

### Wichtige Funktionen

`new_deck()` erstellt und mischt ein normales 52-Karten-Deck.

`hand_value(cards)` berechnet den Blackjack-Wert; Asse zaehlen zuerst 11 und werden bei Bedarf auf 1 reduziert.

`is_blackjack(cards)` und `is_bust(cards)` sind kleine Regel-Helfer.

`hand_outcome(cards, bet, dealer_hand, blackjack_eligible=True)` bewertet eine Hand gegen den Dealer und liefert `(outcome, payout, balance_delta)`. Diese eine Funktion wird sowohl fuer die Ergebnisanzeige (`build_result`) als auch fuer die Abrechnung (`settle_bets`) verwendet - Anzeige und Kontostand koennen dadurch nicht auseinanderlaufen. Split-Haende sind nicht Blackjack-berechtigt.

### Wichtige Table-Methoden

`join(player_id, name)` fuegt einen Spieler hinzu oder markiert einen vorhandenen Spieler wieder als verbunden. Neue Spieler koennen nur zwischen den Runden beitreten.

`place_bet(player_id, amount)` setzt einen Einsatz (nur zwischen den Runden; begrenzt auf das Guthaben; Guthaben 0 verlangt vorher `refill`).

`start_round()` startet eine neue Runde: neues Deck, Startkarten fuer Dealer und Spieler. Spieler mit 21 auf der Startkarte werden automatisch auf Stand gesetzt.

`hit(player_id)` gibt eine Karte. Bei Bust oder 21 wird zur Split-Hand gewechselt (falls vorhanden und noch offen) oder zum naechsten Spieler weitergegangen.

`stand(player_id)` beendet die aktive Hand. Mit offener Split-Hand wird zuerst auf diese gewechselt.

`double(player_id)` verdoppelt den Einsatz (maximal bis zum Guthaben), gibt genau eine Karte und beendet die Hand. Nur mit genau zwei Karten erlaubt.

`split(player_id)` teilt ein Paar in zwei Haende mit eigenem Einsatz. Nur mit Paar auf den ersten beiden Karten und ausreichendem Guthaben erlaubt.

`finish_dealer()` laesst den Dealer ziehen, bis er mindestens 17 hat (Standard-Regel: steht auf 17). Danach wird die Runde beendet, `last_result` gebaut und abgerechnet. Die naechste Runde wird nicht automatisch gestartet - der Client startet sie mit `NEW_ROUND`.

`add_bot(bot_id, name, default_bet)` fuegt einen Bot hinzu. Bots ziehen unter 16 und bleiben ab 16 stehen; sie spielen automatisch in jeder aktiven Runde.

`refill(player_id, amount)` fuellt das Guthaben auf (fuer Spieler ohne Chips).

`snapshot()` liefert die Client-Sicht (lesbare Kartenlabels, Werte, `turn_remaining` in Sekunden). `to_dict()`/`from_dict()` serialisieren den vollstaendigen Zustand inklusive Deck fuer den State Sync.

### Abrechnungsregel

- Einsatz setzen aendert den Kontostand noch nicht.
- Bei Gewinn steigt `balance` um den Einsatz, bei Blackjack um das 1,5-fache (3:2).
- Bei Verlust sinkt `balance` um den Einsatz.
- Bei Push bleibt `balance` gleich.
- Split-Haende werden separat mit `split_bet` abgerechnet.

## 5. Modul: `blackjack_royale.messages`

Dieses Modul definiert das gemeinsame Nachrichtenformat.

Alle Nachrichten sind JSON-Zeilen. Eine Nachricht endet mit `\n`. Dadurch kann `asyncio` einfach mit `readline()` lesen.

### Message-Felder

- `type`: Nachrichtentyp, zum Beispiel `JOIN_TABLE` oder `HEARTBEAT`.
- `sender`: Absender, zum Beispiel Server-ID oder `client`.
- `payload`: Nutzdaten als Dictionary.
- `timestamp`: Zeitpunkt der Erstellung.

### Warum JSON-Zeilen?

- Einfach lesbar.
- Ohne externe Bibliotheken.
- Plattformunabhaengig.
- Gut fuer kleine TCP-Protokolle geeignet.

## 6. Modul: `blackjack_royale.state`

Dieses Modul enthaelt den Zustand des Serverclusters.

### Peer

Ein Peer ist ein bekannter anderer Server. Gespeichert werden Server-ID, Host, Server-Port, Client-Port und `last_seen` fuer Heartbeat-Timeouts. Peers, die laenger als das Heartbeat-Timeout nicht antworten, werden aus der Peer-Liste entfernt (und beim naechsten Announce wieder aufgenommen).

### ClusterState

`ClusterState` ist der lokale Blick eines Servers auf den Cluster: eigene Server-ID und Ports, bekannte Peers, bekannte Blackjack-Tabellen.

`ensure_table(table_id)`

- Erstellt eine Tabelle mit neuer Lineage. Wird nur vom Cluster-Koordinator im `JOIN_TABLE`-Pfad aufgerufen (siehe Abschnitt 7).
- Als initialer Game Master wird die hoechste bekannte aktive Server-ID verwendet.

`apply_snapshot(snapshot)`

- Uebernimmt einen synchronisierten Tabellenzustand nach folgenden Regeln:
  - Gleiche Lineage: Der Snapshot gewinnt nur mit hoeherer `state_version`.
  - Verschiedene Lineage (Fork): Es gewinnt deterministisch die aeltere Tabelle (`created_at`, bei Gleichstand die kleinere Lineage). Eine versehentlich erzeugte leere Fork kann das echte Spiel damit nicht ueberschreiben - auf keinem Server.

## 7. Modul: `blackjack_royale.server`

Dieses Modul ist der Kern des verteilten Systems.

Jeder Serverprozess startet zwei TCP-Server (Client-Port und Peer-Port) sowie einen UDP-Discovery-Port:

```powershell
python -m blackjack_royale.server --id 3 --client-port 9003 --server-port 9103
```

### Client-Nachrichten

`LIST_TABLES`, `JOIN_TABLE`, `ADD_BOT`, `PLACE_BET`, `START_ROUND`, `NEW_ROUND`, `HIT`, `STAND`, `DOUBLE`, `SPLIT`, `REFILL_BALANCE` (Details im `docs/PROTOCOL.md`).

Verletzt eine Aktion die Spielregeln, antwortet der Server mit `{"error": ..., "table": ...}` statt die Aktion auszufuehren.

### Tabellen-Erzeugung (nur ueber JOIN auf dem Koordinator)

Nur `JOIN_TABLE` darf eine Tabelle erzeugen, und nur der Cluster-Koordinator (hoechste aktive Server-ID) fuehrt die Erzeugung aus:

1. Kennt der angefragte Server die Tabelle nicht und ist er nicht Koordinator, leitet er den Join an den Koordinator weiter.
2. Alle anderen Aktionen auf unbekannte Tabellen werden mit `unknown table` abgelehnt.

Dadurch kann kein Server nebenbei eine zweite, konkurrierende Tabelle mit derselben ID anlegen (Split-Brain). Sollte es durch Netzwerkpartitionen trotzdem zu zwei Lineages kommen, loest die Regel in `apply_snapshot` den Konflikt deterministisch auf.

### Server-Server-Nachrichten

`SERVER_ANNOUNCE`

- Server stellt sich einem anderen Server vor. Antwort enthaelt lokalen Peer und bekannte Tabellen.

`HEARTBEAT`

- Regelmaessige Lebensmeldung. Die Payload enthaelt den eigenen Peer sowie eine Zusammenfassung der eigenen Tabellenstaende (`lineage` + `state_version` pro Tabelle).
- Die Antwort enthaelt volle Snapshots aller Tabellen, fuer die der Antwortende Game Master ist und bei denen der Sender hinterherhinkt (Anti-Entropy). Ein verpasster `STATE_SYNC` heilt sich damit innerhalb von etwa einer Sekunde selbst.

`STATE_SYNC`

- Game Master sendet den aktuellen Tabellenzustand an Backup-Server.

`GET_TABLES`

- Liefert alle lokalen Tabellenzustaende. Wird vom Wahlsieger fuer das Read-Repair vor dem Amtsantritt verwendet.

`ELECTION` / `COORDINATOR`

- Normaler Bully-Algorithmus (siehe unten).

### Game Master Logik

Nur der Game Master darf spielveraendernde Aktionen direkt ausfuehren.

Wenn ein Client eine Aktion an einen Backup-Server sendet:

1. Backup prueft die Game Master ID der Tabelle.
2. Backup sucht den Peer mit dieser ID.
3. Backup leitet die Aktion an den Game Master weiter.
4. Die Antwort wird an den Client zurueckgegeben.

Dadurch bleibt der Game State einfach: Es gibt nur eine autoritative Schreibstelle.

### State Sync

Nach jeder relevanten Spielaktion ruft der Game Master `sync_table()` auf. Dabei wird `table.to_dict()` an alle bekannten Peers geschickt. Backup-Server speichern den Snapshot mit `apply_snapshot()`.

Der Sync ist best-effort (Timeouts werden verworfen). Verpasste Syncs werden durch die Anti-Entropy im Heartbeat nachgeholt.

### Heartbeat

Der aktuelle MVP verwendet folgende Werte (in `config.py`):

- Heartbeat-Intervall: 1 Sekunde.
- Game Master gilt als ausgefallen, wenn ca. 4 Sekunden kein gueltiger Kontakt besteht.
- Election Timeout: 3 Sekunden.
- Turn Timeout: 30 Sekunden.

Heartbeats erkennen Ausfaelle, entfernen tote Peers aus der Peer-Liste und transportieren die Anti-Entropy-Reparatur. Sie veraendern den Spielzustand nur, indem sie verpasste Snapshots nachliefern.

### Normaler Bully-Algorithmus mit Read-Repair

Der Ablauf im Code:

1. Ein Server erkennt, dass der Game Master nicht erreichbar ist.
2. Er sendet `ELECTION` an alle bekannten Server mit hoeherer ID.
3. Antwortet ein hoeherer Server mit `OK`, wartet der Server auf eine Coordinator-Entscheidung.
4. Hoehere Server starten selbst eine Election.
5. Wenn kein hoeherer Server antwortet, wird der aktuelle Server Coordinator.
6. Vor dem Amtsantritt holt sich der neue Coordinator per `GET_TABLES` die Tabellenzustaende aller erreichbaren Peers und uebernimmt jeweils den frischesten Stand (Read-Repair). Ein Backup, das den letzten Sync des alten Masters verpasst hat, kann so keinen veralteten Zustand wiederbeleben.
7. Der neue Coordinator setzt sich als Game Master, erhoeht die `state_version` (damit der Wechsel ueberall ankommt), sendet `COORDINATOR` an alle Peers und re-synct alle Tabellen.

Das ist ein normaler Bully-Algorithmus, nicht die vereinfachte Variante.

## 8. Modul: `blackjack_royale.client`

Der Client ist ein kleiner Kommandozeilen-Client fuer Tests und Demo:

```powershell
python -m blackjack_royale.client --port 9003 join --name Sergej
python -m blackjack_royale.client --port 9003 bet --player-id p1 --amount 50
python -m blackjack_royale.client --port 9003 start
python -m blackjack_royale.client --port 9003 hit --player-id p1
python -m blackjack_royale.client --port 9003 stand --player-id p1
python -m blackjack_royale.client --port 9003 double --player-id p1
python -m blackjack_royale.client --port 9003 split --player-id p1
python -m blackjack_royale.client --port 9003 new-round --player-id p1 --amount 50
python -m blackjack_royale.client --port 9003 refill --player-id p1
python -m blackjack_royale.client --port 9003 tables
python -m blackjack_royale.client discover
```

Der Client sendet genau eine Nachricht, wartet auf genau eine Antwort und beendet sich danach. Ohne `--port` sucht er zuerst per UDP-Discovery nach einem Server.

## 8.1 Modul: `blackjack_royale.gui`

Dieses Modul enthaelt eine Tkinter-Oberflaeche. Tkinter gehoert zur Python-Standardbibliothek und benoetigt deshalb keine zusaetzlichen Pakete.

### Serversteuerung

Die GUI verwaltet drei lokale Serverprozesse:

- Server 1: Client-Port 9001, Peer-Port 9101
- Server 2: Client-Port 9002, Peer-Port 9102
- Server 3: Client-Port 9003, Peer-Port 9103

Jeder Server wird als eigener Python-Prozess gestartet. Beim Stoppen sendet die GUI ein normales Terminate-Signal.

### Spielbefehle

Die Buttons senden dieselben Nachrichtentypen wie der CLI-Client: `Join Table`, `Place Bet`, `Add Bot`, `Start Round`, `New Round`, `Hit`, `Stand`, `Double`, `Split`, `Refresh` (= `LIST_TABLES`). Die Buttons werden passend zum Spielzustand aktiviert und deaktiviert; die eigentliche Regelpruefung passiert aber immer auf dem Server.

### Rundenablauf

Sobald alle Spieler fertig sind oder bust gehen, zieht der Dealer (bis mindestens 17), die Einsaetze werden abgerechnet und der Kontostand angepasst. Das Ergebnis bleibt als `last_result` sichtbar. Die naechste Runde startet nicht automatisch: Die GUI fragt per Popup, ob eine neue Runde mit dem letzten Einsatz gestartet werden soll (`NEW_ROUND`). Hat ein Spieler keine Chips mehr, bietet die GUI eine Auffuellung an (`REFILL_BALANCE`).

### Kohaerente Anzeige

- Die GUI pollt alle 2 Sekunden den Tabellenzustand und aktualisiert die Anzeige nur, wenn der Snapshot neuer ist (gleiche Lineage: hoehere `state_version`; neue Lineage: immer uebernehmen).
- Der Turn-Timer basiert auf `turn_remaining` aus dem Server-Snapshot (verbleibende Sekunden) und nicht auf einem Vergleich der Rechneruhren.
- Schlaegt ein Befehl fehl, weil gerade eine Election laeuft oder der angefragte Server die Tabelle nicht kennt, probiert die GUI automatisch die anderen laufenden Server-Ports.

### Grafische Tischansicht

Die GUI zeichnet den aktuellen Tisch auf einem Canvas: Dealer-Karten und -Wert, Spieler- und Bot-Karten (inklusive Split-Hand), Einsatz und Kontostand, aktueller Game Master, Ergebnis der letzten Runde. Die Karten werden direkt mit Tkinter gezeichnet; es werden keine Bilddateien benoetigt.

## 9. Startskripte

Fuer Windows PowerShell:

```powershell
.\scripts\run_server_1.ps1
.\scripts\run_server_2.ps1
.\scripts\run_server_3.ps1
.\scripts\demo_commands.ps1
```

Fuer macOS/Linux:

```sh
sh scripts/run_server_1.sh
sh scripts/run_server_2.sh
sh scripts/run_server_3.sh
sh scripts/demo_commands.sh
```

Die Server muessen in getrennten Terminals gestartet werden.

## 10. Demo fuer Failover

1. Server 1, 2 und 3 starten.
2. Einige Sekunden warten, damit sich die Server finden.
3. Demo-Kommandos ausfuehren.
4. Server 3 beenden (in der GUI: `Fail GM`), falls Server 3 der Game Master ist.
5. Nach einigen Sekunden startet eine Election.
6. Der hoechste erreichbare Server holt sich per Read-Repair den frischesten Spielstand und wird neuer Game Master.
7. Weitere Client-Kommandos an einen aktiven Server senden - der Spielstand bleibt erhalten.

## 11. Designentscheidungen

### Keine externen Abhaengigkeiten

Das Projekt nutzt nur die Python-Standardbibliothek. Dadurch ist es reproduzierbar und laeuft auf Windows, macOS und Linux.

### Asyncio statt Threads

`asyncio` macht viele gleichzeitige Verbindungen moeglich, ohne fuer jede Verbindung manuell Threads zu verwalten.

### JSON statt binaerem Protokoll

JSON ist fuer ein Uni-Projekt leichter zu debuggen und zu dokumentieren.

### Eine autoritative Schreibstelle statt Konsensprotokoll

Pro Tabelle schreibt nur der Game Master. Backups leiten Aktionen weiter. Dadurch braucht der Spielzustand kein Quorum und keine Konfliktaufloesung auf Aktionsebene.

### Lineage-ID statt reiner Versionsnummern

Versionszaehler zweier unabhaengig erzeugter Tabellen sind nicht vergleichbar. Die Lineage-ID macht Forks erkennbar, und die deterministische Aufloesung (aeltere Tabelle gewinnt) sorgt dafuer, dass alle Server denselben Gewinner waehlen.

### Best-Effort-Sync plus Anti-Entropy statt Acknowledgements

Der State Sync bleibt einfach (fire and forget). Verluste repariert der ohnehin vorhandene Heartbeat, statt ein eigenes Ack/Retry-Protokoll einzufuehren.

### Discovery zweistufig

Clients finden Server per UDP-Broadcast im LAN. Die Server untereinander nutzen fuer die Demo eine einfache Erkennung auf benachbarten lokalen Ports; das ist fuer den lokalen Cluster stabil und plattformunabhaengig.

## 12. Naechste Ausbaustufen

1. Client-Session-Token fuer Reconnect.
2. Bot-Spieler ersetzt einen Spieler nach Reconnect-Timeout.
3. Persistenz fuer Snapshots (Neustart eines einzelnen Servers ohne Peer-Hilfe).
4. Integrationstests fuer Election und Failover mit mehreren laufenden Serverprozessen.
5. Saubere Tabellenverwaltung fuer mehrere parallele Tabellen.
6. Kleine Web-UI als Alternative zur Tkinter-GUI.

## 13. Zusammenhang zur Aufgabenstellung

Die PDF fordert:

- Verteiltes Blackjack-Spiel.
- Mehrere Clients.
- Mehrere Server.
- Dynamische Discovery.
- Fault Tolerance.
- Reconnect Handling.
- Synchronisierung.
- Leader Election.

Der aktuelle Code deckt die zentralen technischen Konzepte ab:

- Game Master Server pro Tabelle mit zentraler Tabellen-Erzeugung.
- Backup-Server mit State Sync, Lineage-Regeln und Anti-Entropy.
- Heartbeat-basierte Ausfallerkennung mit Peer-Pruning.
- Normaler Bully-Algorithmus mit Read-Repair.
- UDP-Discovery fuer Clients.
- TCP-Kommunikation.
- Modulare Blackjack-Logik mit serverseitiger Regeldurchsetzung.

Offen sind Reconnect-Sessions mit Token und Bot-Ersatz nach Timeout; beide sind als naechste Ausbaustufen beschrieben.
