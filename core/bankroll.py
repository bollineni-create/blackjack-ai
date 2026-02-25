"""
Bankroll Management — Kelly Criterion + Risk of Ruin Analysis
World-class money management: never overbetting, maximizing geometric growth rate.
"""

import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class BankrollConfig:
    total_bankroll: float
    table_minimum: float
    table_maximum: float
    num_decks: int = 6
    kelly_fraction: float = 0.25   # Quarter Kelly = conservative, proven best practice
    max_spread: int = 12           # Max bet spread before heat

    @property
    def unit_size(self) -> float:
        """
        Base betting unit.
        Rule: 1 unit = 1/1000th of bankroll for 6-deck.
        This gives ~99% survival over 100k hands at perfect play.
        """
        unit = self.total_bankroll / 1000
        # Must be at least table minimum
        return max(unit, self.table_minimum)


class BankrollManager:
    """
    Full bankroll management system.
    - Kelly Criterion for bet sizing
    - Risk of ruin calculation
    - Session stop-loss / win goals
    - Bet ramping (to avoid casino detection)
    """

    def __init__(self, config: BankrollConfig):
        self.config = config
        self._session_start = config.total_bankroll
        self._current_bankroll = config.total_bankroll
        self._hands_played = 0
        self._session_profit = 0.0
        self._peak_bankroll = config.total_bankroll
        self._hand_results: list[float] = []

    # ──────────────────────────────────────────────────────────────────────────
    # KELLY CRITERION BETTING
    # ──────────────────────────────────────────────────────────────────────────

    def kelly_bet(self, player_edge: float) -> float:
        """
        Full Kelly: f* = edge / variance
        For blackjack variance ≈ 1.33 (6-deck, basic strategy)
        
        We use QUARTER KELLY — maximizes long-run growth while dramatically
        reducing variance (risk of ruin drops from ~13% to <1%).
        """
        BLACKJACK_VARIANCE = 1.33

        if player_edge <= 0:
            # No edge — minimum bet only
            return self.config.table_minimum

        full_kelly_fraction = player_edge / BLACKJACK_VARIANCE
        kelly_fraction = full_kelly_fraction * self.config.kelly_fraction

        optimal_bet = self._current_bankroll * kelly_fraction

        # Hard constraints
        optimal_bet = max(optimal_bet, self.config.table_minimum)
        optimal_bet = min(optimal_bet, self.config.table_maximum)

        # Round to nearest $5 (looks natural, avoids detection)
        optimal_bet = round(optimal_bet / 5) * 5
        return max(optimal_bet, self.config.table_minimum)

    def recommended_bet(self, true_count: float, player_edge: float) -> dict:
        """
        Complete bet recommendation combining Kelly + count-based spread.
        """
        unit = self.config.unit_size
        kelly = self.kelly_bet(player_edge)

        # Count-based bet ramp (for camouflage, step up gradually)
        if true_count <= 1:
            count_bet = unit * 1
        elif true_count <= 2:
            count_bet = unit * 2
        elif true_count <= 3:
            count_bet = unit * 4
        elif true_count <= 4:
            count_bet = unit * 6
        elif true_count <= 5:
            count_bet = unit * 8
        else:
            count_bet = unit * min(12, self.config.max_spread)

        # Use the more conservative of the two (Kelly is the ceiling)
        final_bet = min(kelly, count_bet) if player_edge > 0 else unit
        final_bet = max(final_bet, self.config.table_minimum)
        final_bet = min(final_bet, self.config.table_maximum)
        final_bet = round(final_bet / 5) * 5 or self.config.table_minimum

        return {
            "recommended_bet": final_bet,
            "kelly_optimal": round(kelly, 2),
            "unit_size": round(unit, 2),
            "bankroll": round(self._current_bankroll, 2),
            "session_profit": round(self._session_profit, 2),
            "risk_of_ruin": round(self.risk_of_ruin(player_edge) * 100, 2),
            "stop_loss_triggered": self._should_stop_loss(),
            "win_goal_hit": self._win_goal_hit(),
        }

    # ──────────────────────────────────────────────────────────────────────────
    # RISK OF RUIN
    # ──────────────────────────────────────────────────────────────────────────

    def risk_of_ruin(self, player_edge: float, variance: float = 1.33) -> float:
        """
        Risk of Ruin formula:
        RoR = e^(-2 * edge * bankroll / variance_per_hand)
        Where bankroll is in units.
        
        Source: Wong's "Professional Blackjack"
        """
        if player_edge <= 0:
            return 1.0  # 100% RoR with no edge

        bankroll_units = self._current_bankroll / self.config.unit_size
        ror = math.exp(-2 * player_edge * bankroll_units / variance)
        return min(ror, 1.0)

    # ──────────────────────────────────────────────────────────────────────────
    # SESSION MANAGEMENT
    # ──────────────────────────────────────────────────────────────────────────

    def record_hand_result(self, profit_loss: float) -> None:
        """Record result of a hand (in dollars)."""
        self._current_bankroll += profit_loss
        self._session_profit += profit_loss
        self._hands_played += 1
        self._hand_results.append(profit_loss)
        self._peak_bankroll = max(self._peak_bankroll, self._current_bankroll)

    def _should_stop_loss(self) -> bool:
        """
        Stop loss: quit session if down 50% of session bankroll.
        Prevents tilt and catastrophic loss.
        """
        session_loss = self._session_start - self._current_bankroll
        return session_loss >= self._session_start * 0.50

    def _win_goal_hit(self) -> bool:
        """Win goal: lock in profits at 50% session gain."""
        return self._session_profit >= self._session_start * 0.50

    def session_stats(self) -> dict:
        if not self._hand_results:
            return {}
        
        import statistics
        results = self._hand_results
        
        return {
            "hands_played": self._hands_played,
            "session_profit": round(self._session_profit, 2),
            "current_bankroll": round(self._current_bankroll, 2),
            "win_rate": round(sum(1 for r in results if r > 0) / len(results) * 100, 1),
            "avg_profit_per_hand": round(sum(results) / len(results), 2),
            "max_drawdown": round(self._session_start - min(
                self._current_bankroll,
                *[self._session_start + sum(results[:i]) for i in range(len(results))]
            ), 2),
            "peak_bankroll": round(self._peak_bankroll, 2),
            "stop_loss_triggered": self._should_stop_loss(),
            "win_goal_hit": self._win_goal_hit(),
        }

    def bankroll_growth_projection(self, player_edge: float, hands_per_hour: int = 80,
                                    hours: int = 10) -> dict:
        """
        Project bankroll growth using Kelly growth rate formula.
        g = edge - (variance / (2 * bankroll))
        """
        total_hands = hands_per_hour * hours
        unit = self.config.unit_size
        variance = 1.33

        # Kelly growth rate per hand
        if player_edge > 0:
            growth_rate = player_edge - (variance * (unit / self._current_bankroll) ** 2 / 2)
            projected = self._current_bankroll * math.exp(growth_rate * total_hands)
        else:
            projected = self._current_bankroll  # No growth without edge

        return {
            "current_bankroll": round(self._current_bankroll, 2),
            "projected_bankroll": round(projected, 2),
            "projected_profit": round(projected - self._current_bankroll, 2),
            "hours": hours,
            "total_hands": total_hands,
            "player_edge_pct": round(player_edge * 100, 3),
        }
