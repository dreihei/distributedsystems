import time
import unittest
from unittest.mock import patch

from blackjack_royale.blackjack import Card
from blackjack_royale.messages import Message
from blackjack_royale.server import BlackjackServer
from blackjack_royale.state import Peer

TWO_PLAYER_NON_BLACKJACK_DECK = [
    Card("7", "diamonds"), Card("4", "diamonds"),
    Card("6", "hearts"), Card("5", "hearts"),
    Card("3", "clubs"), Card("2", "clubs"),
]


def start_round_with_fixed_deck(table, fixed_deck) -> None:
    with patch("blackjack_royale.blackjack.new_deck", side_effect=lambda: list(fixed_deck)):
        table.start_round()


class ServerHandlersTest(unittest.IsolatedAsyncioTestCase):
    def make_server(self) -> BlackjackServer:
        return BlackjackServer(1, "127.0.0.1", 9001, 9101, 9201)

    async def test_client_hit_rejects_wrong_player(self) -> None:
        server = self.make_server()
        table = server.state.ensure_table("main")
        table.join("p1", "Alice")
        table.join("p2", "Bob")
        table.place_bet("p1", 50)
        table.place_bet("p2", 50)
        start_round_with_fixed_deck(table, TWO_PLAYER_NON_BLACKJACK_DECK)

        response = await server.client_hit(Message("HIT", "client", {"table_id": "main", "player_id": "p2"}))

        self.assertEqual(response["error"], "not your turn")

    async def test_client_stand_rejects_wrong_player(self) -> None:
        server = self.make_server()
        table = server.state.ensure_table("main")
        table.join("p1", "Alice")
        table.join("p2", "Bob")
        table.place_bet("p1", 50)
        table.place_bet("p2", 50)
        start_round_with_fixed_deck(table, TWO_PLAYER_NON_BLACKJACK_DECK)

        response = await server.client_stand(Message("STAND", "client", {"table_id": "main", "player_id": "p2"}))

        self.assertEqual(response["error"], "not your turn")
        self.assertFalse(table.players["p2"].stood)

    async def test_client_hit_allowed_for_correct_player(self) -> None:
        server = self.make_server()
        table = server.state.ensure_table("main")
        table.join("p1", "Alice")
        table.join("p2", "Bob")
        table.place_bet("p1", 50)
        table.place_bet("p2", 50)
        start_round_with_fixed_deck(table, TWO_PLAYER_NON_BLACKJACK_DECK)

        response = await server.client_hit(Message("HIT", "client", {"table_id": "main", "player_id": "p1"}))

        self.assertNotIn("error", response)

    async def test_busted_player_cannot_act_again_after_turn_advances(self) -> None:
        server = self.make_server()
        table = server.state.ensure_table("main")
        table.join("p1", "Alice")
        table.join("p2", "Bob")
        table.phase = "playing"
        table.players["p1"].hand = [Card("K", "clubs"), Card("Q", "hearts"), Card("5", "spades")]
        table.players["p1"].stood = True
        table.players["p2"].hand = [Card("9", "clubs"), Card("2", "hearts")]
        table.current_player_index = 1

        response = await server.client_hit(Message("HIT", "client", {"table_id": "main", "player_id": "p1"}))

        self.assertEqual(response["error"], "not your turn")

    async def test_action_on_unknown_table_returns_error(self) -> None:
        server = self.make_server()

        response = await server.client_hit(Message("HIT", "client", {"table_id": "main", "player_id": "p1"}))

        self.assertIn("unknown table", response["error"])
        self.assertNotIn("main", server.state.tables)

    async def test_join_creates_table_only_on_coordinator(self) -> None:
        server = self.make_server()  # id 1, no peers -> coordinator

        response = await server.client_join_table(
            Message("JOIN_TABLE", "client", {"table_id": "main", "name": "Alice"})
        )

        self.assertEqual(response["player_id"], "p1")
        self.assertEqual(server.state.tables["main"].game_master_id, 1)

    async def test_rule_error_is_translated_to_error_response(self) -> None:
        server = self.make_server()
        await server.client_join_table(Message("JOIN_TABLE", "client", {"table_id": "main", "name": "Alice"}))

        response = await server.route_client_message(
            Message("SPLIT", "client", {"table_id": "main", "player_id": "p1"})
        )

        self.assertIn("error", response)
        self.assertIn("table", response)

    async def test_heartbeat_repairs_stale_peer(self) -> None:
        server = self.make_server()
        await server.client_join_table(Message("JOIN_TABLE", "client", {"table_id": "main", "name": "Alice"}))
        table = server.state.tables["main"]
        peer_info = {"server_id": 2, "host": "127.0.0.1", "server_port": 9102, "client_port": 9002}

        stale = await server.peer_heartbeat(Message("HEARTBEAT", "2", {
            "peer": peer_info,
            "tables": {"main": {"lineage": table.lineage, "version": table.state_version - 1}},
        }))
        current = await server.peer_heartbeat(Message("HEARTBEAT", "2", {
            "peer": peer_info,
            "tables": {"main": {"lineage": table.lineage, "version": table.state_version}},
        }))
        unknown = await server.peer_heartbeat(Message("HEARTBEAT", "2", {"peer": peer_info, "tables": {}}))

        self.assertEqual(len(stale["tables"]), 1)
        self.assertEqual(stale["tables"][0]["state_version"], table.state_version)
        self.assertEqual(current["tables"], [])
        self.assertEqual(len(unknown["tables"]), 1)

    async def test_rejoin_with_known_player_id_resumes_same_player(self) -> None:
        server = self.make_server()
        first = await server.client_join_table(Message("JOIN_TABLE", "client", {"table_id": "main", "name": "Alice"}))
        player_id = first["player_id"]
        table = server.state.tables["main"]
        table.players[player_id].balance = 750

        second = await server.client_join_table(
            Message("JOIN_TABLE", "client", {"table_id": "main", "player_id": player_id, "name": "Alice"})
        )

        self.assertEqual(second["player_id"], player_id)
        self.assertEqual(len(table.players), 1)
        self.assertEqual(table.players[player_id].balance, 750)

    async def test_detect_failed_master_reclaims_for_returning_higher_peer(self) -> None:
        server = self.make_server()  # id 1
        table = server.state.ensure_table("main")
        table.game_master_id = 1
        server.state.upsert_peer(Peer(2, "127.0.0.1", 9102, 9002))  # higher id, freshly seen

        with patch.object(server, "run_election") as run_election:
            await server.detect_failed_master()

        run_election.assert_called_once()

    async def test_detect_failed_master_does_not_reelect_when_master_is_highest(self) -> None:
        server = self.make_server()  # id 1
        table = server.state.ensure_table("main")
        table.game_master_id = 1
        # No peers known -> id 1 is already the highest active id, nothing to do.

        with patch.object(server, "run_election") as run_election:
            await server.detect_failed_master()

        run_election.assert_not_called()

    async def test_peer_coordinator_rejects_claim_below_known_alive_peer(self) -> None:
        server = self.make_server()  # id 1
        server.state.ensure_table("main").game_master_id = 3
        server.state.upsert_peer(Peer(3, "127.0.0.1", 9103, 9003))  # higher id, alive

        response = await server.peer_coordinator(Message("COORDINATOR", "2", {"server_id": 2}))

        self.assertEqual(response["status"], "REJECTED")
        self.assertEqual(server.state.tables["main"].game_master_id, 3)

    async def test_peer_coordinator_accepts_claim_from_legitimate_highest(self) -> None:
        server = self.make_server()  # id 1
        server.state.ensure_table("main").game_master_id = 1
        server.state.upsert_peer(Peer(3, "127.0.0.1", 9103, 9003))

        response = await server.peer_coordinator(Message("COORDINATOR", "3", {"server_id": 3}))

        self.assertEqual(response["status"], "COORDINATOR_ACCEPTED")
        self.assertEqual(server.state.tables["main"].game_master_id, 3)


if __name__ == "__main__":
    unittest.main()
