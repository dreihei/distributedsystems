"""Pure Blackjack rules without networking."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

SUITS = ("hearts", "diamonds", "clubs", "spades")
RANKS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")


@dataclass(frozen=True)
class Card:
    rank: str
    suit: str

    def label(self) -> str:
        return f"{self.rank} of {self.suit}"

    def to_dict(self) -> dict:
        return {"rank": self.rank, "suit": self.suit}

    @staticmethod
    def from_dict(raw: dict) -> "Card":
        return Card(rank=raw["rank"], suit=raw["suit"])


def new_deck() -> list[Card]:
    deck = [Card(rank, suit) for suit in SUITS for rank in RANKS]
    random.shuffle(deck)
    return deck


def hand_value(cards: list[Card]) -> int:
    total = 0
    aces = 0
    for card in cards:
        if card.rank == "A":
            aces += 1
            total += 11
        elif card.rank in {"J", "Q", "K"}:
            total += 10
        else:
            total += int(card.rank)

    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def is_blackjack(cards: list[Card]) -> bool:
    return len(cards) == 2 and hand_value(cards) == 21


def is_bust(cards: list[Card]) -> bool:
    return hand_value(cards) > 21


@dataclass
class Player:
    player_id: str
    name: str
    balance: int = 1000
    bet: int = 0
    default_bet: int = 50
    hand: list[Card] = field(default_factory=list)
    connected: bool = True
    stood: bool = False
    is_bot: bool = False

    def to_dict(self) -> dict:
        return {
            "player_id": self.player_id,
            "name": self.name,
            "balance": self.balance,
            "bet": self.bet,
            "default_bet": self.default_bet,
            "hand": [card.to_dict() for card in self.hand],
            "connected": self.connected,
            "stood": self.stood,
            "is_bot": self.is_bot,
        }

    @staticmethod
    def from_dict(raw: dict) -> "Player":
        return Player(
            player_id=raw["player_id"],
            name=raw["name"],
            balance=raw["balance"],
            bet=raw["bet"],
            default_bet=raw.get("default_bet", 50),
            hand=[Card.from_dict(card) for card in raw["hand"]],
            connected=raw["connected"],
            stood=raw["stood"],
            is_bot=raw.get("is_bot", False),
        )


@dataclass
class Table:
    table_id: str
    game_master_id: int
    phase: str = "waiting"
    deck: list[Card] = field(default_factory=new_deck)
    players: dict[str, Player] = field(default_factory=dict)
    dealer_hand: list[Card] = field(default_factory=list)
    current_player_index: int = 0
    state_version: int = 0
    last_result: dict | None = None
    dealer_action: str = "waiting"

    def join(self, player_id: str, name: str, is_bot: bool = False) -> Player:
        player = self.players.get(player_id)
        if player:
            player.connected = True
            return player
        player = Player(player_id=player_id, name=name, is_bot=is_bot)
        self.players[player_id] = player
        self.bump()
        return player

    def place_bet(self, player_id: str, amount: int) -> None:
        player = self.players[player_id]
        amount = max(1, min(amount, player.balance))
        player.bet = amount
        player.default_bet = amount
        self.bump()

    def add_bot(self, bot_id: str, name: str, default_bet: int = 50) -> Player:
        bot = self.join(bot_id, name, is_bot=True)
        bot.default_bet = default_bet
        if bot.bet == 0 and bot.balance > 0:
            self.place_bet(bot.player_id, default_bet)
        return bot

    def start_round(self, auto_bets: bool = False) -> None:
        self.phase = "playing"
        self.deck = new_deck()
        self.dealer_hand = [self.draw(), self.draw()]
        if auto_bets:
            self.prepare_auto_bets()
        for player in self.players.values():
            player.hand = [self.draw(), self.draw()]
            player.stood = False
        self.current_player_index = 0
        self.dealer_action = "waiting for players"
        self.play_bots()
        self.bump()

    def hit(self, player_id: str) -> None:
        player = self.players[player_id]
        player.hand.append(self.draw())
        if is_bust(player.hand):
            player.stood = True
        self.advance_turn()
        self.bump()

    def stand(self, player_id: str) -> None:
        self.players[player_id].stood = True
        self.advance_turn()
        self.bump()

    def finish_dealer(self) -> None:
        self.dealer_action = "drawing"
        while hand_value(self.dealer_hand) < 17:
            self.dealer_hand.append(self.draw())
        self.dealer_action = "stand" if hand_value(self.dealer_hand) <= 21 else "bust"
        self.phase = "finished"
        self.last_result = self.build_result()
        self.settle_bets()
        if self.has_human_players_with_money():
            self.start_round(auto_bets=True)
        self.bump()

    def build_result(self) -> dict:
        dealer_score = hand_value(self.dealer_hand)
        dealer_bust = dealer_score > 21
        players = {}
        for player_id, player in self.players.items():
            score = hand_value(player.hand)
            if score > 21:
                outcome = "lost"
                payout = 0
            elif is_blackjack(player.hand) and not is_blackjack(self.dealer_hand):
                outcome = "blackjack"
                payout = int(player.bet * 2.5)
            elif dealer_bust or score > dealer_score:
                outcome = "won"
                payout = player.bet * 2
            elif score == dealer_score:
                outcome = "push"
                payout = player.bet
            else:
                outcome = "lost"
                payout = 0
            players[player_id] = {
                "name": player.name,
                "bet": player.bet,
                "hand": [card.label() for card in player.hand],
                "value": score,
                "outcome": outcome,
                "payout": payout,
                "is_bot": player.is_bot,
            }
        return {
            "dealer_hand": [card.label() for card in self.dealer_hand],
            "dealer_value": dealer_score,
            "dealer_action": self.dealer_action,
            "dealer_bust": dealer_bust,
            "players": players,
        }

    def advance_turn(self) -> None:
        self.play_bots()
        active = list(self.players.values())
        while self.current_player_index < len(active) and active[self.current_player_index].stood:
            self.current_player_index += 1
        if self.current_player_index >= len(active):
            self.finish_dealer()

    def settle_bets(self) -> None:
        if self.last_result is None:
            self.last_result = self.build_result()
        for player_id, player in self.players.items():
            payout = self.last_result["players"][player_id]["payout"]
            player.balance += payout - player.bet
            player.bet = 0

    def prepare_auto_bets(self) -> None:
        for player in self.players.values():
            if player.balance <= 0:
                player.bet = 0
                player.stood = True
                continue
            amount = max(1, min(player.default_bet, player.balance))
            player.bet = amount

    def play_bots(self) -> None:
        if self.phase != "playing":
            return
        for player in self.players.values():
            if not player.is_bot or player.stood:
                continue
            while hand_value(player.hand) < 16:
                player.hand.append(self.draw())
            player.stood = True

    def current_player(self) -> Player | None:
        active = list(self.players.values())
        if self.current_player_index >= len(active):
            return None
        return active[self.current_player_index]

    def has_human_players_with_money(self) -> bool:
        return any(not player.is_bot and player.balance > 0 for player in self.players.values())

    def all_players_done(self) -> bool:
        return bool(self.players) and all(player.stood or is_bust(player.hand) for player in self.players.values())

    def draw(self) -> Card:
        if not self.deck:
            self.deck = new_deck()
        return self.deck.pop()

    def bump(self) -> None:
        self.state_version += 1

    def snapshot(self) -> dict:
        return {
            "table_id": self.table_id,
            "game_master_id": self.game_master_id,
            "phase": self.phase,
            "state_version": self.state_version,
            "dealer_hand": [card.label() for card in self.dealer_hand],
            "dealer_value": hand_value(self.dealer_hand),
            "dealer_action": self.dealer_action,
            "last_result": self.last_result,
            "players": {
                pid: {
                    "name": player.name,
                    "balance": player.balance,
                    "bet": player.bet,
                    "default_bet": player.default_bet,
                    "hand": [card.label() for card in player.hand],
                    "value": hand_value(player.hand),
                    "connected": player.connected,
                    "stood": player.stood,
                    "is_bot": player.is_bot,
                }
                for pid, player in self.players.items()
            },
        }

    def to_dict(self) -> dict:
        return {
            "table_id": self.table_id,
            "game_master_id": self.game_master_id,
            "phase": self.phase,
            "deck": [card.to_dict() for card in self.deck],
            "players": {pid: player.to_dict() for pid, player in self.players.items()},
            "dealer_hand": [card.to_dict() for card in self.dealer_hand],
            "current_player_index": self.current_player_index,
            "state_version": self.state_version,
            "last_result": self.last_result,
            "dealer_action": self.dealer_action,
        }

    @staticmethod
    def from_dict(raw: dict) -> "Table":
        table = Table(table_id=raw["table_id"], game_master_id=raw["game_master_id"])
        table.phase = raw["phase"]
        table.deck = [Card.from_dict(card) for card in raw["deck"]]
        table.players = {pid: Player.from_dict(player) for pid, player in raw["players"].items()}
        table.dealer_hand = [Card.from_dict(card) for card in raw["dealer_hand"]]
        table.current_player_index = raw["current_player_index"]
        table.state_version = raw["state_version"]
        table.last_result = raw.get("last_result")
        table.dealer_action = raw.get("dealer_action", "waiting")
        return table
