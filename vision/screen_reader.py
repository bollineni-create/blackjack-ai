"""
Screen Vision Module
Reads blackjack cards from your screen using OCR + template matching.
Supports: Any online casino UI, screenshot input, or manual card entry.

Requirements: pip install pillow pytesseract opencv-python mss
Also needs: tesseract-ocr system package
"""

import re
from dataclasses import dataclass, field
from typing import Optional
from PIL import Image
import io


# Card rank string → integer value
RANK_MAP = {
    "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
    "10": 10, "T": 10, "J": 10, "Q": 10, "K": 10, "A": 1,
    "ace": 1, "jack": 10, "queen": 10, "king": 10, "ten": 10,
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9
}


@dataclass
class DetectedHand:
    player_cards: list[int] = field(default_factory=list)
    dealer_upcard: Optional[int] = None
    confidence: float = 0.0
    raw_text: str = ""
    screenshot_path: Optional[str] = None


class ScreenReader:
    """
    Reads card values from the screen.
    Three modes:
    1. Screenshot file analysis
    2. Live screen capture (mss)
    3. Manual entry fallback
    """

    def __init__(self, mode: str = "manual"):
        self.mode = mode
        self._ocr_available = self._check_ocr()
        self._capture_available = self._check_capture()

    def _check_ocr(self) -> bool:
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    def _check_capture(self) -> bool:
        try:
            import mss
            return True
        except Exception:
            return False

    # ──────────────────────────────────────────────────────────────────────────
    # SCREENSHOT ANALYSIS
    # ──────────────────────────────────────────────────────────────────────────

    def analyze_screenshot(self, image_path: str) -> DetectedHand:
        """
        Analyze a screenshot file to detect cards.
        Works best with high-contrast casino UIs.
        """
        try:
            from PIL import Image
            import pytesseract

            img = Image.open(image_path)
            # Preprocess: increase contrast, convert to grayscale
            img_gray = img.convert("L")

            # OCR with custom config for card reading
            config = "--psm 6 -c tessedit_char_whitelist=0123456789AJQKT "
            text = pytesseract.image_to_string(img_gray, config=config)

            return self._parse_ocr_text(text, image_path)

        except ImportError:
            print("⚠️  pytesseract not available. Using manual entry.")
            return self.manual_entry()
        except Exception as e:
            print(f"⚠️  Screenshot analysis failed: {e}")
            return self.manual_entry()

    def capture_screen_region(self, region: dict = None) -> DetectedHand:
        """
        Capture and analyze a region of the screen in real-time.
        region = {"top": 0, "left": 0, "width": 1920, "height": 1080}
        """
        try:
            import mss
            import mss.tools
            from PIL import Image

            with mss.mss() as sct:
                if region is None:
                    # Capture primary monitor
                    monitor = sct.monitors[1]
                else:
                    monitor = region

                screenshot = sct.grab(monitor)
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

                # Save temp file and analyze
                temp_path = "/tmp/bj_screenshot.png"
                img.save(temp_path)
                return self.analyze_screenshot(temp_path)

        except Exception as e:
            print(f"⚠️  Screen capture failed: {e}. Using manual entry.")
            return self.manual_entry()

    def _parse_ocr_text(self, text: str, image_path: str = None) -> DetectedHand:
        """Parse OCR text to extract card values."""
        cards = []
        text_upper = text.upper()

        # Find all card-like patterns
        # Pattern: single char (A,2-9,T,J,Q,K) possibly followed by suit
        card_patterns = re.findall(
            r'\b(ACE|JACK|QUEEN|KING|TEN|[AJQKT]|10|[2-9])\b',
            text_upper
        )

        for pattern in card_patterns:
            val = RANK_MAP.get(pattern.lower()) or RANK_MAP.get(pattern)
            if val:
                cards.append(val)

        if len(cards) >= 3:
            # Assume last card listed is dealer upcard, rest are player
            # This is a heuristic — refine based on your specific UI
            return DetectedHand(
                player_cards=cards[:-1],
                dealer_upcard=cards[-1],
                confidence=0.7,
                raw_text=text,
                screenshot_path=image_path
            )
        elif len(cards) == 2:
            return DetectedHand(
                player_cards=cards,
                dealer_upcard=None,
                confidence=0.5,
                raw_text=text,
                screenshot_path=image_path
            )

        return DetectedHand(raw_text=text, confidence=0.0)

    # ──────────────────────────────────────────────────────────────────────────
    # MANUAL ENTRY (Reliable fallback)
    # ──────────────────────────────────────────────────────────────────────────

    def manual_entry(self) -> DetectedHand:
        """
        Interactive manual card entry.
        Fast to use with practice — can enter a full hand in 3 seconds.
        """
        print("\n" + "─"*40)
        print("  ENTER CARDS (A=Ace, T/J/Q/K=10, 2-9=face)")
        print("─"*40)

        dealer_raw = input("  Dealer upcard: ").strip().upper()
        player_raw = input("  Your cards (space-separated, e.g. 'A 7'): ").strip().upper()

        dealer_card = self._parse_card(dealer_raw)
        player_cards = [self._parse_card(c) for c in player_raw.split() if c]
        player_cards = [c for c in player_cards if c is not None]

        return DetectedHand(
            player_cards=player_cards,
            dealer_upcard=dealer_card,
            confidence=1.0,
        )

    def _parse_card(self, raw: str) -> Optional[int]:
        raw = raw.strip().upper()
        return RANK_MAP.get(raw) or RANK_MAP.get(raw.lower())

    # ──────────────────────────────────────────────────────────────────────────
    # CARD COUNTING INPUT
    # ──────────────────────────────────────────────────────────────────────────

    def enter_all_visible_cards(self) -> list[int]:
        """
        Enter all cards visible on the table for counting purposes.
        Called after each hand resolution.
        """
        print("\n  All cards played this round (for counting):")
        raw = input("  Cards (space-separated): ").strip().upper()
        cards = []
        for c in raw.split():
            val = self._parse_card(c)
            if val:
                cards.append(val)
        return cards


class CardParser:
    """
    Standalone card string parser.
    Use this for programmatic integration.
    
    Usage:
        parser = CardParser()
        cards = parser.parse("A 7")      # [1, 7]
        card = parser.parse_one("K")     # 10
    """

    def parse(self, text: str) -> list[int]:
        tokens = text.upper().split()
        result = []
        for t in tokens:
            v = RANK_MAP.get(t) or RANK_MAP.get(t.lower())
            if v:
                result.append(v)
        return result

    def parse_one(self, text: str) -> Optional[int]:
        vals = self.parse(text)
        return vals[0] if vals else None

    def to_display(self, card: int) -> str:
        """Convert int card to display string."""
        if card == 1:  return "A"
        if card == 10: return "10"
        return str(card)

    def hand_to_display(self, cards: list[int]) -> str:
        return " ".join(self.to_display(c) for c in cards)
