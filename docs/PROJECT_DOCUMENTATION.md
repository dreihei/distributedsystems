# Blackjack Royale - Projektdokumentation

## 1. Projektziel

Blackjack Royale ist ein verteilter MVP fuer ein Online-Blackjack-Spiel. Das System besteht aus mehreren Clients und mehreren Serverinstanzen. Pro Blackjack-Tabelle gibt es genau einen Game Master Server. Dieser Game Master ist autoritativ fuer Spielaktionen wie Karten ziehen, Einsaetze verarbeiten und Rundenfortschritt.

Die Backup-Server halten den Spielzustand synchron. Wenn der aktuelle Game Master ausfaellt, erkennen die uebrigen Server den Ausfall ueber Heartbeats und waehlen mit einem normalen Bully-Algorithmus einen neuen Game Master.

Wichtig: Die Election ist nicht die Konsistenzlogik fuer den Game State. Die Election bestimmt nur, welcher Server nach einem Ausfall autoritativ wird. Die eigentliche Wiederherstellung des Spielstands kommt aus der State-Synchronisierung.

## 2. Aktueller Umfang

Der aktuelle Stand ist bewusst einfach gehalten:

- Blackjack-Kernlogik ohne externe Abhaengigkeiten.
- TCP-Kommunikation fuer Client-Server und Server-Server.
- Mehrere Serverinstanzen auf unterschiedlichen Ports.
- Einfache Peer-Erkennung auf benachbarten lokalen Ports.
- Game Master Rolle pro Tabelle.
- State Sync vom Game Master zu Backup-Servern.
- Heartbeats zwischen Servern.
- Normaler Bully-Algorithmus fuer Game-Master-Failover.
- CLI-Client fuer Demo und Tests.

Noch nicht voll umgesetzt:

- Grafische Oberflaeche.
- Echte LAN-Broadcast-Discovery ueber UDP.
- Persistente Speicherung auf Festplatte.
- Vollstaendige Client-Reconnect-Session mit Token.
- Bot-Ersatz nach Client-Timeout.

Diese Punkte sind vorbereitet und in der Pipeline beschrieben, aber noch nicht als volle Produktfunktion implementiert.

## 3. Ordnerstruktur

```text
blackjack_royale/
  __init__.py
  blackjack.py
  client.py
  config.py
  messages.py
  server.py
  state.py
docs/
  PROJECT_DOCUMENTATION.md
scripts/
  run_server_1.ps1
  run_server_2.ps1
  run_server_3.ps1
  demo_commands.ps1
  run_server_1.sh
  run_server_2.sh
  run_server_3.sh
  demo_commands.sh
tests/
  __init__.py
README.md
Blackjack_Royale_Pipeline.md
```

## 3.1 GUI

Die GUI wird mit folgendem Befehl gestartet:

```powershell
python -m blackjack_royale.gui
```

Sie ist ein lokales Control Panel fuer die Demo. Man kann damit:

- Server 1, 2 und 3 starten.
- Server einzeln oder gemeinsam stoppen.
- Server 3 gezielt stoppen, um den Game-Master-Ausfall zu simulieren.
- Spielbefehle senden: Tables, Join, Bet, Start Round, Hit, Stand.
- Eine Demo-Sequenz ausfuehren.
- Antworten und Serverlogs in einem Ausgabefeld sehen.

Die GUI verwendet dieselbe Client-Kommunikation wie der CLI-Client. Dadurch bleibt die Spiellogik an einer Stelle und die GUI ist nur eine Bedienoberflaeche.

## 4. Modul: `blackjack_royale.blackjack`

Dieses Modul enthaelt die reine Spiellogik. Es kennt keine Sockets, keine Server und keine Netzwerk-Nachrichten.

### Wichtige Klassen

`Card`

- Repraesentiert eine einzelne Karte mit Rang und Farbe.
- Hat `label()` fuer lesbare Ausgabe.
- Hat `to_dict()` und `from_dict()` fuer State-Synchronisierung.

`Player`

- Speichert Spieler-ID, Name, Guthaben, Einsatz, Handkarten und Verbindungsstatus.
- `balance` ist der echte Kontostand.
- `bet` ist der aktive Einsatz der aktuellen Runde und wird getrennt vom Kontostand angezeigt.
- `connected` ist bereits fuer spaetere Reconnect-Logik vorbereitet.
- `stood` zeigt, ob der Spieler in der aktuellen Runde fertig ist.

`Table`

- Repraesentiert eine Blackjack-Tabelle.
- Speichert Deck, Spieler, Dealer-Hand, aktuelle Phase, Game Master ID und State-Version.
- Die `state_version` steigt bei jeder relevanten Zustandsaenderung.

### Wichtige Funktionen

`new_deck()`

- Erstellt ein normales 52-Karten-Deck.
- Mischt das Deck zufaellig.

`hand_value(cards)`

- Berechnet den Blackjack-Wert einer Hand.
- Asse zaehlen zuerst als 11 und werden bei Bedarf auf 1 reduziert.

`is_blackjack(cards)` und `is_bust(cards)`

- Kleine Hilfsfunktionen fuer Regeln.

### Wichtige Table-Methoden

`join(player_id, name)`

- Fuegt einen Spieler hinzu oder markiert einen vorhandenen Spieler wieder als verbunden.

`place_bet(player_id, amount)`

- Setzt einen Einsatz.
- Der Einsatz wird auf das vorhandene Guthaben begrenzt.

`start_round()`

- Startet eine neue Runde.
- Mischt ein neues Deck.
- Gibt Dealer und Spielern Startkarten.

`hit(player_id)`

- Gibt dem Spieler eine weitere Karte.
- Wenn der Spieler bust ist, wird automatisch zum naechsten Spieler gewechselt.

`stand(player_id)`

- Markiert den Spieler als fertig.
- Danach wird zum naechsten Spieler gewechselt.

`finish_dealer()`

- Dealer zieht bis mindestens 17.
- Danach wird die Runde beendet und Einsaetze werden abgerechnet.
- Wenn mindestens ein menschlicher Spieler noch Guthaben hat, startet direkt automatisch die naechste Runde.

`add_bot(bot_id, name, default_bet)`

- Fuegt einen Bot-Spieler zum Tisch hinzu.
- Bots erhalten einen Standard-Einsatz.
- Bots spielen automatisch nach einfacher Strategie: ziehen unter 16, ab 16 stehen bleiben.

`to_dict()` und `from_dict()`

- Diese Methoden sind wichtig fuer State Sync.
- Sie serialisieren und rekonstruieren einen echten Tabellenzustand, nicht nur eine Anzeige.

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

Ein Peer ist ein bekannter anderer Server.

Gespeichert werden:

- Server-ID
- Host
- Server-Port
- Client-Port
- letzter erfolgreicher Kontakt

`last_seen` wird fuer Heartbeat-Timeouts verwendet.

### ClusterState

`ClusterState` ist der lokale Blick eines Servers auf den Cluster.

Er enthaelt:

- Eigene Server-ID
- Eigene Ports
- Bekannte Peers
- Bekannte Blackjack-Tabellen

Wichtige Methoden:

`ensure_table(table_id)`

- Erstellt eine Tabelle, falls sie noch nicht existiert.
- Als initialer Game Master wird die hoechste bekannte aktive Server-ID verwendet.

`apply_snapshot(snapshot)`

- Uebernimmt einen synchronisierten Tabellenzustand.
- Alte Snapshots werden ignoriert, wenn die lokale Version neuer oder gleich neu ist.

## 7. Modul: `blackjack_royale.server`

Dieses Modul ist der Kern des verteilten Systems.

Jeder Serverprozess startet zwei TCP-Server:

- Einen Port fuer Clients.
- Einen Port fuer Peer-Server.

Beispiel:

```powershell
python -m blackjack_royale.server --id 3 --client-port 9003 --server-port 9103
```

### Client-Nachrichten

`LIST_TABLES`

- Gibt bekannte Tabellen zurueck.

`JOIN_TABLE`

- Fuegt einen Spieler zu einer Tabelle hinzu.

`PLACE_BET`

- Setzt den Einsatz eines Spielers.

`START_ROUND`

- Startet eine Blackjack-Runde.

`HIT`

- Spieler zieht eine Karte.

`STAND`

- Spieler bleibt stehen.

### Server-Server-Nachrichten

`SERVER_ANNOUNCE`

- Server stellt sich einem anderen Server vor.
- Antwort enthaelt lokalen Peer und bekannte Tabellen.

`HEARTBEAT`

- Regelmaessige Lebensmeldung zwischen Servern.
- Antwort aktualisiert `last_seen`.

`STATE_SYNC`

- Game Master sendet den aktuellen Tabellenzustand an Backup-Server.

`ELECTION`

- Teil des normalen Bully-Algorithmus.
- Ein Server fragt hoehere Server-IDs, ob sie erreichbar sind.

`COORDINATOR`

- Der Gewinner der Election teilt mit, dass er neuer Game Master ist.

### Game Master Logik

Nur der Game Master darf spielveraendernde Aktionen direkt ausfuehren.

Wenn ein Client eine Aktion an einen Backup-Server sendet:

1. Backup prueft die Game Master ID der Tabelle.
2. Backup sucht den Peer mit dieser ID.
3. Backup leitet die Aktion an den Game Master weiter.
4. Die Antwort wird an den Client zurueckgegeben.

Dadurch bleibt der Game State einfach: Es gibt nur eine autoritative Schreibstelle.

### State Sync

Nach jeder relevanten Spielaktion ruft der Game Master `sync_table()` auf.

Dabei wird `table.to_dict()` an alle bekannten Peers geschickt. Backup-Server speichern den Snapshot mit `apply_snapshot()`.

Die State-Version verhindert, dass alte Updates neuere lokale Zustaende ueberschreiben.

### Heartbeat

Der aktuelle MVP verwendet folgende Werte:

- Heartbeat-Intervall: 1 Sekunde.
- Game Master gilt als ausgefallen, wenn ca. 4 Sekunden kein gueltiger Kontakt besteht.
- Election Timeout: 3 Sekunden.

Diese Werte stehen in `config.py` und koennen dort angepasst werden.

Heartbeats veraendern nicht den Spielzustand. Sie erkennen nur, ob ein Server noch lebt.

### Normaler Bully-Algorithmus

Der Ablauf im Code:

1. Ein Server erkennt, dass der Game Master nicht erreichbar ist.
2. Er sendet `ELECTION` an alle bekannten Server mit hoeherer ID.
3. Antwortet ein hoeherer Server mit `OK`, wartet der Server auf eine Coordinator-Entscheidung.
4. Hoehere Server starten selbst eine Election.
5. Wenn kein hoeherer Server antwortet, wird der aktuelle Server Coordinator.
6. Der neue Coordinator sendet `COORDINATOR` an alle Peers.
7. Alle Server setzen die Game Master ID ihrer Tabellen auf den neuen Server.

Das ist ein normaler Bully-Algorithmus, nicht die vereinfachte Variante.

## 8. Modul: `blackjack_royale.client`

Der Client ist ein kleiner Kommandozeilen-Client fuer Tests und Demo.

Beispiele:

```powershell
python -m blackjack_royale.client --port 9003 join --player-id p1 --name Sergej
python -m blackjack_royale.client --port 9003 bet --player-id p1 --amount 50
python -m blackjack_royale.client --port 9003 start
python -m blackjack_royale.client --port 9003 hit --player-id p1
python -m blackjack_royale.client --port 9003 stand --player-id p1
python -m blackjack_royale.client --port 9003 tables
```

Der Client sendet genau eine Nachricht, wartet auf genau eine Antwort und beendet sich danach. Dadurch ist er sehr leicht nachzuvollziehen.

## 8.1 Modul: `blackjack_royale.gui`

Dieses Modul enthaelt eine Tkinter-Oberflaeche. Tkinter gehoert zur Python-Standardbibliothek und benoetigt deshalb keine zusaetzlichen Pakete.

### Serversteuerung

Die GUI verwaltet drei lokale Serverprozesse:

- Server 1: Client-Port 9001, Peer-Port 9101
- Server 2: Client-Port 9002, Peer-Port 9102
- Server 3: Client-Port 9003, Peer-Port 9103

Jeder Server wird als eigener Python-Prozess gestartet. Beim Stoppen sendet die GUI ein normales Terminate-Signal. Falls ein Prozess nicht beendet, wird er nach kurzer Wartezeit beendet.

### Spielbefehle

Die Buttons senden dieselben Nachrichtentypen wie der CLI-Client:

- `Tables` sendet `LIST_TABLES`
- `Join` sendet `JOIN_TABLE`
- `Bet` sendet `PLACE_BET`
- `Add Bot` sendet `ADD_BOT`
- `Start Round` sendet `START_ROUND`
- `New Round` sendet `NEW_ROUND`
- `Hit` sendet `HIT`
- `Stand` sendet `STAND`

### Demo Sequence

Die Demo-Sequenz fuehrt automatisch aus:

1. Join
2. Bet
3. Start Round
4. Tables

Danach kann man Server 3 stoppen und den Failover ueber Server 2 pruefen.

### Automatische Folgerunden

Sobald alle Spieler fertig sind oder bust gehen, zieht der Dealer, die Einsaetze werden abgerechnet und der Kontostand wird angepasst. Danach startet automatisch eine neue Runde, solange mindestens ein menschlicher Spieler noch Guthaben hat. Der neue Einsatz basiert auf dem zuletzt gesetzten Einsatz des Spielers.

Das Ergebnis der vorherigen Runde bleibt als `last_result` im Tabellenzustand sichtbar. Dadurch kann die GUI zeigen, welche Dealer-Karten am Ende gezogen wurden und wer gewonnen, verloren oder gepusht hat, obwohl bereits die naechste Runde laeuft.

Abrechnungsregel:

- Einsatz setzen aendert den Kontostand noch nicht.
- Bei Gewinn steigt `balance` um den Einsatz.
- Bei Verlust sinkt `balance` um den Einsatz.
- Bei Push bleibt `balance` gleich.
- Der neue automatische Einsatz wird als `bet` angezeigt und nicht sofort vom Kontostand abgezogen.

Dealer-Regel:

- Dealer zieht, solange sein Handwert unter 17 ist.
- Dealer bleibt ab 17 stehen.
- Wenn der Dealer ueber 21 kommt, ist er bust.

Bot-Regel:

- Bots ziehen, solange ihr Handwert unter 16 ist.
- Bots bleiben ab 16 stehen.
- Bots spielen automatisch in jeder aktiven Runde.

### Grafische Tischansicht

Die GUI zeichnet den aktuellen Tisch auf einem Canvas:

- Dealer-Karten und Dealer-Wert.
- Spieler- und Bot-Karten.
- Einsatz und Kontostand.
- Aktueller Game Master.
- Ergebnis der letzten Runde.

Die Karten werden direkt mit Tkinter gezeichnet. Es werden keine Bilddateien und keine externen Bibliotheken benoetigt.

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
4. Server 3 beenden, falls Server 3 der Game Master ist.
5. Nach einigen Sekunden sollte eine Election starten.
6. Der hoechste erreichbare Server wird neuer Game Master.
7. Weitere Client-Kommandos an einen aktiven Server senden.

## 11. Designentscheidungen

### Keine externen Abhaengigkeiten

Das Projekt nutzt nur die Python-Standardbibliothek. Dadurch ist es reproduzierbar und laeuft auf Windows, macOS und Linux.

### Asyncio statt Threads

`asyncio` macht viele gleichzeitige Verbindungen moeglich, ohne fuer jede Verbindung manuell Threads zu verwalten.

### JSON statt binaerem Protokoll

JSON ist fuer ein Uni-Projekt leichter zu debuggen und zu dokumentieren.

### Kurze zentrale Fehlerbehandlung

Netzwerkfehler werden in `request()` zentral abgefangen. Dadurch entstehen keine langen If-Else-Ketten in der Spiellogik.

### Lokale Port-Discovery statt voller UDP-Broadcast

Der MVP sucht andere Server auf benachbarten Ports. Das ist fuer lokale Demo und Entwicklung stabiler und plattformunabhaengiger. Die PDF-Anforderung spricht von Broadcast; dieser Schritt kann spaeter durch echte UDP-Broadcast-Discovery ersetzt werden, ohne die restliche Architektur zu aendern.

## 12. Naechste Ausbaustufen

1. Echte UDP-Broadcast-Discovery fuer LAN.
2. Client-Session-Token fuer Reconnect.
3. Bot-Spieler nach Reconnect-Timeout.
4. Persistenz fuer Snapshots.
5. Tests fuer Election und Failover mit mehreren laufenden Serverprozessen.
6. Kleine Text-UI oder Web-UI fuer bessere Demo.
7. Saubere Tabellenverwaltung fuer mehrere parallele Tabellen.

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

- Game Master Server pro Tabelle.
- Backup-Server mit State Sync.
- Heartbeat-basierte Ausfallerkennung.
- Normaler Bully-Algorithmus.
- TCP-Kommunikation.
- Modulare Blackjack-Logik.

Die noch offenen Punkte sind bewusst als naechste Ausbaustufen dokumentiert, damit das Projekt schrittweise weitergebaut werden kann.
