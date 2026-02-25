"""
Perfect Basic Strategy Engine
Based on Griffin's Theory of Blackjack and Stanford Wong's Professional Blackjack.
Covers: Hard hands, Soft hands, Pairs - all for standard 6-deck, S17, DAS, No RSA rules.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class Action(Enum):
    HIT        = "H"
    STAND      = "S"
    DOUBLE     = "D"
    SPLIT      = "P"
    SURRENDER  = "R"
    DOUBLE_HIT = "Dh"  # Double if allowed, else Hit
    DOUBLE_STAND = "Ds" # Double if allowed, else Stand
    SPLIT_HIT  = "Ph"  # Split if DAS allowed, else Hit
    SURRENDER_HIT = "Rh"  # Surrender if allowed, else Hit
    SURRENDER_SPLIT = "Rp" # Surrender if allowed, else Split
    SURRENDER_STAND = "Rs" # Surrender if allowed, else Stand

    def resolve(self, can_double: bool, can_split: bool, can_surrender: bool) -> 'Action':
        if self == Action.DOUBLE_HIT:
            return Action.DOUBLE if can_double else Action.HIT
        if self == Action.DOUBLE_STAND:
            return Action.DOUBLE if can_double else Action.STAND
        if self == Action.SPLIT_HIT:
            return Action.SPLIT if can_split else Action.HIT
        if self == Action.SURRENDER_HIT:
            return Action.SURRENDER if can_surrender else Action.HIT
        if self == Action.SURRENDER_SPLIT:
            return Action.SURRENDER if can_surrender else (Action.SPLIT if can_split else Action.HIT)
        if self == Action.SURRENDER_STAND:
            return Action.SURRENDER if can_surrender else Action.STAND
        return self


# ──────────────────────────────────────────────────────────────────────────────
# HARD HAND STRATEGY  (rows = player total 4-21, cols = dealer upcard 2-A)
# ──────────────────────────────────────────────────────────────────────────────
#                    2    3    4    5    6    7    8    9   10    A
HARD_STRATEGY = {
     4: [Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT ],
     5: [Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT ],
     6: [Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT ],
     7: [Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT ],
     8: [Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT ],
     9: [Action.HIT,  Action.DOUBLE_HIT, Action.DOUBLE_HIT, Action.DOUBLE_HIT, Action.DOUBLE_HIT, Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT ],
    10: [Action.DOUBLE_HIT, Action.DOUBLE_HIT, Action.DOUBLE_HIT, Action.DOUBLE_HIT, Action.DOUBLE_HIT, Action.DOUBLE_HIT, Action.DOUBLE_HIT, Action.DOUBLE_HIT, Action.HIT, Action.HIT ],
    11: [Action.DOUBLE_HIT, Action.DOUBLE_HIT, Action.DOUBLE_HIT, Action.DOUBLE_HIT, Action.DOUBLE_HIT, Action.DOUBLE_HIT, Action.DOUBLE_HIT, Action.DOUBLE_HIT, Action.DOUBLE_HIT, Action.DOUBLE_HIT],
    12: [Action.HIT,  Action.HIT,  Action.STAND, Action.STAND, Action.STAND, Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT ],
    13: [Action.STAND, Action.STAND, Action.STAND, Action.STAND, Action.STAND, Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT ],
    14: [Action.STAND, Action.STAND, Action.STAND, Action.STAND, Action.STAND, Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT ],
    15: [Action.STAND, Action.STAND, Action.STAND, Action.STAND, Action.STAND, Action.HIT,  Action.HIT,  Action.HIT,  Action.SURRENDER_HIT, Action.HIT ],
    16: [Action.STAND, Action.STAND, Action.STAND, Action.STAND, Action.STAND, Action.HIT,  Action.HIT,  Action.SURRENDER_HIT, Action.SURRENDER_HIT, Action.SURRENDER_HIT],
    17: [Action.STAND, Action.STAND, Action.STAND, Action.STAND, Action.STAND, Action.STAND, Action.STAND, Action.STAND, Action.STAND, Action.SURRENDER_STAND],
    18: [Action.STAND]*10,
    19: [Action.STAND]*10,
    20: [Action.STAND]*10,
    21: [Action.STAND]*10,
}

# ──────────────────────────────────────────────────────────────────────────────
# SOFT HAND STRATEGY  (rows = non-ace card value, cols = dealer upcard 2-A)
# ──────────────────────────────────────────────────────────────────────────────
#                      2    3    4    5    6    7    8    9   10    A
SOFT_STRATEGY = {
    2: [Action.HIT,  Action.HIT,  Action.HIT,  Action.DOUBLE_HIT, Action.DOUBLE_HIT, Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT ],  # A,2
    3: [Action.HIT,  Action.HIT,  Action.HIT,  Action.DOUBLE_HIT, Action.DOUBLE_HIT, Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT ],  # A,3
    4: [Action.HIT,  Action.HIT,  Action.DOUBLE_HIT, Action.DOUBLE_HIT, Action.DOUBLE_HIT, Action.HIT, Action.HIT, Action.HIT, Action.HIT, Action.HIT],   # A,4
    5: [Action.HIT,  Action.HIT,  Action.DOUBLE_HIT, Action.DOUBLE_HIT, Action.DOUBLE_HIT, Action.HIT, Action.HIT, Action.HIT, Action.HIT, Action.HIT],   # A,5
    6: [Action.DOUBLE_HIT, Action.DOUBLE_HIT, Action.DOUBLE_HIT, Action.DOUBLE_HIT, Action.DOUBLE_HIT, Action.HIT, Action.HIT, Action.HIT, Action.HIT, Action.HIT],  # A,6
    7: [Action.STAND, Action.DOUBLE_STAND, Action.DOUBLE_STAND, Action.DOUBLE_STAND, Action.DOUBLE_STAND, Action.STAND, Action.STAND, Action.HIT, Action.HIT, Action.HIT],  # A,7
    8: [Action.STAND, Action.STAND, Action.STAND, Action.STAND, Action.DOUBLE_STAND, Action.STAND, Action.STAND, Action.STAND, Action.STAND, Action.STAND],  # A,8
    9: [Action.STAND]*10,   # A,9
}

# ──────────────────────────────────────────────────────────────────────────────
# PAIR STRATEGY (rows = pair card value, cols = dealer upcard 2-A)
# ──────────────────────────────────────────────────────────────────────────────
#                      2    3    4    5    6    7    8    9   10    A
PAIR_STRATEGY = {
    2:  [Action.SPLIT_HIT, Action.SPLIT_HIT, Action.SPLIT, Action.SPLIT, Action.SPLIT, Action.SPLIT, Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT ],
    3:  [Action.SPLIT_HIT, Action.SPLIT_HIT, Action.SPLIT, Action.SPLIT, Action.SPLIT, Action.SPLIT, Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT ],
    4:  [Action.HIT,  Action.HIT,  Action.HIT,  Action.SPLIT_HIT, Action.SPLIT_HIT, Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT ],
    5:  [Action.DOUBLE_HIT]*8 + [Action.HIT, Action.HIT],  # Never split 5s
    6:  [Action.SPLIT_HIT, Action.SPLIT, Action.SPLIT, Action.SPLIT, Action.SPLIT, Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT ],
    7:  [Action.SPLIT, Action.SPLIT, Action.SPLIT, Action.SPLIT, Action.SPLIT, Action.SPLIT, Action.HIT,  Action.HIT,  Action.HIT,  Action.HIT ],
    8:  [Action.SPLIT, Action.SPLIT, Action.SPLIT, Action.SPLIT, Action.SPLIT, Action.SPLIT, Action.SPLIT, Action.SPLIT, Action.SPLIT, Action.SURRENDER_SPLIT],
    9:  [Action.SPLIT, Action.SPLIT, Action.SPLIT, Action.SPLIT, Action.SPLIT, Action.STAND, Action.SPLIT, Action.SPLIT, Action.STAND, Action.STAND],
    10: [Action.STAND]*10,  # Never split 10s
    11: [Action.SPLIT]*10,  # Always split Aces (11 = Ace)
}

DEALER_INDEX = {2: 0, 3: 1, 4: 2, 5: 3, 6: 4, 7: 5, 8: 6, 9: 7, 10: 8, 1: 9}  # 1 = Ace


@dataclass
class HandState:
    """Represents the current state of a blackjack hand."""
    player_cards: list[int]       # Card values (1=Ace, 2-10, face=10)
    dealer_upcard: int             # Dealer's visible card
    can_double: bool = True
    can_split: bool = True
    can_surrender: bool = True
    is_post_split: bool = False    # After splitting aces, limited actions

    @property
    def total(self) -> int:
        return best_total(self.player_cards)

    @property
    def is_soft(self) -> bool:
        return has_soft_ace(self.player_cards)

    @property
    def is_pair(self) -> bool:
        return (len(self.player_cards) == 2 and
                card_value(self.player_cards[0]) == card_value(self.player_cards[1]))

    @property
    def pair_value(self) -> Optional[int]:
        if self.is_pair:
            v = card_value(self.player_cards[0])
            return 11 if v == 1 else v  # Treat Ace pair as 11 in lookup
        return None


def card_value(card: int) -> int:
    """Normalize card to 1-11 range."""
    return min(card, 10)


def best_total(cards: list[int]) -> int:
    """Calculate best hand total (handles aces)."""
    total = sum(min(c, 10) for c in cards)
    aces = cards.count(1)
    # Promote one ace to 11 if it doesn't bust
    if aces > 0 and total + 10 <= 21:
        total += 10
    return total


def has_soft_ace(cards: list[int]) -> bool:
    """True if hand contains a soft ace (ace counted as 11)."""
    total = sum(min(c, 10) for c in cards)
    return 1 in cards and total + 10 <= 21


def get_action(state: HandState) -> tuple[Action, str]:
    """
    Returns the optimal action and a human-readable explanation.
    This is the core decision engine.
    """
    dealer_idx = DEALER_INDEX.get(min(state.dealer_upcard, 10), 8)
    raw_action: Action

    # ── 1. Pair check ──────────────────────────────────────────────────────────
    if state.is_pair and state.can_split and not state.is_post_split:
        pair_val = state.pair_value
        row = PAIR_STRATEGY.get(pair_val, [Action.HIT]*10)
        raw_action = row[dealer_idx]
        category = f"PAIR ({pair_val},{pair_val})"

    # ── 2. Soft hand ───────────────────────────────────────────────────────────
    elif state.is_soft and state.total < 21:
        # Key: which non-ace card? total = 11 + other, so other = total - 11
        other = state.total - 11
        other = max(2, min(9, other))  # clamp to table range
        row = SOFT_STRATEGY.get(other, [Action.STAND]*10)
        raw_action = row[dealer_idx]
        category = f"SOFT {state.total}"

    # ── 3. Hard hand ───────────────────────────────────────────────────────────
    else:
        total = min(max(state.total, 4), 21)
        row = HARD_STRATEGY.get(total, [Action.STAND]*10)
        raw_action = row[dealer_idx]
        category = f"HARD {state.total}"

    # ── Resolve conditional actions ────────────────────────────────────────────
    final_action = raw_action.resolve(
        can_double=state.can_double and len(state.player_cards) == 2,
        can_split=state.can_split,
        can_surrender=state.can_surrender
    )

    explanation = _explain(final_action, category, state.dealer_upcard)
    return final_action, explanation


def _explain(action: Action, category: str, dealer_upcard: int) -> str:
    dealer_str = "Ace" if dealer_upcard == 1 else str(dealer_upcard)
    msgs = {
        Action.HIT:       f"{category} vs dealer {dealer_str} → HIT (maximize drawing potential)",
        Action.STAND:     f"{category} vs dealer {dealer_str} → STAND (dealer likely busts or you have enough)",
        Action.DOUBLE:    f"{category} vs dealer {dealer_str} → DOUBLE DOWN (highest EV play — bet max here)",
        Action.SPLIT:     f"{category} vs dealer {dealer_str} → SPLIT (create two winning hands)",
        Action.SURRENDER: f"{category} vs dealer {dealer_str} → SURRENDER (save 50% — EV loss too steep)",
    }
    return msgs.get(action, f"{category} → {action.value}")
