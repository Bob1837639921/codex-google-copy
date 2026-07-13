---
name: xiaohongshu-automation
description: "Safely browse and inspect bounded Xiaohongshu (XHS) search results, notes, and comments with strict risk-control handling. Trigger keywords: 小红书, xiaohongshu, xhs, 红书."
---

# Xiaohongshu Automation Skill

Use this skill when you need to search or inspect a bounded set of Xiaohongshu (小红书) notes and comments through the user's existing Chrome session.

## Triggers
- **Trigger keywords**: `["小红书", "xiaohongshu", "xhs", "红书"]`

## Execution Guide
- Uses the generic `auto_operator.py` driven by `site_profiles/xhs.json`.
- Reuse one controlled tab and the existing signed-in session. Do not fan out into parallel tabs or repeatedly reload the same page.
- Start with `nodex_observe`, perform one action, then verify the resulting URL, overlay, or visible content before continuing.
- Keep `smart` mode for clicks and typing. Do not use direct DOM clicks as a speed shortcut.
- Inspect only the notes and comment batches needed for the user's decision. Prefer bounded extraction over exhaustive comment crawling.
- Let the runtime wait for Xiaohongshu's DOM to become stable after navigation. After submission, clicks, or scrolling, use an evidence-based `wait_for` or fresh observation instead of a fixed delay.
- If a locator fails, observe again and choose a new evidence-backed locator. Never repeat the same failed action in a tight loop.

## Risk-Control Stop Conditions

Stop automatic interaction immediately when a snapshot reports `blocked_by_login` or `blocked_by_risk`, or when the page shows login, CAPTCHA, slider verification, unusual traffic, frequent access/operation, page abnormality, access denied, or retry-later messaging.

- Do not solve or bypass a CAPTCHA, slider, device check, login challenge, or account-risk prompt.
- Do not change fingerprints, user agents, browser properties, storage, or network identity to conceal automation.
- Preserve the current page and report the blocker to the user. Resume only after the user has handled the challenge and a fresh observation shows the blocker is gone.
