"""
Core BlackJack game logic and components.

This module encapsulates all the rules, components (Card, Deck, Player, AIPlayer),
and state management (`GameSession`) for a BlackJack game. 

It is designed to be fully serializable to/from JSON to support
a stateless, Redis-backed architecture.
"""
import random
import logging
from enum import Enum

logger = logging.getLogger(__name__)

class DIFFICULTY(Enum):
    EASY = 1
    MEDIUM = 2
    HARD = 3

class GamePhase(Enum):
    WAITING_FOR_BET = "waiting_for_bet"
    DEALING = "dealing"
    PLAYER_TURN = "player_turn"
    AI_TURN = "ai_turn"
    DEALER_TURN = "dealer_turn"
    ROUND_END = "round_end"
    GAME_OVER = "game_over"


class Card:
    """
    Represents a single playing card. Fully JSON serializable.
    """
    def __init__(self, suit: str, rank: str):
        self.suit = suit
        self.rank = rank
        self.value = self._get_value(rank)

    def _get_value(self, rank: str) -> int:
        if rank in ['Jack', 'Queen', 'King']:
            return 10
        elif rank == 'Ace':
            return 11
        else:
            return int(rank)

    def to_dict(self) -> dict:
        return {'suit': self.suit, 'rank': self.rank}

    @classmethod
    def from_dict(cls, data: dict):
        if not data:
            return None
        return cls(data['suit'], data['rank'])

    def __repr__(self) -> str:
        return f"{self.rank} of {self.suit}"


class Deck:
    """
    Represents a deck of 52 playing cards. Fully JSON serializable.
    """
    SUITS = ['Hearts', 'Diamonds', 'Clubs', 'Spades']
    RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'Jack', 'Queen', 'King', 'Ace']

    def __init__(self, create_new=True):
        self.cards: list[Card] = []
        if create_new:
            self.cards = self._create_deck()
            self.shuffle()

    def _create_deck(self) -> list[Card]:
        return [Card(suit, rank) for suit in self.SUITS for rank in self.RANKS]

    def shuffle(self):
        random.shuffle(self.cards)
        logger.info("Deck shuffled.")

    def deal_card(self) -> Card:
        if not self.cards:
            logger.error("Attempted to deal from an empty deck.")
            raise IndexError("Deck is empty!")
        card = self.cards.pop()
        logger.debug(f"Dealt card: {card}")
        return card

    def remaining_cards(self) -> int:
        return len(self.cards)

    def to_dict(self) -> dict:
        # Serialize the *entire* deck state, including remaining cards
        return {'cards': [card.to_dict() for card in self.cards]}

    @classmethod
    def from_dict(cls, data: dict):
        deck = cls(create_new=False) # Create an empty deck
        deck.cards = [Card.from_dict(c_data) for c_data in data['cards']]
        return deck


class Player:
    """
    Base class for a Blackjack player. Fully JSON serializable.
    """
    def __init__(self, name: str, is_dealer: bool = False):
        self.name = name
        self.hand: list[Card] = []
        self.is_dealer = is_dealer

    def add_card(self, card: Card):
        self.hand.append(card)
        logger.debug(f"{self.name} received {card}.")

    def get_score(self) -> int:
        score = sum(card.value for card in self.hand)
        num_aces = sum(1 for card in self.hand if card.rank == 'Ace')
        while score > 21 and num_aces > 0:
            score -= 10
            num_aces -= 1
        return score

    def is_bust(self) -> bool:
        return self.get_score() > 21

    def is_blackjack(self) -> bool:
        return len(self.hand) == 2 and self.get_score() == 21

    def clear_hand(self):
        self.hand = []

    def get_hand_display(self, hide_first_card: bool = False) -> list[dict]:
        if hide_first_card and self.is_dealer and len(self.hand) > 0:
            return [{'suit': 'Hidden', 'rank': 'Hidden', 'value': 0}] + [card.to_dict() for card in self.hand[1:]]
        return [card.to_dict() for card in self.hand]

    def to_dict_for_state(self, hide_dealer_first_card: bool = False) -> dict:
        """
        Generates a dictionary for the *client state* (get_game_state).
        This hides information as needed.
        """
        score = self.get_score()
        hand_display = self.get_hand_display(hide_dealer_first_card)
        
        if hide_dealer_first_card and self.is_dealer and len(self.hand) > 1:
            # Show only the value of the up-card
            score = self.hand[1].value
        elif hide_dealer_first_card and self.is_dealer:
            score = 0

        return {
            'name': self.name,
            'hand': hand_display,
            'score': score,
            'is_bust': self.is_bust(),
            'is_blackjack': self.is_blackjack()
        }

    def to_dict(self) -> dict:
        """
        Serializes the *full* object state for Redis.
        """
        return {
            'name': self.name,
            'hand': [card.to_dict() for card in self.hand],
            'is_dealer': self.is_dealer,
            # Subclasses will add their own data
        }

    @classmethod
    def from_dict(cls, data: dict):
        player = cls(data['name'], data.get('is_dealer', False))
        player.hand = [Card.from_dict(c_data) for c_data in data['hand']]
        return player


class HumanPlayer(Player):
    """
    Represents the human player. Fully JSON serializable.
    """
    def __init__(self, name: str, initial_balance: int = 1000):
        super().__init__(name, is_dealer=False)
        self.balance = initial_balance
        self.current_bet = 0

    def place_bet(self, amount: int) -> bool:
        if amount <= 0 or amount > self.balance:
            logger.warning(f"Invalid bet amount {amount} for {self.name} with balance {self.balance}")
            return False
        self.current_bet = amount
        self.balance -= amount
        logger.info(f"{self.name} placed a bet of {amount}. New balance: {self.balance}")
        return True

    def win_bet(self, multiplier: float = 2.0):
        winnings = int(self.current_bet * multiplier)
        self.balance += winnings
        logger.info(f"{self.name} won {winnings}. New balance: {self.balance}")
        self.current_bet = 0

    def lose_bet(self):
        logger.info(f"{self.name} lost their bet of {self.current_bet}. Current balance: {self.balance}")
        self.current_bet = 0

    def push_bet(self):
        self.balance += self.current_bet
        logger.info(f"{self.name} pushed. Bet {self.current_bet} returned. New balance: {self.balance}")
        self.current_bet = 0

    def to_dict_for_state(self, hide_dealer_first_card: bool = False) -> dict:
        """
        Generates a dictionary for the *client state*.
        """
        player_data = super().to_dict_for_state(hide_dealer_first_card)
        player_data['balance'] = self.balance
        player_data['current_bet'] = self.current_bet
        return player_data

    def to_dict(self) -> dict:
        """
        Serializes the *full* object state for Redis.
        """
        data = super().to_dict()
        data.update({
            'balance': self.balance,
            'current_bet': self.current_bet
        })
        return data

    @classmethod
    def from_dict(cls, data: dict):
        player = super().from_dict(data) # This will be HumanPlayer(name, is_dealer)
        player.balance = data['balance']
        player.current_bet = data['current_bet']
        return player


class AIPlayer(Player):
    """
    Represents an AI player. Fully JSON serializable.
    """
    def __init__(self, name: str, difficulty: DIFFICULTY = DIFFICULTY.MEDIUM):
        super().__init__(name, is_dealer=False)
        self.difficulty = difficulty

    def decide_action(self, dealer_up_card: Card) -> str:
        player_score = self.get_score()
        dealer_value = dealer_up_card.value

        if self.difficulty == DIFFICULTY.EASY:
            if player_score < 17:
                return 'hit'
            else:
                return 'stand'
        
        elif self.difficulty == DIFFICULTY.MEDIUM:
            if player_score < 12: return 'hit'
            if player_score >= 17: return 'stand'
            if 12 <= player_score <= 16:
                if dealer_value >= 7 or dealer_value == 11: return 'hit'
                else: return 'stand'
            return 'stand'

        elif self.difficulty == DIFFICULTY.HARD:
            if player_score <= 11: return 'hit'
            if player_score == 12:
                if 4 <= dealer_value <= 6: return 'stand'
                else: return 'hit'
            if 13 <= player_score <= 16:
                if 2 <= dealer_value <= 6: return 'stand'
                else: return 'hit'
            if player_score >= 17: return 'stand'
            return 'stand'
        
        return 'stand'

    def to_dict(self) -> dict:
        """
        Serializes the *full* object state for Redis.
        """
        data = super().to_dict()
        data.update({
            'difficulty': self.difficulty.name
        })
        return data

    @classmethod
    def from_dict(cls, data: dict):
        player = super().from_dict(data) # This will be AIPlayer(name, is_dealer)
        player.difficulty = DIFFICULTY[data['difficulty']]
        return player


class GameSession:
    """
    Manages the state and flow of a single BlackJack game for a specific user session.
    Fully JSON serializable.
    """
    def __init__(self, session_id: str, difficulty: DIFFICULTY, initial_balance: int = 1000):
        self.session_id = session_id
        self.player = HumanPlayer("Player", initial_balance)
        self.ai_player = AIPlayer("AI Player", difficulty)
        self.dealer = Player("Dealer", is_dealer=True)
        self.deck = Deck()
        self.phase = GamePhase.WAITING_FOR_BET
        self.difficulty = difficulty
        self.last_round_winner: str = "None"
        logger.info(f"Game session {session_id} initialized for difficulty {difficulty.name}.")

    def get_game_state(self, hide_dealer_first_card: bool = True) -> dict:
        """
        Returns the current *client-facing state* of the game session.
        """
        return {
            'session_id': self.session_id,
            'player': self.player.to_dict_for_state(),
            'ai_player': self.ai_player.to_dict_for_state(),
            'dealer': self.dealer.to_dict_for_state(hide_dealer_first_card),
            'deck': {"remaining": self.deck.remaining_cards()}, # Only send remaining count
            'phase': self.phase.value,
            'difficulty': self.difficulty.name,
            'last_round_winner': self.last_round_winner,
            'can_bet': self.phase == GamePhase.WAITING_FOR_BET or self.phase == GamePhase.ROUND_END,
            'can_hit_stand': self.phase == GamePhase.PLAYER_TURN,
            'is_game_over': self.player.balance <= 0 and self.phase == GamePhase.GAME_OVER
        }

    def start_round(self, bet_amount: int):
        if self.phase != GamePhase.WAITING_FOR_BET and self.phase != GamePhase.ROUND_END:
            raise ValueError("Cannot start round at this time.")
        if self.player.balance <= 0:
            self.phase = GamePhase.GAME_OVER
            raise ValueError("Game Over. Player has no money.")
        if not self.player.place_bet(bet_amount):
            raise ValueError(f"Invalid bet amount {bet_amount} or insufficient funds.")
        
        self.player.clear_hand()
        self.ai_player.clear_hand()
        self.dealer.clear_hand()
        self.last_round_winner = "None"

        if self.deck.remaining_cards() < 15: # Reshuffle if deck is low
            self.deck = Deck()
            logger.info("Deck was low, new deck created and shuffled.")

        self.phase = GamePhase.DEALING
        logger.info(f"Round started for {self.session_id} with bet {bet_amount}.")
        
        try:
            self.player.add_card(self.deck.deal_card())
            self.ai_player.add_card(self.deck.deal_card())
            self.dealer.add_card(self.deck.deal_card())
            self.player.add_card(self.deck.deal_card())
            self.ai_player.add_card(self.deck.deal_card())
            self.dealer.add_card(self.deck.deal_card())
        except IndexError as e:
            logger.error(f"Deck ran out during initial deal: {e}")
            self.deck = Deck() # Failsafe: reset deck
            raise ValueError("Deck error. Round reset.")

        if self.player.is_blackjack():
            self.phase = GamePhase.AI_TURN
        elif self.ai_player.is_blackjack():
            self.phase = GamePhase.DEALER_TURN
        elif self.dealer.is_blackjack():
            self.phase = GamePhase.DEALER_TURN
        else:
            self.phase = GamePhase.PLAYER_TURN
        
        logger.info(f"Initial deal complete. Current phase: {self.phase.value}")
        # No return value, state is saved in routes
    
    def player_hit(self):
        if self.phase != GamePhase.PLAYER_TURN:
            raise ValueError("Not player's turn to hit.")

        self.player.add_card(self.deck.deal_card())
        logger.info(f"{self.player.name} hit. Score: {self.player.get_score()}")

        if self.player.is_bust() or self.player.get_score() == 21:
            self.phase = GamePhase.AI_TURN
    
    def player_stand(self):
        if self.phase != GamePhase.PLAYER_TURN:
            raise ValueError("Not player's turn to stand.")
        
        logger.info(f"{self.player.name} stood. Score: {self.player.get_score()}.")
        self.phase = GamePhase.AI_TURN
    
    def play_ai_turn(self):
        if self.phase != GamePhase.AI_TURN:
            raise ValueError("Not AI player's turn.")
        
        if self.player.is_bust():
            self.phase = GamePhase.DEALER_TURN
            logger.info("Player busted, skipping AI turn.")
            return

        while not self.ai_player.is_bust() and self.ai_player.get_score() < 21:
            dealer_up_card = self.dealer.hand[1]
            action = self.ai_player.decide_action(dealer_up_card)
            
            if action == 'hit':
                self.ai_player.add_card(self.deck.deal_card())
                logger.info(f"{self.ai_player.name} hit. Score: {self.ai_player.get_score()}")
            else:
                logger.info(f"{self.ai_player.name} stood. Score: {self.ai_player.get_score()}")
                break
        
        self.phase = GamePhase.DEALER_TURN

    def play_dealer_turn(self):
        if self.phase != GamePhase.DEALER_TURN:
            raise ValueError("Not dealer's turn.")
        
        logger.info("Dealer's turn started. Revealing hole card.")

        while self.dealer.get_score() < 17:
            self.dealer.add_card(self.deck.deal_card())
            logger.info(f"Dealer hit. Score: {self.dealer.get_score()}")
        
        logger.info(f"Dealer stood/busted. Final score: {self.dealer.get_score()}")
        self.phase = GamePhase.ROUND_END
        self._determine_winner()

    def _determine_winner(self):
        player_score = self.player.get_score()
        dealer_score = self.dealer.get_score()
        player_bust = self.player.is_bust()
        dealer_bust = self.dealer.is_bust()
        player_blackjack = self.player.is_blackjack()
        dealer_blackjack = self.dealer.is_blackjack()

        # Evaluate Player vs Dealer
        if player_bust:
            self.player.lose_bet()
            player_result = "Bust (Loss)"
        elif dealer_bust:
            if player_blackjack:
                self.player.win_bet(2.5)
                player_result = "Blackjack (Win)"
            else:
                self.player.win_bet()
                player_result = "Win (Dealer Bust)"
        elif player_blackjack and not dealer_blackjack:
            self.player.win_bet(2.5)
            player_result = "Blackjack (Win)"
        elif dealer_blackjack and not player_blackjack:
            self.player.lose_bet()
            player_result = "Loss (Dealer Blackjack)"
        elif player_score > dealer_score:
            self.player.win_bet()
            player_result = "Win"
        elif player_score < dealer_score:
            self.player.lose_bet()
            player_result = "Loss"
        else: # player_score == dealer_score
            self.player.push_bet()
            player_result = "Push"

        if player_result.startswith("Win") or player_result.startswith("Blackjack"):
            self.last_round_winner = self.player.name
        elif player_result.startswith("Loss"):
            self.last_round_winner = self.dealer.name
        else:
            self.last_round_winner = "Push"
            
        logger.info(f"Round result for {self.player.name}: {player_result}. New balance: {self.player.balance}")

        if self.player.balance <= 0:
            self.phase = GamePhase.GAME_OVER
            logger.info(f"Player {self.player.name} ran out of money. Game Over.")
    
    def reset_game(self, initial_balance: int = 1000):
        """
        Resets the entire game session, restoring initial balance and getting a new deck.
        """
        self.player = HumanPlayer("Player", initial_balance)
        self.ai_player = AIPlayer("AI Player", self.difficulty)
        self.dealer = Player("Dealer", is_dealer=True)
        self.deck = Deck()
        self.phase = GamePhase.WAITING_FOR_BET
        self.last_round_winner = "None"
        logger.info(f"Game session {self.session_id} reset.")

    def to_dict(self) -> dict:
        """
        Serializes the *entire* game session for storage in Redis.
        """
        return {
            'session_id': self.session_id,
            'player': self.player.to_dict(),
            'ai_player': self.ai_player.to_dict(),
            'dealer': self.dealer.to_dict(),
            'deck': self.deck.to_dict(),
            'phase': self.phase.name, # Store enum by name
            'difficulty': self.difficulty.name,
            'last_round_winner': self.last_round_winner
        }

    @classmethod
    def from_dict(cls, data: dict):
        """
        Reconstructs a GameSession object from a dictionary (e.g., from Redis).
        """
        difficulty = DIFFICULTY[data['difficulty']]
        session_id = data['session_id']
        
        # Create an empty session
        session = cls(session_id, difficulty, 1000) 
        
        # Overwrite the components with the loaded data
        session.player = HumanPlayer.from_dict(data['player'])
        session.ai_player = AIPlayer.from_dict(data['ai_player'])
        session.dealer = Player.from_dict(data['dealer'])
        session.deck = Deck.from_dict(data['deck'])
        session.phase = GamePhase[data['phase']]
        session.last_round_winner = data['last_round_winner']
        
        logger.debug(f"Game session {session_id} reconstructed from Redis.")
        return session