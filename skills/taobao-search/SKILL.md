---
name: taobao-search
description: Perform generic product search and price/sales extraction on Taobao. Trigger keywords: 淘宝, taobao, 搜商品, 买东西, 比价.
---

# Taobao Search Skill

Use this skill when you need to search for any item or category on Taobao, extract the search result cards (title, price, sales, shop, product link), and present them to the user.

## Triggers
- **Trigger keywords**: `["淘宝", "taobao", "搜商品", "买东西", "比价"]`

## Execution Guide
- Uses the generic `auto_operator.py` driven by `site_profiles/taobao.json`.
- Parameterized search allows query input (e.g., search for "显卡", "手机", or "猫粮").
- Automatically scrolls to load cards, extracts details, and outputs a structured report.
- Can redirect the active browser tab to the top product link.
