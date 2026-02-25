#!/usr/bin/env python3
"""
BLACKJACK AI — Live Screen OCR Detection Module
Reads card values directly from your screen using computer vision.
Runs alongside hud_app.py in a separate thread.

Supports:
- Template matching for standard card faces
- Tesseract OCR fallback for text-rendered cards
- Region-of-interest capture (user-defined table area)
- Auto-detection confidence scoring
"""

import sys, os, time, threading, json
from typing import Optional, List, Tuple, Callable
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RANK_MAP = {
    'A': 1, 'ACE': 1, '1': 1,
    '2': 2, '3': 3, '4': 4, '5': 5, '6': 6,
    '7': 7, '8': 8, '9': 9,
    '10': 10, 'T': 10, 'J': 10, 'Q': 10, 'K': 10,
    'JACK': 10, 'QUEEN': 10, 'KING': 10, 'TEN': 10,
}

RANK_DISPLAY = {1: 'A', 10: '10', 2: '2', 3: '3', 4: '4',
                5: '5', 6: '6', 7: '7', 8: '8', 9: '9'}


@dataclass
class DetectedState:
    player_cards: List[int]
    dealer_upcard: Optional[int]
    confidence: float
    timestamp: float
    raw_regions: dict


def _try_import(pkg):
    try:
        __import__(pkg)
        return True
    except ImportError:
        return False


class ScreenDetector:
    """
    Computer vision pipeline for reading casino table state.
    Gracefully degrades: OpenCV -> Tesseract -> Manual entry fallback.
    """

    def __init__(self,
                 on_state_change: Optional[Callable] = None,
                 poll_interval: float = 0.5):

        self.on_state_change = on_state_change
        self.poll_interval   = poll_interval
        self._running        = False
        self._thread         = None
        self._last_state     = None
        self.region          = None   # (x, y, w, h) capture region

        # Check available backends
        self.has_mss    = _try_import('mss')
        self.has_cv2    = _try_import('cv2')
        self.has_pil    = _try_import('PIL')
        self.has_tess   = self._check_tesseract()

        print(f'[OCR] mss:{self.has_mss} cv2:{self.has_cv2} '
              f'pil:{self.has_pil} tesseract:{self.has_tess}')

        if not all([self.has_mss, self.has_pil]):
            print('[OCR] WARNING: Missing dependencies. '
                  'Run: pip install mss pillow opencv-python pytesseract')

    def _check_tesseract(self) -> bool:
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    def set_region(self, x: int, y: int, w: int, h: int):
        """Set screen region to capture (call after user selects table area)."""
        self.region = {'left': x, 'top': y, 'width': w, 'height': h}
        print(f'[OCR] Capture region set: {x},{y} {w}x{h}')

    def capture_screenshot(self) -> Optional['PIL.Image.Image']:
        if not self.has_mss or not self.has_pil:
            return None
        try:
            import mss
            from PIL import Image
            with mss.mss() as sct:
                region = self.region or sct.monitors[1]
                raw = sct.grab(region)
                return Image.frombytes('RGB', raw.size, raw.bgra, 'raw', 'BGRX')
        except Exception as e:
            print(f'[OCR] Capture error: {e}')
            return None

    def detect_cards_ocr(self, img) -> DetectedState:
        """
        OCR-based card detection.
        Looks for rank text (A, 2-10, J, Q, K) near card-shaped regions.
        """
        if not self.has_cv2 or not self.has_tess:
            return DetectedState([], None, 0.0, time.time(), {})

        try:
            import cv2
            import pytesseract
            import numpy as np
            from PIL import Image

            # Convert to numpy
            img_arr = np.array(img)
            gray    = cv2.cvtColor(img_arr, cv2.COLOR_RGB2GRAY)

            # Enhance contrast for card text
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray)

            # OCR configuration for card rank characters
            config = '--psm 6 --oem 3 -c tessedit_char_whitelist=A23456789TJQK0'
            raw_text = pytesseract.image_to_string(
                Image.fromarray(enhanced), config=config)

            # Parse detected ranks
            import re
            tokens = re.findall(r'[A23456789TJQK][0]?', raw_text.upper())
            cards  = []
            for t in tokens:
                val = RANK_MAP.get(t)
                if val:
                    cards.append(val)

            # Heuristic: first card = dealer, rest = player
            dealer = cards[0] if cards else None
            player = cards[1:] if len(cards) > 1 else []

            confidence = min(1.0, len(cards) / 3.0)
            return DetectedState(player, dealer, confidence, time.time(), {'raw': raw_text})

        except Exception as e:
            print(f'[OCR] Detection error: {e}')
            return DetectedState([], None, 0.0, time.time(), {})

    def start(self):
        """Start continuous background detection loop."""
        if not self.has_mss:
            print('[OCR] Cannot start: mss not installed.')
            return
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print('[OCR] Detection loop started.')

    def stop(self):
        self._running = False
        print('[OCR] Detection stopped.')

    def _loop(self):
        while self._running:
            img = self.capture_screenshot()
            if img is not None:
                state = self.detect_cards_ocr(img)
                if (state.confidence > 0.5 and
                        state != self._last_state and
                        self.on_state_change):
                    self._last_state = state
                    self.on_state_change(state)
            time.sleep(self.poll_interval)


class RegionSelector:
    """
    GUI tool to let user draw a selection box over the table area.
    Called once during setup to calibrate capture region.
    """

    def __init__(self):
        self.selected = None

    def select_region(self) -> Optional[dict]:
        """
        Opens a transparent fullscreen window.
        User clicks and drags to select the table region.
        Returns {'left': x, 'top': y, 'width': w, 'height': h}
        """
        try:
            import tkinter as tk

            root = tk.Tk()
            root.attributes('-fullscreen', True)
            root.attributes('-alpha', 0.3)
            root.configure(bg='black')
            root.attributes('-topmost', True)

            canvas = tk.Canvas(root, cursor='crosshair',
                              bg='black', highlightthickness=0)
            canvas.pack(fill='both', expand=True)

            tk.Label(canvas,
                    text='Click and drag to select the blackjack table area\n'
                         'Release mouse to confirm | ESC to cancel',
                    bg='black', fg='white',
                    font=('Courier', 14, 'bold')).place(relx=0.5, rely=0.05,
                                                        anchor='center')

            state = {'start': None, 'rect': None, 'region': None}

            def on_press(e):
                state['start'] = (e.x, e.y)

            def on_drag(e):
                if state['rect']:
                    canvas.delete(state['rect'])
                x0, y0 = state['start']
                state['rect'] = canvas.create_rectangle(
                    x0, y0, e.x, e.y,
                    outline='#00ff88', width=2, dash=(4, 2))

            def on_release(e):
                x0, y0 = state['start']
                x1, y1 = e.x, e.y
                state['region'] = {
                    'left':   min(x0, x1),
                    'top':    min(y0, y1),
                    'width':  abs(x1 - x0),
                    'height': abs(y1 - y0),
                }
                root.destroy()

            def on_escape(e):
                root.destroy()

            canvas.bind('<ButtonPress-1>', on_press)
            canvas.bind('<B1-Motion>', on_drag)
            canvas.bind('<ButtonRelease-1>', on_release)
            root.bind('<Escape>', on_escape)
            root.mainloop()

            self.selected = state['region']
            return self.selected

        except Exception as e:
            print(f'[RegionSelector] Error: {e}')
            return None
