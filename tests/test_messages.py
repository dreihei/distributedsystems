import unittest

from blackjack_royale.messages import Message


class MessageTest(unittest.TestCase):
    def test_message_line_round_trip(self) -> None:
        original = Message("HEARTBEAT", "1", {"server_id": 1})
        restored = Message.from_line(original.to_line())

        self.assertEqual(restored.type, "HEARTBEAT")
        self.assertEqual(restored.sender, "1")
        self.assertEqual(restored.payload["server_id"], 1)


if __name__ == "__main__":
    unittest.main()
