"""
Blackjack AI — Master Recommendation Engine
Combines: Perfect Basic Strategy + Hi-Lo Counting + Illustrious 18 Deviations
          + Kelly Criterion Bankroll + Real-time Screen Reading

Usage:
    python recommender.py --bankroll 10000 --min-bet 25 --max-bet 500
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.strategy import get_action, HandState, Action, best_total, has_soft_ace
from core.counting import CardCounter
from core.bankroll import BankrollManager, BankrollConfig
from vision.screen_reader import ScreenReader, CardParser, DetectedHand
from typing import Optional


# ──────────────────────────────────────────────────────────────────────────────
# RICH TERMINAL DISPLAY
# ──────────────────────────────────────────────────────────────────────────────

ACTION_COLORS = {
    Action.HIT:       "\033[92m",   # Green
    Action.STAND:     "\033[93m",   # Yellow
    Action.DOUBLE:    "\033[96m",   # Cyan
    Action.SPLIT:     "\033[95m",   # Magenta
    Action.SURRENDER: "\033[91m",   # Red
}
RESET = "\033[0m"
BOLD  = "\033[1m"
DIM   = "\033[2m"


def colored_action(action: Action) -> str:
    color = ACTION_COLORS.get(action, "")
    return f"{BOLD}{color}{action.name}{RESET}"


class BlackjackAdvisor:
    """
    The master class. Manages game state, counts cards, 
    and gives real-time recommendations.
    """

    def __init__(
        self,
        bankroll: float = 10_000,
        table_min: float = 25,
        table_max: float = 500,
        num_decks: int = 6,
        can_surrender: bool = True,
        das: bool = True,          # Double after split
        kelly_fraction: float = 0.25,
    ):
        config = BankrollConfig(
            total_bankroll=bankroll,
            table_minimum=table_min,
            table_maximum=table_max,
            num_decks=num_decks,
            kelly_fraction=kelly_fraction,
        )
        self.bankroll_mgr = BankrollManager(config)
        self.counter = CardCounter(num_decks)
        self.reader = ScreenReader()
        self.parser = CardParser()
        self.can_surrender = can_surrender
        self.das = das
        self.num_decks = num_decks
        self._hand_count = 0

    # ──────────────────────────────────────────────────────────────────────────
    # MAIN RECOMMENDATION
    # ──────────────────────────────────────────────────────────────────────────

    def get_recommendation(
        self,
        player_cards: list[int],
        dealer_upcard: int,
        can_double: bool = True,
        can_split: bool = True,
        is_post_split: bool = False,
    ) -> dict:
        """
        Core recommendation method.
        Returns full recommendation dict with action, bet, count info.
        """
        state = HandState(
            player_cards=player_cards,
            dealer_upcard=dealer_upcard,
            can_double=can_double and len(player_cards) == 2,
            can_split=can_split and len(player_cards) == 2,
            can_surrender=self.can_surrender and len(player_cards) == 2 and not is_post_split,
            is_post_split=is_post_split,
        )

        # Basic strategy action
        basic_action, basic_explanation = get_action(state)

        # Check for count-based deviation (Illustrious 18)
        deviation = self.counter.get_deviation(state.total, dealer_upcard)
        final_action = basic_action
        deviation_note = None

        if deviation and deviation not in ("NO_INSURANCE", "TAKE_INSURANCE"):
            dev_action = _parse_deviation_action(deviation)
            if dev_action and dev_action != basic_action:
                deviation_note = (
                    f"⚡ DEVIATION: TC={self.counter.true_count:.1f} → "
                    f"{dev_action.name} (overrides basic {basic_action.name})"
                )
                final_action = dev_action

        # Insurance check
        insurance_advice = None
        if dealer_upcard == 1:  # Dealer showing Ace
            take_ins, ins_msg = self.counter.check_insurance()
            insurance_advice = ins_msg

        # Count & betting info
        bet_info = self.bankroll_mgr.recommended_bet(
            self.counter.true_count,
            self.counter.state.player_edge
        )

        return {
            "action": final_action,
            "action_name": final_action.name,
            "explanation": basic_explanation,
            "deviation": deviation_note,
            "insurance": insurance_advice,
            "player_total": state.total,
            "is_soft": state.is_soft,
            "is_pair": state.is_pair,
            "true_count": round(self.counter.true_count, 2),
            "running_count": self.counter.running_count,
            "decks_remaining": round(self.counter.state.decks_remaining, 2),
            "player_edge_pct": round(self.counter.state.player_edge * 100, 3),
            "table_status": self._table_status(),
            "recommended_bet": bet_info["recommended_bet"],
            "bankroll": bet_info["bankroll"],
            "risk_of_ruin_pct": bet_info["risk_of_ruin"],
            "stop_loss": bet_info["stop_loss_triggered"],
            "win_goal": bet_info["win_goal_hit"],
        }

    def display_recommendation(self, rec: dict) -> None:
        """Pretty-print recommendation to terminal."""
        action = rec["action"]
        color = ACTION_COLORS.get(action, "")
        
        hand_type = ""
        if rec["is_pair"]:  hand_type = " [PAIR]"
        elif rec["is_soft"]: hand_type = " [SOFT]"
        
        print(f"\n{'═'*55}")
        print(f"  {BOLD}HAND: {rec['player_total']}{hand_type}{RESET}")
        print(f"{'─'*55}")
        print(f"  {BOLD}▶  ACTION: {color}{BOLD}{action.name}{RESET}")
        print(f"  {DIM}{rec['explanation']}{RESET}")
        
        if rec["deviation"]:
            print(f"\n  {rec['deviation']}")
        
        if rec["insurance"]:
            print(f"\n  INSURANCE: {rec['insurance']}")
        
        print(f"\n{'─'*55}")
        print(f"  COUNT INTELLIGENCE")
        print(f"{'─'*55}")
        print(f"  True Count:        {rec['true_count']:+.1f}")
        print(f"  Running Count:     {rec['running_count']:+d}")
        print(f"  Decks Remaining:   {rec['decks_remaining']:.1f}")
        print(f"  Player Edge:       {rec['player_edge_pct']:+.3f}%")
        print(f"  Table Status:      {rec['table_status']}")
        print(f"\n{'─'*55}")
        print(f"  BANKROLL")
        print(f"{'─'*55}")
        print(f"  Recommended Bet:   ${rec['recommended_bet']:.0f}")
        print(f"  Current Bankroll:  ${rec['bankroll']:,.0f}")
        print(f"  Risk of Ruin:      {rec['risk_of_ruin_pct']:.2f}%")
        
        if rec["stop_loss"]:
            print(f"\n  🛑 STOP LOSS TRIGGERED — Leave the table!")
        if rec["win_goal"]:
            print(f"\n  🎯 WIN GOAL HIT — Consider locking in profits!")
        
        print(f"{'═'*55}\n")

    # ──────────────────────────────────────────────────────────────────────────
    # CARD COUNTING
    # ──────────────────────────────────────────────────────────────────────────

    def count_cards(self, cards: list[int]) -> None:
        """Register seen cards into the count."""
        self.counter.see_cards(cards)

    def new_shoe(self) -> None:
        """Reset count for a new shoe."""
        self.counter.reset_shoe()
        print("🔄 New shoe — count reset to 0")

    def record_result(self, profit_loss: float) -> None:
        """Record hand result for bankroll tracking."""
        self.bankroll_mgr.record_hand_result(profit_loss)
        self._hand_count += 1

    # ──────────────────────────────────────────────────────────────────────────
    # INTERACTIVE LOOP
    # ──────────────────────────────────────────────────────────────────────────

    def run_interactive(self) -> None:
        """Full interactive session loop."""
        _print_banner()
        print(f"  Bankroll: ${self.bankroll_mgr._current_bankroll:,.0f}")
        print(f"  Decks: {self.num_decks} | Min: ${self.bankroll_mgr.config.table_minimum} | Max: ${self.bankroll_mgr.config.table_maximum}\n")

        while True:
            print("\n[MENU]  h=hand  c=count  s=shoe  r=result  q=quit  stats=stats")
            cmd = input("→ ").strip().lower()

            if cmd == "q":
                self._print_session_stats()
                print("\n  Good luck! 🃏\n")
                break

            elif cmd in ("h", "hand", ""):
                self._interactive_hand()

            elif cmd in ("c", "count"):
                self._interactive_count()

            elif cmd in ("s", "shoe"):
                self.new_shoe()

            elif cmd in ("r", "result"):
                try:
                    amount = float(input("  Result (+profit / -loss): $"))
                    self.record_result(amount)
                    print(f"  Recorded. Bankroll: ${self.bankroll_mgr._current_bankroll:,.0f}")
                except ValueError:
                    print("  Invalid amount.")

            elif cmd == "stats":
                self._print_session_stats()

            elif cmd.startswith("bet"):
                info = self.bankroll_mgr.recommended_bet(
                    self.counter.true_count,
                    self.counter.state.player_edge
                )
                print(f"\n  Recommended bet: ${info['recommended_bet']:.0f}")
                print(f"  True count: {self.counter.true_count:+.1f} | Edge: {self.counter.state.player_edge*100:+.3f}%")
                print(f"  {self._table_status()}")

    def _interactive_hand(self) -> None:
        """Process one hand interactively."""
        try:
            d_raw = input("  Dealer upcard: ").strip()
            p_raw = input("  Your cards: ").strip()
            
            dealer = self.parser.parse_one(d_raw.upper())
            player = self.parser.parse(p_raw.upper())

            if not dealer or not player:
                print("  ⚠️  Could not parse cards. Try: A, 2-9, T, J, Q, K")
                return

            # Get recommendation
            rec = self.get_recommendation(player, dealer)
            self.display_recommendation(rec)

            # Count the seen cards
            self.count_cards([dealer] + player)

        except Exception as e:
            print(f"  Error: {e}")

    def _interactive_count(self) -> None:
        """Manually add cards to the count."""
        raw = input("  Cards seen (space-separated): ").strip()
        cards = self.parser.parse(raw.upper())
        if cards:
            self.count_cards(cards)
            print(f"  Counted {len(cards)} cards. RC={self.counter.running_count:+d} | TC={self.counter.true_count:+.1f}")
        else:
            print("  No valid cards found.")

    def _table_status(self) -> str:
        from core.counting import _table_status
        return _table_status(self.counter.true_count)

    def _print_session_stats(self) -> None:
        stats = self.bankroll_mgr.session_stats()
        if not stats:
            print("  No hands recorded yet.")
            return
        print(f"\n{'─'*40}")
        print(f"  SESSION STATS")
        print(f"{'─'*40}")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        print(f"{'─'*40}")


def _parse_deviation_action(deviation: str) -> Optional[Action]:
    MAP = {
        "STAND": Action.STAND,
        "HIT": Action.HIT,
        "DOUBLE": Action.DOUBLE,
        "SPLIT": Action.SPLIT,
        "SURRENDER": Action.SURRENDER,
        "SURRENDER_OR_HIT": Action.SURRENDER,
    }
    return MAP.get(deviation)


def _print_banner():
    print("""
╔══════════════════════════════════════════════════════╗
║         BLACKJACK AI — PROFESSIONAL ADVISOR          ║
║  Perfect Basic Strategy + Hi-Lo Counting + Kelly     ║
║  Illustrious 18 Deviations + Bankroll Management     ║
╚══════════════════════════════════════════════════════╝""")
