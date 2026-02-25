"""
Hi-Lo Card Counting System
The gold standard. Balanced count, Level 1, high correlation to player edge.
Includes: Running count, True count, Illustrious 18 deviations, Fab 4 surrenders.
"""

from dataclasses import dataclass, field
from typing import Optional


# ──────────────────────────────────────────────────────────────────────────────
# Hi-Lo Tag Values
# ──────────────────────────────────────────────────────────────────────────────
HI_LO_TAGS = {
    1:  -1,   # Ace
    2:  +1,
    3:  +1,
    4:  +1,
    5:  +1,
    6:  +1,
    7:   0,
    8:   0,
    9:   0,
    10: -1,   # 10, J, Q, K
}

# Cards per deck
CARDS_PER_DECK = 52


@dataclass
class CountState:
    running_count: int = 0
    decks_remaining: float = 6.0
    cards_seen: int = 0
    total_decks: int = 6

    @property
    def true_count(self) -> float:
        if self.decks_remaining <= 0:
            return self.running_count
        return self.running_count / self.decks_remaining

    @property
    def player_edge(self) -> float:
        """
        Approximate player edge (%).
        Base house edge for 6-deck S17 DAS is ~0.4%.
        Each TC point worth ~0.5%.
        """
        base_house_edge = -0.004   # -0.4%
        return base_house_edge + (self.true_count * 0.005)

    @property
    def bet_units(self) -> int:
        """
        Optimal bet sizing in units based on true count.
        Spread: 1-12 units.
        """
        tc = self.true_count
        if tc <= 1:   return 1
        if tc == 2:   return 2
        if tc == 3:   return 4
        if tc == 4:   return 6
        if tc == 5:   return 8
        return 12  # TC >= 6

    def decks_remaining_from_cards(self, cards_seen: int, total_decks: int) -> float:
        cards_in_shoe = total_decks * CARDS_PER_DECK
        return max(0.25, (cards_in_shoe - cards_seen) / CARDS_PER_DECK)


class CardCounter:
    """
    Hi-Lo card counter with full deviation tables.
    """

    def __init__(self, total_decks: int = 6):
        self.total_decks = total_decks
        self.state = CountState(total_decks=total_decks, decks_remaining=float(total_decks))
        self._card_history: list[int] = []

    def see_card(self, card: int) -> None:
        """Register a seen card (1=Ace, 10=all faces)."""
        card = min(card, 10)
        self.state.running_count += HI_LO_TAGS.get(card, 0)
        self.state.cards_seen += 1
        self.state.decks_remaining = self.state.decks_remaining_from_cards(
            self.state.cards_seen, self.total_decks
        )
        self._card_history.append(card)

    def see_cards(self, cards: list[int]) -> None:
        for c in cards:
            self.see_card(c)

    def reset_shoe(self) -> None:
        self.state = CountState(total_decks=self.total_decks, decks_remaining=float(self.total_decks))
        self._card_history.clear()

    @property
    def true_count(self) -> float:
        return self.state.true_count

    @property
    def running_count(self) -> int:
        return self.state.running_count

    # ──────────────────────────────────────────────────────────────────────────
    # ILLUSTRIOUS 18 — Basic Strategy Deviations
    # Source: Don Schlesinger's Blackjack Attack
    # Format: (player_total, dealer_upcard, is_soft): (pivot_tc, action_at_or_above, action_below)
    # ──────────────────────────────────────────────────────────────────────────
    ILLUSTRIOUS_18 = {
        # (player_total, dealer_upcard): (tc_pivot, action_above_or_at, action_below)
        ("insurance", 0):       (+3,  "TAKE_INSURANCE",  "NO_INSURANCE"),  # TC >= 3: take insurance
        (16,  10):              (+0,  "STAND",            "HIT"),
        (15,  10):              (+4,  "STAND",            "SURRENDER_OR_HIT"),
        (20,   5):              (+5,  "DOUBLE",           "STAND"),
        (20,   6):              (+4,  "DOUBLE",           "STAND"),
        (10,  10):              (+4,  "DOUBLE",           "HIT"),
        (12,   3):              (+2,  "STAND",            "HIT"),
        (12,   2):              (+3,  "STAND",            "HIT"),
        (11,  11):              (+1,  "DOUBLE",           "HIT"),   # 11 = Ace
        (9,    2):              (+1,  "DOUBLE",           "HIT"),
        (10,  11):              (+4,  "DOUBLE",           "HIT"),
        (9,    7):              (+3,  "DOUBLE",           "HIT"),
        (16,   9):              (+5,  "STAND",            "SURRENDER_OR_HIT"),
        (13,   2):              (-1,  "STAND",            "HIT"),
        (12,   4):              (+0,  "STAND",            "HIT"),
        (12,   5):              (-2,  "STAND",            "HIT"),
        (12,   6):              (-1,  "STAND",            "HIT"),
        (13,   3):              (-2,  "STAND",            "HIT"),
    }

    def get_deviation(self, player_total: int, dealer_upcard: int) -> Optional[str]:
        """
        Check if true count warrants a deviation from basic strategy.
        Returns action string if deviation applies, None otherwise.
        """
        dealer_val = min(dealer_upcard, 10) if dealer_upcard != 1 else 11
        tc = self.true_count

        key = (player_total, dealer_val)
        if key not in self.ILLUSTRIOUS_18:
            return None

        pivot_tc, action_above, action_below = self.ILLUSTRIOUS_18[key]

        if tc >= pivot_tc:
            return action_above
        else:
            return action_below

    def check_insurance(self) -> tuple[bool, str]:
        """Should we take insurance? Only profitable at TC >= 3."""
        tc = self.true_count
        if tc >= 3:
            return True, f"✅ TAKE INSURANCE — True Count {tc:.1f} ≥ 3.0 (profitable)"
        return False, f"❌ SKIP INSURANCE — True Count {tc:.1f} < 3.0 (negative EV)"

    def betting_recommendation(self, unit_size: float) -> dict:
        """Full betting recommendation for next hand."""
        units = self.state.bet_units
        tc = self.true_count
        edge = self.state.player_edge * 100

        return {
            "bet_units": units,
            "bet_amount": units * unit_size,
            "true_count": round(tc, 2),
            "running_count": self.running_count,
            "decks_remaining": round(self.state.decks_remaining, 2),
            "player_edge_pct": round(edge, 3),
            "table_status": _table_status(tc),
        }


def _table_status(tc: float) -> str:
    if tc >= 4:   return "🔥 HOT — Maximum bet!"
    if tc >= 2:   return "✅ FAVORABLE — Increase bet"
    if tc >= 0:   return "⚖️  NEUTRAL — Min/table bet"
    if tc >= -2:  return "⚠️  UNFAVORABLE — Minimum bet"
    return "❄️  COLD — Leave table or minimum bet"
