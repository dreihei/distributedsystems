import unittest

from blackjack_royale.blackjack import Table
from blackjack_royale.state import ClusterState, Peer


class ClusterStateTest(unittest.TestCase):
    def test_highest_active_server_id(self) -> None:
        state = ClusterState(server_id=1, host="127.0.0.1", server_port=9101, client_port=9001)
        state.upsert_peer(Peer(server_id=3, host="127.0.0.1", server_port=9103, client_port=9003))

        self.assertEqual(state.highest_active_server_id(), 3)

    def test_old_snapshot_is_ignored(self) -> None:
        state = ClusterState(server_id=2, host="127.0.0.1", server_port=9102, client_port=9002)
        newer = Table(table_id="main", game_master_id=2)
        newer.state_version = 10
        state.tables["main"] = newer

        older = Table(table_id="main", game_master_id=1)
        older.lineage = newer.lineage
        older.created_at = newer.created_at
        older.state_version = 5
        state.apply_snapshot(older.to_dict())

        self.assertEqual(state.tables["main"].game_master_id, 2)
        self.assertEqual(state.tables["main"].state_version, 10)

    def test_fork_resolves_to_older_lineage_regardless_of_version(self) -> None:
        state = ClusterState(server_id=2, host="127.0.0.1", server_port=9102, client_port=9002)
        fork = Table(table_id="main", game_master_id=2)
        fork.lineage = "b" * 32
        fork.created_at = 200.0
        fork.state_version = 50
        state.tables["main"] = fork

        original = Table(table_id="main", game_master_id=3)
        original.lineage = "a" * 32
        original.created_at = 100.0
        original.state_version = 5
        state.apply_snapshot(original.to_dict())

        self.assertEqual(state.tables["main"].lineage, original.lineage)
        self.assertEqual(state.tables["main"].state_version, 5)

        # And the losing fork can never overwrite the original again.
        state.apply_snapshot(fork.to_dict())
        self.assertEqual(state.tables["main"].lineage, original.lineage)


if __name__ == "__main__":
    unittest.main()
