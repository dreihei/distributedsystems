import time
import unittest
from unittest.mock import patch

from blackjack_royale.blackjack import Card
from blackjack_royale.messages import Message
from blackjack_royale.server import BlackjackServer

ONE_PLAYER_NON_BLACKJACK_DECK = [
    Card("6", "hearts"), Card("5", "hearts"),
    Card("3", "clubs"), Card("2", "clubs"),
]
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

    async def test_join_table_assigns_id_when_omitted(self) -> None:
        server = self.make_server()

        response = await server.client_join_table(Message("JOIN_TABLE", "client", {"table_id": "main", "name": "Alice"}))

        self.assertEqual(response["player_id"], "p1")
        self.assertIn("p1", response["table"]["players"])

    async def test_join_table_assigns_sequential_ids(self) -> None:
        server = self.make_server()
        await server.client_join_table(Message("JOIN_TABLE", "client", {"table_id": "main", "name": "Alice"}))

        response = await server.client_join_table(Message("JOIN_TABLE", "client", {"table_id": "main", "name": "Bob"}))

        self.assertEqual(response["player_id"], "p2")

    async def test_check_turn_timeouts_auto_stands_expired_player(self) -> None:
        server = self.make_server()
        table = server.state.ensure_table("main")
        table.join("p1", "Alice")
        table.place_bet("p1", 50)
        start_round_with_fixed_deck(table, ONE_PLAYER_NON_BLACKJACK_DECK)
        table.turn_deadline = time.time() - 1

        await server.check_turn_timeouts()

        self.assertTrue(table.players["p1"].stood)

    async def test_check_turn_timeouts_ignores_future_deadline(self) -> None:
        server = self.make_server()
        table = server.state.ensure_table("main")
        table.join("p1", "Alice")
        table.place_bet("p1", 50)
        start_round_with_fixed_deck(table, ONE_PLAYER_NON_BLACKJACK_DECK)
        table.turn_deadline = time.time() + 30

        await server.check_turn_timeouts()

        self.assertFalse(table.players["p1"].stood)


if __name__ == "__main__":
    unittest.main()
