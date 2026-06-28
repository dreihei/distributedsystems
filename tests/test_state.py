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
        older.state_version = 5
        state.apply_snapshot(older.to_dict())

        self.assertEqual(state.tables["main"].game_master_id, 2)
        self.assertEqual(state.tables["main"].state_version, 10)


if __name__ == "__main__":
    unittest.main()
