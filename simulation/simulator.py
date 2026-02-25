"""
Monte Carlo Simulation Engine
Validates strategy EV, stress-tests bankroll, computes house edge empirically.
Runs millions of hands to produce statistically significant results.
"""

import random
import numpy as np
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict
import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core.strategy import get_action, HandState, Action, best_total, has_soft_ace


# ──────────────────────────────────────────────────────────────────────────────
# SHOE / DECK MANAGEMENT
# ──────────────────────────────────────────────────────────────────────────────

def build_shoe(num_decks: int = 6) -> list[int]:
    """Build a shuffled shoe. Cards 1-10 (1=Ace, 10=all faces)."""
    single_deck = [1]*4 + [2]*4 + [3]*4 + [4]*4 + [5]*4 + [6]*4 + [7]*4 + [8]*4 + [9]*4 + [10]*16
    shoe = single_deck * num_decks
    random.shuffle(shoe)
    return shoe


def draw(shoe: list[int], shoe_idx: list[int]) -> int:
    card = shoe[shoe_idx[0]]
    shoe_idx[0] += 1
    return card


# ──────────────────────────────────────────────────────────────────────────────
# DEALER PLAY
# ──────────────────────────────────────────────────────────────────────────────

def dealer_play(hand: list[int], shoe: list[int], shoe_idx: list[int],
                stand_soft_17: bool = True) -> list[int]:
    """Dealer draws until 17+ (stands on soft 17 = S17 rules)."""
    while True:
        total = best_total(hand)
        is_soft = has_soft_ace(hand)

        if total > 17:
            break
        if total == 17:
            # S17: dealer stands on soft 17 too
            if stand_soft_17:
                break
            # H17: dealer hits soft 17
            if is_soft:
                hand.append(draw(shoe, shoe_idx))
            else:
                break
        else:
            hand.append(draw(shoe, shoe_idx))

    return hand


# ──────────────────────────────────────────────────────────────────────────────
# HAND RESOLUTION
# ──────────────────────────────────────────────────────────────────────────────

def resolve_hand(player_total: int, dealer_total: int,
                 player_blackjack: bool = False,
                 dealer_blackjack: bool = False,
                 bet: float = 1.0) -> float:
    """Returns profit/loss for a hand."""
    if player_blackjack and dealer_blackjack:
        return 0.0   # Push
    if player_blackjack:
        return bet * 1.5   # BJ pays 3:2
    if dealer_blackjack:
        return -bet

    if player_total > 21:
        return -bet   # Player bust
    if dealer_total > 21:
        return bet    # Dealer bust

    if player_total > dealer_total:
        return bet
    if player_total < dealer_total:
        return -bet
    return 0.0   # Push


# ──────────────────────────────────────────────────────────────────────────────
# SINGLE HAND SIMULATION
# ──────────────────────────────────────────────────────────────────────────────

def simulate_hand(shoe: list[int], shoe_idx: list[int],
                  bet: float = 1.0,
                  can_surrender: bool = True,
                  can_double: bool = True,
                  can_split: bool = True,
                  stand_soft_17: bool = True,
                  das: bool = True,         # Double after split
                  max_splits: int = 3) -> float:
    """
    Simulate one complete hand using perfect basic strategy.
    Returns net profit/loss.
    """
    if shoe_idx[0] >= len(shoe) - 20:
        return 0.0  # Shoe depleted

    # Initial deal
    player = [draw(shoe, shoe_idx), draw(shoe, shoe_idx)]
    dealer_up = draw(shoe, shoe_idx)
    dealer_hole = draw(shoe, shoe_idx)
    dealer_hand = [dealer_up, dealer_hole]

    # Check for dealer blackjack
    dealer_bj = best_total(dealer_hand) == 21 and len(dealer_hand) == 2

    # Check for player blackjack
    player_bj = best_total(player) == 21 and len(player) == 2

    if player_bj or dealer_bj:
        return resolve_hand(
            best_total(player), best_total(dealer_hand),
            player_bj, dealer_bj, bet
        )

    # Play the player's hand(s)
    total_profit = _play_hand(
        player, dealer_up, shoe, shoe_idx, bet,
        can_surrender, can_double, can_split, das, max_splits,
        is_post_split=False, split_depth=0
    )

    # Dealer plays
    dealer_hand = dealer_play(dealer_hand, shoe, shoe_idx, stand_soft_17)
    dealer_total = best_total(dealer_hand)

    # Resolve (split hands were already resolved against dealer bust logic)
    # For non-split hands, compare against dealer
    if not isinstance(total_profit, list):
        player_total = best_total(player)
        if player_total > 21:
            return -bet  # Already bust
        return resolve_hand(player_total, dealer_total, bet=bet) + (total_profit - 0)

    # Aggregate split results
    return sum(
        resolve_hand(pt, dealer_total, bet=b)
        for pt, b in total_profit
        if pt <= 21
    ) + sum(
        -b for pt, b in total_profit if pt > 21
    )


def _play_hand(hand: list[int], dealer_up: int, shoe: list[int], shoe_idx: list[int],
               bet: float, can_surrender: bool, can_double: bool, can_split: bool,
               das: bool, max_splits: int, is_post_split: bool, split_depth: int) -> float:
    """Play out one hand, returns profit delta (0 = will be resolved later)."""

    state = HandState(
        player_cards=hand,
        dealer_upcard=dealer_up,
        can_double=can_double,
        can_split=can_split and split_depth < max_splits,
        can_surrender=can_surrender and not is_post_split,
        is_post_split=is_post_split,
    )

    while True:
        if best_total(hand) >= 21:
            break

        action, _ = get_action(state)

        if action == Action.STAND:
            break

        elif action == Action.HIT:
            hand.append(draw(shoe, shoe_idx))

        elif action == Action.DOUBLE:
            hand.append(draw(shoe, shoe_idx))
            bet *= 2
            break

        elif action == Action.SURRENDER:
            return -bet * 0.5

        elif action == Action.SPLIT:
            # Split: create two hands
            card = hand[0]
            hand1 = [card, draw(shoe, shoe_idx)]
            hand2 = [card, draw(shoe, shoe_idx)]
            is_ace_split = (card == 1)

            r1 = _play_hand(hand1, dealer_up, shoe, shoe_idx, bet,
                            can_surrender=False, can_double=das,
                            can_split=(not is_ace_split),
                            das=das, max_splits=max_splits,
                            is_post_split=True, split_depth=split_depth+1)
            r2 = _play_hand(hand2, dealer_up, shoe, shoe_idx, bet,
                            can_surrender=False, can_double=das,
                            can_split=(not is_ace_split),
                            das=das, max_splits=max_splits,
                            is_post_split=True, split_depth=split_depth+1)

            # Store final totals for later dealer resolution
            # Simplified: return surrender amounts already encoded
            return (r1, best_total(hand1), bet) , (r2, best_total(hand2), bet)

        # Update state for next iteration
        state = HandState(
            player_cards=hand,
            dealer_upcard=dealer_up,
            can_double=False,    # Can't double after first action
            can_split=False,
            can_surrender=False,
            is_post_split=is_post_split,
        )

    return 0.0  # Placeholder; caller resolves against dealer


# ──────────────────────────────────────────────────────────────────────────────
# FULL SIMULATION ENGINE
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class SimulationResult:
    hands: int
    net_profit: float
    house_edge: float   # As a percentage
    win_rate: float
    push_rate: float
    loss_rate: float
    std_deviation: float
    sharpe_ratio: float
    max_drawdown: float
    bankroll_history: list[float] = field(default_factory=list)
    hand_results: list[float] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"\n{'='*60}\n"
            f"  BLACKJACK SIMULATION RESULTS ({self.hands:,} hands)\n"
            f"{'='*60}\n"
            f"  House Edge:        {self.house_edge:+.4f}%\n"
            f"  Net Profit:        ${self.net_profit:+,.2f}\n"
            f"  Win Rate:          {self.win_rate:.2f}%\n"
            f"  Push Rate:         {self.push_rate:.2f}%\n"
            f"  Loss Rate:         {self.loss_rate:.2f}%\n"
            f"  Std Deviation:     {self.std_deviation:.4f} units/hand\n"
            f"  Sharpe Ratio:      {self.sharpe_ratio:.4f}\n"
            f"  Max Drawdown:      ${self.max_drawdown:,.2f}\n"
            f"{'='*60}\n"
        )


def run_simulation(
    num_hands: int = 1_000_000,
    num_decks: int = 6,
    bet_per_hand: float = 1.0,
    penetration: float = 0.75,   # % of shoe dealt before reshuffling
    verbose: bool = True
) -> SimulationResult:
    """
    Run full Monte Carlo simulation of blackjack basic strategy.
    """
    results = []
    bankroll = 0.0
    bankroll_history = []
    wins = pushes = losses = 0
    peak = 0.0
    max_drawdown = 0.0

    shoe = build_shoe(num_decks)
    shoe_idx = [0]
    reshuffle_at = int(len(shoe) * penetration)

    if verbose:
        print(f"Running {num_hands:,} hand simulation...")

    for i in range(num_hands):
        # Reshuffle if needed
        if shoe_idx[0] >= reshuffle_at:
            shoe = build_shoe(num_decks)
            shoe_idx[0] = 0

        # Simplified hand simulation (fast path)
        result = _fast_simulate_hand(shoe, shoe_idx, bet_per_hand)
        results.append(result)
        bankroll += result
        bankroll_history.append(bankroll)

        if result > 0:   wins += 1
        elif result == 0: pushes += 1
        else:             losses += 1

        # Track drawdown
        peak = max(peak, bankroll)
        drawdown = peak - bankroll
        max_drawdown = max(max_drawdown, drawdown)

    n = len(results)
    arr = np.array(results)
    mean = arr.mean()
    std = arr.std()
    sharpe = (mean / std * np.sqrt(80)) if std > 0 else 0  # Annualized to 80 hands/hr

    return SimulationResult(
        hands=n,
        net_profit=bankroll,
        house_edge=round(mean / bet_per_hand * 100, 4),
        win_rate=wins / n * 100,
        push_rate=pushes / n * 100,
        loss_rate=losses / n * 100,
        std_deviation=std,
        sharpe_ratio=sharpe,
        max_drawdown=max_drawdown,
        bankroll_history=bankroll_history[::1000],  # Sample every 1000 hands
        hand_results=results,
    )


def _fast_simulate_hand(shoe: list[int], shoe_idx: list[int], bet: float) -> float:
    """
    Optimized hand simulator using lookup tables.
    Returns profit/loss.
    """
    if shoe_idx[0] >= len(shoe) - 10:
        return 0.0

    p = [shoe[shoe_idx[0]], shoe[shoe_idx[0]+1]]
    d_up = shoe[shoe_idx[0]+2]
    d_hole = shoe[shoe_idx[0]+3]
    shoe_idx[0] += 4

    dealer = [d_up, d_hole]

    # Blackjack checks
    p_bj = best_total(p) == 21
    d_bj = best_total(dealer) == 21

    if p_bj or d_bj:
        return resolve_hand(best_total(p), best_total(dealer), p_bj, d_bj, bet)

    # Player action
    current_bet = bet
    surrendered = False
    doubled = False

    # Hard limit iterations to prevent infinite loops
    for _ in range(20):
        pt = best_total(p)
        if pt >= 21:
            break

        state = HandState(
            player_cards=p,
            dealer_upcard=d_up,
            can_double=len(p) == 2,
            can_split=len(p) == 2 and min(p[0],10) == min(p[1],10),
            can_surrender=len(p) == 2,
        )
        action, _ = get_action(state)

        if action == Action.STAND:
            break
        elif action == Action.HIT:
            p.append(shoe[shoe_idx[0]]); shoe_idx[0] += 1
        elif action == Action.DOUBLE:
            p.append(shoe[shoe_idx[0]]); shoe_idx[0] += 1
            current_bet *= 2
            doubled = True
            break
        elif action == Action.SURRENDER:
            surrendered = True
            break
        elif action == Action.SPLIT:
            # Simplified split: just play both halves as independent hands
            c = min(p[0], 10)
            hand1 = [p[0], shoe[shoe_idx[0]]]; shoe_idx[0] += 1
            hand2 = [p[1], shoe[shoe_idx[0]]]; shoe_idx[0] += 1

            # Quick play each split hand
            for hand in [hand1, hand2]:
                for _ in range(10):
                    ht = best_total(hand)
                    if ht >= 21: break
                    hs = HandState(player_cards=hand, dealer_upcard=d_up,
                                   can_double=len(hand)==2, can_split=False,
                                   can_surrender=False, is_post_split=True)
                    ha, _ = get_action(hs)
                    if ha in (Action.STAND, Action.SURRENDER): break
                    elif ha == Action.HIT:
                        hand.append(shoe[shoe_idx[0]]); shoe_idx[0] += 1
                    elif ha == Action.DOUBLE:
                        hand.append(shoe[shoe_idx[0]]); shoe_idx[0] += 1
                        break
                    else: break

            # Dealer plays
            while best_total(dealer) < 17:
                dealer.append(shoe[shoe_idx[0]]); shoe_idx[0] += 1

            dt = best_total(dealer)
            return (resolve_hand(best_total(hand1), dt, bet=bet) +
                    resolve_hand(best_total(hand2), dt, bet=bet))
        else:
            break

    if surrendered:
        return -current_bet * 0.5

    # Dealer plays
    while best_total(dealer) < 17:
        if shoe_idx[0] >= len(shoe):
            break
        dealer.append(shoe[shoe_idx[0]]); shoe_idx[0] += 1

    return resolve_hand(best_total(p), best_total(dealer), bet=current_bet)


def run_count_simulation(
    num_hands: int = 500_000,
    num_decks: int = 6,
    unit_size: float = 10.0,
    verbose: bool = True
) -> SimulationResult:
    """
    Simulate with Hi-Lo counting and bet spreading.
    Demonstrates actual counter edge vs house.
    """
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from core.counting import CardCounter, HI_LO_TAGS

    counter = CardCounter(num_decks)
    results = []
    bankroll = 0.0
    bankroll_history = []
    wins = pushes = losses = 0
    peak = 0.0
    max_drawdown = 0.0

    shoe = build_shoe(num_decks)
    shoe_idx = [0]
    reshuffle_at = int(len(shoe) * 0.75)

    if verbose:
        print(f"Running {num_hands:,} count-based simulation...")

    for i in range(num_hands):
        if shoe_idx[0] >= reshuffle_at:
            shoe = build_shoe(num_decks)
            shoe_idx[0] = 0
            counter.reset_shoe()

        # Determine bet based on true count
        tc = counter.true_count
        if tc <= 1:   bet = unit_size
        elif tc <= 2: bet = unit_size * 2
        elif tc <= 3: bet = unit_size * 4
        elif tc <= 4: bet = unit_size * 6
        elif tc <= 5: bet = unit_size * 8
        else:         bet = unit_size * 12

        # Simulate hand
        start_idx = shoe_idx[0]
        result = _fast_simulate_hand(shoe, shoe_idx, bet)

        # Count all dealt cards
        for card in shoe[start_idx:shoe_idx[0]]:
            counter.see_card(card)

        results.append(result)
        bankroll += result
        bankroll_history.append(bankroll)

        if result > 0:   wins += 1
        elif result == 0: pushes += 1
        else:             losses += 1

        peak = max(peak, bankroll)
        drawdown = peak - bankroll
        max_drawdown = max(max_drawdown, drawdown)

    n = len(results)
    arr = np.array(results)
    mean = arr.mean()
    std = arr.std()
    avg_bet = np.mean([abs(r) for r in results if r != 0]) if results else unit_size

    return SimulationResult(
        hands=n,
        net_profit=bankroll,
        house_edge=round(mean / avg_bet * 100, 4),
        win_rate=wins / n * 100,
        push_rate=pushes / n * 100,
        loss_rate=losses / n * 100,
        std_deviation=std,
        sharpe_ratio=(mean / std * np.sqrt(80)) if std > 0 else 0,
        max_drawdown=max_drawdown,
        bankroll_history=bankroll_history[::500],
        hand_results=results,
    )
