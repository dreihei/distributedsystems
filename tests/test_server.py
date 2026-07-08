import time
import unittest
from unittest.mock import patch

from blackjack_royale.blackjack import Card
from blackjack_royale.messages import Message
from blackjack_royale.server import BlackjackServer

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


if __name__ == "__main__":
    unittest.main()
