#!/usr/bin/env python3
"""
BLACKJACK AI HUD — Setup & Install Script
Run once to install all dependencies and verify the system.
"""

import subprocess, sys, os, platform

print("""
╔══════════════════════════════════════════════════════════════════╗
║         BLACKJACK AI HUD — SETUP                                 ║
╚══════════════════════════════════════════════════════════════════╝
""")

# Python packages
PACKAGES = [
    'pillow',
    'mss',
    'numpy',
    'pytesseract',
    'opencv-python',
]

print('Installing Python packages...')
for pkg in PACKAGES:
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', pkg, '--quiet'],
            capture_output=True, text=True)
        status = '✓' if result.returncode == 0 else '✗'
        print(f'  {status} {pkg}')
    except Exception as e:
        print(f'  ✗ {pkg}: {e}')

# Tesseract binary
print('\nChecking Tesseract OCR...')
plat = platform.system()
if plat == 'Windows':
    print('  Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki')
    print('  Then add to PATH or set pytesseract.pytesseract.tesseract_cmd')
elif plat == 'Darwin':
    print('  macOS: Run: brew install tesseract')
else:
    print('  Linux: Run: sudo apt-get install tesseract-ocr')

try:
    import pytesseract
    version = pytesseract.get_tesseract_version()
    print(f'  ✓ Tesseract found: v{version}')
except Exception:
    print('  ✗ Tesseract not found — manual card entry will be used instead')
    print('    (OCR auto-detection is optional. Manual entry works perfectly.)')

# Verify core modules
print('\nVerifying Blackjack AI core...')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from core.strategy import get_action
    from core.counting import CardCounter
    from core.bankroll import BankrollManager
    print('  ✓ Strategy engine')
    print('  ✓ Card counter (Hi-Lo)')
    print('  ✓ Bankroll manager (Kelly)')
except ImportError as e:
    print(f'  ✗ Core module missing: {e}')

print("""
╔══════════════════════════════════════════════════════════════════╗
║  SETUP COMPLETE. Launch the HUD with:                            ║
║                                                                  ║
║  python hud_app.py --bankroll 1000 --min-bet 10 --max-bet 200   ║
║                                                                  ║
║  Options:                                                        ║
║    --bankroll  Your total bankroll ($)                           ║
║    --min-bet   Table minimum ($)                                 ║
║    --max-bet   Table maximum ($)                                 ║
║    --decks     Number of decks (1, 2, 6, or 8)                  ║
║    --kelly     Kelly fraction (0.25=conservative, 0.35=Rainman)  ║
║    --no-surrender  If table doesn't offer surrender              ║
╚══════════════════════════════════════════════════════════════════╝
""")
