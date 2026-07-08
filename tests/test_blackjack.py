import time
import unittest
from unittest.mock import patch

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
        self.assertEqual(restored.turn_deadline, table.turn_deadline)

    def test_finished_round_waits_for_manual_next_round(self) -> None:
        table = Table(table_id="main", game_master_id=3)
        table.join("p1", "Sergej")
        table.place_bet("p1", 50)
        table.start_round()

        table.stand("p1")

        self.assertEqual(table.phase, "finished")
        self.assertEqual(table.players["p1"].bet, 0)
        self.assertIsNotNone(table.last_result)
        self.assertGreaterEqual(table.last_result["dealer_value"], 18)

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

    def test_dealer_draws_until_18_then_stands(self) -> None:
        table = Table(table_id="main", game_master_id=3)
        table.dealer_hand = [Card("5", "clubs"), Card("6", "spades")]
        table.deck = [Card("K", "diamonds"), Card("7", "hearts")]

        table.finish_dealer()

        self.assertGreaterEqual(table.last_result["dealer_value"], 18)
        self.assertIn(table.last_result["dealer_action"], {"stand", "bust"})

    def test_turn_deadline_set_on_start_round(self) -> None:
        table = Table(table_id="main", game_master_id=3)
        table.join("p1", "Alice")
        table.place_bet("p1", 50)
        fixed_deck = [
            Card("6", "hearts"), Card("5", "hearts"),
            Card("3", "clubs"), Card("2", "clubs"),
        ]
        with patch("blackjack_royale.blackjack.new_deck", side_effect=lambda: list(fixed_deck)):
            table.start_round()

        self.assertIsNotNone(table.turn_deadline)
        self.assertGreater(table.turn_deadline, time.time())

    def test_turn_deadline_refreshes_on_advance_turn(self) -> None:
        table = Table(table_id="main", game_master_id=3)
        table.join("p1", "Alice")
        table.join("p2", "Bertha")
        table.place_bet("p1", 50)
        table.place_bet("p2", 50)
        fixed_deck = [
            Card("7", "diamonds"), Card("4", "diamonds"),
            Card("6", "hearts"), Card("5", "hearts"),
            Card("3", "clubs"), Card("2", "clubs"),
        ]
        with patch("blackjack_royale.blackjack.new_deck", side_effect=lambda: list(fixed_deck)):
            table.start_round()

        deadline1 = table.turn_deadline
        time.sleep(0.01)
        table.stand("p1")

        self.assertEqual(table.current_player().player_id, "p2")
        self.assertIsNotNone(table.turn_deadline)
        self.assertGreater(table.turn_deadline, deadline1)

    def test_stand_switch_to_split_hand_refreshes_deadline(self) -> None:
        table = Table(table_id="main", game_master_id=3)
        player = table.join("p1", "Alice")
        table.phase = "playing"
        player.hand = [Card("9", "clubs"), Card("8", "hearts")]
        player.split_hand = [Card("2", "spades"), Card("3", "spades")]
        player.split_bet = 50
        table.current_player_index = 0
        table.turn_deadline = time.time() + 5

        old_deadline = table.turn_deadline
        time.sleep(0.01)
        table.stand("p1")

        self.assertTrue(player.on_split_hand)
        self.assertFalse(player.stood)
        self.assertIsNotNone(table.turn_deadline)
        self.assertGreater(table.turn_deadline, old_deadline)

    def test_timeout_current_player_matches_stand(self) -> None:
        table = Table(table_id="main", game_master_id=3)
        table.join("p1", "Alice")
        table.join("p2", "Bertha")
        table.phase = "playing"
        table.players["p1"].hand = [Card("9", "clubs"), Card("2", "hearts")]
        table.players["p2"].hand = [Card("9", "spades"), Card("2", "diamonds")]
        table.current_player_index = 0

        table.timeout_current_player()

        self.assertTrue(table.players["p1"].stood)
        self.assertEqual(table.current_player().player_id, "p2")

    def test_next_player_id_sequential_and_disjoint_from_bots(self) -> None:
        table = Table(table_id="main", game_master_id=3)
        table.add_bot(None, "DealerBot", 25)

        self.assertEqual(table.next_player_id(), "p1")
        table.join("p1", "Alice")
        self.assertEqual(table.next_player_id(), "p2")

    def test_start_round_skips_already_stood_player_at_index_zero(self) -> None:
        table = Table(table_id="main", game_master_id=3)
        table.join("p1", "Alice")
        table.join("p2", "Bertha")
        table.place_bet("p1", 50)
        table.place_bet("p2", 50)
        # p1 gets a natural blackjack (auto-stood on deal), p2 stays active.
        fixed_deck = [
            Card("7", "diamonds"), Card("4", "diamonds"),
            Card("K", "hearts"), Card("A", "spades"),
            Card("3", "clubs"), Card("2", "clubs"),
        ]
        with patch("blackjack_royale.blackjack.new_deck", side_effect=lambda: list(fixed_deck)):
            table.start_round()

        self.assertTrue(table.players["p1"].stood)
        self.assertEqual(table.phase, "playing")
        self.assertEqual(table.current_player().player_id, "p2")
        self.assertEqual(table.snapshot()["current_player_id"], "p2")

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
        self.assertIsNotNone(table.turn_deadline)


if __name__ == "__main__":
    unittest.main()
