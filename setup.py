#!/usr/bin/env python3
"""
Setup script for Hackathon Scraper
Installs dependencies and Playwright browsers
"""
import subprocess
import sys
import os

def run_command(cmd, description):
    print(f"\n[+] {description}...")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"  [OK] Success")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [FAIL] Failed: {e.stderr}")
        return False

def main():
    print("""
===============================================================
         HACKATHON SCRAPER - SETUP
===============================================================
    """)
    
    # Check Python version
    if sys.version_info < (3, 8):
        print("[FAIL] Python 3.8+ required")
        sys.exit(1)
    
    print(f"[OK] Python {sys.version.split()[0]} detected")
    
    # Install pip packages
    if not run_command(f"{sys.executable} -m pip install -r requirements.txt", "Installing Python packages"):
        sys.exit(1)
    
    # Install Playwright browsers
    if not run_command(f"{sys.executable} -m playwright install chromium", "Installing Playwright Chromium"):
        print("  [WARN] Playwright install failed - dynamic scraping won't work")
        print("  Run manually: python -m playwright install chromium")
    
    # Verify installation
    print("\n[*] Verifying installation...")
    try:
        import requests
        import bs4
        import playwright
        print("  [OK] All packages imported successfully")
    except ImportError as e:
        print(f"  [FAIL] Import error: {e}")
        sys.exit(1)
    
    print("""
[OK] Setup complete!

[>] To run the scraper:
    python scraper.py

[>] Output files will be created in this directory:
    - hackathons_2026.csv
    - hackathons_2026.json
    - hackathons_2026.md
    - hackathons_2026_gsheets.csv

[>] For Google Sheets: Import hackathons_2026_gsheets.csv
   The 'Link' column will have clickable hyperlinks!
    """)

if __name__ == '__main__':
    main()