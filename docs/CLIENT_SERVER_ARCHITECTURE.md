# Blackjack Royale - Client-Server-Architektur

## Architekturtyp

Blackjack Royale verwendet eine Client-Server-Architektur.

Die Clients sind fuer Bedienung und Anzeige verantwortlich. Die Server sind fuer Spiellogik, Spielzustand, Synchronisierung und Ausfallsicherheit verantwortlich.

Zusatz: Das Backend besteht aus mehreren Serverinstanzen. Dadurch ist die Architektur nicht nur ein einzelner Client mit einem einzelnen Server, sondern eine Client-Server-Architektur mit repliziertem Server-Cluster.

## Vereinfachte Sicht

```text
Client / GUI
    |
    | TCP
    v
Blackjack Server
    |
    | verwaltet Spielzustand
    v
Blackjack-Tisch, Dealer, Spieler, Bots, Balance
```

## Vollstaendige Projektsicht

```text
                  +----------------+
                  | Client / GUI   |
                  | CLI oder GUI   |
                  +--------+-------+
                           |
                           | TCP Client-Nachrichten
                           v
       +-------------------+-------------------+
       |        Game Master Server             |
       |  autoritative Blackjack-Logik         |
       |  Karten, Einsaetze, Dealer, Bots      |
       +-------------------+-------------------+
                           |
              State Sync / Heartbeat / Election
                           |
          +----------------+----------------+
          |                                 |
          v                                 v
+-------------------+             +-------------------+
| Backup Server     |             | Backup Server     |
| Spielstand-Kopie  |             | Spielstand-Kopie  |
| Failover bereit   |             | Failover bereit   |
+-------------------+             +-------------------+
```

## Rollen

### Client

Der Client ist die Benutzerschnittstelle.

Im Projekt gibt es zwei Client-Arten:

- CLI-Client: `blackjack_royale/client.py`
- GUI-Client: `blackjack_royale/gui.py`

Aufgaben des Clients:

- Server kontaktieren
- Spieler beitreten lassen
- Bots hinzufuegen
- Einsatz setzen
- Spielaktionen senden: Hit, Stand, Start Round
- Spielzustand anzeigen
- Karten, Dealer, Bots und Balance darstellen

Der Client entscheidet nicht ueber Spielregeln. Er zeigt nur an und sendet Befehle.

### Server

Der Server ist fuer die autoritative Logik verantwortlich.

Im Projekt:

- Servermodul: `blackjack_royale/server.py`
- Spiellogik: `blackjack_royale/blackjack.py`
- Clusterzustand: `blackjack_royale/state.py`

Aufgaben des Servers:

- Client-Verbindungen annehmen
- Spielaktionen validieren
- Blackjack-Regeln ausfuehren
- Karten geben
- Dealer-Logik ausfuehren
- Bot-Logik ausfuehren
- Einsaetze abrechnen
- Balance aktualisieren
- Spielzustand synchronisieren
- Heartbeats senden und empfangen
- Game-Master-Failover ueber Bully-Algorithmus durchfuehren

## Kommunikation

Client und Server kommunizieren ueber TCP.

Das Nachrichtenformat ist JSON.

Beispiel:

```json
{
  "type": "HIT",
  "sender": "client",
  "payload": {
    "table_id": "main",
    "player_id": "p1"
  }
}
```

Wichtige Client-Server-Nachrichten:

- `JOIN_TABLE`
- `ADD_BOT`
- `PLACE_BET`
- `START_ROUND`
- `HIT`
- `STAND`
- `LIST_TABLES`

## Erreichbarkeit ohne feste IP-Adresse

Die Server muessen nicht mit einer festen IP-Adresse im Code eingetragen werden.

Der Server bindet standardmaessig an:

```text
0.0.0.0
```

Das bedeutet: Der Server nimmt Verbindungen auf allen Netzwerkinterfaces des Rechners an, zum Beispiel localhost, WLAN oder LAN.

Clients koennen Server per Discovery suchen:

```powershell
python -m blackjack_royale.client discover
```

Oder direkt einen Spielbefehl ohne Host und Port senden. Dann sucht der Client zuerst automatisch nach einem Server:

```powershell
python -m blackjack_royale.client tables
```

Die GUI hat dafuer den Button:

```text
Discover LAN
```

Wenn ein Server gefunden wird, setzt die GUI `Server-Host` und `Server-Port` automatisch.

## Wer kann mitspielen?

Andere Leute koennen mitspielen, wenn sie den Server im Netzwerk erreichen koennen.

Typische Faelle:

- Gleicher Computer: funktioniert ueber `localhost`.
- Gleiches WLAN/LAN: funktioniert ueber LAN-Discovery oder manuelle Eingabe der gefundenen LAN-Adresse.
- Anderes Netzwerk/Internet: funktioniert nur mit Portfreigabe, VPN, Tunnel oder einem oeffentlich erreichbaren Server.

Wichtig: Firewalls koennen Verbindungen blockieren. Unter Windows muss Python eventuell im privaten Netzwerk erlaubt werden.

Verwendete Ports im Demo-Setup:

- Client-Ports: `9001`, `9002`, `9003`
- Peer-Ports: `9101`, `9102`, `9103`
- Discovery-Ports: `9201`, `9202`, `9203`

## Warum ist das Client-Server?

Das Projekt ist eine Client-Server-Architektur, weil:

- Clients keine eigene autoritative Spiellogik besitzen.
- Clients Befehle an Server senden.
- Server den zentralen Spielzustand verwalten.
- Server Antworten und Updates an Clients liefern.
- Spielentscheidungen wie Dealer-Zug, Bot-Zug, Gewinn und Verlust serverseitig passieren.

## Warum gibt es mehrere Server?

Die Aufgabenstellung verlangt Fault Tolerance, Heartbeats, Synchronisierung und Leader Election.

Dafuer reicht ein einzelner Server nicht aus. Deshalb gibt es mehrere Serverinstanzen:

- Ein Server ist Game Master.
- Die anderen Server sind Backups.
- Backups erhalten synchronisierte Spielstaende.
- Wenn der Game Master ausfaellt, wird ein neuer Game Master gewaehlt.

Das bleibt trotzdem Client-Server, weil Clients weiterhin mit Servern sprechen und nicht direkt miteinander.

## Kurzform fuer Abgabe

Das Projekt verwendet eine Client-Server-Architektur mit mehreren replizierten Serverinstanzen. Clients senden Spielaktionen ueber TCP an einen Server. Pro Blackjack-Tisch gibt es einen Game Master Server, der die autoritative Spiellogik ausfuehrt und den Spielzustand verwaltet. Backup-Server halten synchronisierte Kopien des Spielzustands. Heartbeats erkennen Serverausfaelle. Bei Ausfall des Game Masters wird mit einem normalen Bully-Algorithmus ein neuer Game Master gewaehlt.
