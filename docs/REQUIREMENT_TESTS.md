# Blackjack Royale - Anforderungs-Tests

Diese Liste ist dafuer gedacht, das Projekt kurz manuell auszuprobieren.

## 1. GUI startet

Start:

```powershell
python -m blackjack_royale.gui
```

Erwartung:

- Fenster oeffnet sich.
- Server 1, 2 und 3 stehen zuerst auf `stopped`.
- Buttons fuer Start, Stop, Spielbefehle und Demo sind sichtbar.

## 2. Mehrere Server starten

In der GUI:

1. `Start All` klicken.
2. 3 bis 5 Sekunden warten.

Erwartung:

- Server 1, 2 und 3 stehen auf `running`.
- In der Ausgabe erscheinen Startmeldungen.

## 3. Client-Server-Kommunikation

In der GUI:

1. Server-Port auf `9003` lassen.
2. `Join` klicken.
3. `Bet` klicken.
4. `Start Round` klicken.
5. `Tables` klicken.

Erwartung:

- Spieler `p1` erscheint in der Tabelle.
- Balance sinkt nach dem Einsatz.
- Nach `Start Round` haben Spieler und Dealer Karten.

## 4. Blackjack-Spielaktionen

In der GUI:

1. Nach gestarteter Runde `Hit` klicken.
2. Danach `Stand` klicken.
3. `Tables` klicken.

Erwartung:

- Bei `Hit` bekommt der Spieler eine weitere Karte.
- Bei `Stand` wird der Spieler als fertig markiert.
- Wenn alle Spieler fertig sind, zieht der Dealer, Gewinn/Verlust wird berechnet und direkt eine neue Runde gestartet.
- Die neue Runde ist wieder `phase: "playing"`.
- In `last_result` sieht man die finale Dealer-Hand der vorherigen Runde.
- In der GUI sieht man die Karten grafisch auf dem Tisch.
- Bei Gewinn steigt `balance`, bei Verlust sinkt `balance`, und der neue aktive Einsatz steht separat in `bet`.

## 4.1 Bots testen

In der GUI:

1. `Join` fuer Spieler `p1` klicken.
2. `Add Bot` klicken.
3. `Bet` klicken.
4. `Start Round` klicken.
5. `Stand` klicken.
6. `Tables` klicken.

Erwartung:

- Der Bot erscheint mit `is_bot: true`.
- Der Bot hat eigene Karten.
- Der Bot zieht automatisch, wenn sein Wert unter 16 ist.
- Ab 16 bleibt der Bot stehen.
- Danach wird abgerechnet und direkt eine neue Runde gestartet.

## 5. State Sync zwischen Servern

In der GUI:

1. Spielstand ueber Port `9003` erzeugen.
2. Server-Port auf `9002` setzen.
3. `Tables` klicken.

Erwartung:

- Server 2 kennt denselben Spielstand.
- Die `state_version` ist synchronisiert.

## 6. Heartbeat

In der GUI:

1. Alle Server laufen lassen.
2. Einige Sekunden warten.

Erwartung:

- Server bleiben auf `running`.
- Es kommt zu keiner Election, solange der Game Master erreichbar ist.

## 7. Normaler Bully-Algorithmus und Failover

In der GUI:

1. Alle Server starten.
2. Demo-Sequenz ausfuehren.
3. `Simulate Game Master Failure` klicken.
4. 5 bis 8 Sekunden warten.
5. Server-Port auf `9002` setzen.
6. `Tables` klicken.

Erwartung:

- Server 3 wird gestoppt.
- Server 2 uebernimmt als neuer Game Master.
- In der Ausgabe sollte `game_master_id` den Wert `2` zeigen.
- Der Spielstand bleibt erhalten.

## 8. Election ist nicht Game-State-Consistency

Durchfuehrung:

1. Vor dem Stoppen von Server 3 einen Spielstand erzeugen.
2. Nach dem Failover auf Server 2 `Tables` klicken.

Erwartung:

- Die Election aendert nur den Game Master.
- Der Spielstand kommt aus dem vorher synchronisierten Snapshot.

## 9. Reconnect-Grundverhalten

In der GUI:

1. `Join` fuer `p1` klicken.
2. Name oder Port unveraendert lassen.
3. `Join` erneut klicken.

Erwartung:

- Derselbe Spieler wird nicht doppelt angelegt.
- Der vorhandene Spieler wird weiterverwendet.

## 10. Shutdown

In der GUI:

1. `Stop All` klicken.

Erwartung:

- Alle Server wechseln auf `stopped`.
- Weitere Spielbefehle zeigen eine Verbindungsfehlermeldung, bis Server wieder gestartet werden.

## 11. Automatisierte Smoke-Tests

Start:

```powershell
python -m unittest
```

Erwartung:

- Alle Tests laufen erfolgreich durch.
