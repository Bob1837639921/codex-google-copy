---
name: character-generator
description: Generate wasteland character design sheets across multiple dimensions (DALL-E) and sync them to the React frontend UI. Trigger keywords: 生图, 角色生成, 生成角色, 画角色, dalle, 画图.
---

# Character Generator Skill

Use this skill when you want to generate high-fidelity, multi-dimensional visual assets for a character (e.g. main portrait, model sheet, expression sheet, outfit breakdown) using DALL-E, and sync these assets directly to the local React database.

## Triggers
- **Trigger keywords**: `["生图", "角色生成", "生成角色", "画角色", "dalle", "画图"]`

## Execution Guide
- Uses `part_generator.py` under the hood.
- Accepts character name or ID to generate missing assets.
- Automatically handles ChatGPT interaction, retrieves generated image URLs, downloads them, copies/renames them to structured directories under `C:/Ai/character/`, and updates `characterAssets.json` inside the React project constants.
