# Code Assessment — Blackjack Royale

## Summary

This is a well-structured distributed systems project. The architecture shows genuine understanding of the domain, the code is consistently styled, and it runs correctly. The issues below are real but most are the kind found in solid academic or prototype work — not in production systems.

---

## What Works Well

**Separation of concerns is excellent.** `blackjack.py` is pure game logic with zero networking. `state.py` holds only cluster membership and table storage. `server.py` is the orchestration layer. This is the right split and makes the code easy to follow and test in isolation.

**Consistent serialization pattern.** Every domain object (`Card`, `Player`, `Table`) implements `to_dict()` / `from_dict()`. The distinction between `Table.to_dict()` (full deck, for replication) and `Table.snapshot()` (client view, no deck) is deliberate and correct.

**Asyncio usage is sound.** The server stays single-threaded under asyncio, connections are handled as coroutines, and the GUI correctly bridges asyncio into a daemon thread via `asyncio.run()` rather than mixing event loops. The `queue.Queue` pattern for thread-safe GUI updates is the right approach.

**Type annotations are thorough.** `from __future__ import annotations` is used throughout, return types are declared everywhere, and typed dataclasses are used for all domain objects. This is notably better than typical project code of this complexity.

**Tests cover real behaviour.** The 12 tests all pass and target meaningful invariants: ace adjustment, round-trip serialization, auto-round cycling, bot AI threshold, balance changes. These are not trivial getter tests.

**Distributed systems mechanics are present and functional.** Bully election, heartbeat failure detection, UDP broadcast discovery, and state sync with version guards (`apply_snapshot` rejects stale versions) are all implemented correctly at the conceptual level.

---

## Issues

### 1. Double `finish_dealer` call (correctness bug)

In `Table.hit()` and `Table.stand()`:

```python
# blackjack.py:151-160
def hit(self, player_id: str) -> None:
    ...
    if is_bust(player.hand):
        player.stood = True
        self.advance_turn()          # (A) may call finish_dealer()
    self.play_bots()
    if self.all_players_done() and self.phase == "playing":
        self.finish_dealer()         # (B) may call it again
```

`advance_turn()` calls `finish_dealer()` when all players are done. `finish_dealer()` immediately starts the next round, setting `phase = "playing"`. Control then returns to `hit()`, which runs the `(B)` check. If bots have already stood in the new round, `all_players_done()` returns `True` and `finish_dealer()` is called a second time, settling bets that were just dealt. The same pattern exists in `stand()`. This is a latent bug that would surface in an all-bot table or with specific timing.

### 2. No concurrency guard on game state mutations

Asyncio is single-threaded, but since coroutines yield at `await` points, two concurrent client connections can interleave. Both could pass the `table.phase != "playing"` check before either mutates state:

```python
# server.py:171-175 — two concurrent HIT requests can both pass this guard
if table.phase != "playing":
    return {"error": ...}
table.hit(message.payload["player_id"])
```

An asyncio `Lock` per table would fix this cleanly.

### 3. Duplicated win/loss logic

`build_result()` (line 182) and `settle_bets()` (line 224) both independently compute dealer bust, player win/push/loss. They agree now, but diverge silently if one is changed. The result should be derived from the outcome computed once.

### 4. `is_blackjack()` is defined but never used

The function is tested but not called anywhere in `build_result` or `settle_bets`. A natural blackjack currently pays the same 1:1 as any other win. Standard rules pay 3:2. This is either a missing feature or the function is dead code.

### 5. Missing payload validation

Handlers do direct dict access without guards:

```python
# server.py:126
table.join(message.payload["player_id"], message.payload["name"])
```

A malformed or missing field raises a `KeyError` that propagates as an unhandled exception in the coroutine. The connection drops without a useful error response. `message.payload.get("player_id")` with an explicit error return would be safer.

### 6. `Peer.__dict__` used for serialization

```python
# server.py:189, 219, 245
self.state.local_peer().__dict__
```

This works as long as `Peer` never gains a non-JSON-serializable field (e.g., a `datetime` or another dataclass). A `to_dict()` method on `Peer` would be more robust.

### 7. Card string parsing in the GUI

`draw_cards()` at `gui.py:443` parses card labels with:

```python
rank = card.split(" of ")[0]
suit = card.split(" of ")[1][0].upper()
```

This works only because `card.label()` produces a fixed format. If the format ever changes, this silently breaks rendering. Passing `Card` objects (or at least dicts) to the GUI rather than pre-formatted strings would be more robust.

### 8. Mixed language in the GUI

Labels alternate between German ("Spiel", "Aktueller Stand") and English ("Server", "Log", "Blackjack Table"). Pick one.

---

## Minor Observations

- `nearby_peer_ports()` (`server.py:233`) scans a hardcoded 10-port window. Fine for the demo but would need to be configurable for real deployment.
- `discover_servers()` does not use a context manager for the socket, so an unexpected exception before `sock.close()` would leak the file descriptor.
- `Table.phase` is a plain string. A `Literal["waiting", "playing", "finished"]` or `enum.Enum` would catch typos at the type-checker level.

---

## Verdict

| Dimension | Assessment |
|---|---|
| Architecture | Strong — clean layering, good abstractions |
| Code style & consistency | High — uniform patterns throughout |
| Type safety | Good — comprehensive annotations |
| Correctness | Mostly sound, with one real bug (double `finish_dealer`) |
| Testing | Adequate for a prototype — covers key invariants, no integration or network tests |
| Distributed systems | Concepts correctly understood and implemented |
| Production-readiness | Not there yet — no auth, no locking, no structured error handling |

This reads like strong prototype/academic code. The architecture and style are well above average for this kind of project. The double `finish_dealer` bug and the lack of async locking are the only issues that would cause real failures under use; everything else is a cleanliness or robustness concern.
