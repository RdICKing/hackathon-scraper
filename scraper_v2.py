#!/usr/bin/env python3
"""
Hackathon Scraper v2 - Improved selectors, better error handling, debugging
Scrapes: Devfolio, HackerEarth, Unstop, Devpost, MLH
"""

import asyncio
import csv
import json
import re
from datetime import datetime
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any
from urllib.parse import urljoin


@dataclass
class Hackathon:
    platform: str
    name: str
    url: str
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    registration_deadline: str = ""
    status: str = ""
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


class HackathonScraper:
    def __init__(self):
        self.browser = None
        self.context = None
        self.playwright = None

    async def _init_browser(self):
        from playwright.async_api import async_playwright
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True)
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )

    async def _close_browser(self):
        if self.browser:
            await self.browser.close()
            await self.playwright.stop()

    async def _goto_with_retry(self, page, url, max_retries=2):
        for attempt in range(max_retries):
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=60000)
                await page.wait_for_load_state('networkidle', timeout=15000)
                return True
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"  [FAIL] Navigation failed after {max_retries} attempts: {url} - {e}")
                    return False
                await asyncio.sleep(2)
        return False

    async def _safe_text(self, element, selectors: List[str]) -> str:
        for sel in selectors:
            try:
                el = await element.query_selector(sel)
                if el:
                    text = await el.inner_text()
                    if text and text.strip():
                        return text.strip()
            except:
                continue
        return ""

    async def _safe_attr(self, element, selectors: List[str], attr: str) -> str:
        for sel in selectors:
            try:
                el = await element.query_selector(sel)
                if el:
                    val = await el.get_attribute(attr)
                    if val:
                        return val
            except:
                continue
        return ""

    # ========== DATE PARSING ==========
    def _parse_dates(self, text: str) -> tuple:
        if not text:
            return "", "", ""
        text = text.strip()
        start_date = end_date = reg_deadline = ""

        # Registration deadline patterns
        reg_patterns = [
            r'(?:registration|register|apply|deadline|closes?|ends?)[:\s]+([A-Za-z]+\s+\d{1,2},?\s*\d{4})',
            r'(?:registration|register|apply|deadline|closes?|ends?)[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        ]
        for pat in reg_patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                reg_deadline = self._normalize_date(match.group(1))
                break

        # Date range patterns
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
        if not text:
            return ""
        text = text.strip().replace(',', '')
        formats = [
            '%B %d %Y', '%b %d %Y', '%d %B %Y', '%d %b %Y',
            '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y',
            '%B %d', '%b %d'
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

    # ========== PLATFORM SCRAPERS ==========

    async def scrape_devfolio(self) -> List[Hackathon]:
        print("[>] Scraping Devfolio...")
        hackathons = []
        page = await self.context.new_page()
        
        try:
            if not await self._goto_with_retry(page, 'https://devfolio.co/hackathons'):
                return hackathons
            
            # Wait for content to load
            await asyncio.sleep(3)
            
            # Try multiple selector strategies
            cards = await page.query_selector_all('a[href*="/hackathons/"]')
            print(f"  Found {len(cards)} hackathon links")
            
            # Get unique hackathon URLs
            seen_urls = set()
            hackathon_urls = []
            for card in cards:
                href = await card.get_attribute('href')
                if href and '/hackathons/' in href and href not in seen_urls:
                    seen_urls.add(href)
                    full_url = f"https://devfolio.co{href}" if not href.startswith('http') else href
                    hackathon_urls.append(full_url)
            
            print(f"  Unique hackathon URLs: {len(hackathon_urls)}")
            
            # Visit each hackathon page for details (limit to 20 to avoid timeout)
            for url in hackathon_urls[:20]:
                try:
                    detail_page = await self.context.new_page()
                    if await self._goto_with_retry(detail_page, url):
                        await asyncio.sleep(1)
                        
                        # Extract details from the detail page
                        name = await self._safe_text(detail_page, ['h1', '[data-testid="hackathon-name"]', '.hackathon-name'])
                        location = await self._safe_text(detail_page, ['[data-testid="location"]', '.location', '.hackathon-location'])
                        date_text = await self._safe_text(detail_page, ['[data-testid="date"]', '.date', '.hackathon-date', 'time'])
                        status = await self._safe_text(detail_page, ['[data-testid="status"]', '.status', '.badge', '.tag'])
                        prize = await self._safe_text(detail_page, ['[data-testid="prize"]', '.prize', '.hackathon-prize'])
                        desc = await self._safe_text(detail_page, ['[data-testid="description"]', '.description', '.hackathon-desc', '.about'])
                        
                        # Themes
                        theme_els = await detail_page.query_selector_all('[data-testid="theme"], .theme-tag, .tag, .topic, .theme')
                        themes = []
                        for te in theme_els:
                            t = await te.inner_text()
                            if t: themes.append(t.strip())
                        
                        if name:
                            is_online = 'online' in location.lower() or 'virtual' in location.lower() or 'remote' in location.lower()
                            start_date, end_date, reg_deadline = self._parse_dates(date_text)
                            
                            hackathons.append(Hackathon(
                                platform='Devfolio',
                                name=name.strip(),
                                url=url,
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
                    await detail_page.close()
                    await asyncio.sleep(0.5)  # Rate limit
                except Exception as e:
                    continue
                    
        except Exception as e:
            print(f"  [FAIL] Devfolio: {e}")
        finally:
            await page.close()
        
        print(f"  [OK] Devfolio: {len(hackathons)} hackathons")
        return hackathons

    async def scrape_hackerearth(self) -> List[Hackathon]:
        print("[>] Scraping HackerEarth...")
        hackathons = []
        page = await self.context.new_page()
        
        try:
            if not await self._goto_with_retry(page, 'https://hackerearth.com/challenges/hackathon/'):
                return hackathons
            
            await asyncio.sleep(3)
            
            # HackerEarth challenge cards - try multiple selectors
            card_selectors = [
                'a[href*="/challenges/"]',  # Direct links to challenges
                '.challenge-card',
                '.hackathon-card', 
                '[data-cy="challenge-card"]',
                '.challenge-list-item',
                '.upcoming-challenge'
            ]
            
            cards = []
            for sel in card_selectors:
                found = await page.query_selector_all(sel)
                if found:
                    cards = found
                    print(f"  Found {len(cards)} cards with selector: {sel}")
                    break
            
            if not cards:
                # Fallback: get all links to challenges
                all_links = await page.query_selector_all('a[href*="/challenge/"]')
                cards = all_links
                print(f"  Fallback: Found {len(cards)} challenge links")
            
            seen_urls = set()
            for card in cards[:40]:
                try:
                    href = await card.get_attribute('href')
                    if not href or '/challenge/' not in href:
                        continue
                    if href in seen_urls:
                        continue
                    seen_urls.add(href)
                    
                    full_url = f"https://hackerearth.com{href}" if not href.startswith('http') else href
                    
                    # Get name from the card or link text
                    name = await card.inner_text()
                    if not name or len(name) < 5:
                        # Try parent elements
                        parent = await card.query_selector('xpath=..')
                        if parent:
                            name = await parent.inner_text()
                    
                    name = name.strip()[:200] if name else "Unknown"
                    if len(name) < 5:
                        continue
                    
                    # Try to get more details from the card
                    status = await self._safe_text(card, ['.challenge-type', '.status', '.badge', '.label', '[data-cy="challenge-type"]'])
                    date_text = await self._safe_text(card, ['.challenge-date', '.date', '.duration', '[data-cy="challenge-date"]'])
                    prize = await self._safe_text(card, ['.prize', '.prize-amount', '.reward'])
                    
                    start_date, end_date, reg_deadline = self._parse_dates(date_text)
                    
                    hackathons.append(Hackathon(
                        platform='HackerEarth',
                        name=name,
                        url=full_url,
                        status=status.strip() or "Upcoming",
                        prize_pool=prize.strip(),
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

    async def scrape_unstop(self) -> List[Hackathon]:
        print("[>] Scraping Unstop...")
        hackathons = []
        page = await self.context.new_page()
        
        try:
            if not await self._goto_with_retry(page, 'https://unstop.com/hackathons'):
                return hackathons
            
            await asyncio.sleep(3)
            
            # Unstop uses dynamic loading - scroll to load more
            for _ in range(3):
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await asyncio.sleep(1.5)
            
            # Try multiple selectors for hackathon cards
            card_selectors = [
                'a[href*="/hackathon/"]',
                'a[href*="/opportunity/"]',
                '.hackathon-card',
                '.opportunity-card',
                '.opportunity-box',
                '.compact-card',
                '[data-testid="hackathon-card"]',
                '.card'
            ]
            
            cards = []
            for sel in card_selectors:
                found = await page.query_selector_all(sel)
                if found:
                    cards = found
                    print(f"  Found {len(cards)} elements with: {sel}")
                    break
            
            seen_urls = set()
            for card in cards[:40]:
                try:
                    href = await card.get_attribute('href')
                    if not href or ('/hackathon/' not in href and '/opportunity/' not in href):
                        continue
                    if href in seen_urls:
                        continue
                    seen_urls.add(href)
                    
                    full_url = f"https://unstop.com{href}" if not href.startswith('http') else href
                    
                    # Get details from card
                    name = await self._safe_text(card, ['h3', 'h2', '.title', '.opportunity-name', '.card-title'])
                    if not name:
                        name = await card.inner_text()
                    name = name.strip()[:200]
                    if len(name) < 5:
                        continue
                    
                    location = await self._safe_text(card, ['.location', '.venue', '.place'])
                    date_text = await self._safe_text(card, ['.date', '.deadline', '.duration', '.deadline-text'])
                    status = await self._safe_text(card, ['.status', '.badge', '.label', '.chip'])
                    prize = await self._safe_text(card, ['.prize', '.reward', '.prize-money'])
                    
                    theme_els = await card.query_selector_all('.tag, .skill-tag, .theme, .topic')
                    themes = []
                    for te in theme_els:
                        t = await te.inner_text()
                        if t: themes.append(t.strip())
                    
                    is_online = 'online' in location.lower() or 'virtual' in location.lower() or 'remote' in location.lower()
                    start_date, end_date, reg_deadline = self._parse_dates(date_text)
                    
                    hackathons.append(Hackathon(
                        platform='Unstop',
                        name=name,
                        url=full_url,
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

    async def scrape_devpost(self) -> List[Hackathon]:
        print("[>] Scraping Devpost...")
        hackathons = []
        page = await self.context.new_page()
        
        try:
            urls = [
                'https://devpost.com/hackathons',
                'https://devpost.com/hackathons?status=upcoming',
            ]
            
            for url in urls:
                try:
                    if not await self._goto_with_retry(page, url):
                        continue
                    
                    await asyncio.sleep(2)
                    
                    # Devpost hackathon tiles
                    tiles = await page.query_selector_all('a[href*="/hackathons/"]')
                    print(f"  Found {len(tiles)} hackathon links at {url}")
                    
                    seen = set()
                    for tile in tiles[:30]:
                        try:
                            href = await tile.get_attribute('href')
                            if not href or '/hackathons/' not in href:
                                continue
                            if href in seen:
                                continue
                            seen.add(href)
                            
                            full_url = f"https://devpost.com{href}" if not href.startswith('http') else href
                            
                            # Get tile content
                            name = await self._safe_text(tile, ['h3', '.hackathon-name', '.challenge-name', '.software-title'])
                            if not name:
                                name = await tile.inner_text()
                            name = name.strip()[:200]
                            if len(name) < 5:
                                continue
                            
                            # Get sibling/parent elements for more info
                            parent = await tile.query_selector('xpath=..')
                            location = ""
                            date_text = ""
                            status = ""
                            prize = ""
                            
                            if parent:
                                location = await self._safe_text(parent, ['.location', '.venue', '.hackathon-location'])
                                date_text = await self._safe_text(parent, ['.date', '.submission-period', '.deadline', '.hackathon-date'])
                                status = await self._safe_text(parent, ['.status', '.label', '.badge', '.hackathon-status'])
                                prize = await self._safe_text(parent, ['.prize', '.prize-amount', '.hackathon-prize'])
                            
                            is_online = 'online' in location.lower() or 'virtual' in location.lower() or 'remote' in location.lower()
                            start_date, end_date, reg_deadline = self._parse_dates(date_text)
                            
                            hackathons.append(Hackathon(
                                platform='Devpost',
                                name=name,
                                url=full_url,
                                location=location.strip() or "Online",
                                start_date=start_date,
                                end_date=end_date,
                                registration_deadline=reg_deadline,
                                status=status.strip() or "Upcoming",
                                prize_pool=prize.strip(),
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
        
        # Deduplicate
        seen = set()
        unique = []
        for h in hackathons:
            key = h.name.lower().strip()[:50]
            if key not in seen:
                seen.add(key)
                unique.append(h)
        
        print(f"  [OK] Devpost: {len(unique)} hackathons")
        return unique

    async def scrape_mlh(self) -> List[Hackathon]:
        print("[>] Scraping MLH...")
        hackathons = []
        page = await self.context.new_page()
        
        try:
            # Try 2026 season first, then 2025
            for season_url in ['https://mlh.io/seasons/2026/events', 'https://mlh.io/seasons/2025/events', 'https://mlh.io/events']:
                try:
                    if not await self._goto_with_retry(page, season_url):
                        continue
                    
                    await asyncio.sleep(2)
                    
                    # MLH event cards
                    card_selectors = [
                        'a[href*="/events/"]',
                        '.event-wrapper',
                        '.event-card',
                        '.hackathon-event',
                        '[data-testid="event-card"]',
                        '.event'
                    ]
                    
                    cards = []
                    for sel in card_selectors:
                        found = await page.query_selector_all(sel)
                        if found:
                            cards = found
                            print(f"  Found {len(cards)} events with: {sel} at {season_url}")
                            break
                    
                    if not cards:
                        continue
                    
                    seen_urls = set()
                    for card in cards[:40]:
                        try:
                            href = await card.get_attribute('href')
                            if not href or '/events/' not in href:
                                continue
                            if href in seen_urls:
                                continue
                            seen_urls.add(href)
                            
                            full_url = f"https://mlh.io{href}" if not href.startswith('http') else href
                            
                            name = await self._safe_text(card, ['h3', '.event-name', '.hackathon-name', '.event-title'])
                            if not name:
                                name = await card.inner_text()
                            name = name.strip()[:200]
                            if len(name) < 5:
                                continue
                            
                            location = await self._safe_text(card, ['.event-location', '.location', '.venue', '.event-venue'])
                            date_text = await self._safe_text(card, ['.event-date', '.date', '.duration', '.event-time'])
                            
                            theme_els = await card.query_selector_all('.track, .theme, .category, .event-track')
                            themes = []
                            for te in theme_els:
                                t = await te.inner_text()
                                if t: themes.append(t.strip())
                            
                            is_online = 'online' in location.lower() or 'virtual' in location.lower() or 'remote' in location.lower()
                            start_date, end_date, reg_deadline = self._parse_dates(date_text)
                            
                            hackathons.append(Hackathon(
                                platform='MLH',
                                name=name,
                                url=full_url,
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
                    
                    if hackathons:
                        break  # Success, don't try other URLs
                        
                except Exception as e:
                    print(f"  Error with {season_url}: {e}")
                    continue
                    
        except Exception as e:
            print(f"  [FAIL] MLH: {e}")
        finally:
            await page.close()
        
        print(f"  [OK] MLH: {len(hackathons)} hackathons")
        return hackathons

    async def scrape_all(self) -> List[Hackathon]:
        print("\n[+] Starting scrapers for all platforms...\n")
        await self._init_browser()
        
        all_results = []
        
        # Run all scrapers
        for scraper_method in [
            self.scrape_devfolio,
            self.scrape_hackerearth,
            self.scrape_unstop,
            self.scrape_devpost,
            self.scrape_mlh
        ]:
            try:
                results = await scraper_method()
                all_results.extend(results)
            except Exception as e:
                print(f"  [FAIL] {scraper_method.__name__}: {e}")
        
        await self._close_browser()
        return all_results


# ========== EXPORT UTILITIES ==========

class Exporter:
    @staticmethod
    def to_csv(hackathons: List[Hackathon], filename: str):
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
        print(f"[OK] Exported {len(hackathons)} to {filename}")

    @staticmethod
    def to_json(hackathons: List[Hackathon], filename: str):
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump([h.to_dict() for h in hackathons], f, indent=2, ensure_ascii=False)
        print(f"[OK] Exported {len(hackathons)} to {filename}")

    @staticmethod
    def to_markdown(hackathons: List[Hackathon], filename: str):
        filtered = [h for h in hackathons if 'open' in h.status.lower() or 'upcoming' in h.status.lower() or 'regist' in h.status.lower() or 'left' in h.status.lower() or not h.status]
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
        print(f"[OK] Exported {len(filtered)} filtered to {filename}")

    @staticmethod
    def to_gsheets_csv(hackathons: List[Hackathon], filename: str):
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
        print(f"[OK] Exported Google Sheets CSV to {filename}")


# ========== MAIN ==========

class Aggregator:
    def __init__(self):
        self.scraper = HackathonScraper()
        self.all_hackathons: List[Hackathon] = []

    async def run(self):
        self.all_hackathons = await self.scraper.scrape_all()
        self.all_hackathons = self.deduplicate(self.all_hackathons)
        return self.all_hackathons

    def filter_students(self, hackathons: List[Hackathon]) -> List[Hackathon]:
        keywords_student = ['student', 'university', 'college', 'undergrad', 'campus', 'academic']
        keywords_open = ['open', 'upcoming', 'register', 'apply', 'accepting', 'live', 'left', 'days']
        
        filtered = []
        for h in hackathons:
            text = f"{h.name} {h.eligibility} {h.status} {h.description}".lower()
            is_student = h.is_student_only or any(k in text for k in keywords_student)
            is_open = any(k in h.status.lower() for k in keywords_open) or not h.status
            if is_student and is_open:
                filtered.append(h)
        return filtered

    def deduplicate(self, hackathons: List[Hackathon]) -> List[Hackathon]:
        seen = set()
        unique = []
        for h in hackathons:
            key = h.name.lower().strip()[:50]
            if key not in seen:
                seen.add(key)
                unique.append(h)
        print(f"  Deduplicated: {len(hackathons)} -> {len(unique)}")
        return unique

    def export_all(self, prefix: str = 'hackathons_2026'):
        Exporter.to_csv(self.all_hackathons, f'{prefix}.csv')
        Exporter.to_json(self.all_hackathons, f'{prefix}.json')
        Exporter.to_markdown(self.all_hackathons, f'{prefix}.md')
        Exporter.to_gsheets_csv(self.all_hackathons, f'{prefix}_gsheets.csv')

    def print_summary(self):
        print(f"\n{'='*60}")
        print(f"SCRAPING COMPLETE - Total: {len(self.all_hackathons)} hackathons")
        print(f"{'='*60}")
        
        by_platform = {}
        for h in self.all_hackathons:
            by_platform[h.platform] = by_platform.get(h.platform, 0) + 1
        
        for platform, count in sorted(by_platform.items()):
            print(f"  {platform}: {count}")
        
        student = self.filter_students(self.all_hackathons)
        print(f"\n  [STUDENT] Student-friendly & registration open: {len(student)}")
        
        online = [h for h in self.all_hackathons if h.is_online]
        print(f"  [ONLINE] Online/Virtual: {len(online)}")
        
        india = [h for h in self.all_hackathons if 'india' in h.location.lower()]
        print(f"  [INDIA] India-based: {len(india)}")
        
        if student:
            print(f"\n  Top Student-Friendly Hackathons:")
            for i, h in enumerate(student[:10], 1):
                date_str = h.start_date or h.registration_deadline or 'TBD'
                print(f"    {i}. {h.name} ({h.platform}) - {date_str} - {h.location}")


async def main():
    print("""
===============================================================
           HACKATHON AGGREGATOR v2.0
   Scrapes Devfolio, HackerEarth, Unstop, Devpost, MLH
===============================================================
    """)
    
    agg = Aggregator()
    
    try:
        await agg.run()
    except KeyboardInterrupt:
        print("\n[WARN] Interrupted")
    except Exception as e:
        print(f"\n[FAIL] Error: {e}")
        import traceback
        traceback.print_exc()
    
    if agg.all_hackathons:
        agg.print_summary()
        print("\n[>] Exporting...")
        agg.export_all()
        
        print("""
[OK] Done! Files created:
  - hackathons_2026.csv          - Raw data (Excel/pandas ready)
  - hackathons_2026.json         - Structured data (API ready)
  - hackathons_2026.md           - Markdown table (GitHub/Notion ready)
  - hackathons_2026_gsheets.csv  - Google Sheets import (hyperlinks!)

[>] Import hackathons_2026_gsheets.csv to Google Sheets for best experience
    """)


if __name__ == '__main__':
    asyncio.run(main())