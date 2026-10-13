# 🎯 Hackathon Scraper for BE-CSE Students

Automated scraper that fetches upcoming hackathons from **Devfolio, HackerEarth, Unstop, Devpost, and MLH** — tailored for Indian Computer Science undergraduates.

## ✨ Features

| Feature | Description |
|---------|-------------|
| **Multi-platform** | Scrapes 5 major hackathon platforms |
| **Student-focused** | Filters for student-eligible, registration-open events |
| **Multiple exports** | CSV, JSON, Markdown, Google Sheets-ready CSV |
| **Deduplication** | Removes duplicate entries across platforms |
| **Dynamic support** | Playwright for JavaScript-heavy sites (Devfolio) |
| **Date normalization** | Converts all dates to ISO format (YYYY-MM-DD) |
| **Online/Offline tags** | Identifies virtual vs in-person events |
| **India-aware** | Flags India-based hackathons |

## 🚀 Quick Start

```bash
# 1. Clone/navigate to the directory
cd hackathon_scraper

# 2. Run setup (installs dependencies + Playwright browser)
python setup.py

# 3. Run the scraper
python scraper.py
```

## 📁 Output Files

| File | Description | Best For |
|------|-------------|----------|
| `hackathons_2026.csv` | Raw data, all fields | Data analysis, Python/pandas |
| `hackathons_2026.json` | Structured JSON | Web apps, APIs |
| `hackathons_2026.md` | Markdown table | README, Notion, GitHub |
| `hackathons_2026_gsheets.csv` | **Google Sheets optimized** | **👉 Import this to Google Sheets!** |

### Google Sheets Import (Recommended)
1. Open [Google Sheets](https://sheets.google.com)
2. File → Import → Upload `hackathons_2026_gsheets.csv`
3. The **Link** column will have clickable hyperlinks!
4. Use Filter views to sort by: Status, Platform, Online, Date

## 🎯 Sample Output (Markdown)

```markdown
| Platform | Hackathon | Location | Dates | Status | Prize | Themes | Link |
|----------|-----------|----------|-------|--------|-------|--------|------|
| Devfolio | HackIndia 2026 | IIT Delhi | 2026-02-15 to 2026-02-17 | Registrations Open | ₹5,00,000 | AI, Web, FinTech | [Link](https://devfolio.co/hackathons/hackindia-2026) |
| Unstop | Smart India Hackathon 2026 | Online + Onsite | 2026-01-20 | Upcoming | ₹1 Cr+ | Govt PS, Social Impact | [Link](https://unstop.com/hackathon/sih-2026) |
| MLH | HackMIT 2026 | MIT Cambridge | 2026-09-16 to 2026-09-18 | Registrations Open | $50,000+ | General, Hardware | [Link](https://mlh.io/seasons/2026/events/hackmit) |
```

## 🔧 Configuration

Edit `scraper.py` to customize:

```python
# Adjust scrape limits per platform
cards = soup.select('...')[:50]  # Change 50 to desired limit

# Modify delay between requests (be respectful!)
delay: float = 1.5  # seconds

# Add custom filters in filter_for_students()
keywords_student = ['student', 'university', 'college', 'undergrad', ...]
```

## 📅 Automated Scheduling

### GitHub Actions (Free, runs daily)
Create `.github/workflows/hackathons.yml`:

```yaml
name: Daily Hackathon Scrape
on:
  schedule:
    - cron: '0 6 * * *'  # Daily at 6 AM UTC
  workflow_dispatch:  # Manual trigger

jobs:
  scrape:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install -r requirements.txt
      - run: python -m playwright install chromium
      - run: python scraper.py
      - uses: actions/upload-artifact@v4
        with:
          name: hackathon-data
          path: hackathons_2026_*.csv
```

### Local Cron (Linux/Mac)
```bash
# Edit crontab
crontab -e

# Add: Run daily at 7 AM
0 7 * * * cd /path/to/hackathon_scraper && python scraper.py >> scraper.log 2>&1
```

### Windows Task Scheduler
1. Open Task Scheduler → Create Basic Task
2. Trigger: Daily, 7:00 AM
3. Action: Start Program
   - Program: `python.exe` (full path)
   - Arguments: `scraper.py`
   - Start in: `C:\Users\RAJAT\hackathon_scraper`

## 🛡️ Ethical Scraping Guidelines

- **Rate limited**: 1.5-2 second delays between requests
- **Respects robots.txt**: Only scrapes public listing pages
- **No authentication**: Only accesses publicly visible data
- **Educational purpose**: For student hackathon discovery
- **Check ToS**: Review each platform's Terms of Service before production use

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError` | Run `python setup.py` again |
| Playwright browser missing | Run `python -m playwright install chromium` |
| Empty results | Site structure changed; check selectors in scraper |
| Timeout errors | Increase `timeout` in `_get()` method |
| Blocked by Cloudflare | Use Playwright scraper instead of requests |

## 📊 Extending the Scraper

### Add a New Platform
```python
class NewPlatformScraper(BaseScraper):
    def __init__(self):
        super().__init__('NewPlatform', 'https://newplatform.com')
    
    def scrape(self) -> List[Hackathon]:
        # Implement parsing logic
        return hackathons

# Register in HackathonAggregator.__init__()
self.scrapers.append(NewPlatformScraper())
```

### Add Email/Slack Notifications
```python
# In main(), after export:
import smtplib
from email.mime.text import MIMEText

def send_summary(hackathons):
    student_hacks = aggregator.filter_for_students(hackathons)
    if student_hacks:
        # Send email with top 5
        pass
```

## 🤝 Contributing

1. Fork the repo
2. Add platform scraper or improve selectors
3. Submit PR with sample output

## ⚠️ Disclaimer

This tool is for **educational and personal use only**. Always:
- Check hackathon eligibility on the official site
- Verify dates and registration links manually
- Respect platform Terms of Service
- Use official APIs where available

## 📄 License

MIT License - Feel free to modify and distribute.

---

**Happy Hacking!** 🚀 Built for BE-CSE students by a fellow developer.