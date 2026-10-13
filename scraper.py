#!/usr/bin/env python3
"""
Hackathon Scraper - Scrapes upcoming hackathons from major platforms
Uses Playwright for JavaScript-rendered sites (Devfolio, HackerEarth, Unstop, Devpost, MLH)
Exports to CSV, JSON, and Google Sheets-ready format
"""

import asyncio
import csv
import json
import re
import time
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict, field
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin, urlparse


# ============================================================
# DATA MODELS
# ============================================================

@dataclass
class Hackathon:
    """Standardized hackathon data structure"""
    platform: str
    name: str
    url: str
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    registration_deadline: str = ""
    status: str = ""  # "Registrations Open", "Upcoming", "Ongoing", "Ended"
    eligibility: str = ""
    prize_pool: str = ""
    themes: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    description: str = ""
    is_online: bool = False
    is_student_only: bool = False
    scraped_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['themes'] = '; '.join(self.themes)
        d['tags'] = '; '.join(self.tags)
        return d

    def to_csv_row(self) -> List[str]:
        return [
            self.platform, self.name, self.url, self.location,
            self.start_date, self.end_date, self.registration_deadline,
            self.status, self.eligibility, self.prize_pool,
            '; '.join(self.themes), '; '.join(self.tags),
            self.description[:200] + '...' if len(self.description) > 200 else self.description,
            'Yes' if self.is_online else 'No',
            'Yes' if self.is_student_only else 'No',
            self.scraped_at
        ]


# ============================================================
# PLAYWRIGHT SCRAPERS (for JavaScript-heavy sites)
# ============================================================

class PlaywrightScraper:
    """Scrape JavaScript-rendered hackathon platforms"""
    
    def __init__(self):
        self.browser = None
        self.context = None
    
    async def _init_browser(self):
        if not self.browser:
            from playwright.async_api import async_playwright
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=True)
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
    
    async def _close_browser(self):
        if self.browser:
            await self.browser.close()
            await self.playwright.stop()
            self.browser = None

    async def _safe_goto(self, page, url, wait_selector=None, timeout=60000):
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=timeout)
            if wait_selector:
                await page.wait_for_selector(wait_selector, timeout=15000)
            await page.wait_for_load_state('networkidle', timeout=10000)
            return True
        except Exception as e:
            print(f"  Navigation error for {url}: {e}")
            return False

    async def _safe_text(self, element, selector):
        try:
            el = await element.query_selector(selector)
            return await el.inner_text() if el else ""
        except:
            return ""

    async def _safe_attr(self, element, selector, attr):
        try:
            el = await element.query_selector(selector)
            return await el.get_attribute(attr) if el else ""
        except:
            return ""

    # ---- DEVFOLIO ----
    async def scrape_devfolio(self) -> List[Hackathon]:
        print("[>] Scraping Devfolio (Playwright)...")
        hackathons = []
        await self._init_browser()
        page = await self.context.new_page()
        
        try:
            if not await self._safe_goto(page, 'https://devfolio.co/hackathons', 
                                        wait_selector='[data-testid="hackathon-card"], .hackathon-card, article'):
                return hackathons
            
            # Scroll to load more
            for _ in range(3):
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await asyncio.sleep(1)
            
            cards = await page.query_selector_all('[data-testid="hackathon-card"], .hackathon-card, article:has(a[href*="/hackathons/"])')
            print(f"  Found {len(cards)} cards")
            
            for card in cards[:60]:
                try:
                    name = await self._safe_text(card, 'h3, h2, [data-testid="hackathon-name"], .hackathon-name')
                    href = await self._safe_attr(card, 'a[href*="/hackathons/"]', 'href')
                    location = await self._safe_text(card, '[data-testid="location"], .location, .hackathon-location')
                    date_text = await self._safe_text(card, '[data-testid="date"], .date, .hackathon-date')
                    status = await self._safe_text(card, '[data-testid="status"], .status-badge, .badge, .tag')
                    prize = await self._safe_text(card, '[data-testid="prize"], .prize, .hackathon-prize')
                    desc = await self._safe_text(card, '[data-testid="description"], .description, .hackathon-desc')
                    
                    # Themes
                    theme_elements = await card.query_selector_all('[data-testid="theme"], .theme-tag, .tag, .topic')
                    themes = []
                    for te in theme_elements:
                        t = await te.inner_text()
                        if t: themes.append(t.strip())
                    
                    if not name: continue
                    
                    hack_url = f"https://devfolio.co{href}" if href and not href.startswith('http') else (href or "https://devfolio.co/hackathons")
                    is_online = 'online' in location.lower() or 'virtual' in location.lower() or 'remote' in location.lower()
                    
                    # Parse dates
                    start_date, end_date, reg_deadline = self._parse_date_range(date_text)
                    
                    hackathons.append(Hackathon(
                        platform='Devfolio',
                        name=name.strip(),
                        url=hack_url,
                        location=location.strip() or "Online",
                        start_date=start_date,
                        end_date=end_date,
                        registration_deadline=reg_deadline,
                        status=status.strip() or "Upcoming",
                        prize_pool=prize.strip(),
                        themes=themes,
                        description=desc.strip()[:500],
                        is_online=is_online,
                        is_student_only='student' in name.lower() or 'university' in name.lower() or 'campus' in name.lower()
                    ))
                except Exception as e:
                    continue
                    
        except Exception as e:
            print(f"  [FAIL] Devfolio: {e}")
        finally:
            await page.close()
        
        print(f"  [OK] Devfolio: {len(hackathons)} hackathons")
        return hackathons

    # ---- HACKEREARTH ----
    async def scrape_hackerearth(self) -> List[Hackathon]:
        print("[>] Scraping HackerEarth (Playwright)...")
        hackathons = []
        await self._init_browser()
        page = await self.context.new_page()
        
        try:
            if not await self._safe_goto(page, 'https://hackerearth.com/challenges/hackathon/',
                                        wait_selector='.challenge-card, .hackathon-card, .upcoming-challenge, [data-cy="challenge-card"]'):
                return hackathons
            
            await asyncio.sleep(2)
            cards = await page.query_selector_all('.challenge-card, .hackathon-card, .upcoming-challenge, [data-cy="challenge-card"], .challenge-list-item')
            print(f"  Found {len(cards)} cards")
            
            for card in cards[:50]:
                try:
                    name = await self._safe_text(card, '.challenge-name, .challenge-title, h3, h4, [data-cy="challenge-title"]')
                    href = await self._safe_attr(card, 'a[href*="/challenge/"]', 'href')
                    status = await self._safe_text(card, '.challenge-type, .status, .badge, .label, [data-cy="challenge-type"]')
                    date_text = await self._safe_text(card, '.challenge-date, .date, .duration, [data-cy="challenge-date"]')
                    prize = await self._safe_text(card, '.prize, .prize-amount, .reward')
                    
                    theme_elements = await card.query_selector_all('.theme, .tag, .topic, .skill-tag')
                    themes = []
                    for te in theme_elements:
                        t = await te.inner_text()
                        if t: themes.append(t.strip())
                    
                    if not name: continue
                    
                    hack_url = f"https://hackerearth.com{href}" if href and not href.startswith('http') else (href or "https://hackerearth.com/challenges/hackathon/")
                    
                    start_date, end_date, reg_deadline = self._parse_date_range(date_text)
                    
                    hackathons.append(Hackathon(
                        platform='HackerEarth',
                        name=name.strip(),
                        url=hack_url,
                        status=status.strip() or "Upcoming",
                        prize_pool=prize.strip(),
                        themes=themes,
                        start_date=start_date,
                        end_date=end_date,
                        registration_deadline=reg_deadline,
                        is_student_only='student' in name.lower() or 'university' in name.lower()
                    ))
                except Exception as e:
                    continue
                    
        except Exception as e:
            print(f"  [FAIL] HackerEarth: {e}")
        finally:
            await page.close()
        
        print(f"  [OK] HackerEarth: {len(hackathons)} hackathons")
        return hackathons

    # ---- UNSTOP ----
    async def scrape_unstop(self) -> List[Hackathon]:
        print("[>] Scraping Unstop (Playwright)...")
        hackathons = []
        await self._init_browser()
        page = await self.context.new_page()
        
        try:
            if not await self._safe_goto(page, 'https://unstop.com/hackathons',
                                        wait_selector='.hackathon-card, .opportunity-card, [data-testid="hackathon-card"], .opportunity-box'):
                return hackathons
            
            await asyncio.sleep(2)
            cards = await page.query_selector_all('.hackathon-card, .opportunity-card, [data-testid="hackathon-card"], .opportunity-box, .compact-card')
            print(f"  Found {len(cards)} cards")
            
            for card in cards[:50]:
                try:
                    name = await self._safe_text(card, 'h3, h2, .title, .opportunity-name, .card-title')
                    href = await self._safe_attr(card, 'a[href*="/hackathon/"], a[href*="/opportunity/"]', 'href')
                    location = await self._safe_text(card, '.location, .venue, .place')
                    date_text = await self._safe_text(card, '.date, .deadline, .duration, .deadline-text')
                    status = await self._safe_text(card, '.status, .badge, .label, .chip')
                    prize = await self._safe_text(card, '.prize, .reward, .prize-money')
                    
                    theme_elements = await card.query_selector_all('.tag, .skill-tag, .theme, .topic')
                    themes = []
                    for te in theme_elements:
                        t = await te.inner_text()
                        if t: themes.append(t.strip())
                    
                    if not name: continue
                    
                    hack_url = f"https://unstop.com{href}" if href and not href.startswith('http') else (href or "https://unstop.com/hackathons")
                    is_online = 'online' in location.lower() or 'virtual' in location.lower() or 'remote' in location.lower()
                    
                    start_date, end_date, reg_deadline = self._parse_date_range(date_text)
                    
                    hackathons.append(Hackathon(
                        platform='Unstop',
                        name=name.strip(),
                        url=hack_url,
                        location=location.strip() or "Online",
                        start_date=start_date,
                        end_date=end_date,
                        registration_deadline=reg_deadline,
                        status=status.strip() or "Registrations Open",
                        prize_pool=prize.strip(),
                        themes=themes,
                        is_online=is_online,
                        is_student_only=True
                    ))
                except Exception as e:
                    continue
                    
        except Exception as e:
            print(f"  [FAIL] Unstop: {e}")
        finally:
            await page.close()
        
        print(f"  [OK] Unstop: {len(hackathons)} hackathons")
        return hackathons

    # ---- DEVPOST ----
    async def scrape_devpost(self) -> List[Hackathon]:
        print("[>] Scraping Devpost (Playwright)...")
        hackathons = []
        await self._init_browser()
        page = await self.context.new_page()
        
        try:
            # Try multiple Devpost URLs
            urls = [
                'https://devpost.com/hackathons',
                'https://devpost.com/hackathons?status=upcoming',
                'https://devpost.com/hackathons?location=india'
            ]
            
            for url in urls:
                try:
                    if not await self._safe_goto(page, url, wait_selector='.hackathon-tile, .software-tile, .challenge-tile, .hackathon-card', timeout=45000):
                        continue
                    
                    await asyncio.sleep(2)
                    cards = await page.query_selector_all('.hackathon-tile, .software-tile, .challenge-tile, .hackathon-card, .tile')
                    print(f"  Found {len(cards)} cards at {url}")
                    
                    for card in cards[:30]:
                        try:
                            name = await self._safe_text(card, 'h3, .hackathon-name, .challenge-name, .software-title')
                            href = await self._safe_attr(card, 'a[href*="/hackathons/"], a[href*="/software/"]', 'href')
                            location = await self._safe_text(card, '.location, .venue, .hackathon-location')
                            date_text = await self._safe_text(card, '.date, .submission-period, .deadline, .hackathon-date')
                            status = await self._safe_text(card, '.status, .label, .badge, .hackathon-status')
                            prize = await self._safe_text(card, '.prize, .prize-amount, .hackathon-prize')
                            
                            theme_elements = await card.query_selector_all('.theme, .tag, .topic, .category')
                            themes = []
                            for te in theme_elements:
                                t = await te.inner_text()
                                if t: themes.append(t.strip())
                            
                            if not name: continue
                            
                            hack_url = f"https://devpost.com{href}" if href and not href.startswith('http') else (href or url)
                            is_online = 'online' in location.lower() or 'virtual' in location.lower() or 'remote' in location.lower()
                            
                            start_date, end_date, reg_deadline = self._parse_date_range(date_text)
                            
                            hackathons.append(Hackathon(
                                platform='Devpost',
                                name=name.strip(),
                                url=hack_url,
                                location=location.strip() or "Online",
                                start_date=start_date,
                                end_date=end_date,
                                registration_deadline=reg_deadline,
                                status=status.strip() or "Upcoming",
                                prize_pool=prize.strip(),
                                themes=themes,
                                is_online=is_online,
                                is_student_only='student' in name.lower() or 'university' in name.lower()
                            ))
                        except Exception as e:
                            continue
                except Exception as e:
                    print(f"  Error with {url}: {e}")
                    continue
                    
        except Exception as e:
            print(f"  [FAIL] Devpost: {e}")
        finally:
            await page.close()
        
        # Deduplicate Devpost results
        seen = set()
        unique = []
        for h in hackathons:
            key = h.name.lower().strip()[:50]
            if key not in seen:
                seen.add(key)
                unique.append(h)
        
        print(f"  [OK] Devpost: {len(unique)} hackathons")
        return unique

    # ---- MLH ----
    async def scrape_mlh(self) -> List[Hackathon]:
        print("[>] Scraping MLH (Playwright)...")
        hackathons = []
        await self._init_browser()
        page = await self.context.new_page()
        
        try:
            if not await self._safe_goto(page, 'https://mlh.io/seasons/2026/events',
                                        wait_selector='.event-wrapper, .event-card, .hackathon-event, [data-testid="event-card"]'):
                # Try 2025 if 2026 not available
                if not await self._safe_goto(page, 'https://mlh.io/seasons/2025/events',
                                            wait_selector='.event-wrapper, .event-card, .hackathon-event'):
                    return hackathons
            
            await asyncio.sleep(2)
            cards = await page.query_selector_all('.event-wrapper, .event-card, .hackathon-event, [data-testid="event-card"], .event')
            print(f"  Found {len(cards)} cards")
            
            for card in cards[:50]:
                try:
                    name = await self._safe_text(card, 'h3, .event-name, .hackathon-name, .event-title')
                    href = await self._safe_attr(card, 'a[href*="/events/"], a[href*="/hackathon/"]', 'href')
                    location = await self._safe_text(card, '.event-location, .location, .venue, .event-venue')
                    date_text = await self._safe_text(card, '.event-date, .date, .duration, .event-time')
                    
                    theme_elements = await card.query_selector_all('.track, .theme, .category, .event-track')
                    themes = []
                    for te in theme_elements:
                        t = await te.inner_text()
                        if t: themes.append(t.strip())
                    
                    if not name: continue
                    
                    hack_url = f"https://mlh.io{href}" if href and not href.startswith('http') else (href or "https://mlh.io/seasons/2026/events")
                    is_online = 'online' in location.lower() or 'virtual' in location.lower() or 'remote' in location.lower()
                    
                    start_date, end_date, reg_deadline = self._parse_date_range(date_text)
                    
                    hackathons.append(Hackathon(
                        platform='MLH',
                        name=name.strip(),
                        url=hack_url,
                        location=location.strip() or "TBD",
                        start_date=start_date,
                        end_date=end_date,
                        registration_deadline=reg_deadline,
                        status="Upcoming",
                        themes=themes,
                        is_online=is_online,
                        is_student_only=True
                    ))
                except Exception as e:
                    continue
                    
        except Exception as e:
            print(f"  [FAIL] MLH: {e}")
        finally:
            await page.close()
        
        print(f"  [OK] MLH: {len(hackathons)} hackathons")
        return hackathons

    # ---- DATE PARSING ----
    def _parse_date_range(self, text: str) -> tuple:
        """Parse date strings into start_date, end_date, reg_deadline"""
        if not text:
            return "", "", ""
        
        text = text.strip()
        start_date = ""
        end_date = ""
        reg_deadline = ""
        
        # Common patterns
        # "Mar 15 - Mar 17, 2026" or "March 15-17, 2026"
        # "Registration deadline: Mar 10, 2026"
        # "Mar 15, 2026"
        
        # Try to find registration deadline
        reg_patterns = [
            r'(?:registration|register|apply|deadline|closes?)[:\s]+([A-Za-z]+\s+\d{1,2},?\s*\d{4})',
            r'(?:registration|register|apply|deadline|closes?)[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        ]
        for pat in reg_patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                reg_deadline = self._normalize_date(match.group(1))
                break
        
        # Try to find date range
        range_patterns = [
            r'([A-Za-z]+\s+\d{1,2},?\s*\d{4})\s*[-–—]\s*([A-Za-z]+\s+\d{1,2},?\s*\d{4})',
            r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s*[-–—]\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
            r'([A-Za-z]+\s+\d{1,2})\s*[-–—]\s*([A-Za-z]+\s+\d{1,2},?\s*\d{4})',
        ]
        for pat in range_patterns:
            match = re.search(pat, text)
            if match:
                start_date = self._normalize_date(match.group(1))
                end_date = self._normalize_date(match.group(2))
                break
        
        # Single date
        if not start_date:
            single_patterns = [
                r'([A-Za-z]+\s+\d{1,2},?\s*\d{4})',
                r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
            ]
            for pat in single_patterns:
                match = re.search(pat, text)
                if match:
                    start_date = self._normalize_date(match.group(1))
                    break
        
        return start_date, end_date, reg_deadline

    def _normalize_date(self, text: str) -> str:
        """Normalize date to YYYY-MM-DD"""
        if not text:
            return ""
        text = text.strip().replace(',', '')
        
        formats = [
            '%B %d %Y', '%b %d %Y', '%d %B %Y', '%d %b %Y',
            '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y',
            '%B %d', '%b %d', '%Y-%m-%d'
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(text, fmt)
                if dt.year == 1900:
                    dt = dt.replace(year=datetime.now().year)
                    if dt < datetime.now():
                        dt = dt.replace(year=datetime.now().year + 1)
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                continue
        return text

    async def scrape_all(self) -> List[Hackathon]:
        """Scrape all platforms"""
        print("\n[+] Starting Playwright scrapers for all platforms...\n")
        
        all_results = []
        
        # Scrape each platform
        results = await self.scrape_devfolio()
        all_results.extend(results)
        
        results = await self.scrape_hackerearth()
        all_results.extend(results)
        
        results = await self.scrape_unstop()
        all_results.extend(results)
        
        results = await self.scrape_devpost()
        all_results.extend(results)
        
        results = await self.scrape_mlh()
        all_results.extend(results)
        
        await self._close_browser()
        return all_results


# ============================================================
# EXPORT UTILITIES
# ============================================================

class HackathonExporter:
    @staticmethod
    def to_csv(hackathons: List[Hackathon], filename: str = 'hackathons.csv'):
        headers = [
            'Platform', 'Name', 'URL', 'Location', 'Start Date', 'End Date',
            'Registration Deadline', 'Status', 'Eligibility', 'Prize Pool',
            'Themes', 'Tags', 'Description', 'Online', 'Student Only', 'Scraped At'
        ]
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for h in hackathons:
                writer.writerow(h.to_csv_row())
        print(f"[OK] Exported {len(hackathons)} hackathons to {filename}")

    @staticmethod
    def to_json(hackathons: List[Hackathon], filename: str = 'hackathons.json'):
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump([h.to_dict() for h in hackathons], f, indent=2, ensure_ascii=False)
        print(f"[OK] Exported {len(hackathons)} hackathons to {filename}")

    @staticmethod
    def to_markdown_table(hackathons: List[Hackathon], filename: str = 'hackathons.md'):
        # Filter for registrations open + student-eligible
        filtered = [h for h in hackathons if 'open' in h.status.lower() or 'upcoming' in h.status.lower() or 'regist' in h.status.lower() or not h.status]
        filtered.sort(key=lambda x: x.registration_deadline or x.start_date or '9999-12-31')
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write('# Upcoming Hackathons for BE-CSE Students\n\n')
            f.write(f'*Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}*\n\n')
            f.write('| Platform | Hackathon | Location | Dates | Status | Prize | Themes | Link |\n')
            f.write('|----------|-----------|----------|-------|--------|-------|--------|------|\n')
            for h in filtered:
                themes = ', '.join(h.themes[:3]) if h.themes else '-'
                date_info = f"{h.start_date} to {h.end_date}" if h.start_date else (h.registration_deadline or 'TBD')
                f.write(f"| {h.platform} | [{h.name}]({h.url}) | {h.location or 'Online'} | {date_info} | {h.status or 'Upcoming'} | {h.prize_pool or '-'} | {themes} | [Link]({h.url}) |\n")
        print(f"[OK] Exported {len(filtered)} filtered hackathons to {filename}")

    @staticmethod
    def to_google_sheets_csv(hackathons: List[Hackathon], filename: str = 'hackathons_gsheets.csv'):
        """Optimized for Google Sheets import with hyperlinks"""
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Platform', 'Hackathon Name', 'Link', 'Location', 'Start Date', 'End Date',
                'Reg Deadline', 'Status', 'Eligibility', 'Prize Pool', 'Themes', 'Tags',
                'Online?', 'Students Only?', 'Notes'
            ])
            for h in hackathons:
                link_formula = f'=HYPERLINK("{h.url}", "{h.name}")'
                writer.writerow([
                    h.platform, h.name, link_formula, h.location,
                    h.start_date, h.end_date, h.registration_deadline,
                    h.status, h.eligibility, h.prize_pool,
                    '; '.join(h.themes), '; '.join(h.tags),
                    'Yes' if h.is_online else 'No',
                    'Yes' if h.is_student_only else 'No',
                    ''
                ])
        print(f"[OK] Exported Google Sheets-ready CSV to {filename}")


# ============================================================
# MAIN ORCHESTRATOR
# ============================================================

class HackathonAggregator:
    def __init__(self):
        self.scraper = PlaywrightScraper()
        self.all_hackathons: List[Hackathon] = []

    async def run(self) -> List[Hackathon]:
        """Run all scrapers"""
        self.all_hackathons = await self.scraper.scrape_all()
        
        # Deduplicate
        print("\n[>] Deduplicating...")
        self.all_hackathons = self.deduplicate(self.all_hackathons)
        
        return self.all_hackathons

    def filter_for_students(self, hackathons: List[Hackathon]) -> List[Hackathon]:
        """Filter for student-eligible, registration-open hackathons"""
        keywords_student = ['student', 'university', 'college', 'undergrad', 'campus', 'academic']
        keywords_open = ['open', 'upcoming', 'register', 'apply', 'accepting', 'live']
        
        filtered = []
        for h in hackathons:
            text = f"{h.name} {h.eligibility} {h.status} {h.description}".lower()
            is_student_friendly = h.is_student_only or any(k in text for k in keywords_student)
            is_registration_open = any(k in h.status.lower() for k in keywords_open) or not h.status
            
            if is_student_friendly and is_registration_open:
                filtered.append(h)
        return filtered

    def deduplicate(self, hackathons: List[Hackathon]) -> List[Hackathon]:
        """Remove duplicates based on name similarity"""
        seen = set()
        unique = []
        for h in hackathons:
            key = h.name.lower().strip()[:50]
            if key not in seen:
                seen.add(key)
                unique.append(h)
        print(f"  Removed {len(hackathons) - len(unique)} duplicates")
        return unique

    def export_all(self, prefix: str = 'hackathons'):
        """Export in all formats"""
        HackathonExporter.to_csv(self.all_hackathons, f'{prefix}.csv')
        HackathonExporter.to_json(self.all_hackathons, f'{prefix}.json')
        HackathonExporter.to_markdown_table(self.all_hackathons, f'{prefix}.md')
        HackathonExporter.to_google_sheets_csv(self.all_hackathons, f'{prefix}_gsheets.csv')

    def print_summary(self):
        print(f"\n{'='*60}")
        print(f"SCRAPING COMPLETE - Total: {len(self.all_hackathons)} hackathons")
        print(f"{'='*60}")
        
        by_platform = {}
        for h in self.all_hackathons:
            by_platform[h.platform] = by_platform.get(h.platform, 0) + 1
        
        for platform, count in sorted(by_platform.items()):
            print(f"  {platform}: {count}")
        
        student_friendly = self.filter_for_students(self.all_hackathons)
        print(f"\n  [STUDENT] Student-friendly & registration open: {len(student_friendly)}")
        
        online = [h for h in self.all_hackathons if h.is_online]
        print(f"  [ONLINE] Online/Virtual: {len(online)}")
        
        india = [h for h in self.all_hackathons if 'india' in h.location.lower()]
        print(f"  [INDIA] India-based: {len(india)}")
        
        # Show top 5 student-friendly
        if student_friendly:
            print(f"\n  Top Student-Friendly Hackathons:")
            for i, h in enumerate(student_friendly[:5], 1):
                date_str = h.start_date or h.registration_deadline or 'TBD'
                print(f"    {i}. {h.name} ({h.platform}) - {date_str} - {h.location}")


# ============================================================
# CLI ENTRY POINT
# ============================================================

async def main():
    print("""
===============================================================
           HACKATHON AGGREGATOR v1.0
   Scrapes Devfolio, HackerEarth, Unstop, Devpost, MLH
===============================================================
    """)
    
    aggregator = HackathonAggregator()
    
    try:
        await aggregator.run()
    except KeyboardInterrupt:
        print("\n[WARN] Scraping interrupted")
    except Exception as e:
        print(f"\n[FAIL] Scraping failed: {e}")
        import traceback
        traceback.print_exc()
    
    if aggregator.all_hackathons:
        aggregator.print_summary()
        print("\n[>] Exporting...")
        aggregator.export_all('hackathons_2026')
        
        print("""
[OK] Done! Check these files:
  - hackathons_2026.csv          - Raw data
  - hackathons_2026.json         - Structured data
  - hackathons_2026.md           - Markdown table (README-ready)
  - hackathons_2026_gsheets.csv  - Google Sheets import (with hyperlinks)

[>] Tip: Import hackathons_2026_gsheets.csv into Google Sheets for filtering/sorting!
    """)


if __name__ == '__main__':
    asyncio.run(main())