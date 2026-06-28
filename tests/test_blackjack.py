import unittest

from blackjack_royale.blackjack import Card, Table, hand_value, is_blackjack, is_bust


class BlackjackRulesTest(unittest.TestCase):
    def test_ace_value_is_adjusted(self) -> None:
        cards = [Card("A", "spades"), Card("9", "clubs"), Card("5", "hearts")]
        self.assertEqual(hand_value(cards), 15)

    def test_blackjack_and_bust_detection(self) -> None:
        self.assertTrue(is_blackjack([Card("A", "spades"), Card("K", "clubs")]))
        self.assertTrue(is_bust([Card("K", "spades"), Card("Q", "clubs"), Card("2", "hearts")]))

    def test_table_snapshot_round_trip(self) -> None:
        table = Table(table_id="main", game_master_id=3)
        table.join("p1", "Sergej")
        table.place_bet("p1", 50)
        table.start_round()

        restored = Table.from_dict(table.to_dict())

        self.assertEqual(restored.table_id, "main")
        self.assertEqual(restored.game_master_id, 3)
        self.assertEqual(restored.state_version, table.state_version)
        self.assertEqual(restored.players["p1"].name, "Sergej")
        self.assertEqual(len(restored.players["p1"].hand), 2)

    def test_finished_round_starts_next_round_automatically(self) -> None:
        table = Table(table_id="main", game_master_id=3)
        table.join("p1", "Sergej")
        table.place_bet("p1", 50)
        table.start_round()

        table.stand("p1")

        self.assertEqual(table.phase, "playing")
        self.assertEqual(table.players["p1"].bet, 50)
        self.assertEqual(len(table.players["p1"].hand), 2)
        self.assertEqual(len(table.dealer_hand), 2)
        self.assertIsNotNone(table.last_result)
        self.assertGreaterEqual(table.last_result["dealer_value"], 17)

    def test_bot_can_join_table(self) -> None:
        table = Table(table_id="main", game_master_id=3)

        table.add_bot("bot1", "DealerBot", 25)

        self.assertTrue(table.players["bot1"].is_bot)
        self.assertEqual(table.players["bot1"].default_bet, 25)
        self.assertEqual(table.players["bot1"].bet, 25)
        self.assertEqual(table.players["bot1"].balance, 1000)

    def test_balance_increases_when_player_wins(self) -> None:
        table = Table(table_id="main", game_master_id=3)
        player = table.join("p1", "Sergej")
        table.place_bet("p1", 50)
        player.hand = [Card("K", "clubs"), Card("9", "spades")]
        table.dealer_hand = [Card("8", "clubs"), Card("8", "spades")]

        table.settle_bets()

        self.assertEqual(player.balance, 1050)
        self.assertEqual(player.bet, 0)

    def test_balance_decreases_when_player_loses(self) -> None:
        table = Table(table_id="main", game_master_id=3)
        player = table.join("p1", "Sergej")
        table.place_bet("p1", 50)
        player.hand = [Card("K", "clubs"), Card("7", "spades")]
        table.dealer_hand = [Card("K", "hearts"), Card("9", "diamonds")]

        table.settle_bets()

        self.assertEqual(player.balance, 950)
        self.assertEqual(player.bet, 0)

    def test_bot_draws_until_at_least_16(self) -> None:
        table = Table(table_id="main", game_master_id=3)
        bot = table.add_bot("bot1", "DealerBot", 25)
        table.phase = "playing"
        bot.hand = [Card("6", "clubs"), Card("4", "spades")]
        bot.stood = False
        table.deck = [Card("2", "hearts"), Card("7", "diamonds")]

        table.play_bots()

        self.assertGreaterEqual(hand_value(bot.hand), 16)
        self.assertTrue(bot.stood)

    def test_dealer_draws_until_17_then_stands(self) -> None:
        table = Table(table_id="main", game_master_id=3)
        table.dealer_hand = [Card("5", "clubs"), Card("6", "spades")]
        table.deck = [Card("2", "hearts"), Card("K", "diamonds")]

        table.finish_dealer()

        self.assertGreaterEqual(table.last_result["dealer_value"], 17)
        self.assertIn(table.last_result["dealer_action"], {"stand", "bust"})


if __name__ == "__main__":
    unittest.main()
