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
2. `Join Table` klicken.
3. `Place Bet` klicken.
4. `Start Round` klicken.
5. `Refresh` klicken.

Erwartung:

- Spieler `p1` erscheint in der Tabelle.
- Der Einsatz steht in `bet`; die Balance aendert sich erst bei der Abrechnung am Rundenende.
- Nach `Start Round` haben Spieler und Dealer Karten.

## 4. Blackjack-Spielaktionen

In der GUI:

1. Nach gestarteter Runde `Hit` klicken.
2. Danach `Stand` klicken.
3. `Refresh` klicken.

Erwartung:

- Bei `Hit` bekommt der Spieler eine weitere Karte.
- Bei `Stand` wird der Spieler als fertig markiert.
- Wenn alle Spieler fertig sind, zieht der Dealer (bis mindestens 17), Gewinn/Verlust wird berechnet und die Runde geht auf `phase: "finished"`.
- Die GUI fragt per Popup, ob eine neue Runde gestartet werden soll (`New Round`).
- In `last_result` sieht man die finale Dealer-Hand der Runde.
- In der GUI sieht man die Karten grafisch auf dem Tisch.
- Bei Gewinn steigt `balance` (bei Blackjack im Verhaeltnis 3:2), bei Verlust sinkt `balance`; der Einsatz der naechsten Runde steht separat in `bet`.
- Unzulaessige Aktionen (z.B. `Start Round` waehrend eine Runde laeuft oder Einsatz aendern mid-round) liefern eine Fehlerantwort.

## 4.1 Bots testen

In der GUI:

1. `Join Table` fuer Spieler `p1` klicken.
2. `Add Bot` klicken.
3. `Place Bet` klicken.
4. `Start Round` klicken.
5. `Stand` klicken.
6. `Refresh` klicken.

Erwartung:

- Der Bot erscheint mit `is_bot: true`.
- Der Bot hat eigene Karten.
- Der Bot zieht automatisch, wenn sein Wert unter 16 ist.
- Ab 16 bleibt der Bot stehen.
- Danach wird abgerechnet; die naechste Runde startet ueber das Popup bzw. `New Round`.

## 5. State Sync zwischen Servern

In der GUI:

1. Spielstand ueber Port `9003` erzeugen.
2. Server-Port auf `9002` setzen.
3. `Refresh` klicken.

Erwartung:

- Server 2 kennt denselben Spielstand.
- `state_version` und `lineage` sind auf allen Servern identisch.
- Auch ein absichtlich verpasster Sync (z.B. Server 2 kurz pausieren) wird ueber den Heartbeat innerhalb von 1 bis 2 Sekunden nachgeliefert.

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
3. `Fail GM` klicken.
4. 5 bis 8 Sekunden warten.
5. Server-Port auf `9002` setzen.
6. `Refresh` klicken.

Erwartung:

- Server 3 wird gestoppt.
- Server 2 uebernimmt als neuer Game Master (mit Read-Repair: er uebernimmt vorher den frischesten Spielstand der erreichbaren Peers).
- In der Ausgabe sollte `game_master_id` den Wert `2` zeigen und die `state_version` um 1 erhoeht sein.
- Der Spielstand (Spieler, Haende, Balance, `lineage`) bleibt erhalten.

## 8. Election ist nicht Game-State-Consistency

Durchfuehrung:

1. Vor dem Stoppen von Server 3 einen Spielstand erzeugen.
2. Nach dem Failover auf Server 2 `Refresh` klicken.

Erwartung:

- Die Election aendert nur den Game Master.
- Der Spielstand kommt aus dem vorher synchronisierten Snapshot.

## 9. Reconnect-Grundverhalten

In der GUI:

1. `Join Table` fuer `p1` klicken.
2. Name oder Port unveraendert lassen.
3. `Join Table` erneut klicken.

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
