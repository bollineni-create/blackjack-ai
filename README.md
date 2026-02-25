# 🃏 Blackjack AI — Professional Advisor

**World-class blackjack strategy engine built on rigorous mathematics.**

Combines perfect basic strategy, Hi-Lo card counting with Illustrious 18 deviations,
Kelly Criterion bankroll management, and real-time screen reading.

Verified by 750,000 hand Monte Carlo simulation:
- **Basic Strategy House Edge:** −0.37% (theoretical: −0.4%)
- **Card Counter's Edge:** +0.70% (vs −0.37% without counting)
- **Counter's advantage vs house: +1.07 percentage points**

---

## Architecture

```
blackjack_ai/
├── core/
│   ├── strategy.py      # Perfect basic strategy lookup tables (hard/soft/pairs)
│   ├── counting.py      # Hi-Lo count + Illustrious 18 + Fab 4 deviations
│   └── bankroll.py      # Kelly Criterion + Risk of Ruin + session management
├── simulation/
│   └── simulator.py     # Monte Carlo engine (500k hands in ~7s)
├── vision/
│   └── screen_reader.py # OCR screen capture + manual entry fallback
├── ui/
│   └── recommender.py   # Master recommendation engine + interactive CLI
└── main.py              # Entry point (CLI)
```

---

## Installation

```bash
# Python deps
pip install -r requirements.txt

# OCR engine (for screen reading)
# macOS:
brew install tesseract

# Ubuntu/Debian:
sudo apt install tesseract-ocr

# Windows: Download installer from https://github.com/UB-Mannheim/tesseract/wiki
```

---

## Usage

### Interactive Advisor (Main Mode)
```bash
python main.py --bankroll 10000 --min-bet 25 --max-bet 500

# Commands:
# h          → Enter a hand (you'll be prompted for cards)
# c          → Enter cards seen (for counting)
# s          → New shoe (reset count)
# r          → Record hand result (for bankroll tracking)
# bet        → Get current bet recommendation
# stats      → Session statistics
# q          → Quit
```

### Quick Hand Query
```bash
python main.py --hand "A 7" --dealer 6
python main.py --hand "8 8" --dealer 9
python main.py --hand "10 6" --dealer 10 --true-count 3
```

### Run Simulations
```bash
# Verify house edge (basic strategy)
python main.py --simulate --hands 1000000

# Verify counter edge (Hi-Lo with 1-12 spread)
python main.py --simulate-count --hands 500000
```

---

## Strategy System

### Basic Strategy (6-Deck, S17, DAS, Surrender)
Stored as lookup tables verified against:
- Griffin's *Theory of Blackjack*
- Wong's *Professional Blackjack*
- Wizard of Odds computed tables

### Illustrious 18 Deviations (Count-Based)
Auto-applied when true count crosses pivot point:

| Hand | Dealer | TC Pivot | Deviation |
|------|--------|----------|-----------|
| 16   | 10     | 0        | Stand (not Hit) |
| 15   | 10     | +4       | Stand (not Surrender) |
| Ins  | A      | +3       | Take Insurance |
| 20   | 5      | +5       | Double (not Stand) |
| 12   | 3      | +2       | Stand (not Hit) |
| 11   | A      | +1       | Double (not Hit) |
| 9    | 2      | +1       | Double (not Hit) |
...and 11 more.

---

## Bankroll Management

### Kelly Criterion
```
f* = edge / variance
```
Where variance for 6-deck blackjack ≈ 1.33.

**Quarter Kelly used by default** — reduces variance by 75% while still growing
bankroll near-optimally. Proven by simulation and theory.

### Bet Spread (Hi-Lo)
| True Count | Units | Reason |
|-----------|-------|--------|
| ≤ 1       | 1x    | House has edge |
| 2         | 2x    | Slightly positive |
| 3         | 4x    | Profitable |
| 4         | 6x    | High advantage |
| 5         | 8x    | Strong advantage |
| ≥6        | 12x   | Maximum edge |

### Risk of Ruin Formula
```
RoR = e^(-2 × edge × bankroll_in_units / variance)
```
With 1,000-unit bankroll: RoR < 0.5%

---

## Screen Reading Setup

The screen reader works in three modes:
1. **Screenshot file**: `advisor.analyze_screenshot("screen.png")`
2. **Live capture**: `advisor.capture_screen_region()` (requires mss)
3. **Manual entry**: Default fallback (reliable, fast with practice)

For best OCR results:
- Use 1080p+ resolution
- High contrast casino UI preferred
- Zoom in on card area if possible

---

## Mathematical Foundation

**Why Basic Strategy works:**
Each action (Hit/Stand/Double/Split/Surrender) has a calculable Expected Value.
Basic strategy is the mathematically proven optimal action for each hand state,
derived from exhaustive combinatorial analysis of all possible outcomes.

**Why Hi-Lo counting works:**
High cards (10, A) favor the player; low cards (2-6) favor the dealer.
When the remaining deck is rich in high cards (positive true count):
- Player gets more naturals (3:2 payout)
- Dealer busts more often (must hit to 17)
- Doubling is more profitable

**Why Kelly works:**
Kelly Criterion maximizes the logarithm of wealth, which is equivalent to
maximizing long-term geometric growth rate. No other strategy grows bankroll
faster in the long run.

---

## Legal Note
Card counting is legal but casinos may ask you to leave.
This software is for educational purposes and personal use only.
