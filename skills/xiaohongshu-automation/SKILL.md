---
name: xiaohongshu-automation
description: Automate search and content scraping on Xiaohongshu (XHS). Trigger keywords: 小红书, xiaohongshu, xhs, 红书.
---

# Xiaohongshu Automation Skill

Use this skill when you need to automate searching or extracting notes, details, and comments from Xiaohongshu (小红书).

## Triggers
- **Trigger keywords**: `["小红书", "xiaohongshu", "xhs", "红书"]`

## Execution Guide
- Uses the generic `auto_operator.py` driven by `site_profiles/xhs.json`.
- Automatically opens Chrome, navigates to the Xiaohongshu search results page, waits for cards to render, and extracts up to 20 search result cards (title, author, likes, link, image).
- Can also scrape note details and comments by clicking the note card and extracting the overlay elements.
