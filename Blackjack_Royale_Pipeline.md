# Blackjack Royale - Umsetzungs-Pipeline

## Ziel der Aufgabe

Das Projekt ist ein verteiltes Online-Blackjack-Spiel mit mehreren Clients und mehreren Serverinstanzen. Clients verbinden sich dynamisch mit verfuegbaren Servern, Spieler koennen Tabellen beitreten, Einsaetze setzen, Karten ziehen und Spielupdates erhalten. Mehrere Server halten den Spielzustand synchron, damit eine laufende Runde weitergehen kann, wenn ein Client oder der aktuelle Game Master Server ausfaellt.

Wichtige Zusatzentscheidungen:

- Es wird kein vereinfachter Bully-Algorithmus verwendet, sondern ein normaler Bully-Algorithmus.
- Die Leader Election dient nicht der Game-State-Consistency selbst, sondern der Wahl eines neuen Game Master Servers bei Ausfall oder Tabellenuebernahme.
- Heartbeats muessen fest definiert werden, inklusive Frequenz und Timeout-Regeln.

## Pipeline: Was nacheinander passieren muss

### 1. Anforderungen und Scope festlegen

- Blackjack-Regeln fuer die Implementierung festlegen: Spieleraktionen, Dealer-Verhalten, Einsatzlogik, Rundenende, Auszahlung.
- Festlegen, was Clients koennen muessen: Tabelle suchen, beitreten, setzen, Hit/Stand ausfuehren, Updates anzeigen, reconnecten.
- Festlegen, was Server koennen muessen: Tabellen verwalten, Spielaktionen validieren, Game State speichern, mit anderen Servern synchronisieren, Failover ausloesen.
- Konfigurationen definieren: Ports, Broadcast-Adresse, Heartbeat-Intervall, Timeouts, Reconnect-Zeitfenster, Server-ID.

### 2. Architekturmodell definieren

- Komponenten definieren:
  - Client fuer menschliche Spieler oder Bots.
  - Serverinstanz als Teil des verteilten Serverpools.
  - Game Master Server pro aktiver Blackjack-Tabelle.
  - Backup-Server, die synchronisierte Zustaende halten.
- Kommunikationswege festlegen:
  - Client zu Server ueber TCP.
  - Server zu Server ueber TCP fuer Synchronisierung, Election und Heartbeats.
  - Discovery ueber Broadcast im lokalen Netzwerk.
- Architekturdiagramm erstellen oder aktualisieren.

### 3. Nachrichtenprotokoll entwerfen

- Gemeinsames Message-Format definieren, zum Beispiel JSON.
- Client-Server-Nachrichten festlegen:
  - DISCOVER_TABLES
  - JOIN_TABLE
  - PLACE_BET
  - HIT
  - STAND
  - GAME_UPDATE
  - RECONNECT
  - ERROR
- Server-Server-Nachrichten festlegen:
  - SERVER_DISCOVERY
  - SERVER_ANNOUNCE
  - STATE_SYNC
  - STATE_ACK
  - HEARTBEAT
  - HEARTBEAT_ACK
  - ELECTION
  - OK
  - COORDINATOR
- Jede Nachricht braucht mindestens Typ, Absender-ID, Zeitstempel und optional Tabellen-ID, Spieler-ID und Payload.

### 4. Grundlegendes Blackjack-Modell implementieren

- Karten, Deck, Handwerte, Blackjack-Erkennung und Bust-Erkennung implementieren.
- Spielerzustand modellieren: ID, Name, Hand, Einsatz, Balance, Verbindungsstatus.
- Dealerzustand modellieren.
- Tabellenzustand modellieren: Table-ID, aktuelle Phase, Spieler, Dealer, Deck, Turn Order, Game Master ID.
- Spielrunden lokal ohne Netzwerk testen.

### 5. TCP-Kommunikation aufbauen

- Server so implementieren, dass mehrere Clients parallel verbunden sein koennen.
- Client so implementieren, dass er Befehle senden und Updates empfangen kann.
- Fehlerhafte oder unbekannte Nachrichten sauber behandeln.
- Verbindungsabbrueche erkennen und nicht sofort den Spielzustand verlieren.

### 6. Dynamic Discovery implementieren

- Client sendet Broadcast-Anfrage im lokalen Netzwerk.
- Verfuegbare Server antworten mit Host, Port und aktiven Tabellen.
- Client verbindet sich automatisch mit einem passenden Server.
- Server entdecken andere Server ebenfalls per Broadcast.
- Neue Server treten dem Serverpool bei und fordern den aktuellen Zustand an.

### 7. Game Master Rolle einfuehren

- Fuer jede Blackjack-Tabelle gibt es genau einen Game Master Server.
- Der Game Master ist verantwortlich fuer:
  - Kartengeben
  - Validieren von Spieleraktionen
  - Dealer-Verhalten
  - Rundenfortschritt
  - Ausloesen der State-Synchronisierung
- Backup-Server duerfen nicht gleichzeitig autoritativ Aktionen ausfuehren.

### 8. Game-State-Synchronisierung implementieren

- Nach relevanten Aktionen sendet der Game Master den aktuellen Tabellenzustand an Backup-Server.
- Backup-Server bestaetigen empfangene Updates mit STATE_ACK.
- Der Zustand sollte Versionen oder Sequenznummern enthalten.
- Bei neu gestarteten Servern wird ein kompletter Snapshot vom aktuellen Zustand angefordert.
- Synchronisierung dient dazu, nach einem Failover weiterzuspielen, aber sie ersetzt nicht die Leader Election.

### 9. Heartbeat-Konzept implementieren

- Server senden regelmaessig Heartbeats an bekannte andere Server.
- Empfehlung:
  - Heartbeat alle 1 Sekunde.
  - Server gilt als verdachtig nach 3 fehlenden Antworten.
  - Server gilt als ausgefallen nach ca. 3 bis 5 Sekunden ohne gueltigen Heartbeat.
- Clients koennen ebenfalls ueber Ping, Heartbeat oder TCP-Timeout ueberwacht werden.
- Empfehlung fuer Clients:
  - Client-Heartbeat alle 2 Sekunden oder serverseitiger Ping alle 2 Sekunden.
  - Client gilt als disconnected nach 5 bis 10 Sekunden ohne Antwort.
  - Reconnect-Fenster z. B. 30 bis 60 Sekunden.
- Heartbeat-Status darf einen Ausfall erkennen, aber nicht selbst den Game State veraendern. Er triggert nur Reconnect-Logik oder Election.

### 10. Normalen Bully-Algorithmus implementieren

- Jede Serverinstanz hat eine eindeutige numerische ID.
- Der Server mit der hoechsten aktiven ID gewinnt die Election.
- Ablauf normaler Bully-Algorithmus:
  - Ein Server erkennt, dass der aktuelle Game Master nicht mehr erreichbar ist.
  - Er sendet ELECTION-Nachrichten an alle Server mit hoeherer ID.
  - Antwortet kein hoeherer Server, erklaert er sich selbst zum Coordinator/Game Master.
  - Antwortet mindestens ein hoeherer Server mit OK, wartet der ausloesende Server auf eine COORDINATOR-Nachricht.
  - Hoehere Server starten ihrerseits eine Election gegen noch hoehere Server.
  - Der hoechste erreichbare Server sendet COORDINATOR an alle aktiven Server.
- Election-Zweck:
  - Wahl eines neuen Game Master Servers fuer eine Tabelle.
  - Nicht direkte Loesung der Game-State-Consistency.
- Nach erfolgreicher Election laedt der neue Game Master den neuesten synchronisierten Tabellenzustand und setzt die Runde fort.

### 11. Client-Fault-Tolerance und Reconnect implementieren

- Wenn ein Client ausfaellt, bleibt sein Spielerzustand temporaer erhalten.
- Bei Reconnect identifiziert sich der Client wieder ueber Spieler-ID oder Session-Token.
- Innerhalb des Reconnect-Fensters wird die laufende Session wiederhergestellt.
- Nach Ablauf des Fensters wird der Spieler entfernt oder durch einen Bot ersetzt.
- Bot-Verhalten definieren, falls Bots verwendet werden.

### 12. Server-Failover implementieren

- Backup-Server erkennen Game-Master-Ausfall ueber Heartbeats.
- Election wird gestartet.
- Neuer Game Master uebernimmt die Tabelle.
- Letzter bestaetigter Game State wird geladen.
- Clients werden ueber den neuen Game Master informiert oder vom Serverpool transparent weitergeleitet.
- Die laufende Runde soll nicht komplett neu gestartet werden.

### 13. Konsistenzregeln festlegen

- Nur der Game Master akzeptiert und validiert spielveraendernde Aktionen.
- Backup-Server halten replizierte Zustandskopien.
- Jede State-Version hat eine eindeutige Nummer.
- Alte Updates werden ignoriert.
- Bei Konflikten gewinnt der neueste bestaetigte Zustand des vorherigen Game Masters oder der Zustand mit der hoechsten Sequenznummer.
- Election bestimmt die Autoritaet, State Sync bestimmt den wiederherstellbaren Zustand.

### 14. Testszenarien planen und durchfuehren

- Einzelner Client verbindet sich und spielt eine Runde.
- Mehrere Clients spielen an einer Tabelle.
- Client trennt Verbindung und reconnectet.
- Client trennt Verbindung und wird nach Timeout entfernt oder ersetzt.
- Neuer Server startet und synchronisiert sich.
- Game Master faellt aus.
- Neuer Game Master wird per normalem Bully-Algorithmus gewaehlt.
- Spiel geht nach Failover weiter.
- Heartbeat-Ausfall wird korrekt erkannt.
- Split-Brain vermeiden: nie zwei aktive Game Master fuer dieselbe Tabelle.

### 15. Demo-Ablauf vorbereiten

- Mindestens drei Serverinstanzen starten, damit der Bully-Algorithmus sichtbar wird.
- Mindestens zwei Clients starten.
- Tabelle erstellen und Runde starten.
- Game Master absichtlich stoppen.
- Heartbeat-Timeout abwarten.
- Election-Logs zeigen.
- Neuer Game Master uebernimmt.
- Runde wird mit synchronisiertem Zustand fortgesetzt.
- Optional: Client disconnect/reconnect demonstrieren.

## Empfohlene Implementierungsreihenfolge

1. Lokale Blackjack-Logik ohne Netzwerk.
2. Einfacher TCP-Server und TCP-Client.
3. Client-Server-Protokoll fuer Spielaktionen.
4. Mehrere Serverinstanzen mit Server-IDs.
5. Server-Discovery.
6. Game Master Rolle pro Tabelle.
7. State Sync vom Game Master zu Backups.
8. Heartbeats zwischen Servern und Clients.
9. Normaler Bully-Algorithmus.
10. Server-Failover mit Wiederherstellung des letzten Zustands.
11. Client-Reconnect und Bot/Remove-Logik.
12. End-to-End-Tests und Demo-Skripte.

## Offene Designentscheidungen

- Programmiersprache und Framework.
- Ob eine grafische Oberflaeche oder eine Konsolenoberflaeche verwendet wird.
- Genaues Reconnect-Zeitfenster.
- Ob Bots wirklich implementiert werden oder ob Spieler nach Timeout entfernt werden.
- Ob pro Tabelle ein eigener Game Master existiert oder ein Server mehrere Tabellen als Game Master verwalten kann.
- Wie State-Versionierung konkret umgesetzt wird.

## Kurzfassung fuer die Projektlogik

Die Server bilden einen dynamischen Pool. Clients finden Server automatisch und verbinden sich mit ihnen. Jede Blackjack-Tabelle hat einen Game Master, der alle spielveraendernden Aktionen kontrolliert. Backup-Server halten den Zustand synchron. Heartbeats erkennen Ausfaelle. Wenn der Game Master ausfaellt, startet ein normaler Bully-Algorithmus und waehlt den erreichbaren Server mit der hoechsten ID als neuen Game Master. Danach stellt dieser den letzten synchronisierten Game State wieder her und fuehrt das Spiel fort.
