"""Cluster state shared by the server modules."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .blackjack import Table


@dataclass
class Peer:
    server_id: int
    host: str
    server_port: int
    client_port: int
    last_seen: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.last_seen = time.time()


@dataclass
class ClusterState:
    server_id: int
    host: str
    server_port: int
    client_port: int
    peers: dict[int, Peer] = field(default_factory=dict)
    tables: dict[str, Table] = field(default_factory=dict)
    turn_timeout: float = 30.0

    def local_peer(self) -> Peer:
        return Peer(self.server_id, self.host, self.server_port, self.client_port)

    def upsert_peer(self, peer: Peer) -> None:
        if peer.server_id != self.server_id:
            self.peers[peer.server_id] = peer

    def active_server_ids(self) -> list[int]:
        return sorted([self.server_id, *self.peers.keys()])

    def highest_active_server_id(self) -> int:
        return max(self.active_server_ids())

    def ensure_table(self, table_id: str = "main") -> Table:
        table = self.tables.get(table_id)
        if table is None:
            table = Table(
                table_id=table_id,
                game_master_id=self.highest_active_server_id(),
                turn_timeout=self.turn_timeout,
            )
            self.tables[table_id] = table
        return table

    def apply_snapshot(self, snapshot: dict) -> None:
        table_id = snapshot["table_id"]
        current = self.tables.get(table_id)
        if current and not self.snapshot_wins(current, snapshot):
            return
        self.tables[table_id] = Table.from_dict(snapshot)

    @staticmethod
    def snapshot_wins(current: Table, snapshot: dict) -> bool:
        lineage = snapshot.get("lineage", "legacy")
        if lineage != current.lineage:
            # Fork: two tables were created independently under the same id.
            # The older creation survives everywhere; ties break on lineage.
            return (snapshot.get("created_at", 0.0), lineage) < (current.created_at, current.lineage)
        return snapshot["state_version"] > current.state_version
