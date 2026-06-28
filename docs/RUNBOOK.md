# Blackjack Royale - Runbook

## Lokale Demo starten

Empfohlener Weg mit GUI:

```powershell
python -m blackjack_royale.gui
```

Dann:

1. `Start All` klicken.
2. `Join Table` klicken.
3. Optional `Add Bot` klicken.
4. `Place Bet` klicken.
5. `Start Round` klicken.
6. Mit `Hit` oder `Stand` spielen.
7. `Refresh` aktualisiert die grafische Anzeige.
8. Fuer Failover `Simulate Game Master Failure` klicken.
9. Danach erneut `Refresh` oder einen Spielbutton nutzen.

Die grafische Anzeige zeigt oben den Dealer, darunter deine eigene Hand und darunter/nebendran Bots. In der Statuszeile stehen Dealer-Wert, eigener Wert, Einsatz, Kontostand und Bot-Werte.

## Im gleichen Netzwerk spielen

Auf dem Host-Rechner Server starten:

```powershell
python -m blackjack_royale.server --id 1 --client-port 9001 --server-port 9101
```

Auf einem anderen Rechner im gleichen WLAN/LAN:

```powershell
python -m blackjack_royale.client discover
```

Wenn ein Server gefunden wird, kann man direkt ohne feste IP spielen:

```powershell
python -m blackjack_royale.client tables
python -m blackjack_royale.client join --player-id p2 --name Maxime
```

In der GUI:

1. `Discover LAN` klicken.
2. Gefundener `Server-Host` und `Server-Port` werden eingetragen.
3. Danach `Join Table`, `Place Bet`, `Hit`, `Stand` nutzen.

Wenn kein Server gefunden wird, blockiert oft die Firewall UDP-Broadcast oder TCP-Verbindungen.

Alternativ ohne GUI:

Terminal 1:

```powershell
python -m blackjack_royale.server --id 1 --client-port 9001 --server-port 9101
```

Terminal 2:

```powershell
python -m blackjack_royale.server --id 2 --client-port 9002 --server-port 9102
```

Terminal 3:

```powershell
python -m blackjack_royale.server --id 3 --client-port 9003 --server-port 9103
```

Terminal 4:

```powershell
python -m blackjack_royale.client --port 9003 join --player-id p1 --name Sergej
python -m blackjack_royale.client --port 9003 bet --player-id p1 --amount 50
python -m blackjack_royale.client --port 9003 start
python -m blackjack_royale.client --port 9003 tables
```

## Failover zeigen

1. Drei Server starten.
2. Runde starten.
3. Den Server mit der hoechsten ID stoppen.
4. Einige Sekunden warten.
5. Im Log sollte ein anderer Server melden, dass er Game Master wurde.
6. Weitere Client-Kommandos an einen aktiven Server senden.

## Typische Ports

- Server 1: Client 9001, Peer 9101
- Server 2: Client 9002, Peer 9102
- Server 3: Client 9003, Peer 9103

## Tests ausfuehren

```powershell
python -m unittest
```
