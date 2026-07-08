import time
import unittest
import unittest.mock

from blackjack_royale.blackjack import Card, RuleError, Table, hand_value, is_blackjack, is_bust

NO_BLACKJACK_DECK_ONE_PLAYER = [
    Card("7", "diamonds"), Card("4", "diamonds"),
    Card("K", "hearts"), Card("9", "spades"),
]


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

    def test_finished_round_waits_for_manual_next_round(self) -> None:
        table = Table(table_id="main", game_master_id=3)
        table.join("p1", "Sergej")
        table.place_bet("p1", 50)
        table.start_round()

        table.stand("p1")

        self.assertEqual(table.phase, "finished")
        self.assertEqual(table.players["p1"].bet, 0)
        self.assertIsNotNone(table.last_result)
        self.assertGreaterEqual(table.last_result["dealer_value"], 17)

    def test_bot_can_join_table(self) -> None:
        table = Table(table_id="main", game_master_id=3)

        table.add_bot(None, "DealerBot", 25)

        self.assertTrue(table.players["bot1"].is_bot)
        self.assertEqual(table.players["bot1"].default_bet, 25)
        self.assertEqual(table.players["bot1"].bet, 25)
        self.assertEqual(table.players["bot1"].balance, 1000)

    def test_bot_ids_are_assigned_sequentially(self) -> None:
        table = Table(table_id="main", game_master_id=3)

        first = table.add_bot(None, "DealerBot", 25)
        second = table.add_bot(None, "DealerBot", 25)

        self.assertEqual(first.player_id, "bot1")
        self.assertEqual(second.player_id, "bot2")
        self.assertEqual(len(table.players), 2)

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
        table.deck = [Card("K", "diamonds"), Card("7", "hearts")]

        table.finish_dealer()

        self.assertGreaterEqual(table.last_result["dealer_value"], 17)
        self.assertIn(table.last_result["dealer_action"], {"stand", "bust"})

    def test_dealer_stands_on_exactly_17(self) -> None:
        table = Table(table_id="main", game_master_id=3)
        table.dealer_hand = [Card("K", "clubs"), Card("7", "spades")]
        table.deck = [Card("5", "diamonds")]

        table.finish_dealer()

        self.assertEqual(table.last_result["dealer_value"], 17)
        self.assertEqual(table.last_result["dealer_action"], "stand")

    def test_join_without_player_id_assigns_sequential_ids(self) -> None:
        table = Table(table_id="main", game_master_id=3)

        first = table.join(None, "Sergej")
        second = table.join(None, "Maxime")

        self.assertEqual(first.player_id, "p1")
        self.assertEqual(second.player_id, "p2")
        self.assertEqual(len(table.players), 2)

    def test_join_with_explicit_player_id_still_works(self) -> None:
        table = Table(table_id="main", game_master_id=3)

        player = table.join("custom", "Sergej")

        self.assertEqual(player.player_id, "custom")
        self.assertIn("custom", table.players)

    def test_turn_deadline_is_set_for_active_human_player(self) -> None:
        table = Table(table_id="main", game_master_id=3)
        table.join("p1", "Sergej")
        table.place_bet("p1", 50)

        self.assertEqual(table.turn_timeout, 30.0)
        before = time.time()
        table.start_round()

        self.assertIsNotNone(table.turn_deadline)
        self.assertAlmostEqual(table.turn_deadline, before + table.turn_timeout, delta=2)

    def test_turn_deadline_clears_once_round_finished(self) -> None:
        table = Table(table_id="main", game_master_id=3)
        table.join("p1", "Sergej")
        table.place_bet("p1", 50)
        table.start_round()

        table.stand("p1")

        self.assertEqual(table.phase, "finished")
        self.assertIsNone(table.turn_deadline)

    def test_split_both_hands_21_advances_turn(self) -> None:
        table = Table(table_id="main", game_master_id=3)
        p1 = table.join("p1", "Alice")
        p2 = table.join("p2", "Bertha")
        table.phase = "playing"
        p1.hand = [Card("K", "spades"), Card("K", "hearts")]
        p1.bet = 50
        p2.stood = False
        table.current_player_index = 0
        table.deck = [Card("A", "diamonds"), Card("A", "clubs")]

        table.split("p1")

        self.assertTrue(p1.stood)
        self.assertTrue(p1.split_stood)
        self.assertEqual(table.current_player_index, 1)
        self.assertEqual(table.current_player().player_id, "p2")

    def test_start_round_skips_natural_blackjack_at_index_zero(self) -> None:
        table = Table(table_id="main", game_master_id=3)
        table.join("p1", "Alice")
        table.join("p2", "Bertha")
        table.place_bet("p1", 50)
        table.place_bet("p2", 50)
        fixed_deck = [
            Card("7", "diamonds"), Card("4", "diamonds"),
            Card("K", "hearts"), Card("A", "spades"),
            Card("3", "clubs"), Card("2", "clubs"),
        ]
        with unittest.mock.patch("blackjack_royale.blackjack.new_deck", side_effect=lambda: list(fixed_deck)):
            table.start_round()

        self.assertTrue(table.players["p1"].stood)
        self.assertEqual(table.phase, "playing")
        self.assertEqual(table.current_player().player_id, "p2")
        self.assertEqual(table.snapshot()["current_player_id"], "p2")

    def start_fixed_round(self, table: Table) -> None:
        with unittest.mock.patch(
            "blackjack_royale.blackjack.new_deck", side_effect=lambda: list(NO_BLACKJACK_DECK_ONE_PLAYER)
        ):
            table.start_round()

    def test_busting_main_hand_moves_to_split_hand(self) -> None:
        table = Table(table_id="main", game_master_id=3)
        p1 = table.join("p1", "Alice")
        table.place_bet("p1", 50)
        table.phase = "playing"
        p1.hand = [Card("8", "spades"), Card("8", "hearts")]
        table.deck = [Card("K", "clubs"), Card("9", "clubs"), Card("2", "diamonds"), Card("3", "diamonds")]

        table.split("p1")       # hand: 8+3=11, split: 8+2=10
        table.hit("p1")         # hand: +9 -> 20
        table.hit("p1")         # hand: +K -> 30, bust

        self.assertTrue(p1.on_split_hand)
        self.assertFalse(p1.split_stood)
        self.assertEqual(table.phase, "playing")

        table.stand("p1")       # finish the split hand
        self.assertEqual(table.phase, "finished")

    def test_place_bet_rejected_during_round(self) -> None:
        table = Table(table_id="main", game_master_id=3)
        table.join("p1", "Alice")
        table.place_bet("p1", 50)
        self.start_fixed_round(table)

        with self.assertRaises(RuleError):
            table.place_bet("p1", 200)

    def test_start_round_rejected_while_playing(self) -> None:
        table = Table(table_id="main", game_master_id=3)
        table.join("p1", "Alice")
        table.place_bet("p1", 50)
        self.start_fixed_round(table)

        with self.assertRaises(RuleError):
            table.start_round()

    def test_new_players_cannot_join_mid_round_but_reconnect_works(self) -> None:
        table = Table(table_id="main", game_master_id=3)
        table.join("p1", "Alice")
        table.place_bet("p1", 50)
        self.start_fixed_round(table)

        with self.assertRaises(RuleError):
            table.join("p2", "Latecomer")
        reconnected = table.join("p1", "Alice")
        self.assertEqual(reconnected.player_id, "p1")

    def test_split_requires_a_pair(self) -> None:
        table = Table(table_id="main", game_master_id=3)
        p1 = table.join("p1", "Alice")
        table.place_bet("p1", 50)
        table.phase = "playing"
        p1.hand = [Card("K", "spades"), Card("7", "hearts")]

        with self.assertRaises(RuleError):
            table.split("p1")

    def test_double_requires_exactly_two_cards(self) -> None:
        table = Table(table_id="main", game_master_id=3)
        p1 = table.join("p1", "Alice")
        table.place_bet("p1", 50)
        table.phase = "playing"
        p1.hand = [Card("2", "spades"), Card("3", "hearts"), Card("4", "clubs")]

        with self.assertRaises(RuleError):
            table.double("p1")

    def test_result_payout_matches_settled_balance(self) -> None:
        table = Table(table_id="main", game_master_id=3)
        player = table.join("p1", "Alice")
        table.place_bet("p1", 50)
        table.phase = "playing"
        player.hand = [Card("A", "spades"), Card("K", "hearts")]  # blackjack
        table.dealer_hand = [Card("K", "clubs"), Card("9", "diamonds")]
        table.deck = [Card("5", "clubs")]

        table.finish_dealer()

        result = table.last_result["players"]["p1"]
        self.assertEqual(result["outcome"], "blackjack")
        self.assertEqual(result["payout"], 125)          # stake 50 + 3:2 win 75
        self.assertEqual(player.balance, 1075)           # display and balance agree

    def test_rejoin_with_existing_player_id_preserves_state(self) -> None:
        table = Table(table_id="main", game_master_id=3)
        player = table.join("p1", "Alice")
        player.balance = 750
        player.hand = [Card("9", "clubs"), Card("2", "hearts")]

        reconnected = table.join("p1", "Alice")

        self.assertIs(reconnected, player)
        self.assertEqual(reconnected.balance, 750)
        self.assertEqual(len(reconnected.hand), 2)
        self.assertEqual(len(table.players), 1)


if __name__ == "__main__":
    unittest.main()
