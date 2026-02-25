#!/usr/bin/env python3
"""
Blackjack AI — Main Entry Point

USAGE:
    # Interactive advisor (real-time recommendations)
    python main.py --bankroll 10000 --min-bet 25 --max-bet 500

    # Run basic strategy simulation (verify house edge)
    python main.py --simulate --hands 1000000

    # Run counting simulation (verify counter edge)
    python main.py --simulate-count --hands 500000

    # Quick hand query (no interactive mode)
    python main.py --hand "A 7" --dealer 6
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(__file__))


def parse_args():
    p = argparse.ArgumentParser(
        description="🃏 Blackjack AI — Professional Strategy & Counting Advisor"
    )
    p.add_argument("--bankroll",      type=float, default=10_000, help="Starting bankroll")
    p.add_argument("--min-bet",       type=float, default=25,     help="Table minimum bet")
    p.add_argument("--max-bet",       type=float, default=500,    help="Table maximum bet")
    p.add_argument("--decks",         type=int,   default=6,      help="Number of decks")
    p.add_argument("--kelly",         type=float, default=0.25,   help="Kelly fraction (default 0.25)")
    p.add_argument("--no-surrender",  action="store_true",        help="Disable surrender")
    p.add_argument("--no-das",        action="store_true",        help="No double after split")
    
    # Modes
    p.add_argument("--simulate",       action="store_true",       help="Run basic strategy simulation")
    p.add_argument("--simulate-count", action="store_true",       help="Run card counting simulation")
    p.add_argument("--hands",          type=int,  default=1_000_000, help="Hands to simulate")
    p.add_argument("--hand",           type=str,  default=None,   help="Your hand (e.g. 'A 7')")
    p.add_argument("--dealer",         type=str,  default=None,   help="Dealer upcard (e.g. '6')")
    p.add_argument("--true-count",     type=float,default=0,      help="Current true count")
    
    return p.parse_args()


def run_simulation(args):
    """Run Monte Carlo simulation and display results."""
    print(f"\n🎰 Running {args.hands:,} hand simulation...")
    print("   Strategy: Perfect Basic Strategy (6-deck, S17, DAS)")
    print("   This will take ~10-30 seconds for 1M hands...\n")

    from simulation.simulator import run_simulation as _run_sim
    result = _run_sim(num_hands=args.hands, num_decks=args.decks, verbose=True)
    print(result.summary())

    # Save chart
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle("Blackjack Basic Strategy Simulation", fontsize=16, fontweight="bold")

        # 1. Bankroll over time
        ax = axes[0, 0]
        ax.plot(result.bankroll_history, color="#00ff88", linewidth=0.8, alpha=0.9)
        ax.axhline(0, color="white", linestyle="--", alpha=0.3)
        ax.set_title("Bankroll Trajectory (sampled)")
        ax.set_xlabel("Hand (thousands)")
        ax.set_ylabel("Net Profit ($)")
        ax.set_facecolor("#1a1a2e")
        fig.patch.set_facecolor("#0d0d1a")

        # 2. Result distribution
        ax = axes[0, 1]
        results_sample = result.hand_results[::100]
        ax.hist(results_sample, bins=50, color="#4488ff", alpha=0.8, edgecolor="none")
        ax.set_title("Hand Result Distribution")
        ax.set_xlabel("Profit/Loss per Hand ($)")
        ax.set_ylabel("Frequency")
        ax.set_facecolor("#1a1a2e")

        # 3. Win/Push/Loss pie
        ax = axes[1, 0]
        sizes = [result.win_rate, result.push_rate, result.loss_rate]
        labels = [f"Win\n{result.win_rate:.1f}%",
                  f"Push\n{result.push_rate:.1f}%",
                  f"Loss\n{result.loss_rate:.1f}%"]
        colors = ["#00ff88", "#ffaa00", "#ff4444"]
        ax.pie(sizes, labels=labels, colors=colors, startangle=90)
        ax.set_title("Win/Push/Loss Distribution")
        ax.set_facecolor("#1a1a2e")

        # 4. Stats table
        ax = axes[1, 1]
        ax.axis("off")
        stats_data = [
            ["Metric", "Value"],
            ["House Edge", f"{result.house_edge:+.4f}%"],
            ["Win Rate", f"{result.win_rate:.2f}%"],
            ["Push Rate", f"{result.push_rate:.2f}%"],
            ["Loss Rate", f"{result.loss_rate:.2f}%"],
            ["Std Deviation", f"{result.std_deviation:.4f}"],
            ["Sharpe Ratio", f"{result.sharpe_ratio:.4f}"],
            ["Max Drawdown", f"${result.max_drawdown:,.2f}"],
            ["Total Hands", f"{result.hands:,}"],
        ]
        table = ax.table(cellText=stats_data[1:], colLabels=stats_data[0],
                         cellLoc="center", loc="center")
        table.auto_set_font_size(True)
        table.scale(1.2, 1.8)
        ax.set_title("Summary Statistics")

        for ax in axes.flat:
            if hasattr(ax, 'tick_params'):
                ax.tick_params(colors="white")
            for spine in ax.spines.values() if hasattr(ax, 'spines') else []:
                spine.set_edgecolor("#333355")

        plt.tight_layout()
        out_path = "/mnt/user-data/outputs/simulation_results.png"
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        plt.savefig(out_path, dpi=150, facecolor="#0d0d1a", bbox_inches="tight")
        print(f"  📊 Chart saved to: {out_path}")

    except Exception as e:
        print(f"  Chart generation: {e}")


def run_count_simulation(args):
    """Run counting simulation."""
    print(f"\n🎰 Running {args.hands:,} hand CARD COUNTING simulation...")
    print("   Strategy: Hi-Lo with 1-12 bet spread\n")

    from simulation.simulator import run_count_simulation as _run_count
    result = _run_count(num_hands=args.hands, num_decks=args.decks, verbose=True)
    print(result.summary())
    print(f"  → Counter's true edge is approximately: {result.house_edge:+.4f}%")


def quick_hand(args):
    """One-off hand recommendation."""
    from ui.recommender import BlackjackAdvisor
    from vision.screen_reader import CardParser

    parser = CardParser()
    advisor = BlackjackAdvisor(
        bankroll=args.bankroll,
        table_min=args.min_bet,
        table_max=args.max_bet,
        num_decks=args.decks,
    )

    # Inject true count if provided
    if args.true_count != 0:
        advisor.counter.state.running_count = int(args.true_count * advisor.counter.state.decks_remaining)

    player = parser.parse(args.hand.upper())
    dealer = parser.parse_one(args.dealer.upper())

    if not player or not dealer:
        print("Error: could not parse cards.")
        return

    rec = advisor.get_recommendation(player, dealer)
    advisor.display_recommendation(rec)


def main():
    args = parse_args()

    if args.simulate:
        run_simulation(args)

    elif args.simulate_count:
        run_count_simulation(args)

    elif args.hand and args.dealer:
        quick_hand(args)

    else:
        # Interactive mode
        from ui.recommender import BlackjackAdvisor
        advisor = BlackjackAdvisor(
            bankroll=args.bankroll,
            table_min=args.min_bet,
            table_max=args.max_bet,
            num_decks=args.decks,
            can_surrender=not args.no_surrender,
            das=not args.no_das,
            kelly_fraction=args.kelly,
        )
        advisor.run_interactive()


if __name__ == "__main__":
    main()
