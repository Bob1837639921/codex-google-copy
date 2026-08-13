"""
F:\\CharacterBanner\\part_generator.py
======================================================
角色多维度各部位图片（头像、三视图、道具、草图等）自动生成与同步流水线
======================================================
1. 支持单角色“专属会话窗口（Single Character, Single Conversation）”，从根本上保持特征一致性并避免不同角色交叉污染。
2. 缓存会话 URL，第二次或后续生成直接导航至该 URL 进入已有上下文会话。
3. 自动匹配 localFileSystem.ts 里的 TYPE_FOLDER，将生成的图片下载、归档重命名到对应文件夹中。
4. 手术刀式回写 characterData.ts 中的 images 数组，支持追加新部位图片，且增加时间戳避开 Vite 浏览器缓存。

作者：Antigravity Team
日期：2026-06-01
"""

import os
import sys
import re
import time
import shutil
import asyncio
import json
import uuid
import logging
import argparse
import websockets

# 配置精致优雅的日志输出
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
if sys.platform.startswith('win'):
    import codecs
    sys.stdout.reconfigure(encoding='utf-8')

# ======================================================
# 1. 全局配置选项
# ======================================================
OUTPUT_ROOT = "F:/jiaose"
REACT_PROJECT_PATH = "F:/CharacterBanner"

# 尝试从本地配置文件动态加载，实现跨电脑免配置无缝适配
CONFIG_FILE_PATH = "local_config.json"
if os.path.exists(CONFIG_FILE_PATH):
    try:
        with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
            config_data = json.load(f)
            if "output_root" in config_data:
                OUTPUT_ROOT = config_data["output_root"]
            if "react_project_path" in config_data:
                REACT_PROJECT_PATH = config_data["react_project_path"]
            logging.info(f"✨ 动态载入配置：图片输出路径={OUTPUT_ROOT}, React项目路径={REACT_PROJECT_PATH}")
    except Exception as e:
        logging.warning(f"读取 local_config.json 失败: {e}")
        
DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads")
WS_URL = "ws://localhost:8765/client"
SESSIONS_CACHE_FILE = "chat_sessions.json"

# 本地文件夹映射 (与 localFileSystem.ts 保持 100% 绝对一致)
TYPE_FOLDER = {
    'main': '01-主视觉',
    'portrait': '02-头像半身',
    'expression': '03-表情差分',
    'turnaround': '04-三视图角度',
    'outfit': '05-服装差分',
    'prop': '06-道具武器',
    'scene': '07-场景氛围',
    'cover': '09-封面图',
    'moodboard': '10-氛围板',
    'sketch': '11-线稿结构',
    'fullBody': '12-全身立绘',
    'modelSheet': '13-标准设定图',
    'poseSheet': '14-动作姿态',
    'expressionSheet': '15-表情包',
    'detailSheet': '16-细节特写',
    'materialPalette': '17-材质色卡',
    'outfitBreakdown': '18-服装拆分',
    'damageState': '19-破损状态'
}

TYPE_LABEL = {
    'main': '主视觉',
    'portrait': '头像半身',
    'expression': '表情差分',
    'turnaround': '三视图角度',
    'outfit': '服装差分',
    'prop': '道具武器',
    'scene': '场景氛围',
    'cover': '封面图',
    'moodboard': '氛围板',
    'sketch': '线稿结构',
    'fullBody': '全身立绘',
    'modelSheet': '标准设定图',
    'poseSheet': '动作姿态',
    'expressionSheet': '表情包',
    'detailSheet': '细节特写',
    'materialPalette': '材质色卡',
    'outfitBreakdown': '服装拆分',
    'damageState': '破损状态'
}

LOCKS = {
    "char_0001_crimson_guardian": {
        "name": "The Crimson Wall Guardian (赤衣守城者)",
        "features": "slender young East Asian swordsman with handsome refined features, long wind-blown black hair, and unyielding dark red eyes. He wears a flowing crimson silk robe with golden ancient engravings and silver armor plates.",
        "prop": "his divine sword that glows with faint red aura and intricate runes",
        "prop_desc": "a beautifully detailed divine sword with a red aura and ancient runes glowing on the blade",
        "scene": "a massive ancient stone fortress wall under a dramatic sunset with golden and fiery orange light rays piercing through epic clouds, casting a warm glow over a mystical wasteland",
        "outfit_alt": "combat armor plates over a fitted black leather robe with crimson sashes",
        "colors": "crimson silk red, ancient gold, steel silver, sunset orange, graphite grey",
        "materials": "crimson silk fabric, polished silver armor, gold embroidery thread, steel blade",
        "damage": "his crimson robe's sleeves are frayed and torn at the cuffs, and the silver armor plates are scratched and dented, with soot marks on his face and chest. For the heavily damaged state, he stands defiantly next to a cracked and broken stone battlement, his robe shredded, and his divine sword's red glow is dim and flickering."
    },
    "char_0002_midnight_warden": {
        "name": "The Midnight Warden (午夜值守员)",
        "features": "slender young East Asian woman with tired yet sharp dark brown eyes, half-pinned pitch-black mid-length hair, wearing a buttoned deep navy blue duty uniform with a glowing silver badge on her chest.",
        "prop": "her vintage metallic flashlight and silver duty badge",
        "prop_desc": "a detailed vintage metallic flashlight and a bright silver duty badge that glows with warm amber light",
        "scene": "a quiet, dimly lit corridor at night, with a mysterious wooden door that glows brightly from its cracks with warm golden-amber light",
        "outfit_alt": "a casual civilian outfit consisting of a dark grey knit sweater, fitted black trousers, and heavy boots",
        "colors": "navy blue, silver glow, amber gold, corridor grey, moonlight white",
        "materials": "navy blue uniform wool, polished silver badge metal, metallic flashlight shell, polished marble floor",
        "damage": "her navy duty uniform is dusty and slightly torn at the shoulder, and her hair is disheveled. For the heavily damaged state, she stands next to a cracked wooden door, her uniform's sleeves frayed, and her flashlight's beam is dim and flickering."
    },
    "char_0003_sandstorm_pilgrim": {
        "name": "The Sandstorm Pilgrim (风沙朝圣者)",
        "features": "mature weathered East Asian ascetic monk with short grizzled hair tied with a faded red band, deep wise facial lines, and grey eyes. He wears a coarse, heavily patched sand-swept gray linen cloak over survival garments.",
        "prop": "his heavy brass staff adorned with ancient bronze wind chimes",
        "prop_desc": "a heavy brass staff with ancient bronze wind chimes, wrapped leather grip, and weathered metal textures",
        "scene": "an ancient, half-buried sand temple ruins under a massive brewing amber dust storm, with columns glowing with faint gold runes",
        "outfit_alt": "heavy sand-shielding leather armor, thick thermal wraps around his torso, and a protective respirator mask hanging around his neck",
        "colors": "sand-swept grey, bronze brown, brass gold, amber dust yellow, faded red",
        "materials": "coarse grey linen, weathered brass, worn leather wraps, bronze chimes",
        "damage": "his gray linen cloak is frayed and torn, with thick sand and dust covering his face and survival garments. For the heavily damaged state, he stands defiantly in the desert wind next to a cracked stone pillar, his cloak shredded into tattered rags, and his brass staff scratched and dented."
    },
    "char_0004_neon_hacker": {
        "name": "The Neon Shadow Hacker (霓虹潜行者)",
        "features": "cool young East Asian female hacker with asymmetrical glowing pink and purple hair, a translucent yellow holographic tactical visor over her right eye, wearing a matte-black technical raincoat over a dark bodysuit with glowing circuit lines.",
        "prop": "her carbon-fiber cybernetic prosthetic arm releasing glowing blue neural cables",
        "prop_desc": "a black carbon-fiber cybernetic prosthetic arm with glowing blue neural cables, and a yellow translucent holographic visor",
        "scene": "a towering cyberpunk city street at night under heavy rain, with massive glowing pink, purple, and cyan holographic advertisements reflecting on wet asphalt",
        "outfit_alt": "a tight, high-mobility matte-black stealth bodysuit with glowing violet energy seams, and sleek tactical boots",
        "colors": "neon pink, electric purple, matte black, cyan blue, holographic yellow",
        "materials": "matte-black technical fabric, carbon-fiber prosthetic shell, holographic light, wet concrete",
        "damage": "her technical raincoat is torn and scuffed, with cybernetic arm exposing minor wiring, and glowing circuits flickering. For the heavily damaged state, she stands next to a shattered holographic advertisement panel, her raincoat shredded, and the blue neural cables on her prosthetic arm broken and sparking."
    },
    "char_0036_red_umbrella_entity": {
        "name": "The Red Umbrella Entity (红伞执念体)",
        "features": "slender young East Asian woman with long flowing black hair, gentle but vacant dark red eyes, wearing an elegant dark red vintage dress, holding a glowing red oil-paper umbrella. Her figure appears slightly translucent.",
        "prop": "her glowing red oil-paper umbrella",
        "prop_desc": "a detailed vintage red oil-paper umbrella that glows with a warm, soft scarlet radiance",
        "scene": "a modern metropolis street at night under heavy rain, with towering skyscrapers covered in vibrant blue and cyan neon advertisements reflecting on the wet asphalt and puddles",
        "outfit_alt": "a dark blue modern raincoat over a simple black dress, and red boots, while holding her red umbrella",
        "colors": "crimson red, deep night black, neon blue, cyan glow, misty white",
        "materials": "vintage red silk umbrella paper, dark red dress fabric, wet asphalt, glowing neon light",
        "damage": "her vintage red dress is torn at the hem and scuffed, and her hair is slightly messy. For the heavily damaged state, she stands next to a shattered glass storefront, her dress tattered, and her red oil-paper umbrella's scarlet glow is dim and flickering."
    },
    "char_0037_stele_pathfinder": {
        "name": "The Stele Rubbing Pathfinder (残碑拓荒人)",
        "features": "handsome young East Asian scholar with silver-and-black hair tied up in a simple wooden hairpin, wearing a simple gray-and-white scholar robe smudged with ink stains, carrying a rustic leather scroll-case on his back.",
        "prop": "his giant iron calligraphy brush",
        "prop_desc": "a giant iron calligraphy brush as tall as himself, with its bristles dripping with glowing black ink, and a rustic leather scroll-case",
        "scene": "a desolate ancient ruined field of massive wind-eroded crumbling stone steles and monuments under an overcast sky with sun rays piercing through heavy gray clouds",
        "outfit_alt": "a fitted black martial artist robe with leather arm guards, carrying his giant iron brush on his back",
        "colors": "ink black, scholar robe white, iron grey, crumbling stone beige, sky grey",
        "materials": "wide-sleeved linen fabric, polished iron brush body, leather scroll-case, ancient weathered stone",
        "damage": "his gray-and-white scholar robe is torn and tattered, with thick dust and ink smudges on his face and chest. For the heavily damaged state, he stands defiantly in the ruins next to a shattered stone monument, his robe shredded, and his giant iron brush cracked and worn."
    },
    "char_0040_fungal_apothecary": {
        "name": "The Fungal Grove Apothecary (蕈林秘医)",
        "features": "beautiful young elf woman with translucent pale skin and glowing mint-green eyes. She wears an elegant dark-green herbalist robe woven with moss and vines, and a unique hood shaped like a giant glowing, semi-translucent purple mushroom cap.",
        "prop": "her wooden mortar and pestle and glowing glass flasks",
        "prop_desc": "a wooden mortar and pestle, and several glowing glass flasks filled with colorful spores",
        "scene": "a mystical dark cave filled with massive glowing bioluminescent mushrooms and drifting cyan spores",
        "outfit_alt": "an elegant light green herbalist gown with a floral crown instead of a mushroom hood, and a wicker basket on her back",
        "colors": "glowing purple, mint green, moss dark green, cyan glow, leather brown",
        "materials": "woven moss and vine fabric, semi-translucent glowing mushroom skin, polished wood mortar, glass flasks",
        "damage": "her dark-green robe is torn and stained with colorful glowing fungal juices, and her mushroom hood is slightly chipped. For the heavily damaged state, she stands in front of a shattered giant mushroom stalk, her robe heavily tattered, and her glass flasks broken, leaving glowing spore dust swirling around her."
    },
    "char_0041_book_wraith": {
        "name": "The Bound Book-Wraith (禁忌书魂)",
        "features": "ethereal, semi-translucent spectral figure floating in the air, wearing tattered, dusty dark archivist robes with a deep hood obscuring its face, showing only two glowing golden eyes. Swirling in a chaotic vortex around its body are hundreds of floating, aged parchment book pages.",
        "prop": "hundreds of floating book pages and an ancient locked chain",
        "prop_desc": "hundreds of floating parchment pages inscribed with glowing gold and blue runes, and an ancient rusted lock chain around its waist",
        "scene": "a massive, cavernous ancient library vault with towering dark wooden bookshelves stretching into the shadows and dust motes catching shafts of magical light",
        "outfit_alt": "a dark blue spectral priest robe with silver embroidery and a glowing open grimoire floating in front of it",
        "colors": "magical blue, glowing gold, parchment beige, dusty dark grey, ink black",
        "materials": "semi-translucent spectral energy, tattered linen fabric, aged parchment paper, rusted iron chains",
        "damage": "its dark robes are heavily shredded, and the floating book pages around its body are singed and torn, with flickering spectral light. For the heavily damaged state, it floats next to a collapsed burning bookshelf, its robes mostly disintegrated into smoke, and its pages scattering into ashes in the air."
    },
    "char_0042_radio_host": {
        "name": "The Midnight Radio Host (午夜电台主播)",
        "features": "streetwear girl with an oversized black windbreaker, whose head is replaced by a vintage retro cassette tape-player helmet with spinning reels glowing with radioactive neon green and hot pink light inside, glass visor displaying two green soundwave lines as eyes",
        "prop": "a heavy vintage silver condenser microphone and a glowing neon-pink cassette tape",
        "prop_desc": "a heavy vintage silver condenser microphone in her hand, and a glowing neon-pink cassette tape in the other",
        "scene": "a cozy dimly lit radio booth surrounded by vinyl records, glowing audio mixers, and soundproofing foam, window showing a dark misty city with blue and warm amber neon glows",
        "outfit_alt": "a reflective neon-green oversized hoodie with street art prints and headphones resting around her neck",
        "colors": "radioactive neon green, hot pink, charcoal black, neon blue, warm amber",
        "materials": "matte black plastic casing of helmet, glossy glass visor, nylon windbreaker fabric, silver metal mic, spinning plastic tape reels",
        "damage": "her helmet casing is cracked with escaping neon light and small sparks, and her nylon jacket is torn. For the heavily damaged state, her tape helmet is partially broken revealing inner circuit boards, and the cassette tape is shattered on the floor, surrounded by flickering sparks."
    }
,
        "char_0043_spectral_glitch": {
        "name": "The Frequency Wraith (频段噬灵)",
        "features": "glitching spectral demon without a face, whose head is a floating distorted analog TV screen displaying black-and-white static noise and red glowing 'ERROR' text, body composed of flashing neon-pink and cyan digital glitch lines",
        "prop": "floating broken circuit boards and copper cables",
        "prop_desc": "floating rusted copper cables wrapped around its arms, and several broken PCB motherboards floating in the air",
        "scene": "a rainy, dark city alleyway at night with glowing wet pavement and neon reflections, digital noise and particles drifting in the air",
        "outfit_alt": "a dark digital vortex of pixelated noise and glowing matrix code instead of cables",
        "colors": "neon pink, neon cyan, static black and white, warning red, copper orange",
        "materials": "glass CRT screen casing, pixelated neon glitch lines, rusted copper wire, broken green PCB plates",
        "damage": "its analog screen is shattered with sparks flying, and its glitching body is fragmenting into loose pixel dust. For the heavily damaged state, its head is completely broken exposing inner glass shards, and it floats next to a sparking electricity transformer box, its cable limbs disconnected."
    },
    "char_0043_blade_wraith": {
        "name": "The Soul-Devouring Blade-Wraith (噬魂刀魅)",
        "features": "shattered ancient bronze curved saber floating in the air, glowing with sinister blood-red veins of light, with a tall shadowy phantom of a general in dilapidated black iron armor emerging from the hilt, two chilling green flames glowing inside its helmet as eyes",
        "prop": "swirling torn white talisman bands and broken weapons",
        "prop_desc": "swirling torn white talisman paper bands with gold scriptures, and a devastated battlefield with broken weapons scattered around",
        "scene": "a devastated ancient battlefield under a blood-red sunset with ruined stone walls and dark smoke",
        "outfit_alt": "a dark vortex of shattered metal blades and black aura instead of the general phantom",
        "colors": "crimson red, dark grey, glowing green, gold scripture yellow, iron black",
        "materials": "rusted ancient bronze, glowing magma-like veins, semi-translucent smoke armor, glowing energy flame",
        "damage": "its floating bronze saber is heavily cracked with bright golden light leaking from within, and the general phantom is dissolving into dark ash. For the heavily damaged state, the saber is broken into three floating fragments, the armored shadow is half disintegrated, and it floats next to a ruined war banner."
    },
    "char_0044_abyssal_dread": {
        "name": "The Abyssal Dread-Fiend (深渊煞魔)",
        "features": "terrifying spectral demon without a face, whose head is a floating burning sphere of dark purple and black malice flames with two glowing scarlet eyes, body made of jagged black basalt bone plates",
        "prop": "broken golden sealing chains and sharp obsidian claws",
        "prop_desc": "broken golden chains with faint glowing ancient runes wrapped around its skeletal arms, and sharp black obsidian claws dripping purple mist",
        "scene": "ruins of a broken ancient Chinese great wall under a pale full moon at night, dark swirling fog and purple sparks in the air",
        "outfit_alt": "a torn, ragged cape made of dark ghostly feathers and flowing black smoke",
        "colors": "deep purple, pitch black, glowing scarlet, warning gold, bone grey",
        "materials": "burning purple flames, jagged black basalt plates, obsidian crystals, metallic gold chains",
        "damage": "its purple head flame is faint and dim, and the golden talisman chains wrapped around its body are glowing intensely, cracking its dark stone armor with beams of golden light. For the heavily damaged state, it stands next to a shattered stone monument, its skeletal arm is partially shattered into basalt debris, and its chest core is exposed showing bright gold seals."
    },
    "char_0045_thousand_faces": {
        "name": "The Thousand-Faced Skin-Wraith (千面皮魔)",
        "features": "ethereal faceless female figure in layered tattered semi-translucent white hemp robes, her face is a patchwork of stitched human face skins sewn with silver thread",
        "prop": "long bone needle and glowing silver thread",
        "prop_desc": "a long slender bone needle threaded with glowing silver thread, and a massive worn ancient Chinese silk scroll unrolling horizontally with ink-wash drawings of screaming human faces",
        "scene": "desolate ruins of a bamboo forest under a dark red sky with paper talismans and autumn leaves scattering in the wind",
        "outfit_alt": "a dark crimson traditional bridal gown with a tattered red veil obscuring her face",
        "colors": "pure white, ink black, eerie purple, blood red, silver",
        "materials": "tattered hemp cloth, worn ancient silk scroll, polished bone needle, glowing ethereal thread",
        "damage": "her white robes are heavily torn and stained with dark blood, and the silk scroll behind her is burning and shredding at the edges. For the heavily damaged state, she clutches her face as the stitched skins peel off, her white hemp robe is shredded, and the scroll is torn in half with screaming souls escaping in black smoke."
    },
    "char_0046_bone_spider": {
        "name": "The Bone-Corroding Broodmother (蚀骨蛛后)",
        "features": "colossal spider monster with glossy black obsidian shell, a distinct white human skull pattern on its back, and dozens of glowing green eyes lining its head",
        "prop": "thick sticky bone-silk web and acid-dripping mandibles",
        "prop_desc": "a massive spiderweb woven from thick sticky green silk and human bones, and sharp obsidian mandibles dripping glowing green acid",
        "scene": "a dark subterranean cavern under ruined stone walls with glowing green mineral veins and poisonous purple mist",
        "outfit_alt": "a heavy volcanic iron plate armor fused into its obsidian shell with volcanic embers drifting around",
        "colors": "obsidian black, toxic green, bone white, poison purple, basalt grey",
        "materials": "glossy obsidian chitin shell, sticky bioluminescent green silk, calcified bones, acidic liquid",
        "damage": "its obsidian shell is cracked with glowing green fluid leaking out, and several of its spider legs are broken. For the heavily damaged state, it stands inside a shattered cavern, its abdomen is cracked open with toxic smoke escaping, and it crawls on a ruined web with broken swords scattered around."
    },
    "char_0047_bone_pipa_wraith": {
        "name": "The Bone-Pipa Wraith (骨琶怨姬)",
        "features": "beautiful but cold-faced blindfolded young female musician with long flowing white hair, wearing an elegant flowy dark-purple and ink-black traditional Chinese silk robe, with a white translucent silk ribbon covering her eyes",
        "prop": "her ivory bone pipa with glowing purple strings",
        "prop_desc": "a beautifully crafted traditional Chinese pipa made of white ivory and bone, with glowing purple energy strings releasing soundwave ripples",
        "scene": "a ruined traditional Chinese stone pavilion under a large dark red moon at night, surrounded by withered red spider lily flowers and floating purple embers",
        "outfit_alt": "a tattered dark-crimson wedding gown with a matching tattered red veil floating around her head",
        "colors": "ink black, glowing purple, bone white, dark red, charcoal grey",
        "materials": "flowing translucent silk, polished ivory bone, ancient weathered stone, glowing energy strings",
        "damage": "her dark-purple robe is torn and frayed, and her white blindfold is partially torn, revealing faint purple glow from her closed eyes. For the heavily damaged state, she stands next to a shattered stone column, her pipa's body cracked and its purple strings broken, releasing chaotic glowing shockwaves into the air."
    },
    "char_0048_withered_daoist": {
        "name": "The Withered Wood Daoist (枯木妖道)",
        "features": "withered and thin ancient Chinese Daoist priest wearing a tattered and burnt dark purple robe, his face hidden behind a sinister wooden mask carved from lightning-struck wood with only one glowing purple eye visible",
        "prop": "his decaying peach-wood sword and floating black talismans",
        "prop_desc": "a decaying dark peach-wood sword dripping with thick black corrosion fluid, surrounded by dozens of floating black paper talismans with glowing purple scriptures",
        "scene": "a scorched and dead withered forest under dark thunderclouds, with purple lightning flashing in the heavy mist and broken swords scattered on the ground",
        "outfit_alt": "a heavy dark iron scale armor combined with tattered Daoist robes and a long tattered black cloak",
        "colors": "deep purple, charcoal black, glowing warning purple, wood brown, toxic green",
        "materials": "rough tattered linen cloth, carbonized lightning-struck wood, decaying rotting wood, glowing magical paper",
        "damage": "his dark purple robe is heavily scorched with burn holes, and his wooden mask is cracked showing a withered mummified face underneath. For the heavily damaged state, his peach-wood sword is broken in half, and thick black toxic mist is escaping from his body as he stands in a field of ashes."
        },
    "char_0049_frostleaf_illusionist": {
        "name": "The Frostleaf Illusionist (霜叶幻术师)",
        "features": "graceful cold winter elf female, pale snow-like skin, long pointed elf ears, flowing silver-blue hair, elegant flowy blue and white gradient robe covered in frost",
        "prop": "large glowing magical polyhedron ice crystal orb levitating above her hands",
        "prop_desc": "a large glowing magical polyhedron ice crystal orb levitating above her hands, refracting colorful holographic illusions",
        "scene": "breathtaking winter elven forest covered in thick white snow, glowing blue bioluminescent flora, gentle falling snow",
        "outfit_alt": "elegant light silver silk dress with blue frosty lace and crystalline accessories",
        "colors": "pure white, ice blue, silver, holographic rainbow refraction",
        "materials": "thin silk freezing into frost, ice crystals",
        "damage": "her elegant robe is torn with frost melting into water droplets, and the ice crystal orb is cracked and shattered into floating icy shards, surrounded by fading illusions."
    },
    "char_0050_thorn_executioner": {
        "name": "The Thorn Executioner (荆棘行刑者)",
        "features": "tall muscular fierce dark wood elf male warrior, tanned bronze skin, long pointed elf ears, half-face mask woven from sharp black thorny briars covering his lower face, fierce amber eyes",
        "prop": "massive thick whip made of cursed thorny briars dripping with glowing green poison",
        "prop_desc": "a massive thick whip made of cursed thorny briars dripping with glowing green poison",
        "scene": "gloomy dark deep elven forest filled with twisting massive tree roots and poisonous fog",
        "outfit_alt": "rugged heavy armor made of thick leather intertwined with dark green and blood-red magical vines, sharp wooden pauldrons",
        "colors": "dark green, blood red, dead wood black, toxic neon green",
        "materials": "heavy rugged leather, magical thorny vines, sharp wood splinters",
        "damage": "his heavy vine armor is ripped open with bleeding gashes, his half-face briar mask is broken revealing his gritting teeth, and the cursed thorny whip is snapped in half, dripping toxic green blood on the forest floor."
    },
    "char_0051_moonphase_templar": {
        "name": "The Moonphase Templar (月影重装骑士)",
        "features": "tall and majestic East Asian female moon elf knight, delicate refined East Asian facial features, soft almond eyes, smooth pale porcelain skin, long flowing silver hair, clad in ornate glowing silver-and-white plate armor crafted from moonstone, no Caucasian features",
        "prop": "massive semi-translucent shield shaped like a crescent moon",
        "prop_desc": "a massive semi-translucent shield shaped like a crescent moon, radiating a holy protective silver aurora",
        "scene": "mystical elven forest at night, with bright moonlight filtering through giant ancient leaf canopies, lighting up glowing blue flora and floating luminescent spores",
        "outfit_alt": "elegant silver silk tunic with leather boots and moon phase engravings",
        "colors": "silver white, moon white, deep velvet blue, glowing cyan-blue",
        "materials": "glowing moonstone, polished silver plates, velvet cloth",
        "damage": "her ornate plate armor is deeply cracked and dented with sparks of silver moonlight leaking out, her crescent shield is split down the center with its protective aurora flickering erratically, and she stands wounded but defiant on a field of crushed forest leaves."
    },
    "char_0052_thunder_talismanist": {
        "name": "The Thunder Talismanist (雷劫画符师)",
        "features": "young energetic Chinese female Taoist talisman cultivator, short messy black hair in double-mytail tied with yellow ribbon, bright yellow eyes, carrying a large dark weathered lightning-struck wooden canvas on her back",
        "prop": "calligraphy brush writing glowing yellow paper talismans in mid-air",
        "prop_desc": "glowing yellow paper talismans with purple electrical arcs floating in mid-air",
        "scene": "ruined ancient courtyard under dark thunderclouds and heavy rain with purple lightning",
        "outfit_alt": "casual lightweight yellow and black crop-top and shorts with Taoist patterns",
        "colors": "bright yellow, charcoal black, purple electric blue, charred wood black",
        "materials": "charred lightning-struck wood, magical paper talismans, gold calligraphy ink",
        "damage": "her yellow Taoist robe is heavily scorched with burn holes, her lightning-struck wood canvas is split down the middle, and she grits her teeth with sparks of wild purple electricity escaping uncontrollably from her body."
        },
    "char_0053_venom_assassin": {
        "name": "The Poison-Ivy Assassin (毒藤魅影)",
        "features": "alluring deadly female wood elf assassin, tanned bronze skin, long flowing messy black hair, voluptuous curvy body, dark green enchanting eyes",
        "prop": "slithering fluorescent green venomous vines intertwined around her fingers",
        "prop_desc": "slithering fluorescent green venomous vines dripping green toxic droplets",
        "scene": "dark poisonous elven swamp, glowing green toxic spores floating, twisting roots",
        "outfit_alt": "seductive emerald silk evening dress with thorned vine straps",
        "colors": "dark emerald green, toxic neon green, dark crimson red, bronze gold",
        "materials": "tight thorned leather, translucent emerald silk, glowing venomous vines",
        "damage": "her tight red leather outfit is deeply slashed with poison gas leaking, her black hair is damp and wild, her glowing vines are severed and bleeding toxic sap, standing wounded on a swamp rock."
    },
    "char_0054_petal_dancer": {
        "name": "The Blossom Dancer (繁花舞姬)",
        "features": "ethereal gorgeous female flower elf dancer, fair radiant skin, long flowing pastel-pink hair adorned with blossoms, bright emerald green eyes",
        "prop": "whirlwind of sharp glowing pink flower petals floating in the air",
        "prop_desc": "a whirlwind of sharp glowing pink flower petals floating and dancing in mid-air",
        "scene": "magical sunlit elven forest clearing filled with blossoming flowers, golden sunbeams piercing ancient canopy",
        "outfit_alt": "elegant floral festival silk robe with flower crown and barefoot ankle bells",
        "colors": "pastel pink, blossom white, fresh leaf green, sunlit gold",
        "materials": "translucent gossamer petals, soft green silk ribbons, glowing pollen spores",
        "damage": "her translucent petal dress is torn and frayed with scattered rose petals, her pink hair is disheveled, and she sits gracefully on a bed of fallen leaves with a whirlwind of fading pink petals."
    },
    "char_0055_vermilion_sovereign": {
        "name": "The Vermilion Sovereign (朱雀天尊·凤仪)",
        "features": "majestic gorgeous East Asian empress goddess with noble refined features, sharp almond eyes, radiant skin, long black hair accented with glowing golden feather strands, wearing a crimson-and-gold phoenix-feather gossamer silk robe with gold chest armor",
        "prop": "swirling sacred solar flames and a massive glowing golden-red phoenix aura soaring behind her",
        "prop_desc": "swirling sacred solar flames and glowing crimson-and-gold phoenix feather talismans",
        "scene": "grand celestial imperial palace floating above a dramatic sunset cloud sea, with golden light beams and glowing fire sparks",
        "outfit_alt": "regal ceremonial crimson silk empress gown with an imperial phoenix crown and flowing gold-embroidered train",
        "colors": "crimson red, radiant gold, solar flame orange, cinnabar, imperial gold",
        "materials": "phoenix feather gossamer silk, engraved polished gold armor, translucent flame veil, glowing fiery plumes",
        "damage": "her crimson robe is scorched and torn with fire embers fading, golden armor cracked, standing proudly with flickering solar flame sparks on a broken celestial stone altar."
    },
    "char_0056_puppet_artificer": {
        "name": "The Puppet Artificer (千机偃灵·墨巧)",
        "features": "clever cute young East Asian female puppet master, porcelain skin, dark brown twin-tails with small bronze gears and red ribbons, stylish asymmetrical black-and-crimson short cheongsam, ornate bronze mechanical puppet glove on one arm",
        "prop": "glowing blue spirit strings controlling floating wooden clockwork puppets and spinning bronze gear blades",
        "prop_desc": "intricate wooden clockwork puppets, spinning bronze gear blades, and glowing blue spirit strings",
        "scene": "traditional ancient workshop filled with blueprints, wooden scrolls, bronze gears, and mechanical puppet components",
        "outfit_alt": "stylish steampunk scholar mechanic coat with brass goggles and leather tool apron",
        "colors": "ink black, crimson red, antique bronze gold, spirit cyan blue, leather brown",
        "materials": "polished bronze gears, carved seasoned wood, crimson silk cheongsam, glowing ethereal blue thread",
        "damage": "her short cheongsam is torn at the seams, her bronze glove sparks with blue electricity, wooden puppets are broken into pieces on the floor, sitting tiredly next to scattered gear fragments."
    },
    "char_0057_azure_sword_spirit": {
        "name": "The Azure Sword Spirit (青霄剑灵·流光)",
        "features": "ethereal gorgeous East Asian female sword spirit, fair porcelain skin, sharp cold cyan-blue eyes with sword glint, long high ponytail hair fading from ink-black to translucent azure-blue with antique jade hairpin, wearing sleek azure-and-white swordmaster silk tunic with sharp blade-like hem",
        "prop": "a legendary ancient glowing cyan-blue crystalline broadsword, surrounded by 8 floating semi-transparent azure flying daggers arranged in a halo behind her",
        "prop_desc": "a legendary azure crystalline broadsword and 8 floating glowing flying daggers",
        "scene": "floating ancient sword grave mountain pavilion amidst swirling clouds and soaring energy sword-auras under blue daylight",
        "outfit_alt": "regal immortal sword deity silk dress with flowing ribbons and engraved silver vambraces",
        "colors": "azure blue, pure white, jade green, blade silver, antique gold",
        "materials": "crystal sword blades, translucent energy veil, embroidered white silk, polished jade",
        "damage": "her white tunic is cut and frayed with fading azure sword energy, standing proudly holding her cracked blade in a rain of falling spirit sword fragments."
    },
    "char_0058_nether_dragon_shaman": {
        "name": "The Nether Dragon Shaman (九幽龙巫·刹夜)",
        "features": "handsome mysterious young East Asian dragon shaman, slender silhouette, black obsidian dragon horns on forehead, heterochromia eyes (left cyan blue, right dark gold), cinnabar dragon tattoo on eye corner, wearing dark embroidered Miao-style shaman robes with elaborate antique silver dragon neck torcs and bone beads",
        "prop": "carved ancient dragon-bone shaman staff topped with glowing soul orb, with a translucent ethereal black dragon spirit coiling around him and glowing spectral butterflies",
        "prop_desc": "a carved dragon-bone shaman staff, coiling ethereal dragon spirit, and glowing spectral butterflies",
        "scene": "misty ancient tribal dragon shrine in deep bamboo forest at twilight, surrounded by glowing blue spirit lanterns and mysterious carved totems",
        "outfit_alt": "regal dragon priest ceremonial feathered cape with grand silver crown and ceremonial daggers",
        "colors": "pitch black, spectral cyan blue, antique Miao silver, phantom purple, cinnabar red",
        "materials": "textured tribal embroidered fabric, antique silver, polished dragon bone, glowing spirit flame",
        "damage": "his embroidered robes are torn with dragon spirit fading into smoke, dragon horn slightly chipped, resting against a broken dragon totem with glowing spectral embers."
    },
    "char_0059_sword_spirit_prime": {
        "name": "The Jade-Water Celestial Sword Spirit (碧水仙剑·灵漪)",
        "features": "transcendent ethereal young female humanoid water-sword spirit avatar, translucent pale jade-crystalline skin, glowing luminous emerald-aqua water-sword droplet rune on forehead, tranquil luminous aqua-teal eyes glowing with liquid blade intent, floating weightlessly barefoot with spirit toes stepping on glowing water lotus ripples, long waist-length liquid crystalline hair floating weightlessly like clear waterfall shifting from emerald jade to translucent aqua-cyan, secured with carved antique lotus jade sword hairpin, wearing gossamer translucent aquatic silk robes with water-ripple hemlines, floating ribbons of pure water sword qi, and carved jade-silver vambraces",
        "prop": "a colossal ancient primordial Jade-Water Celestial God-Sword (碧水仙剑) forged from deep-sea spirit jade and cyan crystal pulsing with luminous aquatic runes floating behind her, her hand pinching a Taoist sword hand seal commanding a revolving halo of 8 translucent liquid jade flying sword blades",
        "prop_desc": "a colossal floating primordial Jade-Water Celestial Sword and 8 revolving translucent aquatic energy flying blades",
        "scene": "ethereal celestial jade-water domain atop tranquil reflection lake amidst misty emerald lotus mountains, colossal ancient water-sword stele monuments, and swirling ribbons of glowing aquatic sword qi",
        "outfit_alt": "divine celestial water-spirit feather gossamer dress with floating crystal water-blade wings and radiant emerald halo",
        "colors": "translucent emerald jade, luminous aqua teal, celestial crystal cyan, pure pearl white, shimmering aquatic gold",
        "materials": "translucent aquatic sword crystal, glowing water gossamer silk, ancient spirit jade, celestial silver metal",
        "damage": "her translucent gossamer robes have delicate battle-tested fraying with dissolving emerald water droplets and sparkling light particles, standing steadfast with her colossal jade-water sword embedded into cracked crystal ground amidst floating aquatic blade shards."
    },
    "char_0060_solar_warlord": {
        "name": "The Solar Warlord (炽阳神将·天罡)",
        "features": "majestic powerful young East Asian solar celestial general, handsome resolute facial features, glowing pure-gold sun flame sigil inscribed on forehead, blazing golden-amber eyes glowing with divine solar fire, long jet-black hair tied in an ornate golden crown with fiery red accents, wearing magnificent radiant golden-and-crimson dragon celestial plate armor with fiery silk battle mantle and floating solar light ribbons",
        "prop": "a massive ancient solar celestial polearm halberd (九转炎阳破军戟) forged from celestial gold and sun-core meteorite dripping with swirling sacred golden flames, and a revolving divine solar halo of 9 radiant miniature suns floating behind his back",
        "prop_desc": "a colossal glowing pure-gold solar halberd and a revolving halo of 9 miniature flaming suns",
        "scene": "grand celestial golden palace platform above majestic sea of sunlit golden clouds, ancient monumental solar bronze pillars, and soaring fiery dragons of pure light",
        "outfit_alt": "regal imperial solar warlord grand ceremonial armor with celestial gold dragon pauldrons and radiant sun-crest helmet",
        "colors": "radiant celestial gold, blazing crimson red, celestial solar white, obsidian black, burning sun-amber",
        "materials": "sun-forged celestial gold metal, radiant solar silk, ancient meteorite crystal, glowing golden flame energy",
        "damage": "his celestial golden plate armor is battle-tested with scorched edge scratches and glowing golden sparks dissipating like embers, standing unyielding holding his cracked solar halberd driven into the ground amidst floating burning sun shards."
    },
    "char_0061_nether_moon_arbiter": {
        "name": "The Nether Moon Arbiter (幽月司命·忘川)",
        "features": "ethereal mysterious and breathtaking young East Asian nether goddess, pale translucent porcelain skin, glowing silver crescent moon rune on forehead, tranquil mesmerizing silver-cyan luminous eyes, floor-length flowing silvery-white moonlight hair adorned with carved white jade spider lily hairpins and silver bells, wearing layered flowing translucent gossamer robes of midnight black and frost-silver moonlight with floating ribbons of spectral water mist",
        "prop": "holding a delicate antique 9-petaled pure white jade lotus soul lantern (九品忘川引魂灯) emitting cold celestial cyan ghost flames, surrounded by swirling ghostly water ripples and floating crimson red spider lily flower petals",
        "prop_desc": "an intricate carved white jade lotus soul lantern glowing with cyan ghost flame and drifting crimson spider lilies",
        "scene": "ethereal tranquil Netherworld River (忘川) reflection domain at midnight, glowing silver moon overhead, misty dark waters blooming with endless radiant red spider lilies",
        "outfit_alt": "divine high priestess ceremonial moon-gossamer gown with embroidered silver constellations and floating midnight veil",
        "colors": "frost moonlight silver, midnight ink black, ethereal cyan blue, vivid cinnabar spider-lily red, pale jade white",
        "materials": "translucent moonlight gossamer silk, pure white nephrite jade, antique silver filigree, glowing cold spirit fire",
        "damage": "her translucent midnight robes have delicate frayed hemlines with drifting cyan soul sparks, holding her weathered jade lotus lantern amidst scattered red spider lily petals and cracked crystal water ripples."
    }
}

def expand_character_plan(plan, char_id, char_name):
    existing_types = {item["img_type"] for item in plan}
    if len(existing_types) == 18:
        return plan
        
    lock = LOCKS.get(char_id)
    if not lock:
        return plan
        
    expanded = list(plan)
    
    # Character Lock setup based on guidelines
    if char_id == 'char_0036_red_umbrella_entity':
        gender_age = "young woman, ethereal and mysterious presence, 19-year appearance"
        body_shape = "slender and delicate silhouette, elegant posture"
        face = "pale delicate face, gentle but vacant dark red eyes, serene expression"
        hair = "long flowing black hair cascading to her waist"
        eyes = "gentle but vacant dark red eyes"
        outfit = "elegant vintage dark crimson silk dress with subtle glowing spider lily patterns embroidered on the hem"
        accessories_weapon = "glowing red oil-paper umbrella casting warm scarlet light"
        fixed_traits = "long black hair, vacant dark red eyes, vintage dark crimson dress, glowing red oil-paper umbrella"
        style_desc = "Eastern fantasy character concept art"
    elif char_id == 'char_0037_stele_pathfinder':
        gender_age = "young man, handsome, scholarly and calm presence"
        body_shape = "slender, tall, graceful scholarly posture"
        face = "handsome refined features, focused expression, smudged with ink stains"
        hair = "silver-and-black hair tied up in a simple wooden hairpin"
        eyes = "focused dark eyes"
        outfit = "simple gray-and-white scholar robe smudged with ink stains, carrying a rustic leather scroll-case on his back"
        accessories_weapon = "giant iron calligraphy brush as tall as himself dripping with glowing black ink, and a leather scroll-case"
        fixed_traits = "silver-and-black hair in wooden hairpin, gray-and-white robe, giant iron calligraphy brush, leather scroll-case"
        style_desc = "Eastern fantasy character concept art"
    elif char_id == 'char_0040_fungal_apothecary':
        gender_age = "young elf woman, beautiful and mysterious presence"
        body_shape = "slender build, delicate posture, light footed"
        face = "translucent pale skin, glowing mint-green eyes, calm expression"
        hair = "long light-blue glowing hair, slightly wavy"
        eyes = "glowing mint-green eyes"
        outfit = "elegant dark-green herbalist robe woven with moss and vines, and a unique hood shaped like a giant glowing, semi-translucent purple mushroom cap"
        accessories_weapon = "wooden mortar and pestle, glowing glass flasks filled with colorful spores"
        fixed_traits = "semi-translucent mushroom cap hood, glowing mint-green eyes, long light-blue hair, wooden mortar"
        style_desc = "modern forest fantasy character concept art"
    elif char_id == 'char_0041_book_wraith':
        gender_age = "ancient ethereal presence, no defined gender"
        body_shape = "semi-translucent floating spectral form, no solid feet"
        face = "dark shadow silhouette obscured under a deep hood, showing only two glowing golden eyes"
        hair = "none, completely obscured by hood"
        eyes = "glowing golden eyes"
        outfit = "tattered, dusty dark archivist robes with a deep hood, with a rusted iron chain around its waist"
        accessories_weapon = "hundreds of floating aged parchment pages inscribed with glowing gold and blue runes"
        fixed_traits = "floating spectral form, deep hood with golden eyes, swirling book pages, magical runes"
        style_desc = "epic fantasy character concept art"
    elif char_id == 'char_0042_radio_host':
        gender_age = "young woman, cool streetwear aesthetic"
        body_shape = "tall slender silhouette, slouching lazily"
        face = "a vintage black cassette tape-player helmet with spinning reels glowing with radioactive neon green and hot pink light, glass visor displaying two green soundwave lines as eyes"
        hair = "no hair, helmet casing with two extendable metal antennas on the sides"
        eyes = "two glowing green soundwave lines displayed on the glass visor of her helmet"
        outfit = "oversized black nylon windbreaker jacket over a radioactive neon-green hoodie, neon striped sneakers"
        accessories_weapon = "a vintage silver condenser microphone, a glowing neon-pink cassette tape, and headphones resting around her neck"
        fixed_traits = "cassette tape helmet, spinning reels glowing green/pink, green soundwave eyes, oversized black windbreaker jacket, vintage microphone"
        style_desc = "modern cyberpunk urban mystery concept art"
    elif char_id == 'char_0043_blade_wraith':
        gender_age = "ancient saber spirit, terrifying and dark presence"
        body_shape = "shadowy general phantom emerging from hilt, tall and dilapidated"
        face = "no physical face, helmet deep interior showing two glowing green flames as eyes"
        hair = "no hair, rolling black smoke from helmet seams"
        eyes = "two glowing green flames inside the helmet"
        outfit = "dilapidated black iron armor plates covered in rust and scratches"
        accessories_weapon = "floating shattered bronze curved saber (Chinese dao) glowing with crimson blood veins, and swirling white talisman bands. Note: the weapon is strictly a curved single-edged saber, not a straight sword."
        fixed_traits = "floating broken curved bronze saber, general shadow, glowing green eyes, swirling talisman bands"
        style_desc = "Eastern fantasy ink-wash character concept art"
    elif char_id == 'char_0044_abyssal_dread':
        gender_age = "ancient demonic entity, terrifying and dark presence"
        body_shape = "tall withered silhouette with elongated limbs, basalt bone structures"
        face = "no physical face, a floating sphere of dark purple and black malice flames with two glowing scarlet eyes"
        hair = "no hair, rolling dark purple flames and black mist"
        eyes = "glowing scarlet eyes shining from within purple flames"
        outfit = "broken black basalt bone armor, a ragged cape made of dark ghostly feathers and smoke"
        accessories_weapon = "broken golden sealing chains with glowing runes, and sharp obsidian claws dripping purple mist"
        fixed_traits = "purple malice flames head, glowing scarlet eyes, broken golden sealing chains, black basalt bone armor"
        style_desc = "Eastern fantasy ink-wash character concept art"
    elif char_id == 'char_0045_thousand_faces':
        gender_age = "ancient诡灵 spirit, terrifying and eerie female presence"
        body_shape = "floating slender silhouette, rigid wooden puppet-like limbs"
        face = "no physical face, a patchwork of stitched human face skins with silver thread"
        hair = "extremely long, messy, disheveled pale white hair"
        eyes = "no eyes, faint purple-red light glowing from the stitches"
        outfit = "layered tattered white hemp robes tied with a straw rope"
        accessories_weapon = "floating massive Chinese ink-wash scroll, bone needle, and glowing silver thread"
        fixed_traits = "white hemp robe, stitched face skins, massive ink scroll, bone needle"
        style_desc = "Eastern fantasy ink-wash character concept art"
    elif char_id == 'char_0046_bone_spider':
        gender_age = "ancient toxic beast, colossal and terrifying presence"
        body_shape = "colossal obsidian spider body with eight sharp hook-like legs"
        face = "spider head with dozens of glowing green eyes"
        hair = "no hair, volcanic ash smoke rising from back shell"
        eyes = "dozens of glowing green eyes"
        outfit = "cracked glossy black obsidian shell with a human skull pattern on its back"
        accessories_weapon = "thick sticky green silk web, bone fragments, acid-dripping mandibles"
        fixed_traits = "obsidian shell, skull pattern on back, glowing green eyes, glowing green abdomen"
        style_desc = "Eastern fantasy ink-wash character concept art"
    elif char_id == 'char_0047_bone_pipa_wraith':
        gender_age = "young woman, cold and tragic spectral presence"
        body_shape = "slender build, floating posture, flowy lines"
        face = "beautiful but cold-faced pale face, blindfolded with a white ribbon"
        hair = "long flowing white hair cascading down her back"
        eyes = "closed eyes obscured by a translucent white silk ribbon"
        outfit = "elegant flowy traditional Chinese silk robes in dark purple and ink black"
        accessories_weapon = "ivory and bone traditional Chinese pipa (lute) with glowing purple strings"
        fixed_traits = "blindfold white ribbon, long white hair, dark purple silk robes, ivory bone pipa"
        style_desc = "Eastern fantasy ink-wash character concept art"
    elif char_id == 'char_0048_withered_daoist':
        gender_age = "withered and thin ancient man, eerie Daoist presence"
        body_shape = "withered, thin, and skeletal posture, slightly hunched"
        face = "hidden behind a dark carbonized wooden mask with one glowing purple eye visible"
        hair = "messy grey-black hair tied in a loose topknot"
        eyes = "one glowing purple eye visible through the mask"
        outfit = "tattered, burnt, and dirty dark purple ancient Daoist robes"
        accessories_weapon = "decaying dark peach-wood sword dripping black liquid, and floating black paper talismans"
        fixed_traits = "wooden mask, tattered dark purple robes, decaying peach-wood sword, floating black talismans"
        style_desc = "Eastern fantasy ink-wash character concept art"
    elif char_id == 'char_0055_vermilion_sovereign':
        gender_age = "young woman, majestic and drop-dead gorgeous empress goddess"
        body_shape = "tall slender silhouette, regal and commanding posture"
        face = "noble refined East Asian features, sharp almond eyes, golden phoenix mark on forehead, majestic expression"
        hair = "long flowing black hair cascading to her waist with glowing golden feather strands and phoenix hairpin"
        eyes = "radiant golden-red phoenix eyes, sharp and authoritative"
        outfit = "ultra-luxurious flowing crimson-and-gold phoenix-feather gossamer silk robe with delicate gold chest armor and phoenix ornaments"
        accessories_weapon = "swirling sacred solar flames and a massive glowing golden-red phoenix aura soaring behind her"
        fixed_traits = "crimson-gold phoenix robe, solar flames, golden phoenix forehead mark, soaring phoenix aura, no Caucasian features"
        style_desc = "Eastern fantasy character concept art, 3D octane render, photorealistic 3D character reference design, hyper-detailed material textures, cinematic lighting"
    elif char_id == 'char_0056_puppet_artificer':
        gender_age = "young woman, clever and cute genius mechanic presence"
        body_shape = "petite agile build, nimble and lively posture"
        face = "delicate porcelain skin, large expressive amber-brown eyes, witty and curious smile"
        hair = "dark brown twin-tails adorned with small bronze gears and red ribbon bells"
        eyes = "bright amber-brown eyes full of curiosity and wit"
        outfit = "asymmetrical stylish black-and-crimson mechanic short cheongsam with leather utility belts and knee-high leather boots"
        accessories_weapon = "ornate bronze mechanical puppet glove on right arm with glowing blue spirit strings, floating wooden clockwork puppets, and spinning gear blades"
        fixed_traits = "dark brown twin-tails with bronze gears, black-and-crimson short cheongsam, bronze mechanical glove, glowing blue spirit strings, no Caucasian features"
        style_desc = "Eastern fantasy character concept art, 3D octane render, photorealistic 3D character reference design, hyper-detailed material textures, cinematic lighting"
    elif char_id == 'char_0057_azure_sword_spirit':
        gender_age = "young woman, ethereal and cold immortal sword spirit"
        body_shape = "slender agile swordmaster build, poised and sharp posture"
        face = "fair porcelain skin, cold focused gaze, cyan-blue sword-energy mark on forehead, aloof serene expression"
        hair = "long flowing high ponytail hair fading from ink-black to translucent azure-blue with antique carved jade hairpin"
        eyes = "striking icy cyan-blue eyes glowing with sharp sword aura"
        outfit = "sleek azure-and-white swordmaster silk tunic with sharp blade-like hem, engraved silver vambraces, and pale jade ribbons"
        accessories_weapon = "a legendary ancient glowing cyan-blue crystalline broadsword, and 8 floating semi-transparent azure flying daggers arranged in a halo behind her"
        fixed_traits = "azure-tipped ponytail, jade sword hairpin, azure-white tunic, glowing cyan crystalline broadsword, 8 floating flying daggers, no Caucasian features"
        style_desc = "Eastern fantasy character concept art, 3D octane render, photorealistic 3D character reference design, hyper-detailed material textures, cinematic lighting"
    elif char_id == 'char_0058_nether_dragon_shaman':
        gender_age = "young man, handsome, mysterious and charismatic dragon shaman presence"
        body_shape = "tall slender silhouette, elegant and eerie shamanistic posture"
        face = "striking handsome features, pale skin, heterochromia eyes (left cyan-blue, right dark gold), cinnabar dragon tattoo at outer eye corner"
        hair = "messy jet-black mid-length layered hair adorned with tiny antique silver dragon rings and bone beads"
        eyes = "captivating heterochromia eyes (left cyan-blue, right dark gold)"
        outfit = "intricate dark embroidered Miao-style shaman robes layered with dark feathers, grand antique silver dragon neck torcs, and engraved bone charms"
        accessories_weapon = "carved ancient dragon-bone shaman staff topped with glowing soul orb, a coiling translucent ethereal black dragon spirit, and glowing spectral butterflies"
        fixed_traits = "black dragon horns on forehead, heterochromia eyes, silver dragon torc, dragon-bone staff, coiling ethereal dragon spirit, no Caucasian features"
        style_desc = "Eastern fantasy character concept art, 3D octane render, photorealistic 3D character reference design, hyper-detailed material textures, cinematic lighting"
    elif char_id == 'char_0059_sword_spirit_prime':
        gender_age = "transcendent ethereal young female humanoid water-sword spirit avatar, immortal and divine presence"
        body_shape = "slender ethereal celestial silhouette, levitating weightlessly barefoot with spirit toes stepping on glowing aquatic lotus ripples"
        face = "flawless translucent pale jade-crystalline skin, glowing luminous emerald-aqua water-sword droplet rune inscribed on forehead, tranquil divine countenance"
        hair = "long waist-length liquid crystalline hair shifting from emerald jade-green to luminous translucent aqua-cyan, floating weightlessly like clear waterfall trails, secured with carved antique lotus jade sword hairpin"
        eyes = "ethereal luminous aqua-teal eyes glowing with pure liquid sword intent and water ripples"
        outfit = "ethereal flowing gossamer translucent aquatic silk robes with water-ripple translucent emerald hemlines, floating ribbons of pure aquatic sword qi, delicate carved jade-silver sword-soul vambraces and floating aquatic jade beads"
        accessories_weapon = "a colossal floating ancient primordial Jade-Water Celestial God-Sword (碧水仙剑) behind her pulsing with luminous deep-sea jade runes, her right hand forming an elegant Taoist sword hand seal commanding a revolving halo of 8 translucent liquid jade flying sword blades"
        fixed_traits = "floating barefoot levitation with lotus water ripples, glowing forehead water-sword droplet rune, luminous aqua-teal eyes, translucent emerald-ripple spirit robes, colossal floating jade-water celestial god-sword, hand forming sword seal, 8 revolving aquatic flying blades, no Caucasian features"
        style_desc = "Eastern fantasy immortal concept art, 3D octane render, ethereal water-blade soul aesthetic, translucent jade-crystal fluid dynamics, hyper-detailed volumetric aquatic lighting, cinematic masterpiece, 8k"
    elif char_id == 'char_0060_solar_warlord':
        gender_age = "majestic powerful young East Asian solar celestial general, handsome and heroic divine presence"
        body_shape = "tall athletic muscular warrior silhouette, imposing and stalwart posture"
        face = "resolute handsome features, glowing pure-gold sun flame sigil inscribed on forehead, heroic and noble expression"
        hair = "long jet-black hair tied in an ornate golden crown with fiery red accents and floating golden flame strands"
        eyes = "blazing golden-amber eyes glowing with divine solar fire and righteous authority"
        outfit = "magnificent radiant golden-and-crimson dragon celestial plate armor with fiery silk battle mantle and floating solar light ribbons"
        accessories_weapon = "a massive ancient solar celestial polearm halberd forged from celestial gold dripping with swirling sacred golden flames, and a revolving divine solar halo of 9 radiant miniature suns floating behind his back"
        fixed_traits = "forehead sun flame sigil, golden-amber eyes, golden celestial dragon armor, solar halberd, 9 miniature sun halo, no Caucasian features"
        style_desc = "Eastern fantasy character concept art, 3D octane render, photorealistic 3D character reference design, hyper-detailed material textures, cinematic lighting"
    elif char_id == 'char_0061_nether_moon_arbiter':
        gender_age = "ethereal mysterious and breathtaking young East Asian nether goddess, immortal and serene presence"
        body_shape = "slender graceful goddess silhouette, floating weightlessly with elegant ethereal posture"
        face = "pale translucent porcelain skin, glowing silver crescent moon rune on forehead, tranquil mesmerizing expression"
        hair = "floor-length flowing silvery-white moonlight hair adorned with carved white jade spider lily hairpins and silver bells"
        eyes = "tranquil mesmerizing silver-cyan luminous eyes glowing with celestial nether wisdom"
        outfit = "layered flowing translucent gossamer robes of midnight black and frost-silver moonlight with floating ribbons of spectral water mist"
        accessories_weapon = "holding a delicate antique 9-petaled pure white jade lotus soul lantern emitting cold celestial cyan ghost flames, surrounded by swirling ghostly water ripples and floating crimson red spider lily petals"
        fixed_traits = "forehead silver crescent moon rune, silver-cyan luminous eyes, silvery-white moonlight hair, jade lotus soul lantern, drifting red spider lilies, no Caucasian features"
        style_desc = "Eastern fantasy character concept art, 3D octane render, photorealistic 3D character reference design, hyper-detailed material textures, cinematic lighting"
    else:
        gender_age = "young appearance"
        body_shape = "slender build"
        face = "detailed facial features"
        hair = "detailed hair"
        eyes = "expressive eyes"
        outfit = lock.get('features', '')
        accessories_weapon = lock.get('prop_desc', '')
        fixed_traits = f"{lock['name']}, {lock['prop']}"
        style_desc = "Character concept art"

    prop_desc = lock['prop_desc']
    scene = lock['scene']
    outfit_alt = lock['outfit_alt']
    colors = lock['colors']
    materials = lock['materials']
    damage = lock['damage']
    name = lock['name']

    all_types = [
        "main", "portrait", "expression", "turnaround", "outfit", "prop", 
        "scene", "fullBody", "cover", "moodboard", "sketch", "modelSheet", 
        "poseSheet", "expressionSheet", "detailSheet", "materialPalette", 
        "outfitBreakdown", "damageState"
    ]
    
    for t in all_types:
        if t in existing_types:
            continue
            
        # Focus and composition based on type
        if t == "main":
            focus = "strong first impression, world mood, signature outfit, weapon, and emotional identity"
            composition = "Full-body or three-quarter character view, cinematic but readable, the character is the clear focal point"
            background = f"Atmospheric scene related to the character's world: {scene}"
            asset_label = "main visual key art image"
        elif t == "portrait":
            focus = "facial identity, eyes, hair, expression, collar and shoulder outfit details"
            composition = "Bust portrait, face clearly visible, centered or slightly turned, clean framing"
            background = "Simple soft background matching her palette, no busy scenery"
            asset_label = "portrait / bust image"
        elif t == "expression":
            focus = "show three different facial expressions side-by-side: one serene and calm, one with a subtle focused look, and one showing a faint, gentle smile. Keep the face structure, hair, and eyes identical"
            composition = "Three side-by-side bust views of the same character showing different emotions, clean alignment"
            background = "Plain clean dark gray studio background"
            asset_label = "expression variant sheet"
        elif t == "turnaround":
            focus = "clear turnaround views (front view, side view, back view) standing neutrally to show outfit construction and hair layout from all sides"
            composition = "Three side-by-side full-body views of the same character standing neutrally: front view, side view, back view. Even lighting"
            background = "Plain clean dark gray studio background"
            asset_label = "clean turnaround / angle reference model sheet"
        elif t == "outfit":
            focus = f"show an alternate outfit: {outfit_alt} while preserving the same face, hairstyle, body shape, and color palette logic"
            composition = f"Show three different outfits side-by-side: on the left, her default outfit; in the middle, her alternative outfit ({outfit_alt}); on the right, a stylized secondary variant. Keep face and hair identical"
            background = "Plain clean dark gray background"
            asset_label = "outfit variant reference sheet"
        elif t == "prop":
            focus = f"detailed design of the signature gear: {prop_desc}, shown from multiple angles"
            composition = "Multi-angle views and close-ups of the signature prop on a clean board layout"
            background = "Plain clean dark gray background"
            asset_label = "prop and weapon reference sheet"
        elif t == "scene":
            focus = f"the environment and setting: {scene}"
            composition = "Wide shot scenic view of the location, character is not present or very small to establish scale"
            background = f"{scene}"
            asset_label = "scene landscape concept art"
        elif t == "fullBody":
            focus = "complete outfit, body proportions, weapon scale, and clear design details"
            composition = "Full body visible from head to toe, neutral standing pose, clear silhouette, no cropping"
            background = "Plain clean dark gray studio background"
            asset_label = "full-body standing character art"
        elif t == "cover":
            focus = "iconic character presence in a dynamic pose, high emotional hook, dramatic lighting, and vertical composition suitable for a card banner or cover poster"
            composition = "Strong vertical cover framing, centered character, highly detailed, dynamic lighting"
            background = f"Atmospheric background matching {scene}"
            asset_label = "cover image"
        elif t == "moodboard":
            focus = f"atmosphere, color swatches of {colors}, texture details of {materials}, and symbolic elements related to the character's lore"
            composition = "Clean 4-panel grid layout collage of textures, patterns, colors, and environment elements, no text"
            background = "Plain dark gray velvet background"
            asset_label = "moodboard collage"
        elif t == "sketch":
            focus = "pencil sketch drawings showing 3 study sketches of the character in different poses and structural details"
            composition = "Multiple drawings arranged on a sheet showing structural details"
            background = "Plain light background"
            asset_label = "sketch sheet / line art reference"
        elif t == "modelSheet":
            focus = "authoritative design reference showing the character standing neutrally in her default costume"
            composition = "Detailed full-body front view of the character standing in her default costume holding her signature prop"
            background = "Clean light gray background"
            asset_label = "character model sheet / standard character design reference"
        elif t == "poseSheet":
            focus = "show 5 poses of the same character on one sheet: performing action, walking, sitting, defending, and standing battle-worn. Keep face, hair, and costume identical"
            composition = "5 full-body figures arranged on a single sheet, showing motion and weight"
            background = "Solid clean dark gray background"
            asset_label = "pose sheet"
        elif t == "expressionSheet":
            focus = "show 8 bust portraits of the character in a clean grid: serene smile, chanting/speaking, sadness, surprise, frown, fatigue, laughter, and intense focus. Keep face, hair, and costume collar identical"
            composition = "8 bust portraits arranged in a clean grid layout"
            background = "Clean dark gray background"
            asset_label = "expression sheet"
        elif t == "detailSheet":
            focus = f"close-up panels of the character's features: hair details, face, costume embroidery, and signature prop texture"
            composition = "Close-up panels arranged neatly on a plain background"
            background = "Clean light gray background"
            asset_label = "detail sheet / close-up reference"
        elif t == "materialPalette":
            focus = f"swatches of materials: {materials} next to a front view of the character to lock color and surface properties"
            composition = "The character standing alongside neatly arranged color and material blocks"
            background = "Plain light gray background"
            asset_label = "material and color palette sheet"
        elif t == "outfitBreakdown":
            focus = "layers of the character's gear: the main robe, outer armor/garment, belt, and shoes shown separately"
            composition = "Separated clothing layers and items laid out clearly on a board"
            background = "Clean light background"
            asset_label = "outfit breakdown sheet"
        elif t == "damageState":
            focus = f"tactical battle-worn aesthetic and weathering: {damage}. Show 3 views side-by-side: left, pristine default; middle, light combat wear; right, seasoned battle-tested state with frayed hemlines and atmospheric dust"
            composition = "Show three side-by-side full-body views of the same character standing, showing wear and tear progression"
            background = "Solid clean dark gray background"
            asset_label = "damage state variants"
        else:
            focus = "character details"
            composition = "full body"
            background = "plain background"
            asset_label = t

        # Special override for radio host helmet removal on certain views
        current_face = face
        current_hair = hair
        current_eyes = eyes
        current_focus = focus
        current_composition = composition
        current_fixed_traits = fixed_traits
        
        if char_id == 'char_0042_radio_host' and t in ['portrait', 'expression', 'expressionSheet', 'damageState']:
            current_face = "a cool young woman's face, pretty but slightly tired/sleepy, with a small glowing neon-pink band-aid on her cheek. She is holding her vintage cassette helmet under her arm or placing it next to her."
            current_hair = "messy short silver-gray hair with neon-green dyed ends"
            current_eyes = "sleepy emerald-green eyes"
            current_fixed_traits = "messy short silver-gray hair with neon-green tips, cool pretty face with sleepiness, vintage cassette tape helmet held in hand or next to her, oversized black windbreaker jacket, vintage microphone."
            
            if t == 'portrait':
                current_focus = "facial identity, sleepy emerald-green eyes, messy short silver-gray hair with neon-green tips, collar and shoulder outfit details, holding her cassette helmet under her arm"
            elif t == 'expression':
                current_focus = "show three different facial expressions side-by-side: one yawning lazily, one blowing a pink bubblegum bubble, and one showing a faint sleepy smile. She is holding her cassette helmet under her arm. Keep the face structure and hair identical"
            elif t == 'expressionSheet':
                current_focus = "show 8 bust portraits of the character in a clean grid: serene sleepy face, yawning, blowing bubblegum, minor fatigue, surprise, slight frown, small smile, and focused. Keep face and hair identical. She is not wearing the helmet."
            elif t == 'damageState':
                current_focus = "progressive clothing and helmet damage: her black windbreaker is torn, her face has minor soot smudges, and her short hair is messy. Show 3 views side-by-side: left, default holding helmet; middle, battle-worn with tattered jacket; right, extreme damaged state standing next to her shattered cassette helmet on the ground"

        prompt = f"""Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: {name}
Gender / age impression: {gender_age}
Body shape: {body_shape}
Face: {current_face}
Hair: {current_hair}
Eyes: {current_eyes}
Outfit: {outfit}
Accessories / weapon: {accessories_weapon}
Color palette: {colors}
Fixed traits that must never change: {current_fixed_traits}

Current asset goal:
Generate a {asset_label}. Focus on {current_focus}.

Style:
{style_desc}, 3D octane render, photorealistic 3D character reference design, hyper-detailed material textures, cinematic lighting, high-fidelity production-ready asset.

Composition:
{current_composition}. Keep the character clearly readable. Avoid unnecessary extra characters.

Background:
{background}

Constraints:
Keep the same face, hairstyle, outfit logic, color palette, body shape, and signature accessories.
Do not redesign the character.
No text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."""
            
        expanded.append({
            "char_id": char_id,
            "char_name": char_name,
            "img_type": t,
            "prompt": prompt
        })
        
    return expanded

# ======================================================
# 2. 轻量级 BrowserAgent WebSocket 控制 SDK
# ======================================================
class BrowserAgent:
    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self.websocket = None

    async def connect(self):
        logging.info(f"正在连接到浏览器桥接服务器: {self.ws_url}...")
        try:
            self.websocket = await websockets.connect(
                self.ws_url,
                ping_interval=None,
                ping_timeout=None,
                max_size=50 * 1024 * 1024
            )
            logging.info("WebSocket 桥接连接成功！")
            return True
        except Exception as e:
            logging.error(f"连接失败！错误: {e}")
            logging.error("请确认 `server_live.py` 正在运行，并且 Chrome 扩展处于活动状态。")
            return False

    async def _send_command(self, action: str, **kwargs):
        if not self.websocket:
            raise RuntimeError("WebSocket 未连接，请先调用 connect()")
            
        cmd_id = str(uuid.uuid4())
        payload = {"id": cmd_id, "action": action}
        payload.update(kwargs)
        
        await self.websocket.send(json.dumps(payload))
        
        async for message in self.websocket:
            try:
                data = json.loads(message)
                if data.get("id") == cmd_id:
                    if data.get("status") == "error":
                        raise RuntimeError(f"浏览器操作执行失败: {data.get('error')}")
                    return data
            except json.JSONDecodeError:
                pass

    async def init(self, task_name: str = "角色多部位图片自动流水线"):
        return await self._send_command("init", taskName=task_name)

    async def snapshot(self):
        response = await self._send_command("snapshot")
        return {
            "blocked_by_login": response.get("blockedByLogin", False),
            "dom": response.get("dom", [])
        }

    async def evaluate(self, js_code: str):
        response = await self._send_command("evaluate", code=js_code)
        return response.get("result")

    async def navigate(self, url: str):
        logging.info(f"正在控制浏览器导航至: {url}")
        return await self._send_command("navigate", url=url)

    async def click(self, selector: str):
        logging.info(f"👉 [模拟真人点击] 正在移动并点击: {selector}")
        return await self._send_command("click", selector=selector)

    async def type(self, selector: str, text: str, mode: str = "smart", submit: bool = True):
        logging.info(f"👉 [模拟真人输入] 正在移动并输入文本 (mode={mode}, submit={submit}): '{text[:40]}...' 到 {selector}")
        return await self._send_command("type", selector=selector, text=text, mode=mode, submit=submit)

    async def hover(self, selector: str):
        logging.info(f"👉 [模拟真人悬停] 正在移动并悬停至: {selector}")
        return await self._send_command("hover", selector=selector)

    async def send_key(self, key: str):
        logging.info(f"👉 [模拟真人按键] 发送按键: {key}")
        return await self._send_command("press", key=key)

    async def fetch_as_file(self, url: str, dest_path: str) -> dict:
        """
        【仅适用于图片文件，< 30MB】
        扩展后台带 Cookie fetch URL → base64 → Python 直接写入 dest_path。
        完全绕过 chrome.downloads，FDM 等下载管理器无感知。
        不需要中转 Downloads 文件夹，支持写入任意本地路径。
        """
        import base64, os
        logging.info(f"fetch_as_file: {url[:60]}... → {dest_path}")
        response = await self._send_command("fetchAsBase64", url=url)
        if not response or response.get("status") != "success":
            error = response.get("error", "Unknown error") if response else "No response"
            reason = response.get("reason", "") if response else ""
            logging.error(f"fetchAsBase64 failed [{reason}]: {error}")
            return {"status": "error", "error": error, "reason": reason}
        b64_data = response.get("base64", "")
        raw_bytes = base64.b64decode(b64_data)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(raw_bytes)
        size = len(raw_bytes)
        logging.info(f"Saved {size:,} bytes → {dest_path}")
        return {"status": "success", "path": dest_path, "size": size, "mime": response.get("mime", "")}

    async def download_via_blob(self, url: str, filename: str) -> dict:
        """
        【适用于非图片文件或大文件】
        扩展 Service Worker 带 Cookie fetch URL → 生成 blob: URL → chrome.downloads 下载。
        blob: URL 不会被 FDM 等第三方下载管理器拦截，后台安全，无需窗口唤醒。
        文件保存在系统 Downloads 目录，filename 指定文件名。
        """
        logging.info(f"download_via_blob: {url[:60]}... → Downloads/{filename}")
        return await self._send_command("downloadViaBlob", url=url, filename=filename)

    async def search_downloads(self, query: dict = None):
        """
        查询 Chrome 下载历史
        """
        logging.info(f"Searching downloads with query: {query}...")
        return await self._send_command("searchDownloads", query=query or {})

    async def smart_save(self, url: str, dest_path: str) -> dict:
        """
        智能路由下载方法，自动选择最优下载方式：
        - 图片文件（image/*，< 30MB）→ fetch_as_file()
        - 其他文件 / 大文件 → download_via_blob()
        """
        import os
        logging.info(f"smart_save: 尝试 fetch_as_file → {dest_path}")
        result = await self.fetch_as_file(url, dest_path)
        if result.get("status") == "success":
            return result

        reason = result.get("reason", "")
        # 如果是不支持的文件类型或文件过大，自动回退到 download_via_blob并搬移
        if reason in ("unsupported_mime", "file_too_large"):
            filename = os.path.basename(dest_path)
            logging.info(f"smart_save: 回退到 download_via_blob，filename={filename}（原因：{reason}）")
            res = await self.download_via_blob(url, filename)
            if res and res.get("status") == "success":
                download_id = res.get("downloadId")
                if download_id:
                    import time, shutil, asyncio
                    start_poll = time.time()
                    download_success = False
                    while time.time() - start_poll < 60:
                        await asyncio.sleep(1.0)
                        search_res = await self.search_downloads({"id": download_id})
                        if search_res and search_res.get("status") == "success":
                            items = search_res.get("results", [])
                            if items and items[0].get("state") == "complete":
                                download_success = True
                                break
                    if download_success:
                        download_dir = os.path.join(os.path.expanduser("~"), "Downloads")
                        src_file = os.path.join(download_dir, filename)
                        if os.path.exists(src_file):
                            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                            shutil.move(src_file, dest_path)
                            logging.info(f"smart_save: 成功从 Downloads 移动到目标路径 {dest_path}")
                            return {"status": "success", "path": dest_path}
            return res or {"status": "error", "error": "Blob download failed"}
        return result

    async def screenshot(self, dest_path: str, full_page: bool = False):
        import base64, os
        logging.info(f"正在捕获屏幕截图 并保存至: {dest_path}")
        response = await self._send_command("screenshot", fullPage=full_page)
        if not response or response.get("status") != "success":
            error = response.get("error", "Unknown error") if response else "No response"
            logging.error(f"截图失败: {error}")
            return False
        b64_data = response.get("base64", "")
        raw_bytes = base64.b64decode(b64_data)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(raw_bytes)
        logging.info(f"已成功保存截图 ({len(raw_bytes):,} 字节) -> {dest_path}")
        return True

    async def close(self):
        if self.websocket:
            await self.websocket.close()
            logging.info("WebSocket 控制连接已断开。")

# ======================================================
# 3. 聊天会话管理逻辑 (持久化)
# ======================================================
def load_sessions():
    if os.path.exists(SESSIONS_CACHE_FILE):
        try:
            with open(SESSIONS_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_session(char_id, url):
    sessions = load_sessions()
    sessions[char_id] = url
    with open(SESSIONS_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(sessions, f, indent=2, ensure_ascii=False)
    logging.info(f"已缓存保存角色「{char_id}」的专属会话链接: {url}")

# ======================================================
# 4. JSON 静态数据库极速同步引擎
# ======================================================
def sync_new_image_to_json(char_id: str, img_type: str, img_label: str, img_local_path: str, prompt: str):
    """
    极速将生成的图片同步写入前端的 characterAssets.json 本地数据库，杜绝任何对 TS 源码文件的改动。
    """
    json_path = os.path.join(REACT_PROJECT_PATH, "src", "constants", "characterAssets.json")
    
    # 1. 载入或初始化 JSON 数据库
    data = {}
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logging.warning(f"读取 characterAssets.json 失败 (可能为空或损坏)，将重新创建: {e}")
            
    # 2. 确保角色节点存在
    char_data = data.setdefault(char_id, {"image": "", "images": []})
    
    # 3. 构造相对路径（使 Vite /@fs 机制发挥作用）
    rel_path = img_local_path.replace("\\", "/")
    # 将输出根路径转换为统一的相对地址
    norm_output = OUTPUT_ROOT.replace("\\", "/").rstrip("/")
    if rel_path.startswith(norm_output):
        rel_path = rel_path[len(norm_output):].lstrip("/")
        
    # 如果路径不是以 /@fs/ 开头，根据 Vite 代理要求自动配置物理代理绝对路径
    # 这能保证无论图片是在本地哪个盘（F 盘或 C 盘），Vite 均能顺畅显示而不会跨域
    proxy_path = img_local_path.replace("\\", "/")
    full_proxy_url = f"/@fs/{proxy_path}"
    
    timestamp = int(time.time() * 1000)
    new_img = {
        "id": f"img_auto_{timestamp}",
        "type": img_type,
        "label": img_label,
        "angle": "",
        "outfit": "",
        "pose": "",
        "action": "",
        "emotion": "",
        "camera": "",
        "scene": "",
        "prompt": prompt,
        "note": "DALL-E 自动化多维度生成",
        "url": f"{full_proxy_url}?t={timestamp}"
    }
    
    # 4. 覆盖更新或追加
    existing_images = char_data.get("images", [])
    filtered_images = [img for img in existing_images if img.get("type") != img_type]
    filtered_images.append(new_img)
    
    # 5. 排序（保持 main 主视觉在首位，便于展示）
    char_data["images"] = sorted(filtered_images, key=lambda x: 0 if x.get("type") == "main" else 1)
    
    # 6. 如果是主视觉，同步更新外层的单图字段
    if img_type == "main":
        char_data["image"] = new_img["url"]
        
    # 7. 写入存盘
    try:
        os.makedirs(os.path.dirname(json_path), exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logging.info(f"✨ [JSON 同步成功] 角色 [{char_id}] 的「{img_label}」资产已安全写入数据库 {json_path}！")
        return True
    except Exception as e:
        logging.error(f"❌ [JSON 同步失败] 写入文件 {json_path} 遭遇错误: {e}")
        return False

# ======================================================
# 5. 下载拦截归档引擎
# ======================================================
def wait_for_new_download(download_dir: str, existing_files: set, timeout_sec: int = 90):
    logging.info(f"等待 Chrome 下载图片完成 (监听目录: {download_dir})…")
    start_time = time.time()
    
    while time.time() - start_time < timeout_sec:
        try:
            current_files = set(os.listdir(download_dir))
        except Exception as e:
            time.sleep(1)
            continue
            
        new_files = current_files - existing_files
        
        for f in new_files:
            lower_name = f.lower()
            if lower_name.endswith(('.png', '.jpg', '.jpeg', '.webp')) and not lower_name.endswith('.crdownload'):
                # 留出安全余量让操作系统释放文件锁
                time.sleep(1.5)
                full_path = os.path.join(download_dir, f)
                if os.path.exists(full_path) and os.path.getsize(full_path) > 1024:
                    return full_path
        time.sleep(1)
        
    return None

def archive_image(downloaded_file: str, char_name: str, char_id: str, img_type: str):
    safe_char_name = re.sub(r'[\\/:*?"<>|]', '-', char_name).strip() or "未命名角色"
    sub_folder_name = TYPE_FOLDER.get(img_type, "其他")
    
    # 构造 C:/Ai/character/{角色名}/{子目录名}
    target_dir = os.path.join(OUTPUT_ROOT, safe_char_name, sub_folder_name)
    os.makedirs(target_dir, exist_ok=True)
    
    ext = downloaded_file.split('.')[-1] if '.' in downloaded_file else 'png'
    # 重新命名为 char_xxxx_portrait.png，防止名字冲突，一目了然
    target_filename = f"{char_id}_{img_type}.{ext}"
    target_path = os.path.join(target_dir, target_filename)
    
    try:
        shutil.move(downloaded_file, target_path)
        normalized_url_path = target_path.replace("\\", "/")
        logging.info(f"图片归档搬运成功！归档路径: {normalized_url_path}")
        return normalized_url_path
    except Exception as e:
        logging.warning(f"直接移动失败 (可能是跨物理卷): {e}，尝试复制备用方案...")
        try:
            shutil.copy(downloaded_file, target_path)
            os.remove(downloaded_file)
            normalized_url_path = target_path.replace("\\", "/")
            logging.info(f"通过复制+删除方式搬运成功！归档路径: {normalized_url_path}")
            return normalized_url_path
        except Exception as ex:
            logging.error(f"归档移动依然失败: {ex}")
            return None

# ======================================================
# 6. ChatGPT 交互控制逻辑
# ======================================================
async def trigger_dalle_generation(agent: BrowserAgent, prompt: str):
    logging.info(f"向 ChatGPT 输入绘制 Prompt (模拟真人): {prompt[:80]}...")
    
    # 1. ProseMirror 原生事务驱动文本插入
    prompt_json = json.dumps(prompt)
    js_input = f"""
    (() => {{
        const el = document.querySelector('#prompt-textarea');
        if (!el) return "textarea_not_found";
        
        el.focus();
        const selection = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(el);
        selection.removeAllRanges();
        selection.addRange(range);
        
        // Execute insertText on active selection in ProseMirror
        document.execCommand('insertText', false, {prompt_json});
        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
        return "ok";
    }})()
    """
    input_res = await agent.evaluate(js_input)
    if input_res == "textarea_not_found":
        # 降级尝试通用 type
        res = await agent.type("#prompt-textarea", prompt, mode="direct", submit=False)
        if res == "textarea_not_found":
            raise RuntimeError("未能在 ChatGPT 页面中找到输入框，请确认当前标签页处于 ChatGPT 对话中！")
        
    await asyncio.sleep(0.6) # 等待使发送按钮就绪并渲染出来
    
    # 2. 找到发送按钮并触发点击
    js_send = """
    (() => {
        const btn = document.querySelector('#composer-submit-button, button[data-testid="send-button"], button.composer-submit-btn');
        if (!btn) return { status: 'no_btn' };
        
        btn.focus();
        const opts = { bubbles: true, cancelable: true, view: window, buttons: 1 };
        btn.dispatchEvent(new PointerEvent('pointerdown', opts));
        btn.dispatchEvent(new MouseEvent('mousedown', opts));
        btn.dispatchEvent(new PointerEvent('pointerup', opts));
        btn.dispatchEvent(new MouseEvent('mouseup', opts));
        btn.click();
        return { status: 'clicked' };
    })()
    """
    await agent.evaluate(js_send)
    logging.info("提示词已由虚拟输入驱动并提交，等待 DALL-E 绘图。")

async def get_assistant_turn_count(agent: BrowserAgent) -> int:
    """
    返回当前页面中 assistant turn 的数量，用于生成前锚定位置，
    生成后仅从编号更大的新 turn 里取图，彻底避免把历史图误判为新生成图。
    """
    js = """
    (() => {
        return document.querySelectorAll('[data-message-author-role="assistant"]').length;
    })()
    """
    res = await agent.evaluate(js)
    return res if isinstance(res, int) else 0

async def get_image_from_newest_turns(agent: BrowserAgent, min_turn_count: int) -> str | None:
    """
    从第 min_turn_count 之后的新 assistant turn 中取最新图片 URL。
    当 poll_until_image_ready 返回的 URL 疑似是历史缓存图时调用此函数作为修正。
    """
    js = f"""
    (() => {{
        const turns = Array.from(document.querySelectorAll('[data-message-author-role="assistant"]'));
        const newTurns = turns.slice({min_turn_count});
        for (let i = newTurns.length - 1; i >= 0; i--) {{
            const imgs = Array.from(newTurns[i].querySelectorAll(
                'img[src*="files.oaiusercontent.com"], img[src*="/backend-api/files"], img[src*="/backend-api/estuary/content"]'
            ));
            if (imgs.length > 0) return imgs[imgs.length - 1].src;
        }}
        return null;
    }})()
    """
    res = await agent.evaluate(js)
    return res if isinstance(res, str) and res.startswith('http') else None

def get_first_significant_word(prompt: str) -> str:
    """
    提取 prompt 的第一个有意义的英文词（长度≥4，跳过介词、角色名等高频通用词），
    用于历史配对时的跨类型误匹配防护。
    """
    # 跳过这些高频词，它们在几乎每个 prompt 里都会出现
    SKIP = {
        'this','that','with','from','show','have','been','will','draw','same',
        'your','character','spirit','guardian','bioluminescent','crimson','midnight',
        'neon','abyssal','stalker','siren','warlord','investigator','painter',
        'keeper','walker','mechanic','sniper','apprentice','nomad','scavenger',
        'queen','boundary','lantern','mirror','tide','rust','sand','astrolabe',
        'also','their','using','into','each','side','both','three','front',
        'back','view','image','picture','sheet','design','concept','style',
        'detailed','detail','clean','clear','light','dark','color','white',
        'black','gray','blue','pink','purple','glow','glowing','include',
        'featuring','shows','shown','showing','professional','masterpiece',
    }
    words = re.findall(r'\b[A-Za-z]{4,}\b', prompt)
    for w in words:
        if w.lower() not in SKIP:
            return w.lower()
    return words[0].lower() if words else ''

async def scan_existing_web_images(agent: BrowserAgent):
    js_get = """
    (() => {
        const imgs = Array.from(document.querySelectorAll('img[src*="files.oaiusercontent.com"], img[src*="/backend-api/files"], img[src*="/backend-api/estuary/content"]'));
        const srcs = imgs.map(img => img.src);
        return Array.from(new Set(srcs));
    })()
    """
    res = await agent.evaluate(js_get)
    if isinstance(res, list):
        return res
    return []

async def poll_until_image_ready(agent: BrowserAgent, pre_existing_srcs: set, pre_assistant_count: int = 0, timeout_sec: int = 600):
    logging.info("开始监测 DOM 生成进度...")
    start_time = time.time()
    pre_srcs_json = json.dumps(list(pre_existing_srcs))
    
    generation_started = False
    
    while time.time() - start_time < timeout_sec:
        js_poll = f"""
        (() => {{
            const bodyText = (() => {{
                const mainEl = document.querySelector('main');
                return mainEl ? mainEl.innerText : (document.body ? document.body.innerText : "");
            }})();
            
            // 1. 检查是否有生图指示或停止按钮，代表生图已经在运行了
            const stopBtn = document.querySelector('button[data-testid="stop-button"], #composer-submit-button[data-testid="stop-button"]');
            const hasStopButton = stopBtn !== null && !stopBtn.disabled && (
                stopBtn.getAttribute('aria-label')?.includes('停止') || 
                stopBtn.getAttribute('aria-label')?.includes('Stop')
            );
            
            const hasImageLoadingState = document.querySelector('[data-testid*="image-gen-loading"]') !== null ||
                                         document.querySelector('[data-testid="image-gen-loading-state-dots"]') !== null;
            
            const latestAssistantTurn = Array.from(document.querySelectorAll('[data-message-author-role="assistant"]')).pop();
            let isThinkingCurrently = false;
            let hasSpinOrLoader = false;
            if (latestAssistantTurn) {{
                const thinkBtn = Array.from(latestAssistantTurn.querySelectorAll('button')).find(b => 
                    b.innerText.includes("Thinking") || 
                    b.innerText.includes("思考中") ||
                    b.innerText.includes("正在思考")
                );
                if (thinkBtn) isThinkingCurrently = true;
                
                const spin = latestAssistantTurn.querySelector('svg[class*="animate-spin"]') !== null;
                const loader = latestAssistantTurn.querySelector('.streaming-loader') !== null;
                const shimmer = latestAssistantTurn.querySelector('.loading-shimmer') !== null;
                hasSpinOrLoader = spin || loader || shimmer;
            }}
            const hasThinking = isThinkingCurrently || hasSpinOrLoader;
            const isGeneratingCurrently = hasStopButton || hasThinking || hasImageLoadingState;

            // 2. 检测系统弹窗/Toast 是否有实时的生图额度上限
            const modalAlertText = (() => {{
                const alerts = Array.from(document.querySelectorAll('[role="alert"], [role="dialog"], [data-testid*="toast"]'));
                return alerts.map(a => a.innerText.toLowerCase()).join(" ");
            }})();
            if (modalAlertText.includes("limit") && (modalAlertText.includes("reset") || modalAlertText.includes("quota") || modalAlertText.includes("rate"))) {{
                return {{ "status": "quota_limit", "error": "ChatGPT DALL-E 弹出额度限制提示" }};
            }}

            // 3. 针对最新的 Assistant Turn 检测回复状态
            const assistantTurns = Array.from(document.querySelectorAll('[data-message-author-role="assistant"]'));
            const lastTurn = assistantTurns.length > {pre_assistant_count} ? assistantTurns[assistantTurns.length - 1] : null;
            if (lastTurn && !isGeneratingCurrently) {{
                const turnText = lastTurn.innerText;
                const lowerTurnText = turnText.toLowerCase();

                // 检测生图额度上限（仅针对最新的一条回复）
                if (lowerTurnText.includes("hit the plus plan limit") || 
                    lowerTurnText.includes("hit the") && lowerTurnText.includes("limit") ||
                    lowerTurnText.includes("limit resets in") ||
                    lowerTurnText.includes("unable to invoke the image generation tool") ||
                    (lowerTurnText.includes("limit") && (lowerTurnText.includes("reset") || lowerTurnText.includes("hour") || lowerTurnText.includes("minute") || lowerTurnText.includes("quota") || lowerTurnText.includes("reached") || lowerTurnText.includes("hit")))) {{
                    return {{ "status": "quota_limit", "error": "ChatGPT DALL-E 生图额度已达上限（Plus Plan Limit Reached）: " + turnText.slice(0, 120) }};
                }}
                if (lowerTurnText.includes("quota") && (lowerTurnText.includes("exceed") || lowerTurnText.includes("limit") || lowerTurnText.includes("reach"))) {{
                    return {{ "status": "quota_limit", "error": "ChatGPT DALL-E 生图额度/频次已达上限" }};
                }}

                // 检测 DALL-E 临时服务错误
                if (turnText.includes("wasn't able to generate") || 
                    turnText.includes("encountered an error") || 
                    turnText.includes("generation tool encountered") || 
                    turnText.includes("Error generating image")) {{
                    return {{ "status": "error", "error": "OpenAI DALL-E 官方绘图服务发生临时错误" }};
                }}

                // 检测 DALL-E 内容安全政策拦截
                if (turnText.includes("违反") || 
                    turnText.includes("违反了") || 
                    turnText.includes("违反了我们的内容政策") || 
                    turnText.includes("violates our content policy") ||
                    turnText.includes("违反内容政策") ||
                    turnText.includes("Content policy violation") ||
                    turnText.includes("content policy")) {{
                    return {{ "status": "policy_violation", "error": "检测到 ChatGPT 官方内容安全政策拦截" }};
                }}

                // 检测纯文本未绘图
                const lastTurnImgs = Array.from(lastTurn.querySelectorAll('img[src*="files.oaiusercontent.com"], img[src*="/backend-api/files"], img[src*="/backend-api/estuary/content"]'));
                if (lastTurnImgs.length === 0) {{
                    return {{ "status": "no_image_in_reply", "text": turnText.slice(0, 100) }};
                }}
            }}

            const preSrcs = new Set({pre_srcs_json});
            const imgs = Array.from(document.querySelectorAll('img[src*="files.oaiusercontent.com"], img[src*="/backend-api/files"], img[src*="/backend-api/estuary/content"]'));
            
            if (imgs.length === 0) {{
                return {{ "status": "waiting", "isGenerating": isGeneratingCurrently }};
            }}
            
            const newImgs = imgs.filter(img => !preSrcs.has(img.src));
            if (newImgs.length === 0) {{
                return {{ "status": "waiting", "isGenerating": isGeneratingCurrently }};
            }}
            
            const latestImg = newImgs[newImgs.length - 1];
            
            if (latestImg.complete && latestImg.naturalWidth > 0) {{
                if (isGeneratingCurrently) {{
                    return {{ "status": "generating", "isGenerating": true }};
                }}
                return {{ "status": "done", "src": latestImg.src, "isGenerating": false }};
            }}
            return {{ "status": "rendering", "isGenerating": true }};
        }})()
        """
        
        res = await agent.evaluate(js_poll)
        if isinstance(res, dict):
            status = res.get("status")
            is_generating = res.get("isGenerating", False)
            
            # 如果确认了生成已经启动（即页面处于 isGenerating 状态，或者我们已经在页面等待了超过 15 秒）
            if is_generating or (time.time() - start_time > 15):
                if not generation_started:
                    logging.info("🔥 检测到 ChatGPT 已成功启动生图流程（Thinking / Loading / StopButton 激活）")
                    generation_started = True
            
            if status == "done":
                if generation_started:
                    logging.info("检测到图片已彻底生成并渲染完毕！")
                    return res.get("src")
                else:
                    logging.warning("⚠️ 警告：检测到图片 done，但生图流程未见启动，疑似旧缓存图片，继续等待新图...")
            elif status == "no_image_in_reply":
                logging.warning(f"⚠️ ChatGPT 仅返回了纯文本回复而未触发 DALL-E 作图: {res.get('text')}")
                return "no_image"
            elif status == "quota_limit":
                logging.error(f"⚠️ [生图限额拦截] 检测到 ChatGPT 官方生图限额已满：{res.get('error')}")
                return "quota_limit"
            elif status == "error":
                logging.error(f"检测到 OpenAI 官方后台发生暂时性生成错误: {res.get('error')}")
                return "error"
            elif status == "policy_violation":
                logging.error(f"⚠️ [内容安全策略拦截] {res.get('error')}")
                return "policy_violation"
            elif status == "generating" or status == "rendering" or is_generating:
                logging.info("图片生成中 / 页面排版中 / AI思考中，继续监控...")
            else:
                logging.info("正在等待 ChatGPT 绘制图片流...")
        await asyncio.sleep(3)
        
    logging.error("等待图片生成超时！")
    return None

def get_prompt_similarity(p1: str, p2: str) -> float:
    """
    计算两个 Prompt 的 Jaccard 相似度（基于英文单词）
    为了避免因为共享的 Character lock 头部导致不同部位的相似度被误判为匹配，
    如果 Prompt 包含 'current asset goal:'，我们将只对比该标记之后的具体绘图目标部分。
    """
    def clean_prompt(p: str) -> str:
        p_lower = p.lower()
        if "current asset goal:" in p_lower:
            parts = p_lower.split("current asset goal:", 1)
            return parts[1]
        if "character lock:" in p_lower:
            for delimiter in ["style:", "composition:", "background:", "constraints:"]:
                if delimiter in p_lower:
                    return p_lower.split(delimiter, 1)[1]
        return p_lower

    w1 = set(re.findall(r'\w+', clean_prompt(p1)))
    w2 = set(re.findall(r'\w+', clean_prompt(p2)))
    if not w1 or not w2:
        return 0.0
    return len(w1 & w2) / len(w1 | w2)

async def scan_conversation_history(agent: BrowserAgent):
    """
    通过模拟滚动的方式，绕过 ChatGPT 消息列表虚拟化(Virtualization)限制，
    完整抓取页面中所有的 (UserPrompt -> AssistantImages) 配对。
    在 JS 层面对每一个 assistant 消息在其上方查找最近的 user 消息进行局部配对，
    彻底解决滚动过程中由于部分 Turn 被虚拟化移除导致的全局配对错位问题。
    """
    js_scroll_collect = """
    (async () => {
        let container = document.querySelector('#main') || document.querySelector('main');
        while (container && container !== document.body) {
            const style = window.getComputedStyle(container);
            if (style.overflowY === 'auto' || style.overflowY === 'scroll') {
                break;
            }
            container = container.parentElement;
        }
        if (!container || container === document.body) {
            container = document.querySelector('.overflow-y-auto') || document.body;
        }
        
        const originalScrollTop = container.scrollTop;
        const userPrompts = new Map();
        const assistantImages = new Map();
        
        const collectTurns = () => {
            const userTurns = document.querySelectorAll('section[data-turn="user"]');
            userTurns.forEach(turn => {
                const testId = turn.getAttribute('data-testid') || "";
                const m = testId.match(/conversation-turn-(\\d+)/);
                if (m) {
                    const num = parseInt(m[1], 10);
                    const text = turn.innerText || "";
                    if (text.trim().length > 0) {
                        userPrompts.set(num, text.trim());
                    }
                }
            });
            
            const assistantTurns = document.querySelectorAll('section[data-turn="assistant"]');
            assistantTurns.forEach(turn => {
                const testId = turn.getAttribute('data-testid') || "";
                const m = testId.match(/conversation-turn-(\\d+)/);
                if (m) {
                    const num = parseInt(m[1], 10);
                    const imgs = turn.querySelectorAll('img[src*="files.oaiusercontent.com"], img[src*="/backend-api/files"], img[src*="/backend-api/estuary/content"]');
                    const imageSrcs = Array.from(imgs).map(img => img.src).filter(src => !!src);
                    if (imageSrcs.length > 0) {
                        assistantImages.set(num, imageSrcs);
                    }
                }
            });
        };
        
        // Fast scroll UP in 3000px steps (max 5 steps)
        let currentScroll = container.scrollTop;
        let stepCount = 0;
        while (currentScroll > 0 && stepCount < 5) {
            stepCount++;
            currentScroll = Math.max(0, currentScroll - 3000);
            container.scrollTop = currentScroll;
            collectTurns();
        }
        
        // Fast scroll DOWN in 3000px steps (max 5 steps)
        const maxScroll = container.scrollHeight - container.clientHeight;
        stepCount = 0;
        while (currentScroll < maxScroll && stepCount < 5) {
            stepCount++;
            currentScroll = Math.min(maxScroll, currentScroll + 3000);
            container.scrollTop = currentScroll;
            collectTurns();
        }
        collectTurns();
        container.scrollTop = originalScrollTop;
        
        const result = [];
        for (let [num, images] of assistantImages.entries()) {
            const prompt = userPrompts.get(num - 1);
            if (prompt) {
                images.forEach(img => {
                    result.push({ prompt: prompt, image: img });
                });
            }
        }
        return result;
    })()
    """
    try:
        logging.info("⏳ 正在运行防虚拟化滚动收集器，抓取历史对话...")
        history_pairs = await agent.evaluate(js_scroll_collect)
        if not isinstance(history_pairs, list):
            logging.warning("⚠️ 滚动历史收集器未返回有效数组，降级使用空历史列表")
            return []
        
        logging.info(f"✨ 历史对话解析完毕，共分析到 {len(history_pairs)} 个 (Prompt -> Image) 配对关系")
        return history_pairs
    except Exception as ex:
        logging.error(f"❌ 滚动收集历史失败: {ex}")
        return []

async def trigger_browser_download(agent: BrowserAgent, img_src: str):
    logging.info(f"正在通过 Fetch 同源机制为图片发起安全下载...")
    js_download = f"""
    (async () => {{
        try {{
            const res = await fetch("{img_src}");
            const blob = await res.blob();
            const blobUrl = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = blobUrl;
            a.download = "dalle_{int(time.time())}.png";
            a.style.display = 'none';
            document.body.appendChild(a);
            a.click();
            setTimeout(() => {{
                a.remove();
                URL.revokeObjectURL(blobUrl);
            }}, 2000);
            return "trigger_success";
        }} catch(err) {{
            return "trigger_error: " + err.message;
        }}
    }})()
    """
    return await agent.evaluate(js_download)

async def capture_current_session_url(agent: BrowserAgent, char_id: str):
    """
    轮询捕获当前的真实聊天 URL (包含 /c/xxxx)，捕获成功后存盘
    """
    for _ in range(5):
        url = await agent.evaluate("window.location.href")
        if url and "/c/" in url:
            save_session(char_id, url)
            return url
        await asyncio.sleep(2)
    return None

# ======================================================
# 7. 主执行管道 (Pipeline Core)
# ======================================================
async def generate_character_part(agent: BrowserAgent, char_id: str, char_name: str, img_type: str, prompt: str, absolute_idx: int):
    logging.info("-" * 60)
    logging.info(f"【生成启动】角色: {char_name} | 类型: {TYPE_LABEL.get(img_type, img_type)} | 绝对序号: {absolute_idx}")
    
    # 0. 智能跳过已存在资产，避免重复生成
    safe_char_name = re.sub(r'[\\/:*?"<>|]', '-', char_name).strip() or "未命名角色"
    sub_folder_name = TYPE_FOLDER.get(img_type, "其他")
    target_dir = os.path.join(OUTPUT_ROOT, safe_char_name, sub_folder_name)
    target_path = os.path.join(target_dir, f"{char_id}_{img_type}.png")
    if os.path.exists(target_path) and os.path.getsize(target_path) > 1024:
        display_path = target_path.replace("\\", "/")
        logging.info(f"✨ [智能跳过] 资产文件已存在于: {display_path}，直接跳过生成进入下一项！")
        return "skipped"

    # 1. 载入历史专属会话 URL，如已经在该会话中则直接复用，不重新刷新加载
    sessions = load_sessions()
    saved_url = sessions.get(char_id)
    
    current_url = ""
    try:
        current_url = await agent.evaluate("window.location.href") or ""
    except Exception:
        pass

    if saved_url:
        if current_url and current_url.split("?")[0] == saved_url.split("?")[0]:
            logging.info(f"✨ 当前已处于角色「{char_name}」的专属会话 ({saved_url})，直接在当前窗口连续发送！")
            await asyncio.sleep(2.0)
        else:
            logging.info(f"检测到角色「{char_name}」拥有已缓存的专属会话。正在导入跳转...")
            await agent.navigate(saved_url)
            await asyncio.sleep(6.0)
    else:
        # 没有已保存的专属会话，必须开启一个全新的专属会话，绝不能复用其他角色的 /c/ 会话！
        if current_url and "/c/" in current_url:
            logging.info(f"检测到当前处于其他角色的会话 ({current_url})，正在为新角色「{char_name}」开启全新独立会话...")
            await agent.navigate("https://chatgpt.com/")
            await asyncio.sleep(6.0)
        elif current_url and "chatgpt.com" in current_url:
            logging.info(f"当前已处于 ChatGPT 主页空白会话，为新角色「{char_name}」直接启动...")
            await asyncio.sleep(2.0)
        else:
            logging.info(f"未找到角色「{char_name}」的历史会话，正在开启全新会话...")
            await agent.navigate("https://chatgpt.com/")
            await asyncio.sleep(6.0)
    
    # 2. 扫描已有大图缓存（做为后面触发 DALL-E 之后寻找新生成图片的基准）
    pre_srcs = await scan_existing_web_images(agent)
    # 【修复】同时记录当前 assistant turn 数量，用于生成后的图片 turn 锚定校验
    pre_turn_count = await get_assistant_turn_count(agent)
    logging.info(f"页面当前大图缓存量: {len(pre_srcs)} 张 | assistant turn 基准索引: {pre_turn_count}")
    
    # 3. 运行防虚拟化滚动收集，提取已生成的历史图与 prompt 的对应关系，并进行 Prompt 相似度精准匹配
    # 如果是已有缓存的专属会话，历史记录绝不应为空。如果是空，则很有可能是因为加载延迟，我们将进行重试
    try:
        history_pairs = await scan_conversation_history(agent)
    except Exception as err:
        logging.warning(f"⚠️ 历史会话扫描略过: {err}")
        history_pairs = []
    
    matched_image_src = None
    max_sim = 0.0
    
    # 临时旁路机制：将废铁重构师的重构设定类型强行重新生成，避开历史中带机械臂和动漫风格的旧图片；将皮影御灵师的战损和场景也强行重新生成
    bypass_types = {"modelSheet", "poseSheet", "expressionSheet", "detailSheet", "materialPalette", "outfitBreakdown", "damageState", "scene"}
    bypass_history = (
        (char_id == "char_0006_rust_mechanic" and img_type in bypass_types) or
        (char_id == "char_0021_shadow_puppeteer" and img_type in {"damageState", "scene"}) or
        (char_id == "char_0043_blade_wraith")
    )
    
    target_first_word = get_first_significant_word(prompt)
    if not bypass_history:
        for pair in history_pairs:
            # 【修复】首词强校验：匹配 pair 的 prompt 首个有意义词必须与目标 prompt 相同，
            # 防止「道具」类型因含 crystal lantern 而与「线稿」「破损」等 prompt 误匹配。
            pair_first_word = get_first_significant_word(pair["prompt"])
            if pair_first_word != target_first_word:
                continue
            sim = get_prompt_similarity(prompt, pair["prompt"])
            if sim > 0.95 and sim >= max_sim: # 使用 >= 保证存在重生成时选取最新一张
                max_sim = sim
                matched_image_src = pair["image"]
            
    if matched_image_src:
        logging.info(f"✨ [历史图智能拾取] 相似度匹配成功 (similarity={max_sim:.2f})！")
        logging.info(f"直接跳过 DALL-E 生图，直存并同步该历史大图: {matched_image_src[:80]}...")
        
        os.makedirs(target_dir, exist_ok=True)
        res = await agent.smart_save(matched_image_src, target_path)
        if res and res.get("status") == "success":
            local_path = target_path.replace("\\", "/")
            sync_new_image_to_json(char_id, img_type, TYPE_LABEL.get(img_type, img_type), local_path, prompt)
            logging.info(f"【成功同步】角色「{char_name}」的「{TYPE_LABEL.get(img_type, img_type)}」（通过匹配拾取）已就绪！")
            return True
        else:
            logging.error(f"历史图直存失败: {res.get('error') if res else '无响应'}，将回退到重新生图流程。")

    # 4. 提交绘图
    # 再次扫描并合并已有大图（防范滚动收集历史对话时在 DOM 中新载入了大量历史图片，导致被误判为新生成的图片）
    post_scroll_srcs = await scan_existing_web_images(agent)
    pre_srcs = set(pre_srcs) | set(post_scroll_srcs)
    
    # 记录发送前的 assistant 回答数量，防范 polling 时误判旧会话中遗留的“内容安全政策拦截/生成失败”等错误提示
    pre_assistant_count = 0
    try:
        count_res = await agent.evaluate('document.querySelectorAll(\'[data-message-author-role="assistant"]\').length')
        if count_res is not None:
            pre_assistant_count = int(count_res)
    except Exception as ec:
        logging.warning(f"获取发送前 assistant 回答数量失败: {ec}")
    
    await trigger_dalle_generation(agent, prompt)
    
    # 4. 如果是新开启的会话，首次发送 Prompt 后立即轮询捕获会话 URL，确保即便后边绘图超时也能完美锁定本角色的专属会话！
    if not saved_url:
        logging.info("新开启会话，正在安全拦截捕获专属聊天 URL...")
        for _ in range(10):
            await asyncio.sleep(1.5)
            url = await agent.evaluate("window.location.href")
            if url and "/c/" in url:
                save_session(char_id, url)
                saved_url = url
                break
                
    # 5. 等待完成
    new_src = await poll_until_image_ready(agent, pre_srcs, pre_assistant_count=pre_assistant_count)
    error_dir = os.path.join(os.path.dirname(OUTPUT_ROOT), "errors")
    if new_src == "quota_limit":
        logging.error(f"⚠️ [限额拦截] 检测到生图限额已满，停止当前角色的流水线生成以避免无谓重试。")
        screenshot_path = os.path.join(error_dir, f"{char_id}_{img_type}_quota_limit.png")
        os.makedirs(error_dir, exist_ok=True)
        try:
            await agent.screenshot(screenshot_path)
            logging.info(f"📸 [限额现场] 已自动保存限额截图至: {screenshot_path}")
        except Exception as se:
            logging.error(f"📸 自动保存限额截图失败: {se}")
        return "quota_limit"
    if new_src == "policy_violation":
        logging.error(f"⚠️ [内容安全策略拦截] 检测到内容政策冲突，跳过此资产生成。")
        screenshot_path = os.path.join(error_dir, f"{char_id}_{img_type}_policy_violation.png")
        os.makedirs(error_dir, exist_ok=True)
        try:
            await agent.screenshot(screenshot_path)
            logging.info(f"📸 [策略拦截现场] 已自动保存内容安全截图至: {screenshot_path}")
        except Exception as se:
            logging.error(f"📸 自动保存内容安全截图失败: {se}")
        return "policy_violation"
    if new_src == "error" or not new_src:
        logging.error(f"绘图执行出现错误或超时，本次生成失败。")
        screenshot_path = os.path.join(error_dir, f"{char_id}_{img_type}_error.png")
        os.makedirs(error_dir, exist_ok=True)
        try:
            await agent.screenshot(screenshot_path)
            logging.info(f"📸 [超时/错误现场] 已自动保存错误截图至: {screenshot_path}")
        except Exception as se:
            logging.error(f"📸 自动保存错误截图失败: {se}")
        return False

    # 【修复】Turn 索引锚定校验：验证 poll 返回的图片是否真的来自新 turn（编号 > pre_turn_count）。
    # 若 URL 集合差值检测到的图片实为被虚拟滚动重新载入的旧图，则从最新 turn 里重新取图修正。
    anchored_src = await get_image_from_newest_turns(agent, pre_turn_count)
    if anchored_src and anchored_src != new_src:
        logging.warning(
            f"⚠️ [Turn锚定修正] poll 检测到的图片 URL 与最新 turn 的图片不一致，"
            f"疑似历史虚拟化重载图，已切换为最新 turn 图片。"
        )
        new_src = anchored_src
    elif not anchored_src:
        logging.warning("⚠️ [Turn锚定] 未找到新 turn 图片，继续使用 poll 返回的 URL。")
        
    # 6. 智能保存大图，绕过 FDM 拦截，直接存入目标文件夹
    logging.info(f"正在通过 smart_save 智能直存图片至: {target_path}")
    os.makedirs(target_dir, exist_ok=True)
    res = await agent.smart_save(new_src, target_path)
    if not res or res.get("status") != "success":
        logging.error(f"图片直存失败: {res.get('error') if res else '无响应'}")
        return False
        
    local_path = target_path.replace("\\", "/")
    
    # 7. 同步回写 JSON 数据库
    sync_new_image_to_json(char_id, img_type, TYPE_LABEL.get(img_type, img_type), local_path, prompt)
    
    # 彻底确保会话 URL 存盘
    try:
        final_url = await agent.evaluate("window.location.href")
        if final_url and "/c/" in final_url:
            save_session(char_id, final_url)
    except Exception:
        pass

    logging.info(f"【成功同步】角色「{char_name}」的「{TYPE_LABEL.get(img_type, img_type)}」已全部就绪！")
    return True

async def run_all_pipeline(dry_run: bool, char_id: str = None, img_type: str = None):
    logging.info("=" * 60)
    logging.info(" React 多部位资产自动化流水线启动…")
    
    # 我们为两个角色定义的部位生成计划
    crimson_plan = [
        {
            "char_id": "char_0001_crimson_guardian",
            "char_name": "赤衣守城者",
            "img_type": "main",
            "prompt": "A breathtaking masterfully crafted epic fantasy concept art of the Crimson Wall Guardian. A young, slender East Asian swordsman with highly refined handsome facial features and long wind-blown black hair. He is wearing an incredibly detailed, flowing crimson silk robe designed with elegant layering, adorned with exquisite golden ancient engravings and silver armor plates. He stands heroic and unyielding on a massive, majestic ancient stone fortress wall. In one hand, he holds a beautifully detailed divine sword that glows with faint red aura and intricate runes. The background features a dramatic, glorious sunset with sweeping rays of golden and fiery orange light piercing through epic clouds, casting a warm, rich glow over the endless scenic mystical wasteland below. Particles of dust and glowing embers float in the air, creating a rich, highly detailed cinematic masterpiece, octane render, hyper-realistic textures, 8k resolution."
        },
        {
            "char_id": "char_0001_crimson_guardian",
            "char_name": "赤衣守城者",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up high-fidelity portrait of the exact same Crimson Wall Guardian character from our conversation. Focus on his face and shoulders, capturing his focused, unyielding dark red eyes and messy long black hair. The warm golden light from a dramatic sunset illuminates one side of his face, showing handsome refined facial features, skin texture, and subtle ancient combat markings on his cheek. Solid, extremely dark, low-contrast studio background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0001_crimson_guardian",
            "char_name": "赤衣守城者",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same Crimson Wall Guardian character from our conversation. Show him on a solid, clean dark gray background with three different facial expressions side-by-side: one calm and focused, one showing a powerful determined war shout, and one tired with a faint, proud smile. High-fidelity details, professional character model sheet, masterpiece, 8k."
        }
    ]
    
    midnight_plan = [
        {
            "char_id": "char_0002_midnight_warden",
            "char_name": "午夜值守员",
            "img_type": "main",
            "prompt": "A stunning, highly detailed modern urban mystery cinematic concept art of the Midnight Warden. A slender, delicate young East Asian woman with beautiful focused dark brown eyes, tired yet sharp with noticeable dark circles under them. Her pitch-black mid-length hair is elegantly half-pinned up with the rest flowing naturally over her shoulders. She wears a tailored, neatly buttoned deep navy blue duty uniform. Pinned elegantly on her left chest is a bright, mystical glowing silver duty badge, casting a soft, warm ethereal light onto her detailed, expressive handsome face, showing exquisite skin texture. She stands alone at the end of an atmospheric, dimly lit quiet corridor. Behind her, a mysterious wooden door glows brightly from its cracks with warm golden-amber light. In one hand, she holds a vintage metallic flashlight, casting a sharp beam of light reflecting on the polished marble floor. Cool moonlight white Tyndall beams pierce through window panes, creating a breathtaking high-fidelity contrast, masterpiece, unreal engine 5 render, 8k."
        },
        {
            "char_id": "char_0002_midnight_warden",
            "char_name": "午夜值守员",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up high-fidelity portrait of the exact same Midnight Warden character from the previous image. Focus on her face and shoulders, capturing her tired yet focused expression and the half-pinned dark hair. Pinned on her navy duty uniform, the silver badge glows softly, casting a warm amber light onto her cheek, highlighting highly realistic skin details. Solid, extremely dark, low-contrast studio background. Masterpiece, cinematic lighting, 8k."
        },
        {
            "char_id": "char_0002_midnight_warden",
            "char_name": "午夜值守员",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same Midnight Warden character from our conversation. Show her on a solid, clean dark gray background with three different facial expressions side-by-side: one tired but calm, one alert with focused eyes, and one showing a rare, gentle subtle smile. High-fidelity details, professional character model sheet, masterpiece, 8k."
        }
    ]

    sandstorm_plan = [
        {
            "char_id": "char_0003_sandstorm_pilgrim",
            "char_name": "风沙朝圣者",
            "img_type": "main",
            "prompt": "A breathtaking epic post-apocalyptic concept art of the Sandstorm Pilgrim. A mature, weathered East Asian ascetic monk with deep, wise facial lines and short grizzled hair tied with a faded red band. He is wearing a coarse, heavily patched sand-swept gray linen cloak over rugged survival garments. He walks barefoot heroically across a vast, barren desert wasteland during a dramatic sandstorm. In one hand, he holds a detailed heavy brass staff adorned with ancient bronze wind chimes that sway in the wind. The background features giant sand dunes, a hazy sun struggling to pierce through thick amber dust clouds, casting a majestic and melancholic warm rim light on his silhouette. Cinematic masterpiece, hyper-realistic textures, octane render, 8k resolution."
        },
        {
            "char_id": "char_0003_sandstorm_pilgrim",
            "char_name": "风沙朝圣者",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up high-fidelity portrait of the exact same Sandstorm Pilgrim character from our conversation. Focus on his face and shoulders, capturing his deep, wise grey eyes and weathered facial features. The warm, hazy amber light from the sandstorm illuminates one side of his face, highlighting his skin texture and dust on his cheek. Solid, extremely dark, low-contrast studio background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0003_sandstorm_pilgrim",
            "char_name": "风沙朝圣者",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same Sandstorm Pilgrim character from our conversation. Show him on a solid, clean dark gray background with three different facial expressions side-by-side: one calm and meditative, one showing a determined yell against the wind, and one displaying a rare, serene and peaceful smile. High-fidelity details, professional character model sheet, masterpiece, 8k."
        },
        {
            "char_id": "char_0003_sandstorm_pilgrim",
            "char_name": "风沙朝圣者",
            "img_type": "turnaround",
            "prompt": "Now, draw a professional character turnaround model sheet of the exact same Sandstorm Pilgrim character from our conversation. Show three full-body views: front, side, and back, standing in a neutral pose. He is wearing his coarse gray linen cloak and rugged survival garments. Solid, clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0003_sandstorm_pilgrim",
            "char_name": "风沙朝圣者",
            "img_type": "outfit",
            "prompt": "Now, draw the exact same Sandstorm Pilgrim character from our conversation, but wearing an alternative survival outfit: a heavy sand-shielding leather armor, thick thermal wraps around his torso, and a protective respirator mask hanging around his neck. Full-body view, standing heroically on a solid clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0003_sandstorm_pilgrim",
            "char_name": "风沙朝圣者",
            "img_type": "prop",
            "prompt": "Now, draw a high-fidelity detailed weapon prop design sheet of the Sandstorm Pilgrim's heavy brass staff. Show the staff from two angles, highlighting the intricate ancient bronze wind chimes, wrapped leather grip, and worn metallic textures. Solid, clean dark gray background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0003_sandstorm_pilgrim",
            "char_name": "风沙朝圣者",
            "img_type": "scene",
            "prompt": "Now, draw a stunning, highly detailed landscape scene concept art. An ancient, half-buried mystical sand temple ruins under a massive brewing amber dust storm, with columns glowing with faint gold runes. Ethereal golden sun rays piercing through the thick clouds, casting a dramatic, glorious rim light over the desolate ruins. Cinematic, hyper-realistic, masterpiece, 8k."
        },
        {
            "char_id": "char_0003_sandstorm_pilgrim",
            "char_name": "风沙朝圣者",
            "img_type": "fullBody",
            "prompt": "Now, draw a full-body cinematic splash art of the exact same Sandstorm Pilgrim character from our conversation. He stands barefoot in his signature patched cloak, holding his brass staff, looking forward with wise grey eyes. Solid, extremely dark, low-contrast studio background. Masterpiece, hyper-realistic textures, 8k."
        }
    ]

    neon_plan = [
        {
            "char_id": "char_0004_neon_hacker",
            "char_name": "霓虹潜行者",
            "img_type": "main",
            "prompt": "A masterpiece cyberpunk cinematic concept art of the Neon Shadow Hacker. A cool young East Asian female hacker with highly detailed expressive facial features and asymmetrical glowing pink and purple hair. Her right eye is covered by a sleek, translucent yellow holographic tactical visor. She wears a matte-black premium technical raincoat over a dark bodysuit with subtle glowing circuit lines. She is crouched dynamically on a concrete ledge high above a futuristic neon-drenched metropolis under heavy rain. Her left arm, a highly detailed black carbon-fiber cybernetic prosthetic, is releasing glowing blue neural cables into a hacking node. The background features towering skyscrapers covered in massive holographic advertisements, casting vibrant neon reflections of pink, cyan, and gold onto the wet surfaces and puddles. Photorealistic, unreal engine 5 render, highly detailed, 8k resolution."
        },
        {
            "char_id": "char_0004_neon_hacker",
            "char_name": "霓虹潜行者",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up high-fidelity portrait of the exact same Neon Shadow Hacker character from our conversation. Focus on her face and shoulders, capturing her focused, cool expression and asymmetrical pink and purple hair. Pinned on her technical raincoat, the yellow translucent visor glows softly, casting a warm light onto her cheek, highlighting highly realistic skin details. Solid, extremely dark, low-contrast studio background. Masterpiece, cinematic lighting, 8k."
        },
        {
            "char_id": "char_0004_neon_hacker",
            "char_name": "霓虹潜行者",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same Neon Shadow Hacker character from our conversation. Show her on a solid, clean dark gray background with three different facial expressions side-by-side: one cool and indifferent, one showing a smirk with a raised eyebrow, and one showing a focused, intense gaze while hacking. High-fidelity details, professional character model sheet, masterpiece, 8k."
        },
        {
            "char_id": "char_0004_neon_hacker",
            "char_name": "霓虹潜行者",
            "img_type": "turnaround",
            "prompt": "Now, draw a professional character turnaround model sheet of the exact same Neon Shadow Hacker character from our conversation. Show three full-body views: front, side, and back, standing in a neutral pose. She is wearing her matte-black technical raincoat and tactical visor. Solid, clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0004_neon_hacker",
            "char_name": "霓虹潜行者",
            "img_type": "outfit",
            "prompt": "Now, draw the exact same Neon Shadow Hacker character from our conversation, but wearing an alternative stealth outfit: a tight, high-mobility matte-black stealth bodysuit with glowing violet energy seams, and sleek tactical boots, without her bulky raincoat. Full-body view, standing dynamically on a solid clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0004_neon_hacker",
            "char_name": "霓虹潜行者",
            "img_type": "prop",
            "prompt": "Now, draw a high-fidelity detailed design sheet of the Neon Shadow Hacker's tactical gear: her yellow translucent visor and the carbon-fiber cybernetic prosthetic arm showing its internal glowing blue neural cables. Solid, clean dark gray background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0004_neon_hacker",
            "char_name": "霓虹潜行者",
            "img_type": "scene",
            "prompt": "Now, draw a breathtaking cyberpunk city street scene concept art. High-altitude view of towering skyscrapers covered in massive glowing pink, purple and cyan holographic advertisements under heavy rain. Wet streets and puddles reflecting the vibrant neon lights, creating a highly detailed cinematic atmospheric masterpiece, unreal engine 5 render, 8k."
        },
        {
            "char_id": "char_0004_neon_hacker",
            "char_name": "霓虹潜行者",
            "img_type": "fullBody",
            "prompt": "Now, draw a full-body cinematic splash art of the exact same Neon Shadow Hacker character from our conversation. She stands in her signature raincoat, arm extended, visor glowing, in a cool stealth pose. Solid, extremely dark, low-contrast studio background. Masterpiece, highly detailed, 8k."
        }
    ]
    astrolabe_plan = [
        {
            "char_id": "char_0005_astrolabe_archivist",
            "char_name": "星轨记录员",
            "img_type": "main",
            "prompt": "A masterfully crafted epic fantasy concept art of the Astrolabe Archivist. A slender, handsome young East Asian male scholar with short, messy silver-gray hair. His eyes are elegantly covered with a fine, star-embroidered silk white blindfold. He is wearing elaborate, layered midnight-blue scholar robes adorned with intricate gold-threaded celestial constellations and constellations embroidery. He stands inside a soaring, dark gothic archives library, holding a highly detailed, glowing mechanical gold and silver astrolabe floating above his open palms. Shimmering, ethereal blue-and-gold stardust and glowing cosmic charts float gently around him, passing through hovering crystal magnification lenses. Masterpiece, unreal engine 5 render, highly detailed, 8k resolution."
        },
        {
            "char_id": "char_0005_astrolabe_archivist",
            "char_name": "星轨记录员",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up portrait of the exact same Astrolabe Archivist character from our conversation. Focus on his face and shoulders, capturing his star-embroidered white blindfold, silver-gray hair, and handsome refined features. The soft ethereal blue and gold micro-lights from his floating astrolabe cast gentle stellar glimmers onto his cheeks, highlighting realistic skin details. Solid, extremely dark, low-contrast studio background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0005_astrolabe_archivist",
            "char_name": "星轨记录员",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same Astrolabe Archivist character from our conversation. Show him on a solid, clean dark gray background with three different facial expressions side-by-side: one serene and calm, one with a subtle focused frown as if deep in observation, and one showing a faint, gentle and warm smile. High-fidelity details, professional character model sheet, masterpiece, 8k."
        },
        {
            "char_id": "char_0005_astrolabe_archivist",
            "char_name": "星轨记录员",
            "img_type": "turnaround",
            "prompt": "Now, draw a professional character turnaround model sheet of the exact same Astrolabe Archivist character from our conversation. Show three full-body views: front, side, and back, standing in a neutral pose. He is wearing his midnight-blue scholar robes and star-embroidered white blindfold. Solid, clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0005_astrolabe_archivist",
            "char_name": "星轨记录员",
            "img_type": "outfit",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Astrolabe Archivist (星轨记录员)
Gender / age impression: young man, elegant, scholarly and calm presence
Body shape: slender, tall, graceful scholarly posture
Face: handsome refined features, serene expression
Hair: silver-gray hair, naturally wavy and slightly messy mid-length
Eyes: covered by a fine white silk blindfold with gold star-embroidered patterns
Outfit: layered midnight-blue scholar robes with gold-threaded celestial constellation embroidery, dark cape with silver buckles
Accessories / weapon: a floating mechanical gold and silver astrolabe with rotating celestial gears and glowing blue crystal runes
Color palette: midnight-blue, star gold, cold white, antique brass, glowing stellar blue
Fixed traits that must never change: silver-gray wavy hair, white star-embroidered blindfold, midnight-blue constellation robes, floating gold-silver astrolabe

Current asset goal:
Generate an outfit variant image. Show three different outfits side-by-side: on the left, his default midnight-blue scholar robes; in the middle, his alternative white and gold high-priest ceremonial robes with silver crescent embroidery; on the right, his dark blue leather astro-explorer gear.

Style:
Fantasy character concept art, high-fidelity design sheet.

Composition:
Show three side-by-side full-body views of the same character standing neutrally.

Background:
Plain clean dark gray background."""
        },
        {
            "char_id": "char_0005_astrolabe_archivist",
            "char_name": "星轨记录员",
            "img_type": "prop",
            "prompt": "Now, draw a high-fidelity detailed artifact design sheet of the Astrolabe Archivist's floating mechanical gold and silver astrolabe. Show it from two angles, highlighting the intricate rotating celestial gears, glowing crystal runes, and metallic textures. Solid, clean dark gray background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0005_astrolabe_archivist",
            "char_name": "星轨记录员",
            "img_type": "scene",
            "prompt": "Now, draw a stunning, highly detailed gothic grand archive library scene concept art. A soaring cathedral-like chamber with massive towering dark-wood bookshelves, mystical glowing blue celestial stardust charts and constellations projecting in mid-air, casting a dramatic, glorious rim light over ancient scrolls. Cinematic, hyper-realistic, masterpiece, 8k."
        },
        {
            "char_id": "char_0005_astrolabe_archivist",
            "char_name": "星轨记录员",
            "img_type": "fullBody",
            "prompt": "Now, draw a full-body cinematic splash art of the exact same Astrolabe Archivist character from our conversation. He stands in his signature midnight-blue scholar robes, holding the glowing floating astrolabe, looking serene and powerful. Solid, extremely dark, low-contrast studio background. Masterpiece, highly detailed, 8k."
        },
        {
            "char_id": "char_0005_astrolabe_archivist",
            "char_name": "星轨记录员",
            "img_type": "cover",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Astrolabe Archivist (星轨记录员)
Gender / age impression: young man, elegant, scholarly and calm presence
Body shape: slender, tall, graceful scholarly posture
Face: handsome refined features, serene expression
Hair: silver-gray hair, naturally wavy and slightly messy mid-length
Eyes: covered by a fine white silk blindfold with gold star-embroidered patterns  
Outfit: layered midnight-blue scholar robes with gold-threaded celestial constellation embroidery, dark cape with silver buckles
Accessories / weapon: a floating mechanical gold and silver astrolabe with rotating celestial gears and glowing blue crystal runes
Color palette: midnight-blue, star gold, cold white, antique brass, glowing stellar blue
Fixed traits that must never change: silver-gray wavy hair, white star-embroidered blindfold, midnight-blue constellation robes, floating gold-silver astrolabe

Current asset goal:
Generate a cover image. The Archivist stands holding his glowing astrolabe in a dark library cathedral with celestial charts floating. High polish, vertical framing.

Style:
Fantasy character concept art, cinematic poster, dramatic lighting.

Composition:
Strong vertical framing, centered character, highly detailed, 8k.

Background:
Gothic Cathedral Library under glowing starry constellations."""
        },
        {
            "char_id": "char_0005_astrolabe_archivist",
            "char_name": "星轨记录员",
            "img_type": "moodboard",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Astrolabe Archivist (星轨记录员)
Gender / age impression: young man, elegant, scholarly and calm presence
Body shape: slender, tall, graceful scholarly posture
Face: handsome refined features, serene expression
Hair: silver-gray hair, naturally wavy and slightly messy mid-length
Eyes: covered by a fine white silk blindfold with gold star-embroidered patterns
Outfit: layered midnight-blue scholar robes with gold-threaded celestial constellation embroidery, dark cape with silver buckles
Accessories / weapon: a floating mechanical gold and silver astrolabe with rotating celestial gears and glowing blue crystal runes
Color palette: midnight-blue, star gold, cold white, antique brass, glowing stellar blue
Fixed traits that must never change: silver-gray wavy hair, white star-embroidered blindfold, midnight-blue constellation robes, floating gold-silver astrolabe

Current asset goal:
Generate a moodboard collage. Four panels: constellations on velvet, brass astrolabe gears, silver-gray hair close-up, dusty library archives. Ethereal mystery tone.

Style:
Fantasy design moodboard, rich textures.

Composition:
Clean 4-panel collage layout.

Background:
Dark velvet background."""
        },
        {
            "char_id": "char_0005_astrolabe_archivist",
            "char_name": "星轨记录员",
            "img_type": "sketch",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Astrolabe Archivist (星轨记录员)
Gender / age impression: young man, elegant, scholarly and calm presence
Body shape: slender, tall, graceful scholarly posture
Face: handsome refined features, serene expression
Hair: silver-gray hair, naturally wavy and slightly messy mid-length
Eyes: covered by a fine white silk blindfold with gold star-embroidered patterns
Outfit: layered midnight-blue scholar robes with gold-threaded celestial constellation embroidery, dark cape with silver buckles
Accessories / weapon: a floating mechanical gold and silver astrolabe with rotating celestial gears and glowing blue crystal runes
Color palette: midnight-blue, star gold, cold white, antique brass, glowing stellar blue
Fixed traits that must never change: silver-gray wavy hair, white star-embroidered blindfold, midnight-blue constellation robes, floating gold-silver astrolabe

Current asset goal:
Generate a concept sketch sheet. Traditional concept pencil sketches showing the Archivist in 3 study poses: holding the astrolabe, reading a code, and looking up. Clean hand-drawn lines.

Style:
Monochrome pencil drawings, clean traditional sketch style.

Composition:
3 study sketches on a plain light background.

Background:
Plain light background."""
        },
        {
            "char_id": "char_0005_astrolabe_archivist",
            "char_name": "星轨记录员",
            "img_type": "modelSheet",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Astrolabe Archivist (星轨记录员)
Gender / age impression: young man, elegant, scholarly and calm presence
Body shape: slender, tall, graceful scholarly posture
Face: handsome refined features, serene expression
Hair: silver-gray hair, naturally wavy and slightly messy mid-length
Eyes: covered by a fine white silk blindfold with gold star-embroidered patterns
Outfit: layered midnight-blue scholar robes with gold-threaded celestial constellation embroidery, dark cape with silver buckles
Accessories / weapon: a floating mechanical gold and silver astrolabe with rotating celestial gears and glowing blue crystal runes
Color palette: midnight-blue, star gold, cold white, antique brass, glowing stellar blue
Fixed traits that must never change: silver-gray wavy hair, white star-embroidered blindfold, midnight-blue constellation robes, floating gold-silver astrolabe

Current asset goal:
Generate a standard model sheet. Full-body front, side, and back views of the Archivist standing neutrally in his midnight-blue scholar robes.

Style:
Fantasy character concept art, high-fidelity design sheet, even lighting.

Composition:
Three side-by-side full-body views, no dramatic shadows.

Background:
Plain clean light gray studio background."""
        },
        {
            "char_id": "char_0005_astrolabe_archivist",
            "char_name": "星轨记录员",
            "img_type": "poseSheet",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Astrolabe Archivist (星轨记录员)
Gender / age impression: young man, elegant, scholarly and calm presence
Body shape: slender, tall, graceful scholarly posture
Face: handsome refined features, serene expression
Hair: silver-gray hair, naturally wavy and slightly messy mid-length
Eyes: covered by a fine white silk blindfold with gold star-embroidered patterns
Outfit: layered midnight-blue scholar robes with gold-threaded celestial constellation embroidery, dark cape with silver buckles
Accessories / weapon: a floating mechanical gold and silver astrolabe with rotating celestial gears and glowing blue crystal runes
Color palette: midnight-blue, star gold, cold white, antique brass, glowing stellar blue
Fixed traits that must never change: silver-gray wavy hair, white star-embroidered blindfold, midnight-blue constellation robes, floating gold-silver astrolabe

Current asset goal:
Generate a pose sheet. Show 5 poses of the Archivist on one clean sheet: standing holding astrolabe, casting a star-shield, walking, reading, and sitting in meditation.

Style:
Fantasy action pose reference sheet, consistent body proportions.

Composition:
5 poses arranged cleanly on a solid dark gray background.

Background:
Solid clean dark gray background."""
        },
        {
            "char_id": "char_0005_astrolabe_archivist",
            "char_name": "星轨记录员",
            "img_type": "expressionSheet",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Astrolabe Archivist (星轨记录员)
Gender / age impression: young man, elegant, scholarly and calm presence
Body shape: slender, tall, graceful scholarly posture
Face: handsome refined features, serene expression
Hair: silver-gray hair, naturally wavy and slightly messy mid-length
Eyes: covered by a fine white silk blindfold with gold star-embroidered patterns
Outfit: layered midnight-blue scholar robes with gold-threaded celestial constellation embroidery, dark cape with silver buckles
Accessories / weapon: a floating mechanical gold and silver astrolabe with rotating celestial gears and glowing blue crystal runes
Color palette: midnight-blue, star gold, cold white, antique brass, glowing stellar blue
Fixed traits that must never change: silver-gray wavy hair, white star-embroidered blindfold, midnight-blue constellation robes, floating gold-silver astrolabe

Current asset goal:
Generate an expression sheet. Show 8 bust portraits of the Archivist in a clean grid: serene, focused, gentle smile, closed eyes praying, surprised, weary, warning look, and determination.

Style:
Fantasy character expression grid, consistent facial structure.

Composition:
8 bust portraits arranged in a clean grid.

Background:
Clean dark gray background."""
        },
        {
            "char_id": "char_0005_astrolabe_archivist",
            "char_name": "星轨记录员",
            "img_type": "detailSheet",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Astrolabe Archivist (星轨记录员)
Gender / age impression: young man, elegant, scholarly and calm presence
Body shape: slender, tall, graceful scholarly posture
Face: handsome refined features, serene expression
Hair: silver-gray hair, naturally wavy and slightly messy mid-length
Eyes: covered by a fine white silk blindfold with gold star-embroidered patterns
Outfit: layered midnight-blue scholar robes with gold-threaded celestial constellation embroidery, dark cape with silver buckles
Accessories / weapon: a floating mechanical gold and silver astrolabe with rotating celestial gears and glowing blue crystal runes
Color palette: midnight-blue, star gold, cold white, antique brass, glowing stellar blue
Fixed traits that must never change: silver-gray wavy hair, white star-embroidered blindfold, midnight-blue constellation robes, floating gold-silver astrolabe

Current asset goal:
Generate a detail sheet. Close-up panels showing his eye blindfold pattern, astrolabe gears, gold robe embroidery, and leather codex buckle.

Style:
Fantasy detail sheet, clean design board.

Composition:
Multiple close-up detail panels arranged cleanly.

Background:
Clean light gray background."""
        },
        {
            "char_id": "char_0005_astrolabe_archivist",
            "char_name": "星轨记录员",
            "img_type": "materialPalette",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Astrolabe Archivist (星轨记录员)
Gender / age impression: young man, elegant, scholarly and calm presence
Body shape: slender, tall, graceful scholarly posture
Face: handsome refined features, serene expression
Hair: silver-gray hair, naturally wavy and slightly messy mid-length
Eyes: covered by a fine white silk blindfold with gold star-embroidered patterns
Outfit: layered midnight-blue scholar robes with gold-threaded celestial constellation embroidery, dark cape with silver buckles
Accessories / weapon: a floating mechanical gold and silver astrolabe with rotating celestial gears and glowing blue crystal runes
Color palette: midnight-blue, star gold, cold white, antique brass, glowing stellar blue
Fixed traits that must never change: silver-gray wavy hair, white star-embroidered blindfold, midnight-blue constellation robes, floating gold-silver astrolabe

Current asset goal:
Generate a material and color palette sheet. Show swatches of midnight-blue velvet, silver-white hair sample, glowing blue crystal, and brass metal beside a neutral front view of the character.

Style:
Fantasy material reference sheet, clean design board layout.

Composition:
Character standing next to neatly arranged material swatches and color blocks.

Background:
Plain gray background."""
        },
        {
            "char_id": "char_0005_astrolabe_archivist",
            "char_name": "星轨记录员",
            "img_type": "outfitBreakdown",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Astrolabe Archivist (星轨记录员)
Gender / age impression: young man, elegant, scholarly and calm presence
Body shape: slender, tall, graceful scholarly posture
Face: handsome refined features, serene expression
Hair: silver-gray hair, naturally wavy and slightly messy mid-length
Eyes: covered by a fine white silk blindfold with gold star-embroidered patterns
Outfit: layered midnight-blue scholar robes with gold-threaded celestial constellation embroidery, dark cape with silver buckles
Accessories / weapon: a floating mechanical gold and silver astrolabe with rotating celestial gears and glowing blue crystal runes
Color palette: midnight-blue, star gold, cold white, antique brass, glowing stellar blue
Fixed traits that must never change: silver-gray wavy hair, white star-embroidered blindfold, midnight-blue constellation robes, floating gold-silver astrolabe

Current asset goal:
Generate an outfit breakdown sheet. Show separate layers and components of his gear: outer cape, scholar robe, inner tunic, leather codex, and belt straps.

Style:
Fantasy armor breakdown sheet, clean layout.

Composition:
Clothing and book parts laid out and separated clearly.

Background:
Plain light background."""
        },
        {
            "char_id": "char_0005_astrolabe_archivist",
            "char_name": "星轨记录员",
            "img_type": "damageState",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Astrolabe Archivist (星轨记录员)
Gender / age impression: young man, elegant, scholarly and calm presence
Body shape: slender, tall, graceful scholarly posture
Face: handsome refined features, serene expression
Hair: silver-gray hair, naturally wavy and slightly messy mid-length
Eyes: covered by a fine white silk blindfold with gold star-embroidered patterns
Outfit: layered midnight-blue scholar robes with gold-threaded celestial constellation embroidery, dark cape with silver buckles
Accessories / weapon: a floating mechanical gold and silver astrolabe with rotating celestial gears and glowing blue crystal runes
Color palette: midnight-blue, star gold, cold white, antique brass, glowing stellar blue
Fixed traits that must never change: silver-gray wavy hair, white star-embroidered blindfold, midnight-blue constellation robes, floating gold-silver astrolabe

Current asset goal:
Generate damage state variants. Show 3 full-body versions of the Archivist: clean/default; battle-worn with a dusty, torn robe; and heavily damaged with fading star-light, cracked astrolabe, torn blindfold, and stardust tears flowing.

Style:
Fantasy character damage reference sheet.

Composition:
Show three side-by-side full-body versions of the character.

Background:
Solid clean dark gray background."""
        }
    ]
    
    rust_mechanic_plan = [
        {
            "char_id": "char_0006_rust_mechanic",
            "char_name": "废铁重构师",
            "img_type": "main",
            "prompt": "A masterfully crafted wasteland post-apocalyptic cinematic concept art of the Rustland Reconstructor. A petite but energetic young East Asian woman with highly detailed expressive facial features and messy, wind-blown dark brown short boyish hair. She has a playful smudge of black grease on her left cheek and bright, alert amber eyes. She is wearing a rugged, sleeveless khaki work jumpsuit, with the upper sleeves tied casually around her waist, and a dark tank top underneath. On her right arm, she wears a giant, heavily modified hydraulic mechanical claw made of rusted steel scrap, venting steam from small copper tubes. She stands in a cluttered wasteland workshop filled with half-assembled engines, old metal chains, and hanging welding goggles. Bright industrial sunset light streams through high corrugated metal windows, casting warm orange rim lighting and long shadows, masterpiece, unreal engine 5 render, highly detailed, 8k resolution."
        },
        {
            "char_id": "char_0006_rust_mechanic",
            "char_name": "废铁重构师",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up portrait of the exact same Rustland Reconstructor character from our conversation. Focus on her face and shoulders, capturing her messy short brown hair, the grease smudge on her cheek, and her energetic amber eyes. The warm glow of a welding fire reflects onto her skin. Solid, extremely dark, low-contrast studio background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0006_rust_mechanic",
            "char_name": "废铁重构师",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same Rustland Reconstructor character from our conversation. Show her on a solid, clean dark gray background with three different facial expressions side-by-side: one bright cheerful grin, one focused with a slight pout, and one looking completely surprised/shocked with soot on her nose. High-fidelity details, professional character model sheet, masterpiece, 8k."
        },
        {
            "char_id": "char_0006_rust_mechanic",
            "char_name": "废铁重构师",
            "img_type": "turnaround",
            "prompt": "Now, draw a professional character turnaround model sheet of the exact same Rustland Reconstructor character from our conversation. Show three full-body views: front, side, and back, standing in a neutral pose. She is wearing her khaki work jumpsuit and her giant mechanical claw. Solid, clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0006_rust_mechanic",
            "char_name": "废铁重构师",
            "img_type": "outfit",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Reconstructor (废铁重构师)
Gender / age impression: young woman, energetic, lively and technical presence
Body shape: petite but strong and athletic build, two normal human arms and hands
Face: cute and expressive face, bright amber eyes, smudge of grease on cheeks, realistic human features
Hair: messy and fluffy dark brown boyish short hair
Outfit: khaki sleeveless work jumpsuit with the top half tied around her waist, black tank top underneath, heavy-duty black tactical gloves on both hands
Accessories / weapon: a dust-proof welding goggle on forehead, heavy tool belt filled with wrenches and gears, an old metal canteen on waist
Color palette: rust orange, khaki gray, oil black, amber gold, industrial copper
Fixed traits that must never change: messy dark brown short hair, forehead goggles, two normal human arms, work jumpsuit, grease smudge, black tactical gloves on both hands

Current asset goal:
Generate an outfit variant image. Show three different outfits side-by-side: on the left, her default khaki work jumpsuit; in the middle, her industrial welder outfit (a thick leather welding apron, heavy insulated leather gloves, and a flip-down welding mask); on the right, her mechanical pilot bodysuit (a sleek black and orange bodysuit with carbon-fiber panels). Keep her two normal human arms and black tactical gloves consistent across all three outfits.

Style:
Semi-realistic 3D game concept art, wasteland post-apocalyptic style, high-fidelity design sheet (no 2D anime, no manga, no flat shading).

Composition:
Show three side-by-side full-body views of the same character standing neutrally.

Background:
Plain clean dark gray background."""
        },
        {
            "char_id": "char_0006_rust_mechanic",
            "char_name": "废铁重构师",
            "img_type": "prop",
            "prompt": "Now, draw a high-fidelity detailed prop design sheet of the Rustland Reconstructor's giant mechanical claw. Show it from two angles, highlighting the rusted steel panels, copper piping, exposed pistons, and the thick leather shoulder harness. Solid, clean dark gray background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0006_rust_mechanic",
            "char_name": "废铁重构师",
            "img_type": "scene",
            "prompt": "Now, draw a stunning, highly detailed wasteland workshop scene concept art. Corrugated iron walls, rows of rusted tool shelves filled with gears and wrenches, a half-assembled steam engine on a wooden workbench venting faint steam under a dusty orange twilight sky. Cinematic, hyper-realistic, masterpiece, 8k."
        },
        {
            "char_id": "char_0006_rust_mechanic",
            "char_name": "废铁重构师",
            "img_type": "fullBody",
            "prompt": "Now, draw a full-body cinematic splash art of the exact same Rustland Reconstructor character from our conversation. She stands proudly in her work jumpsuit, holding her mechanical claw, looking confident. Solid, extremely dark, low-contrast studio background. Masterpiece, highly detailed, 8k."
        },
        {
            "char_id": "char_0006_rust_mechanic",
            "char_name": "废铁重构师",
            "img_type": "cover",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Reconstructor (废铁重构师)
Gender / age impression: young woman, energetic, lively and technical presence
Body shape: petite but strong and athletic build, two normal human arms and hands
Face: cute and expressive face, bright amber eyes, smudge of grease on cheeks, realistic human features
Hair: messy and fluffy dark brown boyish short hair
Outfit: khaki sleeveless work jumpsuit with the top half tied around her waist, black tank top underneath, heavy-duty black tactical gloves on both hands
Accessories / weapon: a dust-proof welding goggle on forehead, heavy tool belt filled with wrenches and gears, an old metal canteen on waist
Color palette: rust orange, khaki gray, oil black, amber gold, industrial copper
Fixed traits that must never change: messy dark brown short hair, forehead goggles, two normal human arms, work jumpsuit, grease smudge, black tactical gloves on both hands

Current asset goal:
Generate a cover image. The Reconstructor stands triumphantly on a massive pile of scrap metal and rusted engines, raising a glowing copper wrench with her hand under a yellow smoggy sunset. High polish, vertical framing.

Style:
Semi-realistic 3D game concept art, wasteland post-apocalyptic style, cinematic poster, dramatic lighting, unreal engine 5 render style (no 2D anime, no manga).

Composition:
Strong vertical framing, centered character, highly detailed, 8k.

Background:
Wasteland scrap yard under a smoky industrial twilight."""
        },
        {
            "char_id": "char_0006_rust_mechanic",
            "char_name": "废铁重构师",
            "img_type": "moodboard",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Reconstructor (废铁重构师)
Gender / age impression: young woman, energetic, lively and technical presence
Body shape: petite but strong and athletic build, two normal human arms and hands
Face: cute and expressive face, bright amber eyes, smudge of grease on cheeks, realistic human features
Hair: messy and fluffy dark brown boyish short hair
Outfit: khaki sleeveless work jumpsuit with the top half tied around her waist, black tank top underneath, heavy-duty black tactical gloves on both hands
Accessories / weapon: a dust-proof welding goggle on forehead, heavy tool belt filled with wrenches and gears, an old metal canteen on waist
Color palette: rust orange, khaki gray, oil black, amber gold, industrial copper
Fixed traits that must never change: messy dark brown short hair, forehead goggles, two normal human arms, work jumpsuit, grease smudge, black tactical gloves on both hands

Current asset goal:
Generate a moodboard collage. Four panels: one showing glowing welding sparks, one showing grease-covered iron gears and wrenches, one showing a rusted sheet of metal with orange painted stripes, and one showing a close-up of messy dark brown hair curls. Heavy industrial feel.

Style:
Industrial wasteland concept board, raw textures.

Composition:
Clean 4-panel collage layout.

Background:
Dark steel plate background."""
        },
        {
            "char_id": "char_0006_rust_mechanic",
            "char_name": "废铁重构师",
            "img_type": "sketch",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Reconstructor (废铁重构师)
Gender / age impression: young woman, energetic, lively and technical presence
Body shape: petite but strong and athletic build, two normal human arms and hands
Face: cute and expressive face, bright amber eyes, smudge of grease on cheeks, realistic human features
Hair: messy and fluffy dark brown boyish short hair
Outfit: khaki sleeveless work jumpsuit with the top half tied around her waist, black tank top underneath, heavy-duty black tactical gloves on both hands
Accessories / weapon: a dust-proof welding goggle on forehead, heavy tool belt filled with wrenches and gears, an old metal canteen on waist
Color palette: rust orange, khaki gray, oil black, amber gold, industrial copper
Fixed traits that must never change: messy dark brown short hair, forehead goggles, two normal human arms, work jumpsuit, grease smudge, black tactical gloves on both hands

Current asset goal:
Generate a concept sketch sheet. Traditional concept pencil sketches showing the Reconstructor in 3 study poses: welding a metal joint with sparks flying, laughing with grease on her face, and adjusting the goggles on her forehead. Clean hand-drawn lines.

Style:
Monochrome pencil drawings, clean traditional sketch style.

Composition:
3 study sketches on a plain light background.

Background:
Plain light background."""
        },
        {
            "char_id": "char_0006_rust_mechanic",
            "char_name": "废铁重构师",
            "img_type": "modelSheet",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Reconstructor (废铁重构师)
Gender / age impression: young woman, energetic, lively and technical presence
Body shape: petite but strong and athletic build, two normal human arms and hands
Face: cute and expressive face, bright amber eyes, smudge of grease on cheeks, realistic human features
Hair: messy and fluffy dark brown boyish short hair
Outfit: khaki sleeveless work jumpsuit with the top half tied around her waist, black tank top underneath, heavy-duty black tactical gloves on both hands
Accessories / weapon: a dust-proof welding goggle on forehead, heavy tool belt filled with wrenches and gears, an old metal canteen on waist
Color palette: rust orange, khaki gray, oil black, amber gold, industrial copper
Fixed traits that must never change: messy dark brown short hair, forehead goggles, two normal human arms, work jumpsuit, grease smudge, black tactical gloves on both hands

Current asset goal:
Generate a standard model sheet. Full-body front, side, and back views of the Reconstructor standing neutrally in her khaki work jumpsuit. She has two normal human arms and hands. Make sure no mechanical claw arm is attached to her body.

Style:
Semi-realistic 3D game concept art style, wasteland character concept art, high-fidelity design sheet, even lighting (no 2D anime, no manga).

Composition:
Three side-by-side full-body views, no dramatic shadows.

Background:
Plain clean light gray studio background."""
        },
        {
            "char_id": "char_0006_rust_mechanic",
            "char_name": "废铁重构师",
            "img_type": "poseSheet",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Reconstructor (废铁重构师)
Gender / age impression: young woman, energetic, lively and technical presence
Body shape: petite but strong and athletic build, two normal human arms and hands
Face: cute and expressive face, bright amber eyes, smudge of grease on cheeks, realistic human features
Hair: messy and fluffy dark brown boyish short hair
Outfit: khaki sleeveless work jumpsuit with the top half tied around her waist, black tank top underneath, heavy-duty black tactical gloves on both hands
Accessories / weapon: a dust-proof welding goggle on forehead, heavy tool belt filled with wrenches and gears, an old metal canteen on waist
Color palette: rust orange, khaki gray, oil black, amber gold, industrial copper
Fixed traits that must never change: messy dark brown short hair, forehead goggles, two normal human arms, work jumpsuit, grease smudge, black tactical gloves on both hands

Current asset goal:
Generate a pose sheet. Show 5 poses of the Reconstructor on one clean sheet: holding a wrench over her shoulder, crouching to weld a gear with sparks, running with a toolbox, warning pose protecting her face, and raising her mechanical claw in victory.

Style:
Wasteland action pose reference sheet, consistent body proportions.

Composition:
5 poses arranged cleanly on a solid dark gray background.

Background:
Solid clean dark gray background."""
        },
        {
            "char_id": "char_0006_rust_mechanic",
            "char_name": "废铁重构师",
            "img_type": "expressionSheet",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Reconstructor (废铁重构师)
Gender / age impression: young woman, energetic, lively and technical presence
Body shape: petite but strong and athletic build, two normal human arms and hands
Face: cute and expressive face, bright amber eyes, smudge of grease on cheeks, realistic human features
Hair: messy and fluffy dark brown boyish short hair
Outfit: khaki sleeveless work jumpsuit with the top half tied around her waist, black tank top underneath, heavy-duty black tactical gloves on both hands
Accessories / weapon: a dust-proof welding goggle on forehead, heavy tool belt filled with wrenches and gears, an old metal canteen on waist
Color palette: rust orange, khaki gray, oil black, amber gold, industrial copper
Fixed traits that must never change: messy dark brown short hair, forehead goggles, two normal human arms, work jumpsuit, grease smudge, black tactical gloves on both hands

Current asset goal:
Generate an expression sheet. Show 8 bust portraits of the Reconstructor in a clean grid: lively grin, focused concentration, soot-covered surprise, shouting orders, tired and sweating, crying from heat, cheeky smirk, and proud determination.

Style:
Wasteland character expression grid, consistent facial structure.

Composition:
8 bust portraits arranged in a clean grid.

Background:
Clean dark gray background."""
        },
        {
            "char_id": "char_0006_rust_mechanic",
            "char_name": "废铁重构师",
            "img_type": "detailSheet",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Reconstructor (废铁重构师)
Gender / age impression: young woman, energetic, lively and technical presence
Body shape: petite but strong and athletic build, two normal human arms and hands
Face: cute and expressive face, bright amber eyes, smudge of grease on cheeks, realistic human features
Hair: messy and fluffy dark brown boyish short hair
Outfit: khaki sleeveless work jumpsuit with the top half tied around her waist, black tank top underneath, heavy-duty black tactical gloves on both hands
Accessories / weapon: a dust-proof welding goggle on forehead, heavy tool belt filled with wrenches and gears, an old metal canteen on waist
Color palette: rust orange, khaki gray, oil black, amber gold, industrial copper
Fixed traits that must never change: messy dark brown short hair, forehead goggles, two normal human arms, work jumpsuit, grease smudge, black tactical gloves on both hands

Current asset goal:
Generate a detail sheet. Close-up panels showing her forehead goggles lens, the hydraulic pistons and steam valves of the separate mechanical claw prop, the gears in her toolbox, and the leather strap of her old canteen.

Style:
Semi-realistic 3D game concept art style, wasteland mechanical detail sheet, clean design board (no 2D anime, no manga).

Composition:
Multiple close-up detail panels arranged cleanly.

Background:
Clean light gray background."""
        },
        {
            "char_id": "char_0006_rust_mechanic",
            "char_name": "废铁重构师",
            "img_type": "materialPalette",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Reconstructor (废铁重构师)
Gender / age impression: young woman, energetic, lively and technical presence
Body shape: petite but strong and athletic build, two normal human arms and hands
Face: cute and expressive face, bright amber eyes, smudge of grease on cheeks, realistic human features
Hair: messy and fluffy dark brown boyish short hair
Outfit: khaki sleeveless work jumpsuit with the top half tied around her waist, black tank top underneath, heavy-duty black tactical gloves on both hands
Accessories / weapon: a dust-proof welding goggle on forehead, heavy tool belt filled with wrenches and gears, an old metal canteen on waist
Color palette: rust orange, khaki gray, oil black, amber gold, industrial copper
Fixed traits that must never change: messy dark brown short hair, forehead goggles, two normal human arms, work jumpsuit, grease smudge, black tactical gloves on both hands

Current asset goal:
Generate a material and color palette sheet. Show swatches of rust-orange painted metal plates, dark engine oil slick, amber glass, and heavy-duty glove leather beside a neutral front view of the character.

Style:
Semi-realistic 3D game concept art style, wasteland material reference sheet, clean design board layout (no 2D anime, no manga).

Composition:
Character standing next to neatly arranged material swatches and color blocks.

Background:
Plain gray background."""
        },
        {
            "char_id": "char_0006_rust_mechanic",
            "char_name": "废铁重构师",
            "img_type": "outfitBreakdown",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Reconstructor (废铁重构师)
Gender / age impression: young woman, energetic, lively and technical presence
Body shape: petite but strong and athletic build, two normal human arms and hands
Face: cute and expressive face, bright amber eyes, smudge of grease on cheeks, realistic human features
Hair: messy and fluffy dark brown boyish short hair
Outfit: khaki sleeveless work jumpsuit with the top half tied around her waist, black tank top underneath, heavy-duty black tactical gloves on both hands
Accessories / weapon: a dust-proof welding goggle on forehead, heavy tool belt filled with wrenches and gears, an old metal canteen on waist
Color palette: rust orange, khaki gray, oil black, amber gold, industrial copper
Fixed traits that must never change: messy dark brown short hair, forehead goggles, two normal human arms, work jumpsuit, grease smudge, black tactical gloves on both hands

Current asset goal:
Generate an outfit breakdown sheet. Show separate layers and components of her clothing: khaki work jumpsuit, black tank top, heavy-duty tactical tool belt, mechanical claw harness, and safety boots.

Style:
Wasteland clothing breakdown sheet, clean layout.

Composition:
Clothing and protective gear parts laid out and separated clearly.

Background:
Plain light background."""
        },
        {
            "char_id": "char_0006_rust_mechanic",
            "char_name": "废铁重构师",
            "img_type": "damageState",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Reconstructor (废铁重构师)
Gender / age impression: young woman, energetic, lively and technical presence
Body shape: petite but strong and athletic build, two normal human arms and hands
Face: cute and expressive face, bright amber eyes, smudge of grease on cheeks, realistic human features
Hair: messy and fluffy dark brown boyish short hair
Outfit: khaki sleeveless work jumpsuit with the top half tied around her waist, black tank top underneath, heavy-duty black tactical gloves on both hands
Accessories / weapon: a dust-proof welding goggle on forehead, heavy tool belt filled with wrenches and gears, an old metal canteen on waist
Color palette: rust orange, khaki gray, oil black, amber gold, industrial copper
Fixed traits that must never change: messy dark brown short hair, forehead goggles, two normal human arms, work jumpsuit, grease smudge, black tactical gloves on both hands

Current asset goal:
Generate damage state variants. Show 3 full-body versions of the Reconstructor: clean/default jumpsuit; battle-worn with oil stains and scratches; and heavily damaged with shattered goggles, leaking oil from cracked joints of her mechanical claw, bandaged forehead, and smoking gears.

Style:
Wasteland character damage reference sheet.

Composition:
Show three side-by-side full-body versions of the character.

Background:
Solid clean dark gray background."""
        }
    ]
    
    rust_sniper_plan = [
        {
            "char_id": "char_0007_rust_sniper",
            "char_name": "尘沙潜行卫",
            "img_type": "main",
            "prompt": "A masterpiece wasteland post-apocalyptic cinematic concept art of the Rustland Silent Sniper. A tall, athletic young East Asian male sniper with sharp, focused facial features and wind-blown, messy black short hair. His left eye is deep and cold, while his right eye is replaced by a glowing sapphire-blue gear-like mechanical bionic eye. He wears a dust-proof, worn matte-black hooded trench coat that flows slightly in the wind, over a dark reinforced tactical armor vest. In his gloved hands, he holds a heavy, detailed electromagnetic sniper rifle with glowing blue energy indicator lines and an integrated copper gear mechanism. He is kneeling on a steel watchtower ledge overlooking a sweeping desert wasteland, under a hazy yellow sandstorm sunset. The warm golden rim light illuminates his silhouette, casting long dramatic shadows, photorealistic, octane render, masterpiece, 8k."
        },
        {
            "char_id": "char_0007_rust_sniper",
            "char_name": "尘沙潜行卫",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up portrait of the exact same Rustland Silent Sniper character from our conversation. Focus on his face and shoulders, capturing his messy black hair, the glowing sapphire-blue mechanical eye, and his calm, focused expression. The hood of his windbreaker is pulled up partially. Solid, extremely dark, low-contrast studio background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0007_rust_sniper",
            "char_name": "尘沙潜行卫",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same Rustland Silent Sniper character from our conversation. Show him on a solid, clean dark gray background with three different facial expressions side-by-side: one cold and indifferent, one focused through a scope view with his mechanical eye, and one with a tense grimace during battle. High-fidelity details, professional character model sheet, masterpiece, 8k."
        },
        {
            "char_id": "char_0007_rust_sniper",
            "char_name": "尘沙潜行卫",
            "img_type": "turnaround",
            "prompt": "Now, draw a professional character turnaround model sheet of the exact same Rustland Silent Sniper character from our conversation. Show three full-body views: front, side, and back, standing in a neutral pose. He is wearing his hooded windbreaker and carrying his electromagnetic sniper rifle. Solid, clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0007_rust_sniper",
            "char_name": "尘沙潜行卫",
            "img_type": "outfit",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Silent Sniper (尘沙潜行卫)
Gender / age impression: young man, cold, focused and battle-hardened
Body shape: tall, slender and athletic silhouette with visible scars
Face: sharp facial features, right eye is a glowing blue gears mechanical eye, left eye deep and cold
Hair: messy black short hair windblown
Outfit: dark tactical armor vest under a dust-proof hooded black trench coat, dark survival cargo pants and combat boots
Accessories / weapon: heavy electromagnetic sniper rifle with glowing energy lines, mechanical blue-glowing eye, tactical respirator mask around neck
Color palette: matte black, desert yellow, glowing sapphire blue, rust red
Fixed traits that must never change: hooded black trench coat, blue mechanical eye, heavy electromagnetic sniper rifle, black short hair

Current asset goal:
Generate an outfit variant image. Show three different outfits side-by-side: on the left, his default hooded black windbreaker; in the middle, his desert travel gear (a sandy-camouflage ghillie cloak, light beige tactical wraps, and a dust goggles hanging around his neck); on the right, his heavy assault armor (reinforced steel plates on chest and shoulders, thick bullet-proof vests, and tactical greaves). Keep his blue mechanical bionic eye on all three outfits.

Style:
Semi-realistic 3D game concept art, wasteland post-apocalyptic style, high-fidelity design sheet (no 2D anime, no manga, no flat shading).

Composition:
Show three side-by-side full-body views of the same character standing neutrally.

Background:
Plain clean dark gray background."""
        },
        {
            "char_id": "char_0007_rust_sniper",
            "char_name": "尘沙潜行卫",
            "img_type": "prop",
            "prompt": "Now, draw a high-fidelity detailed weapon prop design sheet of the Silent Sniper's electromagnetic sniper rifle. Show the rifle from two angles, highlighting the scope lens, carbon-fiber barrel, glowing blue energy cells, and copper gears. Solid, clean dark gray background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0007_rust_sniper",
            "char_name": "尘沙潜行卫",
            "img_type": "scene",
            "prompt": "Now, draw a stunning, highly detailed wasteland landscape scene concept art. A high metal watchtower standing alone in a vast desert under a dusty sandstorm yellow sunset. Rusted steel beams and warning yellow plates reflecting the faint sunlight. Cinematic, hyper-realistic, masterpiece, 8k."
        },
        {
            "char_id": "char_0007_rust_sniper",
            "char_name": "尘沙潜行卫",
            "img_type": "fullBody",
            "prompt": "Now, draw a full-body cinematic splash art of the exact same Silent Sniper character from our conversation. He stands alert in his hooded windbreaker, holding his heavy sniper rifle, looking forward with his glowing bionic eye. Solid, extremely dark, low-contrast studio background. Masterpiece, highly detailed, 8k."
        },
        {
            "char_id": "char_0007_rust_sniper",
            "char_name": "尘沙潜行卫",
            "img_type": "cover",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Silent Sniper (尘沙潜行卫)
Gender / age impression: young man, cold, focused and battle-hardened
Body shape: tall, slender and athletic silhouette with visible scars
Face: sharp facial features, right eye is a glowing blue gears mechanical eye, left eye deep and cold
Hair: messy black short hair windblown
Outfit: dark tactical armor vest under a dust-proof hooded black trench coat, dark survival cargo pants and combat boots
Accessories / weapon: heavy electromagnetic sniper rifle with glowing energy lines, mechanical blue-glowing eye, tactical respirator mask around neck
Color palette: matte black, desert yellow, glowing sapphire blue, rust red
Fixed traits that must never change: hooded black trench coat, blue mechanical eye, heavy electromagnetic sniper rifle, black short hair

Current asset goal:
Generate a cover image. The Sniper aims his rifle from a high metal watchtower, looking down over the vast desert ruins. Ethereal yellow sandstorm sky and dramatic poster lighting. High polish, vertical framing.

Style:
Semi-realistic 3D game concept art, wasteland post-apocalyptic style, cinematic poster, dramatic lighting, unreal engine 5 render style (no 2D anime, no manga).

Composition:
Strong vertical framing, rule of thirds, highly detailed, 8k.

Background:
Desert wasteland ruins under a sandy twilight."""
        },
        {
            "char_id": "char_0007_rust_sniper",
            "char_name": "尘沙潜行卫",
            "img_type": "moodboard",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Silent Sniper (尘沙潜行卫)
Gender / age impression: young man, cold, focused and battle-hardened
Body shape: tall, slender and athletic silhouette with visible scars
Face: sharp facial features, right eye is a glowing blue gears mechanical eye, left eye deep and cold
Hair: messy black short hair windblown
Outfit: dark tactical armor vest under a dust-proof hooded black trench coat, dark survival cargo pants and combat boots
Accessories / weapon: heavy electromagnetic sniper rifle with glowing energy lines, mechanical blue-glowing eye, tactical respirator mask around neck
Color palette: matte black, desert yellow, glowing sapphire blue, rust red
Fixed traits that must never change: hooded black trench coat, blue mechanical eye, heavy electromagnetic sniper rifle, black short hair

Current asset goal:
Generate a moodboard collage. Four panels: one showing a close-up of a high-tech sniper scope glass, one showing a glowing blue mechanical lens, one showing sand-swept black ballistic fabric, and one showing a desolate sandstorm horizon. Cool and deadly tone.

Style:
Wasteland combat reference board, detailed textures.

Composition:
Clean 4-panel collage layout.

Background:
Dark carbon-fiber textured background."""
        },
        {
            "char_id": "char_0007_rust_sniper",
            "char_name": "尘沙潜行卫",
            "img_type": "sketch",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Silent Sniper (尘沙潜行卫)
Gender / age impression: young man, cold, focused and battle-hardened
Body shape: tall, slender and athletic silhouette with visible scars
Face: sharp facial features, right eye is a glowing blue gears mechanical eye, left eye deep and cold
Hair: messy black short hair windblown
Outfit: dark tactical armor vest under a dust-proof hooded black trench coat, dark survival cargo pants and combat boots
Accessories / weapon: heavy electromagnetic sniper rifle with glowing energy lines, mechanical blue-glowing eye, tactical respirator mask around neck
Color palette: matte black, desert yellow, glowing sapphire blue, rust red
Fixed traits that must never change: hooded black trench coat, blue mechanical eye, heavy electromagnetic sniper rifle, black short hair

Current asset goal:
Generate a concept sketch sheet. Traditional concept pencil sketches showing the Sniper in 3 study poses: kneeling and aiming his rifle, reloading a clip, and crouching in shadow with his hood up. Clean hand-drawn lines.

Style:
Monochrome pencil drawings, clean traditional sketch style.

Composition:
3 study sketches on a plain light background.

Background:
Plain light background."""
        },
        {
            "char_id": "char_0007_rust_sniper",
            "char_name": "尘沙潜行卫",
            "img_type": "modelSheet",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Silent Sniper (尘沙潜行卫)
Gender / age impression: young man, cold, focused and battle-hardened
Body shape: tall, slender and athletic silhouette with visible scars
Face: sharp facial features, right eye is a glowing blue gears mechanical eye, left eye deep and cold
Hair: messy black short hair windblown
Outfit: dark tactical armor vest under a dust-proof hooded black trench coat, dark survival cargo pants and combat boots
Accessories / weapon: heavy electromagnetic sniper rifle with glowing energy lines, mechanical blue-glowing eye, tactical respirator mask around neck
Color palette: matte black, desert yellow, glowing sapphire blue, rust red
Fixed traits that must never change: hooded black trench coat, blue mechanical eye, heavy electromagnetic sniper rifle, black short hair

Current asset goal:
Generate a standard model sheet. Full-body front, side, and back views of the Sniper standing neutrally in his hooded windbreaker.

Style:
Semi-realistic 3D game concept art style, wasteland character concept art, high-fidelity design sheet, even lighting (no 2D anime, no manga).

Composition:
Three side-by-side full-body views, no dramatic shadows.

Background:
Plain clean light gray studio background."""
        },
        {
            "char_id": "char_0007_rust_sniper",
            "char_name": "尘沙潜行卫",
            "img_type": "poseSheet",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Silent Sniper (尘沙潜行卫)
Gender / age impression: young man, cold, focused and battle-hardened
Body shape: tall, slender and athletic silhouette with visible scars
Face: sharp facial features, right eye is a glowing blue gears mechanical eye, left eye deep and cold
Hair: messy black short hair windblown
Outfit: dark tactical armor vest under a dust-proof hooded black trench coat, dark survival cargo pants and combat boots
Accessories / weapon: heavy electromagnetic sniper rifle with glowing energy lines, mechanical blue-glowing eye, tactical respirator mask around neck
Color palette: matte black, desert yellow, glowing sapphire blue, rust red
Fixed traits that must never change: hooded black trench coat, blue mechanical eye, heavy electromagnetic sniper rifle, black short hair

Current asset goal:
Generate a pose sheet. Show 5 poses of the Sniper on one clean sheet: kneeling and aiming rifle, standing lookout, running under fire, cleaning rifle barrel, and leaning in shadow. Solid clean dark gray background.

Style:
Wasteland action pose reference sheet, consistent body proportions.

Composition:
5 poses arranged cleanly on a solid dark gray background.

Background:
Solid clean dark gray background."""
        },
        {
            "char_id": "char_0007_rust_sniper",
            "char_name": "尘沙潜行卫",
            "img_type": "expressionSheet",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Silent Sniper (尘沙潜行卫)
Gender / age impression: young man, cold, focused and battle-hardened
Body shape: tall, slender and athletic silhouette with visible scars
Face: sharp facial features, right eye is a glowing blue gears mechanical eye, left eye deep and cold
Hair: messy black short hair windblown
Outfit: dark tactical armor vest under a dust-proof hooded black trench coat, dark survival cargo pants and combat boots
Accessories / weapon: heavy electromagnetic sniper rifle with glowing energy lines, mechanical blue-glowing eye, tactical respirator mask around neck
Color palette: matte black, desert yellow, glowing sapphire blue, rust red
Fixed traits that must never change: hooded black trench coat, blue mechanical eye, heavy electromagnetic sniper rifle, black short hair

Current asset goal:
Generate an expression sheet. Show 8 bust portraits of the Sniper in a clean grid: cold stare, focused scope view, battle grimace, silent warning, exhausted and breathing heavily, gritting teeth, cynical smirk, and calm target-locked look.

Style:
Wasteland character expression grid, consistent facial structure.

Composition:
8 bust portraits arranged in a clean grid.

Background:
Clean dark gray background."""
        },
        {
            "char_id": "char_0007_rust_sniper",
            "char_name": "尘沙潜行卫",
            "img_type": "detailSheet",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Silent Sniper (尘沙潜行卫)
Gender / age impression: young man, cold, focused and battle-hardened
Body shape: tall, slender and athletic silhouette with visible scars
Face: sharp facial features, right eye is a glowing blue gears mechanical eye, left eye deep and cold
Hair: messy black short hair windblown
Outfit: dark tactical armor vest under a dust-proof hooded black trench coat, dark survival cargo pants and combat boots
Accessories / weapon: heavy electromagnetic sniper rifle with glowing energy lines, mechanical blue-glowing eye, tactical respirator mask around neck
Color palette: matte black, desert yellow, glowing sapphire blue, rust red
Fixed traits that must never change: hooded black trench coat, blue mechanical eye, heavy electromagnetic sniper rifle, black short hair

Current asset goal:
Generate a detail sheet. Close-up panels showing his bionic blue mechanical eye, the muzzle and rail of his sniper rifle, the glove strap stitching, and the windbreaker hood texture.

Style:
Semi-realistic 3D game concept art style, wasteland mechanical detail sheet, clean design board (no 2D anime, no manga).

Composition:
Multiple close-up detail panels arranged cleanly.

Background:
Clean light gray background."""
        },
        {
            "char_id": "char_0007_rust_sniper",
            "char_name": "尘沙潜行卫",
            "img_type": "materialPalette",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Silent Sniper (尘沙潜行卫)
Gender / age impression: young man, cold, focused and battle-hardened
Body shape: tall, slender and athletic silhouette with visible scars
Face: sharp facial features, right eye is a glowing blue gears mechanical eye, left eye deep and cold
Hair: messy black short hair windblown
Outfit: dark tactical armor vest under a dust-proof hooded black trench coat, dark survival cargo pants and combat boots
Accessories / weapon: heavy electromagnetic sniper rifle with glowing energy lines, mechanical blue-glowing eye, tactical respirator mask around neck
Color palette: matte black, desert yellow, glowing sapphire blue, rust red
Fixed traits that must never change: hooded black trench coat, blue mechanical eye, heavy electromagnetic sniper rifle, black short hair

Current asset goal:
Generate a material and color palette sheet. Show swatches of matte black carbon, desert sand camo fabric, glowing blue bionic lens glass, and rusted steel plate beside a neutral front view of the character.

Style:
Semi-realistic 3D game concept art style, wasteland material reference sheet, clean design board layout (no 2D anime, no manga).

Composition:
Character standing next to neatly arranged material swatches and color blocks.

Background:
Plain gray background."""
        },
        {
            "char_id": "char_0007_rust_sniper",
            "char_name": "尘沙潜行卫",
            "img_type": "outfitBreakdown",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Silent Sniper (尘沙潜行卫)
Gender / age impression: young man, cold, focused and battle-hardened
Body shape: tall, slender and athletic silhouette with visible scars
Face: sharp facial features, right eye is a glowing blue gears mechanical eye, left eye deep and cold
Hair: messy black short hair windblown
Outfit: dark tactical armor vest under a dust-proof hooded black trench coat, dark survival cargo pants and combat boots
Accessories / weapon: heavy electromagnetic sniper rifle with glowing energy lines, mechanical blue-glowing eye, tactical respirator mask around neck
Color palette: matte black, desert yellow, glowing sapphire blue, rust red
Fixed traits that must never change: hooded black trench coat, blue mechanical eye, heavy electromagnetic sniper rifle, black short hair

Current asset goal:
Generate an outfit breakdown sheet. Show separate layers and components of his gear: the hooded windbreaker, the armor vest, the sniper rifle assembly, the tactical respirator mask, and safety gear.

Style:
Wasteland clothing breakdown sheet, clean layout.

Composition:
Clothing and rifle parts laid out and separated clearly.

Background:
Plain light background."""
        },
        {
            "char_id": "char_0007_rust_sniper",
            "char_name": "尘沙潜行卫",
            "img_type": "damageState",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Silent Sniper (尘沙潜行卫)
Gender / age impression: young man, cold, focused and battle-hardened
Body shape: tall, slender and athletic silhouette with visible scars
Face: sharp facial features, right eye is a glowing blue gears mechanical eye, left eye deep and cold
Hair: messy black short hair windblown
Outfit: dark tactical armor vest under a dust-proof hooded black trench coat, dark survival cargo pants and combat boots
Accessories / weapon: heavy electromagnetic sniper rifle with glowing energy lines, mechanical blue-glowing eye, tactical respirator mask around neck
Color palette: matte black, desert yellow, glowing sapphire blue, rust red
Fixed traits that must never change: hooded black trench coat, blue mechanical eye, heavy electromagnetic sniper rifle, black short hair

Current asset goal:
Generate damage state variants. Show 3 full-body versions of the Sniper: clean/default; battle-worn with scratched armor plates and dust; and heavily damaged with cracked bionic eye lens, torn hood, bleeding shoulder wound, and smoke coming from his rifle chamber.

Style:
Wasteland character damage reference sheet.

Composition:
Show three side-by-side full-body versions of the character.

Background:
Solid clean dark gray background."""
        }
    ]
    
    rust_apprentice_plan = [
        {
            "char_id": "char_0008_rust_apprentice",
            "char_name": "重工坊学徒",
            "img_type": "main",
            "prompt": "A masterfully crafted post-apocalyptic steam workshop concept art of the Rustland Workshop Apprentice. A slender but energetic East Asian teenage boy with highly detailed expressive facial features and messy, wind-blown black short hair, with a small smudge of coal dust on his nose. He is wearing a loose, rugged khaki protective work coverall jumpsuit, with the sleeves rolled up, and oversized yellow rubber safety gloves. In his hands, he carries a massive, heavy iron wrench nearly as big as himself. He stands inside a sprawling industrial steam workshop filled with towering brass pipes, venting steam valves, and rows of old wooden tool cabinets. Dramatic warm orange sunset light streams through high windows, casting bright rim lighting on his silhouette, masterpiece, octane render, highly detailed, 8k resolution."
        },
        {
            "char_id": "char_0008_rust_apprentice",
            "char_name": "重工坊学徒",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up portrait of the exact same Workshop Apprentice character from our conversation. Focus on his face and shoulders, capturing his messy black hair, his large curious eyes, and his bright smiling expression with soot on his nose. Large goggles hanging around his neck. Solid, extremely dark, low-contrast studio background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0008_rust_apprentice",
            "char_name": "重工坊学徒",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same Workshop Apprentice character from our conversation. Show him on a solid, clean dark gray background with three different facial expressions side-by-side: one bright cheerful smile, one curious and surprised with wide eyes, and one sweating with a determined grimace while lifting a heavy tool. High-fidelity details, professional character model sheet, masterpiece, 8k."
        },
        {
            "char_id": "char_0008_rust_apprentice",
            "char_name": "重工坊学徒",
            "img_type": "turnaround",
            "prompt": "Now, draw a professional character turnaround model sheet of the exact same Workshop Apprentice character from our conversation. Show three full-body views: front, side, and back, standing in a neutral pose. He is wearing his khaki coveralls, yellow gloves, and carrying his tool satchel. Solid, clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0008_rust_apprentice",
            "char_name": "重工坊学徒",
            "img_type": "outfit",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Workshop Apprentice (重工坊学徒)
Gender / age impression: teenage boy, energetic, curious and youthful
Body shape: slender and agile teenage build
Face: bright and wide eyes, curious expression, soot smudges on nose
Hair: messy black short hair
Outfit: loose khaki protective coveralls work jumpsuit, oversized yellow rubber protective work gloves
Accessories / weapon: large leather tool satchel, a massive heavy iron wrench, protective welding goggles on neck
Color palette: earth brown, copper green, iron gray, warning yellow
Fixed traits that must never change: messy black hair, leather tool satchel, oversized yellow gloves, large iron wrench

Current asset goal:
Generate an outfit variant image. Show three different outfits side-by-side: on the left, his default khaki protective coveralls; in the middle, his heavy smelting suit (a fireproof copper-plated protective suit, thick heat-resistant leather gloves, and a copper visor hood); on the right, his scrap-metal scout gear (a light brown utility vest with steel-reinforced joints and pockets, light tactical shorts). Keep his large tool satchel on all three outfits.

Style:
Semi-realistic 3D game concept art, wasteland post-apocalyptic style, high-fidelity design sheet (no 2D anime, no manga, no flat shading).

Composition:
Show three side-by-side full-body views of the same character standing neutrally.

Background:
Plain clean dark gray background."""
        },
        {
            "char_id": "char_0008_rust_apprentice",
            "char_name": "重工坊学徒",
            "img_type": "prop",
            "prompt": "Now, draw a high-fidelity detailed prop design sheet of the Workshop Apprentice's giant iron wrench and his large leather tool satchel. Show them from two angles, highlighting the metallic wear, copper fittings, and leather texture. Solid, clean dark gray background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0008_rust_apprentice",
            "char_name": "重工坊学徒",
            "img_type": "scene",
            "prompt": "Now, draw a stunning, highly detailed steam workshop scene concept art. A massive industrial chamber filled with towering copper steam pipes, venting steam valves, gears, and hanging chains. Warm sun rays piercing through high dust-covered windows. Cinematic, hyper-realistic, masterpiece, 8k."
        },
        {
            "char_id": "char_0008_rust_apprentice",
            "char_name": "重工坊学徒",
            "img_type": "fullBody",
            "prompt": "Now, draw a full-body cinematic splash art of the exact same Workshop Apprentice character from our conversation. He stands in his protective coveralls, dragging his giant wrench, looking energetic and determined. Solid, extremely dark, low-contrast studio background. Masterpiece, highly detailed, 8k."
        },
        {
            "char_id": "char_0008_rust_apprentice",
            "char_name": "重工坊学徒",
            "img_type": "cover",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Workshop Apprentice (重工坊学徒)
Gender / age impression: teenage boy, energetic, curious and youthful
Body shape: slender and agile teenage build
Face: bright and wide eyes, curious expression, soot smudges on nose
Hair: messy black short hair
Outfit: loose khaki protective coveralls work jumpsuit, oversized yellow rubber protective work gloves
Accessories / weapon: large leather tool satchel, a massive heavy iron wrench, protective welding goggles on neck
Color palette: earth brown, copper green, iron gray, warning yellow
Fixed traits that must never change: messy black hair, leather tool satchel, oversized yellow gloves, large iron wrench

Current asset goal:
Generate a cover image. The Apprentice holds his giant wrench high inside a massive steam workshop filled with pipes. Golden sun rays and venting steam create a dramatic, atmospheric cover art. High polish, vertical framing.

Style:
Semi-realistic 3D game concept art, wasteland post-apocalyptic style, cinematic poster, dramatic lighting, unreal engine 5 render style (no 2D anime, no manga).

Composition:
Strong vertical framing, centered character, highly detailed, 8k.

Background:
Steam-filled industrial workshop."""
        },
        {
            "char_id": "char_0008_rust_apprentice",
            "char_name": "重工坊学徒",
            "img_type": "moodboard",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Workshop Apprentice (重工坊学徒)
Gender / age impression: teenage boy, energetic, curious and youthful
Body shape: slender and agile teenage build
Face: bright and wide eyes, curious expression, soot smudges on nose
Hair: messy black short hair
Outfit: loose khaki protective coveralls work jumpsuit, oversized yellow rubber protective work gloves
Accessories / weapon: large leather tool satchel, a massive heavy iron wrench, protective welding goggles on neck
Color palette: earth brown, copper green, iron gray, warning yellow
Fixed traits that must never change: messy black hair, leather tool satchel, oversized yellow gloves, large iron wrench

Current asset goal:
Generate a moodboard collage. Four panels: one showing oversized yellow rubber work gloves, one showing copper steam pipes venting steam, one showing hand-drawn gear blueprints, and one showing a close-up of a nose with soot smudges. Warm, curious tone.

Style:
Wasteland workshop moodboard, rich textures.

Composition:
Clean 4-panel collage layout.

Background:
Dark wood drafting board background."""
        },
        {
            "char_id": "char_0008_rust_apprentice",
            "char_name": "重工坊学徒",
            "img_type": "sketch",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Workshop Apprentice (重工坊学徒)
Gender / age impression: teenage boy, energetic, curious and youthful
Body shape: slender and agile teenage build
Face: bright and wide eyes, curious expression, soot smudges on nose
Hair: messy black short hair
Outfit: loose khaki protective coveralls work jumpsuit, oversized yellow rubber protective work gloves
Accessories / weapon: large leather tool satchel, a massive heavy iron wrench, protective welding goggles on neck
Color palette: earth brown, copper green, iron gray, warning yellow
Fixed traits that must never change: messy black hair, leather tool satchel, oversized yellow gloves, large iron wrench

Current asset goal:
Generate a concept sketch sheet. Traditional concept pencil sketches showing the Apprentice in 3 study poses: carrying a heavy wrench over his shoulder, looking in curious wonder, and wiping sweat from his forehead. Clean hand-drawn lines.

Style:
Monochrome pencil drawings, clean traditional sketch style.

Composition:
3 study sketches on a plain light background.

Background:
Plain light background."""
        },
        {
            "char_id": "char_0008_rust_apprentice",
            "char_name": "重工坊学徒",
            "img_type": "modelSheet",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Workshop Apprentice (重工坊学徒)
Gender / age impression: teenage boy, energetic, curious and youthful
Body shape: slender and agile teenage build
Face: bright and wide eyes, curious expression, soot smudges on nose
Hair: messy black short hair
Outfit: loose khaki protective coveralls work jumpsuit, oversized yellow rubber protective work gloves
Accessories / weapon: large leather tool satchel, a massive heavy iron wrench, protective welding goggles on neck
Color palette: earth brown, copper green, iron gray, warning yellow
Fixed traits that must never change: messy black hair, leather tool satchel, oversized yellow gloves, large iron wrench

Current asset goal:
Generate a standard model sheet. Full-body front, side, and back views of the Apprentice standing neutrally in his khaki coveralls.

Style:
Semi-realistic 3D game concept art style, wasteland character concept art, high-fidelity design sheet, even lighting (no 2D anime, no manga).

Composition:
Three side-by-side full-body views, no dramatic shadows.

Background:
Plain clean light gray studio background."""
        },
        {
            "char_id": "char_0008_rust_apprentice",
            "char_name": "重工坊学徒",
            "img_type": "poseSheet",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Workshop Apprentice (重工坊学徒)
Gender / age impression: teenage boy, energetic, curious and youthful
Body shape: slender and agile teenage build
Face: bright and wide eyes, curious expression, soot smudges on nose
Hair: messy black short hair
Outfit: loose khaki protective coveralls work jumpsuit, oversized yellow rubber protective work gloves
Accessories / weapon: large leather tool satchel, a massive heavy iron wrench, protective welding goggles on neck
Color palette: earth brown, copper green, iron gray, warning yellow
Fixed traits that must never change: messy black hair, leather tool satchel, oversized yellow gloves, large iron wrench

Current asset goal:
Generate a pose sheet. Show 5 poses of the Apprentice on one clean sheet: dragging a giant wrench, pointing in curiosity, running from a steam boiler explosion, waving his hand, and resting on a metal toolbox. Solid clean dark gray background.

Style:
Wasteland action pose reference sheet, consistent body proportions.

Composition:
5 poses arranged cleanly on a solid dark gray background.

Background:
Solid clean dark gray background."""
        },
        {
            "char_id": "char_0008_rust_apprentice",
            "char_name": "重工坊学徒",
            "img_type": "expressionSheet",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Workshop Apprentice (重工坊学徒)
Gender / age impression: teenage boy, energetic, curious and youthful
Body shape: slender and agile teenage build
Face: bright and wide eyes, curious expression, soot smudges on nose
Hair: messy black short hair
Outfit: loose khaki protective coveralls work jumpsuit, oversized yellow rubber protective work gloves
Accessories / weapon: large leather tool satchel, a massive heavy iron wrench, protective welding goggles on neck
Color palette: earth brown, copper green, iron gray, warning yellow
Fixed traits that must never change: messy black hair, leather tool satchel, oversized yellow gloves, large iron wrench

Current asset goal:
Generate an expression sheet. Show 8 bust portraits of the Apprentice in a clean grid: cheerful smile, curious wonder, startled/shocked, focused concentration, tired/sweating, crying from smoke, warning look, and proud accomplishment.

Style:
Wasteland character expression grid, consistent facial structure.

Composition:
8 bust portraits arranged in a clean grid.

Background:
Clean dark gray background."""
        },
        {
            "char_id": "char_0008_rust_apprentice",
            "char_name": "重工坊学徒",
            "img_type": "detailSheet",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Workshop Apprentice (重工坊学徒)
Gender / age impression: teenage boy, energetic, curious and youthful
Body shape: slender and agile teenage build
Face: bright and wide eyes, curious expression, soot smudges on nose
Hair: messy black short hair
Outfit: loose khaki protective coveralls work jumpsuit, oversized yellow rubber protective work gloves
Accessories / weapon: large leather tool satchel, a massive heavy iron wrench, protective welding goggles on neck
Color palette: earth brown, copper green, iron gray, warning yellow
Fixed traits that must never change: messy black hair, leather tool satchel, oversized yellow gloves, large iron wrench

Current asset goal:
Generate a detail sheet. Close-up panels showing his yellow glove stitching, the head and teeth of his giant iron wrench, the buckle of his leather satchel, and the goggles resting on his neck.

Style:
Semi-realistic 3D game concept art style, wasteland mechanical detail sheet, clean design board (no 2D anime, no manga).

Composition:
Multiple close-up detail panels arranged cleanly.

Background:
Clean light gray background."""
        },
        {
            "char_id": "char_0008_rust_apprentice",
            "char_name": "重工坊学徒",
            "img_type": "materialPalette",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Workshop Apprentice (重工坊学徒)
Gender / age impression: teenage boy, energetic, curious and youthful
Body shape: slender and agile teenage build
Face: bright and wide eyes, curious expression, soot smudges on nose
Hair: messy black short hair
Outfit: loose khaki protective coveralls work jumpsuit, oversized yellow rubber protective work gloves
Accessories / weapon: large leather tool satchel, a massive heavy iron wrench, protective welding goggles on neck
Color palette: earth brown, copper green, iron gray, warning yellow
Fixed traits that must never change: messy black hair, leather tool satchel, oversized yellow gloves, large iron wrench

Current asset goal:
Generate a material and color palette sheet. Show swatches of khaki canvas fabric, copper pipe patina texture, warning yellow rubber, and steel gray metal beside a neutral front view of the character.

Style:
Semi-realistic 3D game concept art style, wasteland material reference sheet, clean design board layout (no 2D anime, no manga).

Composition:
Character standing next to neatly arranged material swatches and color blocks.

Background:
Plain gray background."""
        },
        {
            "char_id": "char_0008_rust_apprentice",
            "char_name": "重工坊学徒",
            "img_type": "outfitBreakdown",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Workshop Apprentice (重工坊学徒)
Gender / age impression: teenage boy, energetic, curious and youthful
Body shape: slender and agile teenage build
Face: bright and wide eyes, curious expression, soot smudges on nose
Hair: messy black short hair
Outfit: loose khaki protective coveralls work jumpsuit, oversized yellow rubber protective work gloves
Accessories / weapon: large leather tool satchel, a massive heavy iron wrench, protective welding goggles on neck
Color palette: earth brown, copper green, iron gray, warning yellow
Fixed traits that must never change: messy black hair, leather tool satchel, oversized yellow gloves, large iron wrench

Current asset goal:
Generate an outfit breakdown sheet. Show separate layers and components of his gear: loose coveralls, leather satchel, giant wrench, neck goggles, and work boots.

Style:
Wasteland clothing breakdown sheet, clean layout.

Composition:
Clothing and protective gear parts laid out and separated clearly.

Background:
Plain light background."""
        },
        {
            "char_id": "char_0008_rust_apprentice",
            "char_name": "重工坊学徒",
            "img_type": "damageState",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Rustland Workshop Apprentice (重工坊学徒)
Gender / age impression: teenage boy, energetic, curious and youthful
Body shape: slender and agile teenage build
Face: bright and wide eyes, curious expression, soot smudges on nose
Hair: messy black short hair
Outfit: loose khaki protective coveralls work jumpsuit, oversized yellow rubber protective work gloves
Accessories / weapon: large leather tool satchel, a massive heavy iron wrench, protective welding goggles on neck
Color palette: earth brown, copper green, iron gray, warning yellow
Fixed traits that must never change: messy black hair, leather tool satchel, oversized yellow gloves, large iron wrench

Current asset goal:
Generate damage state variants. Show 3 full-body versions of the Apprentice: clean/default coveralls; battle-worn with soot stains and grease; and heavily damaged with torn coveralls sleeve, singed black hair, broken goggles glass, and bandaged hand.

Style:
Wasteland character damage reference sheet.

Composition:
Show three side-by-side full-body versions of the character.

Background:
Solid clean dark gray background."""
        }
    ]
    
    rust_nomad_plan = [
        {
            "char_id": "char_0009_rust_nomad",
            "char_name": "荒原流民",
            "img_type": "main",
            "prompt": "A masterfully crafted post-apocalyptic cinematic concept art of the Wasteland Nomad. An emaciated, slightly hunched middle-aged East Asian man with highly detailed weary facial features and sparse, messy black hair mixed with gray strands. His eyes are alert with a deep survival instinct. He wears a tattered, patched sand-gray wind protection cloak, with coarse linen wraps around his legs and feet. On his back, he carries an old, heavily patched copper water flask, and holds a simple weathered wooden walking staff in his hand. He is walking slowly across a desolate, dry desert landscape under a blazing red sun, with sand grains drifting in the hot air. Cinematic, hyper-realistic, masterpiece, 120mm lens, 8k."
        },
        {
            "char_id": "char_0009_rust_nomad",
            "char_name": "荒原流民",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up portrait of the exact same Wasteland Nomad character from our conversation. Focus on his face and shoulders, capturing his weary face with deep wrinkles, sparse gray-black hair, and alert eyes. A ragged cloth face mask hangs around his neck. Solid, extremely dark, low-contrast studio background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0009_rust_nomad",
            "char_name": "荒原流民",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same Wasteland Nomad character from our conversation. Show him on a solid, clean dark gray background with three different facial expressions side-by-side: one weary and calm, one coughing and squinting against the dust, and one displaying a rare, serene and gentle smile of survival. High-fidelity details, professional character model sheet, masterpiece, 8k."
        },
        {
            "char_id": "char_0009_rust_nomad",
            "char_name": "荒原流民",
            "img_type": "turnaround",
            "prompt": "Now, draw a professional character turnaround model sheet of the exact same Wasteland Nomad character from our conversation. Show three full-body views: front, side, and back, standing in a neutral pose. He is wearing his tattered sand-gray cloak and foot wraps. Solid, clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0009_rust_nomad",
            "char_name": "荒原流民",
            "img_type": "outfit",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Wasteland Nomad (荒原流民)
Gender / age impression: middle-aged man, weary, alert and survival-focused
Body shape: thin, emaciated and slightly hunched posture
Face: weathered face with deep wrinkles, weary eyes showing strong survival instinct
Hair: sparse black hair mixed with gray strands
Outfit: tattered and patched sand-gray wind protection cloak, worn linen wraps around feet and legs
Accessories / weapon: a ragged cloth face mask, an old patched copper water flask carried on back, a wooden walking staff
Color palette: sand yellow, dust gray, weathered copper, earth brown
Fixed traits that must never change: patched copper water flask, ragged face mask, sand-gray cloak, emaciated frame

Current asset goal:
Generate an outfit variant image. Show three different outfits side-by-side: on the left, his default tattered sand-gray cloak; in the middle, his heavy desert travel gear (thick leather sheets wrapped over his torso, heavy sand-resistant canvas cloak, and full head wraps); on the right, his scrap-armored scavenger gear (a tattered utility vest reinforced with rusted metal sheet plates and wiring). Keep his walking staff on all three outfits.

Style:
Semi-realistic 3D game concept art, wasteland post-apocalyptic style, high-fidelity design sheet (no 2D anime, no manga, no flat shading).

Composition:
Show three side-by-side full-body views of the same character standing neutrally.

Background:
Plain clean dark gray background."""
        },
        {
            "char_id": "char_0009_rust_nomad",
            "char_name": "荒原流民",
            "img_type": "prop",
            "prompt": "Now, draw a high-fidelity detailed prop design sheet of the Wasteland Nomad's gear: his patched copper water flask and his weathered wooden walking staff. Show them from two angles, highlighting the dents, patches, and worn textures. Solid, clean dark gray background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0009_rust_nomad",
            "char_name": "荒原流民",
            "img_type": "scene",
            "prompt": "Now, draw a stunning, highly detailed landscape scene concept art. A desolate, endless desert wasteland under a blazing red sun, with heat waves warping the horizon and a half-buried rusted container cabin in the sand. Cinematic, hyper-realistic, masterpiece, 8k."
        },
        {
            "char_id": "char_0009_rust_nomad",
            "char_name": "荒原流民",
            "img_type": "fullBody",
            "prompt": "Now, draw a full-body cinematic splash art of the exact same Wasteland Nomad character from our conversation. He stands in his tattered gray cloak, leaning on his walking staff, looking alert. Solid, extremely dark, low-contrast studio background. Masterpiece, highly detailed, 8k."
        },
        {
            "char_id": "char_0009_rust_nomad",
            "char_name": "荒原流民",
            "img_type": "cover",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Wasteland Nomad (荒原流民)
Gender / age impression: middle-aged man, weary, alert and survival-focused
Body shape: thin, emaciated and slightly hunched posture
Face: weathered face with deep wrinkles, weary eyes showing strong survival instinct
Hair: sparse black hair mixed with gray strands
Outfit: tattered and patched sand-gray wind protection cloak, worn linen wraps around feet and legs
Accessories / weapon: a ragged cloth face mask, an old patched copper water flask carried on back, a wooden walking staff
Color palette: sand yellow, dust gray, weathered copper, earth brown
Fixed traits that must never change: patched copper water flask, ragged face mask, sand-gray cloak, emaciated frame

Current asset goal:
Generate a cover image. The Nomad walks with his staff across a vast sandstorm desert toward a setting red sun. Heat waves and sand dust create a dramatic cover layout. High polish, vertical framing.

Style:
Semi-realistic 3D game concept art, wasteland post-apocalyptic style, cinematic poster, dramatic lighting, unreal engine 5 render style (no 2D anime, no manga).

Composition:
Strong vertical framing, centered character, highly detailed, 8k.

Background:
Desolate desert sunset with drifting sand dust."""
        },
        {
            "char_id": "char_0009_rust_nomad",
            "char_name": "荒原流民",
            "img_type": "moodboard",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Wasteland Nomad (荒原流民)
Gender / age impression: middle-aged man, weary, alert and survival-focused
Body shape: thin, emaciated and slightly hunched posture
Face: weathered face with deep wrinkles, weary eyes showing strong survival instinct
Hair: sparse black hair mixed with gray strands
Outfit: tattered and patched sand-gray wind protection cloak, worn linen wraps around feet and legs
Accessories / weapon: a ragged cloth face mask, an old patched copper water flask carried on back, a wooden walking staff
Color palette: sand yellow, dust gray, weathered copper, earth brown
Fixed traits that must never change: patched copper water flask, ragged face mask, sand-gray cloak, emaciated frame

Current asset goal:
Generate a moodboard collage. Four panels: one showing a patched copper water flask surface, one showing sand-swept gray cloak fabric, one showing weathered staff wood carvings, and one showing a dry desert sandstorm horizon. Survival tone.

Style:
Wasteland texture reference board, realistic textures.

Composition:
Clean 4-panel collage layout.

Background:
Sand-swept wood background."""
        },
        {
            "char_id": "char_0009_rust_nomad",
            "char_name": "荒原流民",
            "img_type": "sketch",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Wasteland Nomad (荒原流民)
Gender / age impression: middle-aged man, weary, alert and survival-focused
Body shape: thin, emaciated and slightly hunched posture
Face: weathered face with deep wrinkles, weary eyes showing strong survival instinct
Hair: sparse black hair mixed with gray strands
Outfit: tattered and patched sand-gray wind protection cloak, worn linen wraps around feet and legs
Accessories / weapon: a ragged cloth face mask, an old patched copper water flask carried on back, a wooden walking staff
Color palette: sand yellow, dust gray, weathered copper, earth brown
Fixed traits that must never change: patched copper water flask, ragged face mask, sand-gray cloak, emaciated frame

Current asset goal:
Generate a concept sketch sheet. Traditional concept pencil sketches showing the Nomad in 3 study poses: walking slowly with his staff, drinking from his copper flask, and shivering in the sandstorm wind. Clean hand-drawn lines.

Style:
Monochrome pencil drawings, clean traditional sketch style.

Composition:
3 study sketches on a plain light background.

Background:
Plain light background."""
        },
        {
            "char_id": "char_0009_rust_nomad",
            "char_name": "荒原流民",
            "img_type": "modelSheet",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Wasteland Nomad (荒原流民)
Gender / age impression: middle-aged man, weary, alert and survival-focused
Body shape: thin, emaciated and slightly hunched posture
Face: weathered face with deep wrinkles, weary eyes showing strong survival instinct
Hair: sparse black hair mixed with gray strands
Outfit: tattered and patched sand-gray wind protection cloak, worn linen wraps around feet and legs
Accessories / weapon: a ragged cloth face mask, an old patched copper water flask carried on back, a wooden walking staff
Color palette: sand yellow, dust gray, weathered copper, earth brown
Fixed traits that must never change: patched copper water flask, ragged face mask, sand-gray cloak, emaciated frame

Current asset goal:
Generate a standard model sheet. Full-body front, side, and back views of the Nomad standing neutrally in his tattered sand-gray cloak.

Style:
Semi-realistic 3D game concept art style, wasteland character concept art, high-fidelity design sheet, even lighting (no 2D anime, no manga).

Composition:
Three side-by-side full-body views, no dramatic shadows.

Background:
Plain clean light gray studio background."""
        },
        {
            "char_id": "char_0009_rust_nomad",
            "char_name": "荒原流民",
            "img_type": "poseSheet",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Wasteland Nomad (荒原流民)
Gender / age impression: middle-aged man, weary, alert and survival-focused
Body shape: thin, emaciated and slightly hunched posture
Face: weathered face with deep wrinkles, weary eyes showing strong survival instinct
Hair: sparse black hair mixed with gray strands
Outfit: tattered and patched sand-gray wind protection cloak, worn linen wraps around feet and legs
Accessories / weapon: a ragged cloth face mask, an old patched copper water flask carried on back, a wooden walking staff
Color palette: sand yellow, dust gray, weathered copper, earth brown
Fixed traits that must never change: patched copper water flask, ragged face mask, sand-gray cloak, emaciated frame

Current asset goal:
Generate a pose sheet. Show 5 poses of the Nomad on one clean sheet: walking with walking staff, drinking from flask, crouched in sandstorm shelter, warning gesture, and sitting exhausted on sand. Solid clean dark gray background.

Style:
Wasteland action pose reference sheet, consistent body proportions.

Composition:
5 poses arranged cleanly on a solid dark gray background.

Background:
Solid clean dark gray background."""
        },
        {
            "char_id": "char_0009_rust_nomad",
            "char_name": "荒原流民",
            "img_type": "expressionSheet",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Wasteland Nomad (荒原流民)
Gender / age impression: middle-aged man, weary, alert and survival-focused
Body shape: thin, emaciated and slightly hunched posture
Face: weathered face with deep wrinkles, weary eyes showing strong survival instinct
Hair: sparse black hair mixed with gray strands
Outfit: tattered and patched sand-gray wind protection cloak, worn linen wraps around feet and legs
Accessories / weapon: a ragged cloth face mask, an old patched copper water flask carried on back, a wooden walking staff
Color palette: sand yellow, dust gray, weathered copper, earth brown
Fixed traits that must never change: patched copper water flask, ragged face mask, sand-gray cloak, emaciated frame

Current asset goal:
Generate an expression sheet. Show 8 bust portraits of the Nomad in a clean grid: weary calm, alert fear, crying from thirst, focused survival, coughing in dust, silent despair, rare dry smile, and determined look.

Style:
Wasteland character expression grid, consistent facial structure.

Composition:
8 bust portraits arranged in a clean grid.

Background:
Clean dark gray background."""
        },
        {
            "char_id": "char_0009_rust_nomad",
            "char_name": "荒原流民",
            "img_type": "detailSheet",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Wasteland Nomad (荒原流民)
Gender / age impression: middle-aged man, weary, alert and survival-focused
Body shape: thin, emaciated and slightly hunched posture
Face: weathered face with deep wrinkles, weary eyes showing strong survival instinct
Hair: sparse black hair mixed with gray strands
Outfit: tattered and patched sand-gray wind protection cloak, worn linen wraps around feet and legs
Accessories / weapon: a ragged cloth face mask, an old patched copper water flask carried on back, a wooden walking staff
Color palette: sand yellow, dust gray, weathered copper, earth brown
Fixed traits that must never change: patched copper water flask, ragged face mask, sand-gray cloak, emaciated frame

Current asset goal:
Generate a detail sheet. Close-up panels showing his patched copper flask surface, the ragged face mask texture, the weathered staff wood grain, and the worn foot bindings.

Style:
Wasteland detail sheet, clean design board.

Composition:
Multiple close-up detail panels arranged cleanly.

Background:
Clean light gray background."""
        },
        {
            "char_id": "char_0009_rust_nomad",
            "char_name": "荒原流民",
            "img_type": "materialPalette",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Wasteland Nomad (荒原流民)
Gender / age impression: middle-aged man, weary, alert and survival-focused
Body shape: thin, emaciated and slightly hunched posture
Face: weathered face with deep wrinkles, weary eyes showing strong survival instinct
Hair: sparse black hair mixed with gray strands
Outfit: tattered and patched sand-gray wind protection cloak, worn linen wraps around feet and legs
Accessories / weapon: a ragged cloth face mask, an old patched copper water flask carried on back, a wooden walking staff
Color palette: sand yellow, dust gray, weathered copper, earth brown
Fixed traits that must never change: patched copper water flask, ragged face mask, sand-gray cloak, emaciated frame

Current asset goal:
Generate a material and color palette sheet. Show swatches of sand-gray linen, weathered copper, walking staff wood, and desert sand dust beside a neutral front view of the character.

Style:
Semi-realistic 3D game concept art style, wasteland material reference sheet, clean design board layout (no 2D anime, no manga).

Composition:
Character standing next to neatly arranged material swatches and color blocks.

Background:
Plain gray background."""
        },
        {
            "char_id": "char_0009_rust_nomad",
            "char_name": "荒原流民",
            "img_type": "outfitBreakdown",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Wasteland Nomad (荒原流民)
Gender / age impression: middle-aged man, weary, alert and survival-focused
Body shape: thin, emaciated and slightly hunched posture
Face: weathered face with deep wrinkles, weary eyes showing strong survival instinct
Hair: sparse black hair mixed with gray strands
Outfit: tattered and patched sand-gray wind protection cloak, worn linen wraps around feet and legs
Accessories / weapon: a ragged cloth face mask, an old patched copper water flask carried on back, a wooden walking staff
Color palette: sand yellow, dust gray, weathered copper, earth brown
Fixed traits that must never change: patched copper water flask, ragged face mask, sand-gray cloak, emaciated frame

Current asset goal:
Generate an outfit breakdown sheet. Show separate layers and components of his clothing: tattered cloak, inner wraps, copper flask straps, foot bindings, and face mask.

Style:
Wasteland clothing breakdown sheet, clean layout.

Composition:
Clothing and accessory parts laid out and separated clearly.

Background:
Plain light background."""
        },
        {
            "char_id": "char_0009_rust_nomad",
            "char_name": "荒原流民",
            "img_type": "damageState",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Wasteland Nomad (荒原流民)
Gender / age impression: middle-aged man, weary, alert and survival-focused
Body shape: thin, emaciated and slightly hunched posture
Face: weathered face with deep wrinkles, weary eyes showing strong survival instinct
Hair: sparse black hair mixed with gray strands
Outfit: tattered and patched sand-gray wind protection cloak, worn linen wraps around feet and legs
Accessories / weapon: a ragged cloth face mask, an old patched copper water flask carried on back, a wooden walking staff
Color palette: sand yellow, dust gray, weathered copper, earth brown
Fixed traits that must never change: patched copper water flask, ragged face mask, sand-gray cloak, emaciated frame

Current asset goal:
Generate damage state variants. Show 3 full-body versions of the Nomad: clean/default; battle-worn with dirt and sand layer; and heavily damaged with torn cloak, cracked water flask, bandaged leg, and cuts from sandstorm debris.

Style:
Wasteland character damage reference sheet.

Composition:
Show three side-by-side full-body versions of the character.

Background:
Solid clean dark gray background."""
        }
    ]
    
    rust_warlord_plan = [
        {
            "char_id": "char_0010_rust_warlord",
            "char_name": "铁血军阀",
            "img_type": "main",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Rustland Warlord (铁血军阀)\nGender / age impression: middle-aged man, muscular, scarred face, ruthless expression\nBody shape: massive, muscular, heavily built, imposing silhouette\nFace: scarred face, left eye fierce and cold, right eye is a crude mechanical bionic eye glowing with intense red light\nHair: sparse gray buzz-cut hair\nOutfit: heavy scrap-metal power armor welded from car panels and steel grids, decorated with warning yellow stripes, chains, and bullet belts\nAccessories / weapon: a massive spiked hydraulic power hammer, right hydraulic mechanical cybernetic arm venting black smoke from exhaust pipes\nColor palette: rust red, diesel black, warning stripe yellow, industrial copper\nFixed traits that must never change: spiked power hammer, mechanical right arm with exhaust pipes, red-glowing bionic eye, scrap power armor, scarred face\n\nCurrent asset goal:\nGenerate a main visual key art image. The Warlord stands heroic and tyrannical on a watchtower overlooking a raider camp filled with modified spiked vehicles. Behind him, a giant rusted aircraft carrier wreckage looms under a dusty red sunset.\n\nStyle:\nWasteland post-apocalyptic concept art, high-fidelity character key art, detailed metal and rust rendering, coherent design language, production-ready asset.\n\nComposition:\nFull-body or three-quarter character view, cinematic but readable, the character is the clear focal point.\n\nBackground:\nWasteland raider fortress camp under a dramatic dusty red sunset, casting a glorious warm rim light."
        },
        {
            "char_id": "char_0010_rust_warlord",
            "char_name": "铁血军阀",
            "img_type": "portrait",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Rustland Warlord (铁血军阀)\nGender / age impression: middle-aged man, muscular, scarred face, ruthless expression\nBody shape: massive, muscular, heavily built, imposing silhouette\nFace: scarred face, left eye fierce and cold, right eye is a crude mechanical bionic eye glowing with intense red light\nHair: sparse gray buzz-cut hair\nOutfit: heavy scrap-metal power armor welded from car panels and steel grids, decorated with warning yellow stripes, chains, and bullet belts\nAccessories / weapon: a massive spiked hydraulic power hammer, right hydraulic mechanical cybernetic arm venting black smoke from exhaust pipes\nColor palette: rust red, diesel black, warning stripe yellow, industrial copper\nFixed traits that must never change: spiked power hammer, mechanical right arm with exhaust pipes, red-glowing bionic eye, scrap power armor, scarred face\n\nCurrent asset goal:\nGenerate a portrait / bust image. Focus on his face and shoulders, capturing his scarred face, buzz-cut grey hair, and his glowing red mechanical eye. Soft orange glowing highlights from his camp engines reflect onto his skin.\n\nStyle:\nWasteland post-apocalyptic concept art, high-fidelity portrait, detailed metallic and skin rendering.\n\nComposition:\nBust portrait, face clearly visible, centered or slightly turned, clean framing.\n\nBackground:\nSolid, extremely dark, low-contrast studio background."
        },
        {
            "char_id": "char_0010_rust_warlord",
            "char_name": "铁血军阀",
            "img_type": "expression",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Rustland Warlord (铁血军阀)\nGender / age impression: middle-aged man, muscular, scarred face, ruthless expression\nBody shape: massive, muscular, heavily built, imposing silhouette\nFace: scarred face, left eye fierce and cold, right eye is a crude mechanical bionic eye glowing with intense red light\nHair: sparse gray buzz-cut hair\nOutfit: heavy scrap-metal power armor welded from car panels and steel grids, decorated with warning yellow stripes, chains, and bullet belts\nAccessories / weapon: a massive spiked hydraulic power hammer, right hydraulic mechanical cybernetic arm venting black smoke from exhaust pipes\nColor palette: rust red, diesel black, warning stripe yellow, industrial copper\nFixed traits that must never change: spiked power hammer, mechanical right arm with exhaust pipes, red-glowing bionic eye, scrap power armor, scarred face\n\nCurrent asset goal:\nGenerate an expression variant sheet. Show three different facial expressions side-by-side: one cold and sneering, one letting out a terrifying roaring laugh, and one with narrowed eyes in silent rage.\n\nStyle:\nWasteland post-apocalyptic concept art, high-fidelity character model sheet.\n\nComposition:\nThree bust portraits side-by-side on a plain clean dark gray background.\n\nBackground:\nPlain clean dark gray background."
        },
        {
            "char_id": "char_0010_rust_warlord",
            "char_name": "铁血军阀",
            "img_type": "turnaround",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Rustland Warlord (铁血军阀)\nGender / age impression: middle-aged man, muscular, scarred face, ruthless expression\nBody shape: massive, muscular, heavily built, imposing silhouette\nFace: scarred face, left eye fierce and cold, right eye is a crude mechanical bionic eye glowing with intense red light\nHair: sparse gray buzz-cut hair\nOutfit: heavy scrap-metal power armor welded from car panels and steel grids, decorated with warning yellow stripes, chains, and bullet belts\nAccessories / weapon: a massive spiked hydraulic power hammer, right hydraulic mechanical cybernetic arm venting black smoke from exhaust pipes\nColor palette: rust red, diesel black, warning stripe yellow, industrial copper\nFixed traits that must never change: spiked power hammer, mechanical right arm with exhaust pipes, red-glowing bionic eye, scrap power armor, scarred face\n\nCurrent asset goal:\nGenerate a professional character turnaround model sheet. Show three full-body views: front, side, and back, standing in a neutral pose. He is wearing his scrap-metal power armor and hydraulic arm.\n\nStyle:\nSemi-realistic 3D game concept art, wasteland post-apocalyptic style, high-fidelity design sheet (no 2D anime, no manga, no flat shading).\n\nComposition:\nThree side-by-side full-body views, neutral standing pose, even lighting.\n\nBackground:\nPlain clean dark gray background."
        },
        {
            "char_id": "char_0010_rust_warlord",
            "char_name": "铁血军阀",
            "img_type": "outfit",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Rustland Warlord (铁血军阀)\nGender / age impression: middle-aged man, muscular, scarred face, ruthless expression\nBody shape: massive, muscular, heavily built, imposing silhouette\nFace: scarred face, left eye fierce and cold, right eye is a crude mechanical bionic eye glowing with intense red light\nHair: sparse gray buzz-cut hair\nOutfit: heavy scrap-metal power armor welded from car panels and steel grids, decorated with warning yellow stripes, chains, and bullet belts\nAccessories / weapon: a massive spiked hydraulic power hammer, right hydraulic mechanical cybernetic arm venting black smoke from exhaust pipes\nColor palette: rust red, diesel black, warning stripe yellow, industrial copper\nFixed traits that must never change: spiked power hammer, mechanical right arm with exhaust pipes, red-glowing bionic eye, scrap power armor, scarred face\n\nCurrent asset goal:\nGenerate an outfit variant image. Show three different outfits side-by-side: on the left, his default scrap-metal power armor; in the middle, his casual warlord outfit (a long, grease-stained leather trench coat over a black tank top and combat trousers); on the right, his heavy battle armor (reinforced with extra steel shielding and chainmail layers). Keep his hydraulic bionic arm.\n\nStyle:\nSemi-realistic 3D game concept art, wasteland post-apocalyptic style, high-fidelity design sheet (no 2D anime, no manga, no flat shading).\n\nComposition:\nShow three side-by-side full-body views of the same character standing neutrally.\n\nBackground:\nPlain clean dark gray background."
        },
        {
            "char_id": "char_0010_rust_warlord",
            "char_name": "铁血军阀",
            "img_type": "prop",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Rustland Warlord (铁血军阀)\nGender / age impression: middle-aged man, muscular, scarred face, ruthless expression\nBody shape: massive, muscular, heavily built, imposing silhouette\nFace: scarred face, left eye fierce and cold, right eye is a crude mechanical bionic eye glowing with intense red light\nHair: sparse gray buzz-cut hair\nOutfit: heavy scrap-metal power armor welded from car panels and steel grids, decorated with warning yellow stripes, chains, and bullet belts\nAccessories / weapon: a massive spiked hydraulic power hammer, right hydraulic mechanical cybernetic arm venting black smoke from exhaust pipes\nColor palette: rust red, diesel black, warning stripe yellow, industrial copper\nFixed traits that must never change: spiked power hammer, mechanical right arm with exhaust pipes, red-glowing bionic eye, scrap power armor, scarred face\n\nCurrent asset goal:\nGenerate a prop and weapon reference sheet. Show his massive spiked hydraulic power hammer and his custom diesel-powered mechanical arm from two angles, highlighting exposed pistons, fuel tubes, and grease-stained rusted metal textures.\n\nStyle:\nIndustrial wasteland concept art, high-fidelity weapon design sheet.\n\nComposition:\nDetailed design views from front and side angles, highlighting mechanical details.\n\nBackground:\nPlain clean dark gray background."
        },
        {
            "char_id": "char_0010_rust_warlord",
            "char_name": "铁血军阀",
            "img_type": "scene",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Rustland Warlord (铁血军阀)\nGender / age impression: middle-aged man, muscular, scarred face, ruthless expression\nBody shape: massive, muscular, heavily built, imposing silhouette\nFace: scarred face, left eye fierce and cold, right eye is a crude mechanical bionic eye glowing with intense red light\nHair: sparse gray buzz-cut hair\nOutfit: heavy scrap-metal power armor welded from car panels and steel grids, decorated with warning yellow stripes, chains, and bullet belts\nAccessories / weapon: a massive spiked hydraulic power hammer, right hydraulic mechanical cybernetic arm venting black smoke from exhaust pipes\nColor palette: rust red, diesel black, warning stripe yellow, industrial copper\nFixed traits that must never change: spiked power hammer, mechanical right arm with exhaust pipes, red-glowing bionic eye, scrap power armor, scarred face\n\nCurrent asset goal:\nGenerate a scene image. A fortress built from a massive, decaying aircraft carrier wreckage, surrounded by watchtowers, barbed wire, and spiked desert vehicles. Billowing black smoke and dramatic amber sunset casting long, dark shadows.\n\nStyle:\nPost-apocalyptic environment concept art, cinematic landscape, photorealistic textures.\n\nComposition:\nWide landscape view showing the scale and mood of the raider fort.\n\nBackground:\nThe fortress itself is the subject, under a dusty red twilight sky."
        },
        {
            "char_id": "char_0010_rust_warlord",
            "char_name": "铁血军阀",
            "img_type": "cover",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Rustland Warlord (铁血军阀)\nGender / age impression: middle-aged man, muscular, scarred face, ruthless expression\nBody shape: massive, muscular, heavily built, imposing silhouette\nFace: scarred face, left eye fierce and cold, right eye is a crude mechanical bionic eye glowing with intense red light\nHair: sparse gray buzz-cut hair\nOutfit: heavy scrap-metal power armor welded from car panels and steel grids, decorated with warning yellow stripes, chains, and bullet belts\nAccessories / weapon: a massive spiked hydraulic power hammer, right hydraulic mechanical cybernetic arm venting black smoke from exhaust pipes\nColor palette: rust red, diesel black, warning stripe yellow, industrial copper\nFixed traits that must never change: spiked power hammer, mechanical right arm with exhaust pipes, red-glowing bionic eye, scrap power armor, scarred face\n\nCurrent asset goal:\nGenerate a cover image. The Warlord stands victoriously on a pile of rusted metal scrap, raising his spiked power hammer high, as black smoke billows behind him under a fiery red sunset.\n\nStyle:\nCinematic vertical cover art, dramatic poster lighting, high polish.\n\nComposition:\nStrong vertical framing, heroic pose, clear focal hierarchy.\n\nBackground:\nFiery red wasteland sunset."
        },
        {
            "char_id": "char_0010_rust_warlord",
            "char_name": "铁血军阀",
            "img_type": "moodboard",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Rustland Warlord (铁血军阀)\nGender / age impression: middle-aged man, muscular, scarred face, ruthless expression\nBody shape: massive, muscular, heavily built, imposing silhouette\nFace: scarred face, left eye fierce and cold, right eye is a crude mechanical bionic eye glowing with intense red light\nHair: sparse gray buzz-cut hair\nOutfit: heavy scrap-metal power armor welded from car panels and steel grids, decorated with warning yellow stripes, chains, and bullet belts\nAccessories / weapon: a massive spiked hydraulic power hammer, right hydraulic mechanical cybernetic arm venting black smoke from exhaust pipes\nColor palette: rust red, diesel black, warning stripe yellow, industrial copper\nFixed traits that must never change: spiked power hammer, mechanical right arm with exhaust pipes, red-glowing bionic eye, scrap power armor, scarred face\n\nCurrent asset goal:\nGenerate a moodboard collage. Four panels: one showing rusted iron plates welded together, one showing black motor oil dripping from a copper pipe, one showing a glowing red mechanical lens, and one showing a dry desert wasteland under a fiery sun.\n\nStyle:\nWasteland texture concept board, atmospheric reference sheet.\n\nComposition:\nClean 4-panel collage layout.\n\nBackground:\nDark industrial board background."
        },
        {
            "char_id": "char_0010_rust_warlord",
            "char_name": "铁血军阀",
            "img_type": "sketch",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Rustland Warlord (铁血军阀)\nGender / age impression: middle-aged man, muscular, scarred face, ruthless expression\nBody shape: massive, muscular, heavily built, imposing silhouette\nFace: scarred face, left eye fierce and cold, right eye is a crude mechanical bionic eye glowing with intense red light\nHair: sparse gray buzz-cut hair\nOutfit: heavy scrap-metal power armor welded from car panels and steel grids, decorated with warning yellow stripes, chains, and bullet belts\nAccessories / weapon: a massive spiked hydraulic power hammer, right hydraulic mechanical cybernetic arm venting black smoke from exhaust pipes\nColor palette: rust red, diesel black, warning stripe yellow, industrial copper\nFixed traits that must never change: spiked power hammer, mechanical right arm with exhaust pipes, red-glowing bionic eye, scrap power armor, scarred face\n\nCurrent asset goal:\nGenerate a concept sketch sheet. Show three pencil drawings of the Warlord: swinging his hammer, shouting orders, and tuning his mechanical arm.\n\nStyle:\nMonochrome pencil drawings, clean hand-drawn lines, traditional sketch style.\n\nComposition:\n3 study sketches on a plain light background.\n\nBackground:\nPlain light background."
        },
        {
            "char_id": "char_0010_rust_warlord",
            "char_name": "铁血军阀",
            "img_type": "fullBody",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Rustland Warlord (铁血军阀)\nGender / age impression: middle-aged man, muscular, scarred face, ruthless expression\nBody shape: massive, muscular, heavily built, imposing silhouette\nFace: scarred face, left eye fierce and cold, right eye is a crude mechanical bionic eye glowing with intense red light\nHair: sparse gray buzz-cut hair\nOutfit: heavy scrap-metal power armor welded from car panels and steel grids, decorated with warning yellow stripes, chains, and bullet belts\nAccessories / weapon: a massive spiked hydraulic power hammer, right hydraulic mechanical cybernetic arm venting black smoke from exhaust pipes\nColor palette: rust red, diesel black, warning stripe yellow, industrial copper\nFixed traits that must never change: spiked power hammer, mechanical right arm with exhaust pipes, red-glowing bionic eye, scrap power armor, scarred face\n\nCurrent asset goal:\nGenerate a full-body standing character art. The Warlord stands triumphantly in his scrap-metal power armor, holding his spiked hydraulic hammer, his red mechanical eye glowing.\n\nStyle:\nWasteland character concept art, high-fidelity full-body splash.\n\nComposition:\nFull body visible from head to toe, standing pose, clear silhouette.\n\nBackground:\nSolid, extremely dark, low-contrast studio background."
        },
        {
            "char_id": "char_0010_rust_warlord",
            "char_name": "铁血军阀",
            "img_type": "modelSheet",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Rustland Warlord (铁血军阀)\nGender / age impression: middle-aged man, muscular, scarred face, ruthless expression\nBody shape: massive, muscular, heavily built, imposing silhouette\nFace: scarred face, left eye fierce and cold, right eye is a crude mechanical bionic eye glowing with intense red light\nHair: sparse gray buzz-cut hair\nOutfit: heavy scrap-metal power armor welded from car panels and steel grids, decorated with warning yellow stripes, chains, and bullet belts\nAccessories / weapon: a massive spiked hydraulic power hammer, right hydraulic mechanical cybernetic arm venting black smoke from exhaust pipes\nColor palette: rust red, diesel black, warning stripe yellow, industrial copper\nFixed traits that must never change: spiked power hammer, mechanical right arm with exhaust pipes, red-glowing bionic eye, scrap power armor, scarred face\n\nCurrent asset goal:\nGenerate a standard model sheet / character design reference. Full-body front, side, and back views of the Warlord standing neutrally in his scrap-metal power armor.\n\nStyle:\nSemi-realistic 3D game concept art style, wasteland character concept art, high-fidelity design sheet, even lighting (no 2D anime, no manga).\n\nComposition:\nThree side-by-side full-body views, no dramatic shadows.\n\nBackground:\nPlain clean light gray studio background."
        },
        {
            "char_id": "char_0010_rust_warlord",
            "char_name": "铁血军阀",
            "img_type": "poseSheet",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Rustland Warlord (铁血军阀)\nGender / age impression: middle-aged man, muscular, scarred face, ruthless expression\nBody shape: massive, muscular, heavily built, imposing silhouette\nFace: scarred face, left eye fierce and cold, right eye is a crude mechanical bionic eye glowing with intense red light\nHair: sparse gray buzz-cut hair\nOutfit: heavy scrap-metal power armor welded from car panels and steel grids, decorated with warning yellow stripes, chains, and bullet belts\nAccessories / weapon: a massive spiked hydraulic power hammer, right hydraulic mechanical cybernetic arm venting black smoke from exhaust pipes\nColor palette: rust red, diesel black, warning stripe yellow, industrial copper\nFixed traits that must never change: spiked power hammer, mechanical right arm with exhaust pipes, red-glowing bionic eye, scrap power armor, scarred face\n\nCurrent asset goal:\nGenerate a pose sheet. Show 5 poses of the Warlord on one clean sheet: idle standing, walking forward heavily, swinging his hydraulic hammer down, raising his mechanical arm to block an attack, and sitting on a scrap metal throne.\n\nStyle:\nWasteland action pose reference sheet, consistent body proportions.\n\nComposition:\n5 poses arranged cleanly on a solid dark gray background.\n\nBackground:\nSolid clean dark gray background."
        },
        {
            "char_id": "char_0010_rust_warlord",
            "char_name": "铁血军阀",
            "img_type": "expressionSheet",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Rustland Warlord (铁血军阀)\nGender / age impression: middle-aged man, muscular, scarred face, ruthless expression\nBody shape: massive, muscular, heavily built, imposing silhouette\nFace: scarred face, left eye fierce and cold, right eye is a crude mechanical bionic eye glowing with intense red light\nHair: sparse gray buzz-cut hair\nOutfit: heavy scrap-metal power armor welded from car panels and steel grids, decorated with warning yellow stripes, chains, and bullet belts\nAccessories / weapon: a massive spiked hydraulic power hammer, right hydraulic mechanical cybernetic arm venting black smoke from exhaust pipes\nColor palette: rust red, diesel black, warning stripe yellow, industrial copper\nFixed traits that must never change: spiked power hammer, mechanical right arm with exhaust pipes, red-glowing bionic eye, scrap power armor, scarred face\n\nCurrent asset goal:\nGenerate an expression sheet. Show 8 bust portraits of the Warlord (without helmet) in a clean grid: calm, menacing sneer, furious roar, mocking laugh, focused aiming with bionic eye, exhausted in battle, look of warning, and victory smirk.\n\nStyle:\nWasteland character expression grid, consistent facial structure.\n\nComposition:\n8 bust portraits arranged in a clean grid.\n\nBackground:\nClean dark gray background."
        },
        {
            "char_id": "char_0010_rust_warlord",
            "char_name": "铁血军阀",
            "img_type": "detailSheet",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Rustland Warlord (铁血军阀)\nGender / age impression: middle-aged man, muscular, scarred face, ruthless expression\nBody shape: massive, muscular, heavily built, imposing silhouette\nFace: scarred face, left eye fierce and cold, right eye is a crude mechanical bionic eye glowing with intense red light\nHair: sparse gray buzz-cut hair\nOutfit: heavy scrap-metal power armor welded from car panels and steel grids, decorated with warning yellow stripes, chains, and bullet belts\nAccessories / weapon: a massive spiked hydraulic power hammer, right hydraulic mechanical cybernetic arm venting black smoke from exhaust pipes\nColor palette: rust red, diesel black, warning stripe yellow, industrial copper\nFixed traits that must never change: spiked power hammer, mechanical right arm with exhaust pipes, red-glowing bionic eye, scrap power armor, scarred face\n\nCurrent asset goal:\nGenerate a detail sheet. Close-up panels showing his glowing red mechanical eye, the welding seams and warning yellow stripes on his scrap metal armor, the fuel tube and exhaust pipes of his cybernetic arm, the spikes on his hydraulic hammer, and the gear gears in his joints.\n\nStyle:\nSemi-realistic 3D game concept art style, wasteland mechanical detail sheet, clean design board (no 2D anime, no manga).\n\nComposition:\nMultiple close-up detail panels arranged cleanly.\n\nBackground:\nClean light gray background."
        },
        {
            "char_id": "char_0010_rust_warlord",
            "char_name": "铁血军阀",
            "img_type": "materialPalette",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Rustland Warlord (铁血军阀)\nGender / age impression: middle-aged man, muscular, scarred face, ruthless expression\nBody shape: massive, muscular, heavily built, imposing silhouette\nFace: scarred face, left eye fierce and cold, right eye is a crude mechanical bionic eye glowing with intense red light\nHair: sparse gray buzz-cut hair\nOutfit: heavy scrap-metal power armor welded from car panels and steel grids, decorated with warning yellow stripes, chains, and bullet belts\nAccessories / weapon: a massive spiked hydraulic power hammer, right hydraulic mechanical cybernetic arm venting black smoke from exhaust pipes\nColor palette: rust red, diesel black, warning stripe yellow, industrial copper\nFixed traits that must never change: spiked power hammer, mechanical right arm with exhaust pipes, red-glowing bionic eye, scrap power armor, scarred face\n\nCurrent asset goal:\nGenerate a material and color palette sheet. Show swatches of rusted steel plates, black diesel oil texture, yellow warning painted metal, industrial copper piping, and glowing red lens glass beside a neutral front view of the character.\n\nStyle:\nSemi-realistic 3D game concept art style, wasteland material reference sheet, clean design board layout (no 2D anime, no manga).\n\nComposition:\nCharacter standing next to neatly arranged material swatches and color blocks.\n\nBackground:\nPlain gray background."
        },
        {
            "char_id": "char_0010_rust_warlord",
            "char_name": "铁血军阀",
            "img_type": "outfitBreakdown",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Rustland Warlord (铁血军阀)\nGender / age impression: middle-aged man, muscular, scarred face, ruthless expression\nBody shape: massive, muscular, heavily built, imposing silhouette\nFace: scarred face, left eye fierce and cold, right eye is a crude mechanical bionic eye glowing with intense red light\nHair: sparse gray buzz-cut hair\nOutfit: heavy scrap-metal power armor welded from car panels and steel grids, decorated with warning yellow stripes, chains, and bullet belts\nAccessories / weapon: a massive spiked hydraulic power hammer, right hydraulic mechanical cybernetic arm venting black smoke from exhaust pipes\nColor palette: rust red, diesel black, warning stripe yellow, industrial copper\nFixed traits that must never change: spiked power hammer, mechanical right arm with exhaust pipes, red-glowing bionic eye, scrap power armor, scarred face\n\nCurrent asset goal:\nGenerate an outfit breakdown sheet. Show separate layers and components of his gear: the scrap-metal chest plate, the shoulder pauldrons, the leg greaves, the hydraulic mechanical arm assembly, the bullet belt, and the spiked hammer.\n\nStyle:\nWasteland armor breakdown sheet, clean layout.\n\nComposition:\nArmor and weapon parts laid out and separated clearly.\n\nBackground:\nPlain light background."
        },
        {
            "char_id": "char_0010_rust_warlord",
            "char_name": "铁血军阀",
            "img_type": "damageState",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Rustland Warlord (铁血军阀)\nGender / age impression: middle-aged man, muscular, scarred face, ruthless expression\nBody shape: massive, muscular, heavily built, imposing silhouette\nFace: scarred face, left eye fierce and cold, right eye is a crude mechanical bionic eye glowing with intense red light\nHair: sparse gray buzz-cut hair\nOutfit: heavy scrap-metal power armor welded from car panels and steel grids, decorated with warning yellow stripes, chains, and bullet belts\nAccessories / weapon: a massive spiked hydraulic power hammer, right hydraulic mechanical cybernetic arm venting black smoke from exhaust pipes\nColor palette: rust red, diesel black, warning stripe yellow, industrial copper\nFixed traits that must never change: spiked power hammer, mechanical right arm with exhaust pipes, red-glowing bionic eye, scrap power armor, scarred face\n\nCurrent asset goal:\nGenerate damage state variants. Show 3 full-body versions of the Warlord: clean/default armor; battle-worn with tattered plates and soot stains; and heavily damaged with shattered mechanical eye, tattered cape, oil leaking from cracked mechanical joints, and sparks flying.\n\nStyle:\nWasteland character damage reference sheet.\n\nComposition:\nShow three side-by-side full-body versions of the character.\n\nBackground:\nSolid clean dark gray background."
        }
    ]


    rust_scavenger_queen_plan = [
        {
            "char_id": "char_0011_scavenger_queen",
            "char_name": "拾荒女皇",
            "img_type": "main",
            "prompt": "A masterpiece post-apocalyptic cinematic concept art of the Scavenger Queen. A slender and agile young East Asian woman with a cunning and sharp gaze. She has short, styled silver hair with glowing neon-green dyed tips. She wears a dark leather tunic reinforced with copper scales, underneath a worn, chemical-resistant dark green hooded hazard cloak that flows in the wind. Her lower face is covered by a detailed brass respirator mask with three circular filters. She stands dynamically amidst the towering rusted ruins of a ruined chemical factory. In her hands, she aims a detailed custom folding metallic crossbow that glows with bubbling, radioactive neon-green liquid vials. The background features acid rain falling through thick yellow clouds, with green toxic puddles reflecting a bleak setting sun casting a sickly warm glow. Cinematic, hyper-realistic, masterpiece, 8k."
        },
        {
            "char_id": "char_0011_scavenger_queen",
            "char_name": "拾荒女皇",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up portrait of the exact same Scavenger Queen character from our conversation. Focus on her face and shoulders, capturing her short silver hair with green tips, her cunning green eyes, and her gas mask. The hood of her dark green cloak is pulled over her head. Solid, extremely dark, low-contrast studio background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0011_scavenger_queen",
            "char_name": "拾荒女皇",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same Scavenger Queen character from our conversation. Show her (without mask) on a solid, clean dark gray background with three different facial expressions side-by-side: one with a mocking smirk, one showing focused aim with narrowed green eyes, and one with an angry, commanding shout. High-fidelity details, professional character model sheet, masterpiece, 8k."
        },
        {
            "char_id": "char_0011_scavenger_queen",
            "char_name": "拾荒女皇",
            "img_type": "turnaround",
            "prompt": "Now, draw a professional character turnaround model sheet of the exact same Scavenger Queen character from our conversation. Show three full-body views: front, side, and back, standing in a neutral pose. She is wearing her green hooded hazard cloak and brass respirator mask. Solid, clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0011_scavenger_queen",
            "char_name": "拾荒女皇",
            "img_type": "outfit",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Scavenger Queen (拾荒女皇)
Gender / age impression: young woman, cunning, sharp and deadly presence
Body shape: tall and slender, agile feline posture
Face: handsome face, cunning green eyes, mocking smirk
Hair: short silver-gray hair with neon-green dyed hair tips
Outfit: chemical-resistant dark green hooded cape over tight black leather armor reinforced with copper scales
Accessories / weapon: a brass respirator mask with three circular filters, a custom folding mechanical crossbow glowing with neon-green acid vials
Color palette: neon green, dark green, brass copper, leather brown, silver-gray
Fixed traits that must never change: silver-green hair, brass respirator mask, dark green hooded cape, neon-green acid crossbow

Current asset goal:
Generate an outfit variant image. Show three different outfits side-by-side: on the left, her default dark green hooded cape; in the middle, her alternative hazard jumpsuit (a tight-fitting black environmental hazard jumpsuit, reinforced knee pads, and a glowing green chemical canister strapped to her back, without her cape); on the right, her scavenger ceremonial armor (adorned with bone trophies, spikes, and copper plates). Keep her gas mask on all three outfits.

Style:
Semi-realistic 3D game concept art, wasteland post-apocalyptic style, high-fidelity design sheet (no 2D anime, no manga, no flat shading).

Composition:
Show three side-by-side full-body views of the same character standing neutrally.

Background:
Plain clean dark gray background."""
        },
        {
            "char_id": "char_0011_scavenger_queen",
            "char_name": "拾荒女皇",
            "img_type": "prop",
            "prompt": "Now, draw a high-fidelity detailed design sheet of the Scavenger Queen's weapons: her custom folding metallic crossbow and a set of glass vials filled with bubbling neon-green acid. Show them from two angles, highlighting the metallic wear and glowing green liquid. Solid, clean dark gray background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0011_scavenger_queen",
            "char_name": "拾荒女皇",
            "img_type": "scene",
            "prompt": "Now, draw a stunning, highly detailed post-apocalyptic chemical factory ruins scene concept art. Towering corroded distillation towers, glowing toxic green acid swamps, acid rain falling from yellow chemical smog under a bleak setting sun. Cinematic, hyper-realistic, masterpiece, 8k."
        },
        {
            "char_id": "char_0011_scavenger_queen",
            "char_name": "拾荒女皇",
            "img_type": "fullBody",
            "prompt": "Now, draw a full-body cinematic splash art of the exact same Scavenger Queen character from our conversation. She stands agilely in her green hooded cloak, holding her folding crossbow, her green eyes glowing slightly in the toxic haze. Solid, extremely dark, low-contrast studio background. Masterpiece, highly detailed, 8k."
        },
        {
            "char_id": "char_0011_scavenger_queen",
            "char_name": "拾荒女皇",
            "img_type": "cover",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Scavenger Queen (拾荒女皇)
Gender / age impression: young woman, cunning, sharp and deadly presence
Body shape: tall and slender, agile feline posture
Face: handsome face, cunning green eyes, mocking smirk
Hair: short silver-gray hair with neon-green dyed hair tips
Outfit: chemical-resistant dark green hooded cape over tight black leather armor reinforced with copper scales
Accessories / weapon: a brass respirator mask with three circular filters, a custom folding mechanical crossbow glowing with neon-green acid vials
Color palette: neon green, dark green, brass copper, leather brown, silver-gray
Fixed traits that must never change: silver-green hair, brass respirator mask, dark green hooded cape, neon-green acid crossbow

Current asset goal:
Generate a cover image. The Queen stands victoriously on a rusted tower platform aiming her acid crossbow over a toxic green swamp ruins under acid rain. High polish, vertical framing.

Style:
Semi-realistic 3D game concept art, wasteland post-apocalyptic style, cinematic poster, dramatic lighting, unreal engine 5 render style (no 2D anime, no manga).

Composition:
Strong vertical framing, centered character, highly detailed, 8k.

Background:
Toxic chemical ruins with neon-green swamp under a yellow twilight."""
        },
        {
            "char_id": "char_0011_scavenger_queen",
            "char_name": "拾荒女皇",
            "img_type": "moodboard",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Scavenger Queen (拾荒女皇)
Gender / age impression: young woman, cunning, sharp and deadly presence
Body shape: tall and slender, agile feline posture
Face: handsome face, cunning green eyes, mocking smirk
Hair: short silver-gray hair with neon-green dyed hair tips
Outfit: chemical-resistant dark green hooded cape over tight black leather armor reinforced with copper scales
Accessories / weapon: a brass respirator mask with three circular filters, a custom folding mechanical crossbow glowing with neon-green acid vials
Color palette: neon green, dark green, brass copper, leather brown, silver-gray
Fixed traits that must never change: silver-green hair, brass respirator mask, dark green hooded cape, neon-green acid crossbow

Current asset goal:
Generate a moodboard collage. Four panels: one showing glowing neon-green acid vials, one showing brass gas mask filters, one showing dark green hooded fabric, and one showing short silver hair with green tips. Toxic survival feel.

Style:
Wasteland chemical moodboard, rich textures.

Composition:
Clean 4-panel collage layout.

Background:
Corroded iron plate background."""
        },
        {
            "char_id": "char_0011_scavenger_queen",
            "char_name": "拾荒女皇",
            "img_type": "sketch",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Scavenger Queen (拾荒女皇)
Gender / age impression: young woman, cunning, sharp and deadly presence
Body shape: tall and slender, agile feline posture
Face: handsome face, cunning green eyes, mocking smirk
Hair: short silver-gray hair with neon-green dyed hair tips
Outfit: chemical-resistant dark green hooded cape over tight black leather armor reinforced with copper scales
Accessories / weapon: a brass respirator mask with three circular filters, a custom folding mechanical crossbow glowing with neon-green acid vials
Color palette: neon green, dark green, brass copper, leather brown, silver-gray
Fixed traits that must never change: silver-green hair, brass respirator mask, dark green hooded cape, neon-green acid crossbow

Current asset goal:
Generate a concept sketch sheet. Traditional concept pencil sketches showing the Queen in 3 study poses: aiming her crossbow, adjusting her respirator mask, and looking down with a cynical smirk. Clean hand-drawn lines.

Style:
Monochrome pencil drawings, clean traditional sketch style.

Composition:
3 study sketches on a plain light background.

Background:
Plain light background."""
        },
        {
            "char_id": "char_0011_scavenger_queen",
            "char_name": "拾荒女皇",
            "img_type": "modelSheet",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Scavenger Queen (拾荒女皇)
Gender / age impression: young woman, cunning, sharp and deadly presence
Body shape: tall and slender, agile feline posture
Face: handsome face, cunning green eyes, mocking smirk
Hair: short silver-gray hair with neon-green dyed hair tips
Outfit: chemical-resistant dark green hooded cape over tight black leather armor reinforced with copper scales
Accessories / weapon: a brass respirator mask with three circular filters, a custom folding mechanical crossbow glowing with neon-green acid vials
Color palette: neon green, dark green, brass copper, leather brown, silver-gray
Fixed traits that must never change: silver-green hair, brass respirator mask, dark green hooded cape, neon-green acid crossbow

Current asset goal:
Generate a standard model sheet. Full-body front, side, and back views of the Queen standing neutrally in her green hooded cape.

Style:
Semi-realistic 3D game concept art style, wasteland character concept art, high-fidelity design sheet, even lighting (no 2D anime, no manga).

Composition:
Three side-by-side full-body views, no dramatic shadows.

Background:
Plain clean light gray studio background."""
        },
        {
            "char_id": "char_0011_scavenger_queen",
            "char_name": "拾荒女皇",
            "img_type": "poseSheet",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Scavenger Queen (拾荒女皇)
Gender / age impression: young woman, cunning, sharp and deadly presence
Body shape: tall and slender, agile feline posture
Face: handsome face, cunning green eyes, mocking smirk
Hair: short silver-gray hair with neon-green dyed hair tips
Outfit: chemical-resistant dark green hooded cape over tight black leather armor reinforced with copper scales
Accessories / weapon: a brass respirator mask with three circular filters, a custom folding mechanical crossbow glowing with neon-green acid vials
Color palette: neon green, dark green, brass copper, leather brown, silver-gray
Fixed traits that must never change: silver-green hair, brass respirator mask, dark green hooded cape, neon-green acid crossbow

Current asset goal:
Generate a pose sheet. Show 5 poses of the Queen on one clean sheet: aiming her crossbow, crouching in ambush, throwing an acid bottle, standing triumphantly, and adjusting her gas mask. Solid clean dark gray background.

Style:
Wasteland action pose reference sheet, consistent body proportions.

Composition:
5 poses arranged cleanly on a solid dark gray background.

Background:
Solid clean dark gray background."""
        },
        {
            "char_id": "char_0011_scavenger_queen",
            "char_name": "拾荒女皇",
            "img_type": "expressionSheet",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Scavenger Queen (拾荒女皇)
Gender / age impression: young woman, cunning, sharp and deadly presence
Body shape: tall and slender, agile feline posture
Face: handsome face, cunning green eyes, mocking smirk
Hair: short silver-gray hair with neon-green dyed hair tips
Outfit: chemical-resistant dark green hooded cape over tight black leather armor reinforced with copper scales
Accessories / weapon: a brass respirator mask with three circular filters, a custom folding mechanical crossbow glowing with neon-green acid vials
Color palette: neon green, dark green, brass copper, leather brown, silver-gray
Fixed traits that must never change: silver-green hair, brass respirator mask, dark green hooded cape, neon-green acid crossbow

Current asset goal:
Generate an expression sheet. Show 8 bust portraits of the Queen (without mask) in a clean grid: cunning smirk, focused aim, angry shout, coughing in toxic gas, mock smile, cold warning stare, battle weariness, and calm determination.

Style:
Wasteland character expression grid, consistent facial structure.

Composition:
8 bust portraits arranged in a clean grid.

Background:
Clean dark gray background."""
        },
        {
            "char_id": "char_0011_scavenger_queen",
            "char_name": "拾荒女皇",
            "img_type": "detailSheet",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Scavenger Queen (拾荒女皇)
Gender / age impression: young woman, cunning, sharp and deadly presence
Body shape: tall and slender, agile feline posture
Face: handsome face, cunning green eyes, mocking smirk
Hair: short silver-gray hair with neon-green dyed hair tips
Outfit: chemical-resistant dark green hooded cape over tight black leather armor reinforced with copper scales
Accessories / weapon: a brass respirator mask with three circular filters, a custom folding mechanical crossbow glowing with neon-green acid vials
Color palette: neon green, dark green, brass copper, leather brown, silver-gray
Fixed traits that must never change: silver-green hair, brass respirator mask, dark green hooded cape, neon-green acid crossbow

Current asset goal:
Generate a detail sheet. Close-up panels showing her gas mask filters, the trigger mechanism of her folding crossbow, the bubbling green acid vial, and her green-dyed hair tips.

Style:
Semi-realistic 3D game concept art style, wasteland mechanical detail sheet, clean design board (no 2D anime, no manga).

Composition:
Multiple close-up detail panels arranged cleanly.

Background:
Clean light gray background."""
        },
        {
            "char_id": "char_0011_scavenger_queen",
            "char_name": "拾荒女皇",
            "img_type": "materialPalette",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Scavenger Queen (拾荒女皇)
Gender / age impression: young woman, cunning, sharp and deadly presence
Body shape: tall and slender, agile feline posture
Face: handsome face, cunning green eyes, mocking smirk
Hair: short silver-gray hair with neon-green dyed hair tips
Outfit: chemical-resistant dark green hooded cape over tight black leather armor reinforced with copper scales
Accessories / weapon: a brass respirator mask with three circular filters, a custom folding mechanical crossbow glowing with neon-green acid vials
Color palette: neon green, dark green, brass copper, leather brown, silver-gray
Fixed traits that must never change: silver-green hair, brass respirator mask, dark green hooded cape, neon-green acid crossbow

Current asset goal:
Generate a material and color palette sheet. Show swatches of neon-green acid liquid, dark green hazard cloth, brass gas mask filters, and black leather armor beside a neutral front view of the character.

Style:
Semi-realistic 3D game concept art style, wasteland material reference sheet, clean design board layout (no 2D anime, no manga).

Composition:
Character standing next to neatly arranged material swatches and color blocks.

Background:
Plain gray background."""
        },
        {
            "char_id": "char_0011_scavenger_queen",
            "char_name": "拾荒女皇",
            "img_type": "outfitBreakdown",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Scavenger Queen (拾荒女皇)
Gender / age impression: young woman, cunning, sharp and deadly presence
Body shape: tall and slender, agile feline posture
Face: handsome face, cunning green eyes, mocking smirk
Hair: short silver-gray hair with neon-green dyed hair tips
Outfit: chemical-resistant dark green hooded cape over tight black leather armor reinforced with copper scales
Accessories / weapon: a brass respirator mask with three circular filters, a custom folding mechanical crossbow glowing with neon-green acid vials
Color palette: neon green, dark green, brass copper, leather brown, silver-gray
Fixed traits that must never change: silver-green hair, brass respirator mask, dark green hooded cape, neon-green acid crossbow

Current asset goal:
Generate an outfit breakdown sheet. Show separate layers and components of her clothing: dark green hooded cape, black leather chest armor, brass respirator mask, folding crossbow and quiver, and tactical belt straps.

Style:
Wasteland clothing breakdown sheet, clean layout.

Composition:
Clothing and gear parts laid out and separated clearly.

Background:
Plain light background."""
        },
        {
            "char_id": "char_0011_scavenger_queen",
            "char_name": "拾荒女皇",
            "img_type": "damageState",
            "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Scavenger Queen (拾荒女皇)
Gender / age impression: young woman, cunning, sharp and deadly presence
Body shape: tall and slender, agile feline posture
Face: handsome face, cunning green eyes, mocking smirk
Hair: short silver-gray hair with neon-green dyed hair tips
Outfit: chemical-resistant dark green hooded cape over tight black leather armor reinforced with copper scales
Accessories / weapon: a brass respirator mask with three circular filters, a custom folding mechanical crossbow glowing with neon-green acid vials
Color palette: neon green, dark green, brass copper, leather brown, silver-gray
Fixed traits that must never change: silver-green hair, brass respirator mask, dark green hooded cape, neon-green acid crossbow

Current asset goal:
Generate damage state variants. Show 3 full-body versions of the Queen: clean/default; battle-worn with acid splatters and dust; and heavily damaged with cracked respirator filters, torn cape, leaking toxic green acid from broken vials, and battle scars.

Style:
Wasteland character damage reference sheet.

Composition:
Show three side-by-side full-body versions of the character.

Background:
Solid clean dark gray background."""
        }
    ]

    boundary_investigator_plan = [
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "main",
            "prompt": "A masterpiece urban mystery concept art of the Boundary Investigator. A handsome, slender young East Asian male detective with short messy ink-blue hair. He wears a gold-rimmed monocle on his left eye, showing sharp, intelligent eyes. He is dressed in a tailored deep-gray double-breasted trench coat with a black vest and crimson tie underneath. He stands in a rainy, dark alleyway at midnight, holding a glowing vintage vacuum-tube radio in his gloved hands. The radio glows with an eerie teal-green aura, casting faint wave ripples in the foggy air. Background features yellow glowing streetlamps reflecting on wet asphalt, cinematic shadows, octane render, 8k."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up portrait of the exact same Boundary Investigator character from our conversation. Focus on his face and shoulders, capturing his messy ink-blue hair, the gold-rimmed monocle on his left eye, and his calm, sharp expression. Rain droplets on his coat. Solid, extremely dark, low-contrast studio background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same Boundary Investigator character from our conversation. Show him on a solid, clean dark gray background with three different facial expressions side-by-side: one calm and calculating, one with a subtle cynical smirk under his monocle, and one looking surprised/tense while listening to the radio. High-fidelity details, professional character model sheet, masterpiece, 8k."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "turnaround",
            "prompt": "Now, draw a professional character turnaround model sheet of the exact same Boundary Investigator character from our conversation. Show three full-body views: front, side, and back, standing in a neutral pose. He is wearing his deep-gray double-breasted trench coat. Solid, clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "outfit",
            "prompt": "Now, draw the exact same Boundary Investigator character from our conversation displaying three different outfits side-by-side on a plain clean dark gray background: on the left, his default deep-gray trench coat uniform; in the middle, his alternative private investigator waistcoat outfit (a dark blue waistcoat vest over a rolled-up white shirt and dark trousers, without his trench coat); on the right, his detective field uniform (a dark utility windbreaker jacket with tactical pockets). Show three side-by-side full-body views, standing on a solid clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "prop",
            "prompt": "Now, draw a high-fidelity detailed design sheet of the Boundary Investigator's gear: his vintage vacuum-tube radio with glowing teal-green indicator lights and dials, and his leather-bound investigator notebook. Show them from two angles. Solid, clean dark gray background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "scene",
            "prompt": "Now, draw a stunning, highly detailed urban mystery scene concept art. A dark, rain-slicked city alleyway at midnight, glowing yellow streetlamps, dark puddles reflecting the lights, and a mysterious door outlined in faint glowing teal-green energy in the shadows. Cinematic, hyper-realistic, masterpiece, 8k."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "cover",
            "prompt": "A cinematic vertical cover art showing the Boundary Investigator debugging his glowing vintage radio, standing on a rainy urban building rooftop. Waves of teal-green radio frequency lines ripple across the sky, with the dark cityscape reflecting off rain puddles. High polish, dramatic rim lighting, 8k."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "moodboard",
            "prompt": "A moodboard collage of 4 panels for the Boundary Investigator: one showing close-up rain reflections on a dark asphalt road, one showing glowing copper vacuum tubes of a vintage radio, one showing a gold-rimmed monocle resting on an open investigation notebook, and one showing ink-blue curls of hair under dim yellow streetlights. Eerie, mysterious tone, 8k."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "sketch",
            "prompt": "A concept sketch sheet of monochrome pencil drawings showing the Boundary Investigator in 3 study sketches: adjusting his monocle, tuning his hand-held radio, and walking down a dark corridor. Clean hand-drawn lines, traditional concept art sketch style, plain light background."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "fullBody",
            "prompt": "Now, draw a full-body cinematic splash art of the exact same Boundary Investigator character from our conversation. He stands alert in his trench coat, holding his glowing vintage radio, looking towards the viewer with a knowing smile. Solid, extremely dark, low-contrast studio background. Masterpiece, highly detailed, 8k."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "modelSheet",
            "prompt": "A clean model sheet of the Boundary Investigator showing full-body front, side, and back views. Standing neutrally in his deep-gray double-breasted trench coat. Even lighting, solid clean light gray background, no dramatic shadows, 8k."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "poseSheet",
            "prompt": "Show 5 poses of the Boundary Investigator on one clean sheet: walking with a flashlight, kneeling to check a rain puddle, tuning his radio close to his ear, running in warning/alarm, and leaning against a brick wall with a cold smirk. Solid clean dark gray background."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "expressionSheet",
            "prompt": "An expression sheet showing 8 bust portraits of the Boundary Investigator in a clean grid: calm, calculating, a sharp smirk, showing tension while listening to static, tired/exhausted with dark circles, a subtle warning look, coughing in wet cold weather, and focused determination. Clean dark gray background."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "detailSheet",
            "prompt": "A clean detail sheet showing close-up panels of the Boundary Investigator's features: his gold-rimmed monocle (left eye), his old vacuum-tube radio's speaker grill and teal-green wave dial, the fabric texture of his deep-gray trench coat collar, the leather gloves on his hands, and his scrawled handwritten notes. Clean light gray background."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "materialPalette",
            "prompt": "A material and color palette sheet for the Boundary Investigator: fabric swatches of deep-gray wool, ink-blue hair sample, gold monocle metal shine, crimson tie silk, and the teal-green light glow of his radio. Clean design layout, plain gray background."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "outfitBreakdown",
            "prompt": "An outfit breakdown sheet for the Boundary Investigator: showing separate layers of his clothing: deep-gray trench coat, black waistcoat vest, white collared shirt with crimson tie, dark trousers, and leather gloves. Clean layout, plain light background."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "damageState",
            "prompt": "Show 3 full-body versions of the Boundary Investigator: clean/default, battle-worn with dust smudges and torn coat sleeve, and heavily damaged with shattered monocle, blood-stained bandages on his forehead, and a cracked vintage radio. Solid clean dark gray background."
        }
    ]

    lantern_keeper_plan = [
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "main",
            "prompt": "A breathtaking gothic fantasy concept art of the Eternal Lantern Keeper. An elegant, young woman with refined features and pale skin. Her eyes glow with a soft starry gold light, and she has long flowing silver-white hair with faint gold reflections. She wears layered midnight-blue gothic robes with intricate gold star-map embroidery on the skirt, and a sheer black cape over her shoulders. She stands inside a silent, towering cathedral library ruins, holding a gothic black-iron candle lantern. Inside the lantern, a floating bright blue stellar flame burns, shedding glowing stardust particles. Dark atmospheric archives in the background, cinematic rim lighting, 8k."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up portrait of the exact same Eternal Lantern Keeper character from our conversation. Focus on her face and shoulders, capturing her starry gold eyes, silver-white hair, and her calm, compassionate expression. Star dust particles floating around. Solid, extremely dark, low-contrast studio background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same Eternal Lantern Keeper character from our conversation. Show her on a solid, clean dark gray background with three different facial expressions side-by-side: one serene and peaceful, one showing gentle sorrow with a starry gold tear, and one with a serious, guarding expression. High-fidelity details, professional character model sheet, masterpiece, 8k."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "turnaround",
            "prompt": "Now, draw a professional character turnaround model sheet of the exact same Eternal Lantern Keeper character from our conversation. Show three full-body views: front, side, and back, standing in a neutral pose. She is wearing her midnight-blue gothic robes and black cape. Solid, clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "outfit",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Eternal Lantern Keeper (永夜守灯人)\nGender / age impression: young woman, elegant, pale skin, serene and holy presence\nBody shape: slender and graceful silhouette\nFace: delicate refined face, calm and compassionate expression\nHair: long flowing silver-white hair with faint gold reflections\nEyes: gold eyes that glow with soft starry light\nOutfit: layered midnight-blue gothic robes with intricate gold star-map embroidery on the skirt, sheer black cape over shoulders\nAccessories / weapon: gothic black-iron candle lantern containing a floating bright blue stellar flame that sheds glowing stardust particles\nColor palette: midnight-blue, silver-white, gold, deep black, bright blue stellar flame highlights\nFixed traits that must never change: silver-white hair, gold-glowing eyes, midnight-blue gothic robes with gold embroidery, black-iron lantern with blue flame, serene holy expression\n\nCurrent asset goal:\nGenerate an outfit variant image. Show three different outfits side-by-side: on the left, her default midnight-blue gothic robes; in the middle, her alternative ceremonial white priestess gown with silver embroidery and a silver crescent crown; on the right, her archival scholar robes (a light blue and gray velvet gown with wide sleeves).\n\nStyle:\nGothic fantasy character concept art, high-fidelity design sheet, detailed fabric and material rendering, coherent design language, consistent facial identity, production-ready asset.\n\nComposition:\nShow three side-by-side full-body views of the same character standing neutrally. Keep the character clearly readable. Avoid unnecessary extra characters.\n\nBackground:\nPlain clean dark gray background.\n\nConstraints:\nKeep the same face, hairstyle, color palette, body shape, and signature accessories.\nDo not redesign the character.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "prop",
            "prompt": "Now, draw a high-fidelity detailed design sheet of the Eternal Lantern Keeper's gear: her gothic black-iron lantern with a floating bright blue stellar flame, and a heavy, leather-bound ancient tome of destiny. Show them from two angles. Solid, clean dark gray background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "scene",
            "prompt": "Now, draw a stunning, highly detailed dark fantasy scene concept art. Towering stone arches of a cathedral library in ruins, ancient bookshelves stretching into darkness, with floating glowing constellation maps and stardust drifting in the air. Cinematic, hyper-realistic, masterpiece, 8k."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "cover",
            "prompt": "A cinematic vertical cover art showing the Eternal Lantern Keeper walking down the giant, cathedral-like library ruins. She holds her glowing blue-flamed black-iron lantern high, casting long shadows on towering book archives, as glowing stellar constellations float above her. High polish, masterpiece, 8k."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "moodboard",
            "prompt": "A moodboard collage of 4 panels for the Eternal Lantern Keeper: one showing ancient, dusty leather-bound books, one showing a bright blue candle flame floating inside a gothic iron cage, one showing golden star constellations mapping on dark velvet fabric, and one showing long silver-white hair reflecting soft gold light. Sacred, gothic, mysterious tone, 8k."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "sketch",
            "prompt": "A concept sketch sheet of monochrome pencil drawings showing the Eternal Lantern Keeper in 3 study sketches: holding the lantern forward, praying, and looking down at a giant open book of destiny. Clean hand-drawn lines, traditional concept art sketch style, plain light background."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "fullBody",
            "prompt": "Now, draw a full-body cinematic splash art of the exact same Eternal Lantern Keeper character from our conversation. She stands gracefully in her midnight-blue robes, holding her glowing lantern, looking forward with compassionate gold eyes. Solid, extremely dark, low-contrast studio background. Masterpiece, highly detailed, 8k."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "modelSheet",
            "prompt": "A clean model sheet of the Eternal Lantern Keeper showing full-body front, side, and back views. Standing neutrally in her midnight-blue gothic priestess robes. Even lighting, solid clean light gray background, no dramatic shadows, 8k."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "poseSheet",
            "prompt": "Show 5 poses of the Eternal Lantern Keeper on one clean sheet: walking gracefully with her lantern, holding the lantern high to examine a wall, kneeling to read an ancient tome, raising her hand to cast a star-barrier, and floating slightly in a state of holy meditation. Solid clean dark gray background."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "expressionSheet",
            "prompt": "An expression sheet showing 8 bust portraits of the Eternal Lantern Keeper in a clean grid: serene, gentle sorrow with a golden tear, serious guarding look, eyes closed in silent prayer, calm warning, surprised by invader, exhausted/fading light, and compassionate gentle gaze. Clean dark gray background."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "detailSheet",
            "prompt": "A clean detail sheet showing close-up panels of the Eternal Lantern Keeper's features: her starry gold eyes, her long silver hair with gold strings, the intricate star-map embroidery on her midnight-blue robe skirt, and the gothic black-iron lantern's candle flame. Clean light gray background."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "materialPalette",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Eternal Lantern Keeper (永夜守灯人)\nGender / age impression: young woman, elegant, pale skin, serene and holy presence\nBody shape: slender and graceful silhouette\nFace: delicate refined face, calm and compassionate expression\nHair: long flowing silver-white hair with faint gold reflections\nEyes: gold eyes that glow with soft starry light\nOutfit: layered midnight-blue gothic robes with intricate gold star-map embroidery on the skirt, sheer black cape over shoulders\nAccessories / weapon: gothic black-iron candle lantern containing a floating bright blue stellar flame that sheds glowing stardust particles\nColor palette: midnight-blue, silver-white, gold, deep black, bright blue stellar flame highlights\nFixed traits that must never change: silver-white hair, gold-glowing eyes, midnight-blue gothic robes with gold embroidery, black-iron lantern with blue flame, serene holy expression\n\nCurrent asset goal:\nGenerate a material and color palette sheet. Show swatches of midnight-blue velvet, silver-white hair sample, starry gold glowing paint, black iron metal texture, and the bright blue stellar flame beside a neutral front view of the character.\n\nStyle:\nGothic fantasy character concept art, high-fidelity design sheet, detailed fabric and material rendering, coherent design language, consistent facial identity, production-ready asset.\n\nComposition:\nClean design-board layout showing the character alongside neatly arranged material swatches.\n\nBackground:\nPlain gray background.\n\nConstraints:\nKeep the same face, hairstyle, outfit logic, color palette, body shape, and signature accessories.\nDo not redesign the character.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "outfitBreakdown",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Eternal Lantern Keeper (永夜守灯人)\nGender / age impression: young woman, elegant, pale skin, serene and holy presence\nBody shape: slender and graceful silhouette\nFace: delicate refined face, calm and compassionate expression\nHair: long flowing silver-white hair with faint gold reflections\nEyes: gold eyes that glow with soft starry light\nOutfit: layered midnight-blue gothic robes with intricate gold star-map embroidery on the skirt, sheer black cape over shoulders\nAccessories / weapon: gothic black-iron candle lantern containing a floating bright blue stellar flame that sheds glowing stardust particles\nColor palette: midnight-blue, silver-white, gold, deep black, bright blue stellar flame highlights\nFixed traits that must never change: silver-white hair, gold-glowing eyes, midnight-blue gothic robes with gold embroidery, black-iron lantern with blue flame, serene holy expression\n\nCurrent asset goal:\nGenerate an outfit breakdown sheet. Show separate layers and components of her clothing: the outer midnight-blue velvet priestess robes, the black lace cape, the silver crescent crown, and the heavy leather-bound ancient tome of destiny.\n\nStyle:\nGothic fantasy character concept art, high-fidelity design sheet, detailed fabric and material rendering, coherent design language, consistent facial identity, production-ready asset.\n\nComposition:\nClean design board layout showing the clothes laid out and separated clearly.\n\nBackground:\nPlain light background.\n\nConstraints:\nKeep all parts consistent with the original character design.\nDo not redesign the character.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "damageState",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Eternal Lantern Keeper (永夜守灯人)\nGender / age impression: young woman, elegant, pale skin, serene and holy presence\nBody shape: slender and graceful silhouette\nFace: delicate refined face, calm and compassionate expression\nHair: long flowing silver-white hair with faint gold reflections\nEyes: gold eyes that glow with soft starry light\nOutfit: layered midnight-blue gothic robes with intricate gold star-map embroidery on the skirt, sheer black cape over shoulders\nAccessories / weapon: gothic black-iron candle lantern containing a floating bright blue stellar flame that sheds glowing stardust particles\nColor palette: midnight-blue, silver-white, gold, deep black, bright blue stellar flame highlights\nFixed traits that must never change: silver-white hair, gold-glowing eyes, midnight-blue gothic robes with gold embroidery, black-iron lantern with blue flame, serene holy expression\n\nCurrent asset goal:\nGenerate damage state variants. Show 3 full-body versions of the same character: clean/default, battle-worn with tattered robe hem and dusty cape, and heavily damaged with her body half-translucent and fading, a cracked glass lantern, and golden stellar tears flowing.\n\nStyle:\nGothic fantasy character concept art, high-fidelity design sheet, detailed fabric and material rendering, coherent design language, consistent facial identity, production-ready asset.\n\nComposition:\nShow three side-by-side full-body versions of the character.\n\nBackground:\nSolid clean dark gray background.\n\nConstraints:\nDo not change the costume into a new outfit. Keep the same identity.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."
        }
    ]

    mirror_walker_plan = [
        {
            "char_id": "char_0014_mirror_walker",
            "char_name": "碎镜行者",
            "img_type": "main",
            "prompt": "A spectacular urban mystery concept art of the Mirror Walker. A slender and sleek female assassin with short silver-gray hair, wearing a full-face reflective silver mirror mask. She wears a translucent, glossy neon-reflecting raincoat over a dark gray stealth suit. She stands in a rainy, neon-drenched city alleyway at midnight, holding a glowing mirror-glass blade that refracts colorful lights. The wet asphalt below reflects her stance, dramatic silhouettes and Tyndall rain effects, octane render, 8k."
        },
        {
            "char_id": "char_0014_mirror_walker",
            "char_name": "碎镜行者",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up portrait of the exact same Mirror Walker character from our conversation. Focus on her face and shoulders, capturing her silver-gray hair, mirror mask, and cold expression. Raindrops on her coat, glowing reflections on her mask. Solid, extremely dark, low-contrast studio background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0014_mirror_walker",
            "char_name": "碎镜行者",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same Mirror Walker character from our conversation. Show her on a solid, clean dark gray background with three different facial expressions side-by-side: one expressionless with mask on, one with mask tilted up showing her left cold black eye in focus, and one showing a rare half-smirk on her lips. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0014_mirror_walker",
            "char_name": "碎镜行者",
            "img_type": "turnaround",
            "prompt": "Now, draw a professional character turnaround model sheet of the exact same Mirror Walker character. Show three full-body views: front, side, and back, standing in a neutral pose. She is wearing her stealth suit and hood. Solid, clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0014_mirror_walker",
            "char_name": "碎镜行者",
            "img_type": "outfit",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Mirror Walker (碎镜行者)\nGender / age impression: young woman, elegant, sleek stealth, mirror reflections\nBody shape: tall, slender, flexible silhouette\nHair: short silver-gray hair in a neat crop\nOutfit: dark gray high-mobility nano-stealth suit under a hooded translucent glossy neon-reflecting raincoat\nAccessories / weapon: a reflective silver mirror mask, a sharp blade made of shattered mirror glass\nColor palette: reflection silver, neon purple, deep gray, rainy street black\nFixed traits that must never change: short silver-gray hair, reflective mirror mask, translucent glassy raincoat, mirror-glass blade\n\nCurrent asset goal:\nGenerate an outfit variant image. Show three different outfits side-by-side: on the left, her default translucent raincoat outfit; in the middle, her casual urban wear (a dark high-neck sweater, black leather jacket, and slim-fit trousers); on the right, her heavy combat gear (reinforced carbon-fiber plating over a matte black stealth suit with purple cybernetic lines). \n\nStyle:\nUrban mystery concept art, high-fidelity design sheet, detailed fabric and material rendering, coherent design language, consistent facial identity, production-ready asset.\n\nComposition:\nShow three side-by-side full-body views of the same character standing neutrally. Keep the character clearly readable. Avoid unnecessary extra characters.\n\nBackground:\nPlain clean dark gray background.\n\nConstraints:\nKeep the same face, hairstyle, color palette, body shape, and signature mask.\nDo not redesign the character.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."
        },
        {
            "char_id": "char_0014_mirror_walker",
            "char_name": "碎镜行者",
            "img_type": "prop",
            "prompt": "Now, draw a high-fidelity detailed design sheet of the Mirror Walker's gear: her mirror-glass dagger showing glowing silver runes, and a set of sharp triangular glass throwing stars. Show them from two angles. Solid, clean dark gray background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0014_mirror_walker",
            "char_name": "碎镜行者",
            "img_type": "scene",
            "prompt": "Now, draw a stunning, highly detailed urban mystery scene concept art. A dark, rain-slicked city alleyway at midnight, glowing yellow streetlamps, dark puddles reflecting the lights, and a mysterious door outlined in faint glowing silver mirror lines in the shadows. Cinematic, hyper-realistic, masterpiece, 8k."
        },
        {
            "char_id": "char_0014_mirror_walker",
            "char_name": "碎镜行者",
            "img_type": "cover",
            "prompt": "A cinematic vertical cover art showing the Mirror Walker stepping out of a giant glass skyscraper wall reflection, looking down onto a rainy, neon-lit street below. Shards of glass float around her. High polish, dramatic rim lighting, 8k."
        },
        {
            "char_id": "char_0014_mirror_walker",
            "char_name": "碎镜行者",
            "img_type": "moodboard",
            "prompt": "A moodboard collage of 4 panels for the Mirror Walker: one showing rain puddles reflecting neon street lights, one showing silver glass shards reflecting a dark silhouette, one showing a silver-gray hair sample, and one showing a glowing purple spatial tear. Mysterious, moody tone, 8k."
        },
        {
            "char_id": "char_0014_mirror_walker",
            "char_name": "碎镜行者",
            "img_type": "sketch",
            "prompt": "A concept sketch sheet of monochrome pencil drawings showing the Mirror Walker in 3 study sketches: stepping through a mirror, crouching in shadows, and cleaning her blade. Clean hand-drawn lines, traditional concept art sketch style, plain light background."
        },
        {
            "char_id": "char_0014_mirror_walker",
            "char_name": "碎镜行者",
            "img_type": "fullBody",
            "prompt": "Now, draw a full-body cinematic splash art of the exact same Mirror Walker character. She stands alert in her raincoat, holding her mirror blade, with her reflective mask mirroring the glowing city lights. Solid, extremely dark, low-contrast studio background. Masterpiece, highly detailed, 8k."
        },
        {
            "char_id": "char_0014_mirror_walker",
            "char_name": "碎镜行者",
            "img_type": "modelSheet",
            "prompt": "A clean model sheet of the Mirror Walker showing full-body front, side, and back views. Standing neutrally in her signature stealth outfit. Even lighting, solid clean light gray background, no dramatic shadows, 8k."
        },
        {
            "char_id": "char_0014_mirror_walker",
            "char_name": "碎镜行者",
            "img_type": "poseSheet",
            "prompt": "Show 5 poses of the Mirror Walker on one clean sheet: running on a wall, diving through a reflection, crouching with a dagger, stepping forward with a cold glare, and leaning against a brick wall. Solid clean dark gray background."
        },
        {
            "char_id": "char_0014_mirror_walker",
            "char_name": "碎镜行者",
            "img_type": "expressionSheet",
            "prompt": "An expression sheet showing 8 bust portraits of the Mirror Walker in a clean grid: blank mask, mask tilted showing cold left eye, a sharp smirk, showing focus, exhausted, showing warning, coughing in wet cold weather, and focused determination. Clean dark gray background."
        },
        {
            "char_id": "char_0014_mirror_walker",
            "char_name": "碎镜行者",
            "img_type": "detailSheet",
            "prompt": "A clean detail sheet showing close-up panels of the Mirror Walker's features: her silver mirror mask, the blade's shattered glass patterns, the translucent plastic texture of her raincoat collar, and the leather gloves on her hands. Clean light gray background."
        },
        {
            "char_id": "char_0014_mirror_walker",
            "char_name": "碎镜行者",
            "img_type": "materialPalette",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Mirror Walker (碎镜行者)\nGender / age impression: young woman, elegant, sleek stealth, mirror reflections\nBody shape: tall, slender, flexible silhouette\nHair: short silver-gray hair in a neat crop\nOutfit: dark gray high-mobility nano-stealth suit under a hooded translucent glossy neon-reflecting raincoat\nAccessories / weapon: a reflective silver mirror mask, a sharp blade made of shattered mirror glass\nColor palette: reflection silver, neon purple, deep gray, rainy street black\nFixed traits that must never change: short silver-gray hair, reflective mirror mask, translucent glassy raincoat, mirror-glass blade\n\nCurrent asset goal:\nGenerate a material and color palette sheet. Show swatches of deep gray nano-fabric, translucent rain-slicked plastic, a silver-gray hair sample, and a glowing purple spatial light next to a neutral front view of the character.\n\nStyle:\nUrban mystery concept art, high-fidelity design sheet, detailed fabric and material rendering, coherent design language, consistent facial identity, production-ready asset.\n\nComposition:\nClean design-board layout showing the character alongside neatly arranged material swatches.\n\nBackground:\nPlain gray background.\n\nConstraints:\nKeep the same face, hairstyle, outfit logic, color palette, body shape, and signature mask.\nDo not redesign the character.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."
        },
        {
            "char_id": "char_0014_mirror_walker",
            "char_name": "碎镜行者",
            "img_type": "outfitBreakdown",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Mirror Walker (碎镜行者)\nGender / age impression: young woman, elegant, sleek stealth, mirror reflections\nBody shape: tall, slender, flexible silhouette\nHair: short silver-gray hair in a neat crop\nOutfit: dark gray high-mobility nano-stealth suit under a hooded translucent glossy neon-reflecting raincoat\nAccessories / weapon: a reflective silver mirror mask, a sharp blade made of shattered mirror glass\nColor palette: reflection silver, neon purple, deep gray, rainy street black\nFixed traits that must never change: short silver-gray hair, reflective mirror mask, translucent glassy raincoat, mirror-glass blade\n\nCurrent asset goal:\nGenerate an outfit breakdown sheet. Show separate layers and components of her clothing: the outer translucent hooded raincoat, the high-mobility gray stealth bodysuit, the reflective mirror mask, and the heavy leather boots.\n\nStyle:\nUrban mystery concept art, high-fidelity design sheet, detailed fabric and material rendering, coherent design language, consistent facial identity, production-ready asset.\n\nComposition:\nClean design board layout showing the clothes laid out and separated clearly.\n\nBackground:\nPlain light background.\n\nConstraints:\nKeep all parts consistent with the original character design.\nDo not redesign the character.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."
        },
        {
            "char_id": "char_0014_mirror_walker",
            "char_name": "碎镜行者",
            "img_type": "damageState",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Mirror Walker (碎镜行者)\nGender / age impression: young woman, elegant, sleek stealth, mirror reflections\nBody shape: tall, slender, flexible silhouette\nHair: short silver-gray hair in a neat crop\nOutfit: dark gray high-mobility nano-stealth suit under a hooded translucent glossy neon-reflecting raincoat\nAccessories / weapon: a reflective silver mirror mask, a sharp blade made of shattered mirror glass\nColor palette: reflection silver, neon purple, deep gray, rainy street black\nFixed traits that must never change: short silver-gray hair, reflective mirror mask, translucent glassy raincoat, mirror-glass blade\n\nCurrent asset goal:\nGenerate damage state variants. Show 3 full-body versions of the same character: clean/default; battle-worn with tattered raincoat and dust smudges; and heavily damaged with her silver mirror mask shattered in half revealing a cold dark eye, her stealth suit torn showing bandaged wounds, and a broken mirror blade leaking white sparks. \n\nStyle:\nUrban mystery concept art, high-fidelity design sheet, detailed fabric and material rendering, coherent design language, consistent facial identity, production-ready asset.\n\nComposition:\nShow three side-by-side full-body versions of the character.\n\nBackground:\nSolid clean dark gray background.\n\nConstraints:\nDo not change the costume into a new outfit. Keep the same identity.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."
        }
    ]

    ink_painter_plan = [
        {
            "char_id": "char_0015_ink_painter",
            "char_name": "画灵师",
            "img_type": "main",
            "prompt": "A breathtaking epic fantasy concept art of the Ink Painter. A serene East Asian woman with long black hair tied with a green bamboo hairpin, dressed in an elegant white-and-teal gradient wide-sleeved Hanfu. She stands inside a misty green bamboo forest, holding a giant jade calligraphy brush glowing with dark green spirit mist. Swirls of glowing black ink splash in the air, materializing into a ghostly tiger outlined in glowing green ink. Ethereal light filtering through the bamboo leaves, cinematic rim lighting, masterpiece, 8k."
        },
        {
            "char_id": "char_0015_ink_painter",
            "char_name": "画灵师",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up portrait of the exact same Ink Painter character from our conversation. Focus on her face and shoulders, capturing her long black hair, green bamboo hairpin, and serene, focused expression. Faint green ink dust floating around her face. Solid, extremely dark, low-contrast studio background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0015_ink_painter",
            "char_name": "画灵师",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same Ink Painter character from our conversation. Show her on a solid, clean dark gray background with three different facial expressions side-by-side: one serene and peaceful, one focused and chanting, and one showing a gentle, warm smile. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0015_ink_painter",
            "char_name": "画灵师",
            "img_type": "turnaround",
            "prompt": "Now, draw a professional character turnaround model sheet of the exact same Ink Painter character. Show three full-body views: front, side, and back, standing in a neutral pose. She is wearing her white-and-teal gradient Hanfu. Solid, clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0015_ink_painter",
            "char_name": "画灵师",
            "img_type": "outfit",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Ink Painter (画灵师)\nGender / age impression: young woman, elegant, serene scholar, painter aesthetic\nBody shape: tall, slender, flowing posture\nHair: long black hair tied with a green bamboo hairpin in a half-up bun\nEyes: clear, gentle black eyes\nOutfit: elegant white-and-teal gradient wide-sleeved Hanfu robe with gold embroidery\nAccessories / weapon: a half-meter long green jade calligraphy brush, white porcelain ink jars at her belt\nColor palette: porcelain blue, bamboo green, ink black, moonlit white\nFixed traits that must never change: long black hair, green bamboo hairpin, jade calligraphy brush, white-and-teal gradient robe\n\nCurrent asset goal:\nGenerate an outfit variant image. Show three different outfits side-by-side: on the left, her default white-and-teal gradient Hanfu robe; in the middle, her simple workshop outfit (a white linen blouse with rolled-up sleeves, a dark green skirt, and a paint-splattered gray apron); on the right, her ceremonial ritual robes (a majestic emerald green and gold silk gown with wide sleeves and crane embroidery). \n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet, detailed fabric and material rendering, coherent design language, consistent facial identity, production-ready asset.\n\nComposition:\nShow three side-by-side full-body views of the same character standing neutrally. Keep the character clearly readable. Avoid unnecessary extra characters.\n\nBackground:\nPlain clean dark gray background.\n\nConstraints:\nKeep the same face, hairstyle, color palette, body shape, and bamboo hairpin.\nDo not redesign the character.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."
        },
        {
            "char_id": "char_0015_ink_painter",
            "char_name": "画灵师",
            "img_type": "prop",
            "prompt": "Now, draw a high-fidelity detailed design sheet of the Ink Painter's gear: her giant green jade calligraphy brush showing copper bindings, and her white porcelain ink jars. Show them from two angles. Solid, clean dark gray background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0015_ink_painter",
            "char_name": "画灵师",
            "img_type": "scene",
            "prompt": "Now, draw a stunning, highly detailed landscape scene concept art. A misty green bamboo forest, stone pathways, and a simple wooden writing desk in a small pavilion, with floating swirls of glowing black-green ink in the air. Cinematic, hyper-realistic, masterpiece, 8k."
        },
        {
            "char_id": "char_0015_ink_painter",
            "char_name": "画灵师",
            "img_type": "cover",
            "prompt": "A cinematic vertical cover art showing the Ink Painter floating in the air above a waterfall, painting a giant water-dragon that materializes from her brush. High polish, dramatic rim lighting, 8k."
        },
        {
            "char_id": "char_0015_ink_painter",
            "char_name": "画灵师",
            "img_type": "moodboard",
            "prompt": "A moodboard collage of 4 panels for the Ink Painter: one showing a close-up of emerald green bamboo leaves, one showing black ink dissolving in clear water, one showing a jade hair ornament, and one showing a teal silk fabric sample. Calm, artistic tone, 8k."
        },
        {
            "char_id": "char_0015_ink_painter",
            "char_name": "画灵师",
            "img_type": "sketch",
            "prompt": "A concept sketch sheet of monochrome pencil drawings showing the Ink Painter in 3 study sketches: meditating, dipping her brush in ink, and walking with her brush slung over her shoulder. Clean hand-drawn lines, traditional concept art sketch style, plain light background."
        },
        {
            "char_id": "char_0015_ink_painter",
            "char_name": "画灵师",
            "img_type": "fullBody",
            "prompt": "Now, draw a full-body cinematic splash art of the exact same Ink Painter character. She stands gracefully in her white-and-teal gradient Hanfu, holding her brush horizontally, with a faint water-snake ink spirit swirling around her feet. Solid, extremely dark, low-contrast studio background. Masterpiece, highly detailed, 8k."
        },
        {
            "char_id": "char_0015_ink_painter",
            "char_name": "画灵师",
            "img_type": "modelSheet",
            "prompt": "A clean model sheet of the Ink Painter showing full-body front, side, and back views. Standing neutrally in her gradient Hanfu robes. Even lighting, solid clean light gray background, no dramatic shadows, 8k."
        },
        {
            "char_id": "char_0015_ink_painter",
            "char_name": "画灵师",
            "img_type": "poseSheet",
            "prompt": "Show 5 poses of the Ink Painter on one clean sheet: drawing in mid-air, dipping her brush, walking in the wind, sitting and reading a scroll, and defending with a water-shield. Solid clean dark gray background."
        },
        {
            "char_id": "char_0015_ink_painter",
            "char_name": "画灵师",
            "img_type": "expressionSheet",
            "prompt": "An expression sheet showing 8 bust portraits of the Ink Painter in a clean grid: calm, closed eyes in thought, gentle smile, focused alarm, coughing, surprised, serious, and a compassionate soft gaze. Clean dark gray background."
        },
        {
            "char_id": "char_0015_ink_painter",
            "char_name": "画灵师",
            "img_type": "detailSheet",
            "prompt": "A clean detail sheet showing close-up panels of the Ink Painter's features: her green bamboo hairpin, the detailed gold embroidery on her wide collar, the porcelain ink jar's white glaze, and the tip of her jade brush with wet ink. Clean light gray background."
        },
        {
            "char_id": "char_0015_ink_painter",
            "char_name": "画灵师",
            "img_type": "materialPalette",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Ink Painter (画灵师)\nGender / age impression: young woman, elegant, serene scholar, painter aesthetic\nBody shape: tall, slender, flowing posture\nHair: long black hair tied with a green bamboo hairpin in a half-up bun\nEyes: clear, gentle black eyes\nOutfit: elegant white-and-teal gradient wide-sleeved Hanfu robe with gold embroidery\nAccessories / weapon: a half-meter long green jade calligraphy brush, white porcelain ink jars at her belt\nColor palette: porcelain blue, bamboo green, ink black, moonlit white\nFixed traits that must never change: long black hair, green bamboo hairpin, jade calligraphy brush, white-and-teal gradient robe\n\nCurrent asset goal:\nGenerate a material and color palette sheet. Show swatches of white silk, teal gradient satin, a black hair sample, jade stone texture, and the glowing green spirit mist next to a neutral front view of the character.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet, detailed fabric and material rendering, coherent design language, consistent facial identity, production-ready asset.\n\nComposition:\nClean design-board layout showing the character alongside neatly arranged material swatches.\n\nBackground:\nPlain gray background.\n\nConstraints:\nKeep the same face, hairstyle, outfit logic, color palette, body shape, and bamboo hairpin.\nDo not redesign the character.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."
        },
        {
            "char_id": "char_0015_ink_painter",
            "char_name": "画灵师",
            "img_type": "outfitBreakdown",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Ink Painter (画灵师)\nGender / age impression: young woman, elegant, serene scholar, painter aesthetic\nBody shape: tall, slender, flowing posture\nHair: long black hair tied with a green bamboo hairpin in a half-up bun\nEyes: clear, gentle black eyes\nOutfit: elegant white-and-teal gradient wide-sleeved Hanfu robe with gold embroidery\nAccessories / weapon: a half-meter long green jade calligraphy brush, white porcelain ink jars at her belt\nColor palette: porcelain blue, bamboo green, ink black, moonlit white\nFixed traits that must never change: long black hair, green bamboo hairpin, jade calligraphy brush, white-and-teal gradient robe\n\nCurrent asset goal:\nGenerate an outfit breakdown sheet. Show separate layers and components of her clothing: the outer gradient wide-sleeved robe, the inner undergarment dress, the green bamboo hairpin, and the white porcelain ink jars.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet, detailed fabric and material rendering, coherent design language, consistent facial identity, production-ready asset.\n\nComposition:\nClean design board layout showing the clothes laid out and separated clearly.\n\nBackground:\nPlain light background.\n\nConstraints:\nKeep all parts consistent with the original character design.\nDo not redesign the character.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."
        },
        {
            "char_id": "char_0015_ink_painter",
            "char_name": "画灵师",
            "img_type": "damageState",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Ink Painter (画灵师)\nGender / age impression: young woman, elegant, serene scholar, painter aesthetic\nBody shape: tall, slender, flowing posture\nHair: long black hair tied with a green bamboo hairpin in a half-up bun\nEyes: clear, gentle black eyes\nOutfit: elegant white-and-teal gradient wide-sleeved Hanfu robe with gold embroidery\nAccessories / weapon: a half-meter long green jade calligraphy brush, white porcelain ink jars at her belt\nColor palette: porcelain blue, bamboo green, ink black, moonlit white\nFixed traits that must never change: long black hair, green bamboo hairpin, jade calligraphy brush, white-and-teal gradient robe\n\nCurrent asset goal:\nGenerate damage state variants. Show 3 full-body versions of the same character: clean/default; battle-worn with ink splatters and torn sleeves; and heavily damaged with her bamboo hairpin snapped in half releasing her messy black hair, her robes tattered and stained with black ink and blood, and her jade brush cracked in pieces. \n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet, detailed fabric and material rendering, coherent design language, consistent facial identity, production-ready asset.\n\nComposition:\nShow three side-by-side full-body versions of the character.\n\nBackground:\nSolid clean dark gray background.\n\nConstraints:\nDo not change the costume into a new outfit. Keep the same identity.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."
        }
    ]

    abyssal_zitherist_plan = [
        {
            "char_id": "char_0016_abyssal_zitherist",
            "char_name": "煞气琴师",
            "img_type": "main",
            "prompt": "A stunning, traditional Chinese ink-wash comic style concept art of the Abyssal Zitherist. A slender young East Asian woman with long messy ink-black hair blowing in the wind. Her eyes are bound by a tattered blood-red silk blindfold. She wears a tattered black-and-charcoal grey wide-sleeved Hanfu robe, sitting cross-legged on a crumbling ancient stone battlement. On her lap lies a charred wood zither, with strings glowing with faint energy. Glowing red sonic wave ripples blast out from her fingers, cutting through graphite-textured fog. Epic dramatic framing, dark graphite shadows with crimson splashes, masterpiece, 8k."
        },
        {
            "char_id": "char_0016_abyssal_zitherist",
            "char_name": "煞气琴师",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up portrait of the exact same Abyssal Zitherist character from our conversation. Focus on her face and shoulders, capturing her long messy black hair, the blood-red blindfold, and a cold, determined expression. Faint crimson mist floating around her face. Solid, extremely dark, low-contrast studio background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0016_abyssal_zitherist",
            "char_name": "煞气琴师",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same Abyssal Zitherist character from our conversation. Show her on a solid, clean dark gray background with three different facial expressions side-by-side: one cold and calm, one reciting a spell with focused lips, and one showing a rare, silent soft smile. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0016_abyssal_zitherist",
            "char_name": "煞气琴师",
            "img_type": "turnaround",
            "prompt": "Now, draw a professional character turnaround model sheet of the exact same Abyssal Zitherist character. Show three full-body views: front, side, and back, standing in a neutral pose. She is wearing her tattered black-and-grey Hanfu. Solid, clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0016_abyssal_zitherist",
            "char_name": "煞气琴师",
            "img_type": "outfit",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Abyssal Zitherist (煞气琴师)\nGender / age impression: young woman, blindfolded, tattered Hanfu, zither musician\nBody shape: tall, slender, rugged posture\nHair: long messy ink-black hair\nEyes: blindfolded with a tattered dark red ribbon\nOutfit: tattered black-and-charcoal grey wide-sleeved Hanfu robe\nAccessories / weapon: a charred wooden zither with beast-tendon strings\nColor palette: blood red, graphite black, charcoal grey, windblown yellow\nFixed traits that must never change: long black hair, red blindfold, black Hanfu, ancient zither\n\nCurrent asset goal:\nGenerate an outfit variant image. Show three different outfits side-by-side: on the left, her default tattered black-and-charcoal Hanfu; in the middle, her battle armor outfit (a dark leather bodice, shoulder guards, and tattered red trousers); on the right, her ceremonial ritual robes (a deep crimson velvet gown with gold star map patterns and a silk veil). \n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet, detailed fabric and material rendering, coherent design language, consistent facial identity, production-ready asset.\n\nComposition:\nShow three side-by-side full-body views of the same character standing neutrally. Keep the character clearly readable. Avoid unnecessary extra characters.\n\nBackground:\nPlain clean dark gray background.\n\nConstraints:\nKeep the same face, hairstyle, color palette, body shape, and red blindfold.\nDo not redesign the character.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."
        },
        {
            "char_id": "char_0016_abyssal_zitherist",
            "char_name": "煞气琴师",
            "img_type": "prop",
            "prompt": "Now, draw a high-fidelity detailed design sheet of the Abyssal Zitherist\'s gear: her charred wooden zither showing golden tendon strings, and her blood-red silk blindfold. Show them from two angles. Solid, clean dark gray background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0016_abyssal_zitherist",
            "char_name": "煞气琴师",
            "img_type": "scene",
            "prompt": "Now, draw a stunning, highly detailed landscape scene concept art. A crumbling ancient fortress wall segment at sunset, surrounded by swirling red mist and graphite-colored dust in the air. Cinematic, hyper-realistic, masterpiece, 8k."
        },
        {
            "char_id": "char_0016_abyssal_zitherist",
            "char_name": "煞气琴师",
            "img_type": "cover",
            "prompt": "A cinematic vertical cover art showing the Abyssal Zitherist sitting on the edge of a high cliff, playing her zither while massive waves of dark red energy crash against the abyss below. High polish, dramatic rim lighting, 8k."
        },
        {
            "char_id": "char_0016_abyssal_zitherist",
            "char_name": "煞气琴师",
            "img_type": "moodboard",
            "prompt": "A moodboard collage of 4 panels for the Abyssal Zitherist: one showing close-up of dark red silk, one showing black ink dissolving in blood, one showing charred ancient wood texture, and one showing a desolate sandstorm. Desolate, artistic tone, 8k."
        },
        {
            "char_id": "char_0016_abyssal_zitherist",
            "char_name": "煞气琴师",
            "img_type": "sketch",
            "prompt": "A concept sketch sheet of monochrome pencil drawings showing the Abyssal Zitherist in 3 study sketches: meditating with her zither, carrying the zither on her back, and kneeling on a broken wall. Clean hand-drawn lines, traditional concept art sketch style, plain light background."
        },
        {
            "char_id": "char_0016_abyssal_zitherist",
            "char_name": "煞气琴师",
            "img_type": "fullBody",
            "prompt": "Now, draw a full-body cinematic splash art of the exact same Abyssal Zitherist character. She stands gracefully in her tattered black-and-charcoal Hanfu, holding her zither with one arm, with swirls of dark red energy around her feet. Solid, extremely dark, low-contrast studio background. Masterpiece, highly detailed, 8k."
        },
        {
            "char_id": "char_0016_abyssal_zitherist",
            "char_name": "煞气琴师",
            "img_type": "modelSheet",
            "prompt": "A clean model sheet of the Abyssal Zitherist showing full-body front, side, and back views. Standing neutrally in her tattered Hanfu robes. Even lighting, solid clean light gray background, no dramatic shadows, 8k."
        },
        {
            "char_id": "char_0016_abyssal_zitherist",
            "char_name": "煞气琴师",
            "img_type": "poseSheet",
            "prompt": "Show 5 poses of the Abyssal Zitherist on one clean sheet: playing zither in mid-air, carrying zither in the wind, standing defiantly on the wall, sitting and meditating, and defending with a red barrier. Solid clean dark gray background."
        },
        {
            "char_id": "char_0016_abyssal_zitherist",
            "char_name": "煞气琴师",
            "img_type": "expressionSheet",
            "prompt": "An expression sheet showing 8 bust portraits of the Abyssal Zitherist in a clean grid: calm, closed eyes in thought, subtle smile, focused alarm, coughing, coughing blood, serious, and a compassionate soft gaze. Clean dark gray background."
        },
        {
            "char_id": "char_0016_abyssal_zitherist",
            "char_name": "煞气琴师",
            "img_type": "detailSheet",
            "prompt": "A clean detail sheet showing close-up panels of the Abyssal Zitherist\'s features: her red blindfold\'s silk weave, the detailed charcoal pattern on her sleeves, the ancient zither\'s wood grain, and the beast-tendon strings glowing with crimson energy. Clean light gray background."
        },
        {
            "char_id": "char_0016_abyssal_zitherist",
            "char_name": "煞气琴师",
            "img_type": "materialPalette",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Abyssal Zitherist (煞气琴师)\nGender / age impression: young woman, blindfolded, tattered Hanfu, zither musician\nBody shape: tall, slender, rugged posture\nHair: long messy ink-black hair\nEyes: blindfolded with a tattered dark red ribbon\nOutfit: tattered black-and-charcoal grey wide-sleeved Hanfu robe\nAccessories / weapon: a charred wooden zither with beast-tendon strings\nColor palette: blood red, graphite black, charcoal grey, windblown yellow\nFixed traits that must never change: long black hair, red blindfold, black Hanfu, ancient zither\n\nCurrent asset goal:\nGenerate a material and color palette sheet. Show swatches of tattered black silk, grey linen, a black hair sample, charred wood texture, and the glowing red spirit mist next to a neutral front view of the character.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet, detailed fabric and material rendering, coherent design language, consistent facial identity, production-ready asset.\n\nComposition:\nClean design-board layout showing the character alongside neatly arranged material swatches.\n\nBackground:\nPlain gray background.\n\nConstraints:\nKeep the same face, hairstyle, outfit logic, color palette, body shape, and red blindfold.\nDo not redesign the character.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."
        },
        {
            "char_id": "char_0016_abyssal_zitherist",
            "char_name": "煞气琴师",
            "img_type": "outfitBreakdown",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Abyssal Zitherist (煞气琴师)\nGender / age impression: young woman, blindfolded, tattered Hanfu, zither musician\nBody shape: tall, slender, rugged posture\nHair: long messy ink-black hair\nEyes: blindfolded with a tattered dark red ribbon\nOutfit: tattered black-and-charcoal grey wide-sleeved Hanfu robe\nAccessories / weapon: a charred wooden zither with beast-tendon strings\nColor palette: blood red, graphite black, charcoal grey, windblown yellow\nFixed traits that must never change: long black hair, red blindfold, black Hanfu, ancient zither\n\nCurrent asset goal:\nGenerate an outfit breakdown sheet. Show separate layers and components of her clothing: the outer tattered wide-sleeved robe, the inner undergarment dress, the blood-red blindfold, and the charred wood zither.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet, detailed fabric and material rendering, coherent design language, consistent facial identity, production-ready asset.\n\nComposition:\nClean design board layout showing the clothes laid out and separated clearly.\n\nBackground:\nPlain light background.\n\nConstraints:\nKeep all parts consistent with the original character design.\nDo not redesign the character.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."
        },
        {
            "char_id": "char_0016_abyssal_zitherist",
            "char_name": "煞气琴师",
            "img_type": "damageState",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Abyssal Zitherist (煞气琴师)\nGender / age impression: young woman, blindfolded, tattered Hanfu, zither musician\nBody shape: tall, slender, rugged posture\nHair: long messy ink-black hair\nEyes: blindfolded with a tattered dark red ribbon\nOutfit: tattered black-and-charcoal grey wide-sleeved Hanfu robe\nAccessories / weapon: a charred wooden zither with beast-tendon strings\nColor palette: blood red, graphite black, charcoal grey, windblown yellow\nFixed traits that must never change: long black hair, red blindfold, black Hanfu, ancient zither\n\nCurrent asset goal:\nGenerate damage state variants. Show 3 full-body versions of the same character: clean/default; battle-worn with ink-wash bloodstains and torn sleeves; and heavily damaged with her red blindfold torn in half revealing a cold dark eye, her Hanfu tattered and heavily stained with blood, and her zither snapped in half with broken strings. \n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet, detailed fabric and material rendering, coherent design language, consistent facial identity, production-ready asset.\n\nComposition:\nShow three side-by-side full-body versions of the character.\n\nBackground:\nSolid clean dark gray background.\n\nConstraints:\nDo not change the costume into a new outfit. Keep the same identity.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."
        }
    ]
    talisman_weaver_plan = [
        {
            "char_id": "char_0017_talisman_weaver",
            "char_name": "符华天师",
            "img_type": "main",
            "prompt": "A spectacular traditional Chinese ink-wash comic style concept art of the Talisman Weaver. A heroic East Asian young woman with silver-white hair tied in a high ponytail. She wears a black-and-vermilion-red Taoist robe with gold accents. She holds a seven-star peachwood sword, surrounded by dozens of yellow paper talismans inscribed with glowing cinnabar runes orbiting her in a spiraling storm. Tiny embers and golden sparkles fly in the dark temple ruins. High-fidelity ink brushstrokes, dramatic volumetric lighting, cinematic masterpiece, 8k."
        },
        {
            "char_id": "char_0017_talisman_weaver",
            "char_name": "符华天师",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up portrait of the exact same Talisman Weaver character from our conversation. Focus on her face and shoulders, capturing her silver-white hair in a high ponytail, the red cinnabar mark on her forehead, and a confident, heroic expression. Golden sparks and floating paper charms in the background. Solid, extremely dark, low-contrast studio background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0017_talisman_weaver",
            "char_name": "符华天师",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same Talisman Weaver character from our conversation. Show her on a solid, clean dark gray background with three different facial expressions side-by-side: one confident and smirking, one chanting an incantation with fierce focused eyes, and one laughing lightheartedly. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0017_talisman_weaver",
            "char_name": "符华天师",
            "img_type": "turnaround",
            "prompt": "Now, draw a professional character turnaround model sheet of the exact same Talisman Weaver character. Show three full-body views: front, side, and back, standing in a neutral pose. She is wearing her black-and-vermilion Taoist robe. Solid, clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0017_talisman_weaver",
            "char_name": "符华天师",
            "img_type": "outfit",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Talisman Weaver (符华天师)\nGender / age impression: young woman, heroic, confident Taoist scribe, exorcist aesthetic\nBody shape: tall, athletic, agile stance\nHair: silver-white hair tied in a high ponytail with a crimson ribbon\nEyes: bright golden eyes\nOutfit: black-and-vermilion-red Taoist robe with gold cloud patterns\nAccessories / weapon: a seven-star peachwood sword, a golden cinnabar brush, leather talisman pouches\nColor palette: cinnabar red, sulfur yellow, charcoal black, silver white\nFixed traits that must never change: silver-white hair, high ponytail, black-and-vermilion robe, floating paper talismans\n\nCurrent asset goal:\nGenerate an outfit variant image. Show three different outfits side-by-side: on the left, her default black-and-vermilion Taoist robe; in the middle, her training outfit (a simple white cotton tunic, red arm guards, and black martial trousers); on the right, her ceremonial arch-master robes (a glorious bright yellow silk robe with intricate purple trigram embroidery and golden silk sashes). \n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet, detailed fabric and material rendering, coherent design language, consistent facial identity, production-ready asset.\n\nComposition:\nShow three side-by-side full-body views of the same character standing neutrally. Keep the character clearly readable. Avoid unnecessary extra characters.\n\nBackground:\nPlain clean dark gray background.\n\nConstraints:\nKeep the same face, hairstyle, color palette, body shape, and white hair.\nDo not redesign the character.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."
        },
        {
            "char_id": "char_0017_talisman_weaver",
            "char_name": "符华天师",
            "img_type": "prop",
            "prompt": "Now, draw a high-fidelity detailed design sheet of the Talisman Weaver\'s gear: her seven-star peachwood sword, and a bundle of yellow paper talismans with glowing red ink. Show them from two angles. Solid, clean dark gray background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0017_talisman_weaver",
            "char_name": "符华天师",
            "img_type": "scene",
            "prompt": "Now, draw a stunning, highly detailed landscape scene concept art. A ruined ancient mountaintop temple under a starry night sky, with floating glowing paper talismans and sparks drifting in the dark wind. Cinematic, hyper-realistic, masterpiece, 8k."
        },
        {
            "char_id": "char_0017_talisman_weaver",
            "char_name": "符华天师",
            "img_type": "cover",
            "prompt": "A cinematic vertical cover art showing the Talisman Weaver standing at the temple gate, pointing her wood sword upward as a massive wave of yellow talismans spirals into the sky like a dragon. High polish, dramatic rim lighting, 8k."
        },
        {
            "char_id": "char_0017_talisman_weaver",
            "char_name": "符华天师",
            "img_type": "moodboard",
            "prompt": "A moodboard collage of 4 panels for the Talisman Weaver: one showing close-up of yellow paper with cinnabar ink, one showing sparks of red fire, one showing carved peachwood grain, and one showing silver-white silk thread. Vibrant, mystical tone, 8k."
        },
        {
            "char_id": "char_0017_talisman_weaver",
            "char_name": "符华天师",
            "img_type": "sketch",
            "prompt": "A concept sketch sheet of monochrome pencil drawings showing the Talisman Weaver in 3 study sketches: writing a talisman on a desk, leaping in mid-air, and sheathing her wood sword. Clean hand-drawn lines, traditional concept art sketch style, plain light background."
        },
        {
            "char_id": "char_0017_talisman_weaver",
            "char_name": "符华天师",
            "img_type": "fullBody",
            "prompt": "Now, draw a full-body cinematic splash art of the exact same Talisman Weaver character. She stands heroically in her black-and-vermilion Taoist robe, holding her peachwood sword, with several paper talismans floating around her. Solid, extremely dark, low-contrast studio background. Masterpiece, highly detailed, 8k."
        },
        {
            "char_id": "char_0017_talisman_weaver",
            "char_name": "符华天师",
            "img_type": "modelSheet",
            "prompt": "A clean model sheet of the Talisman Weaver showing full-body front, side, and back views. Standing neutrally in her black-and-vermilion robes. Even lighting, solid clean light gray background, no dramatic shadows, 8k."
        },
        {
            "char_id": "char_0017_talisman_weaver",
            "char_name": "符华天师",
            "img_type": "poseSheet",
            "prompt": "Show 5 poses of the Talisman Weaver on one clean sheet: leaping with talismans, drawing a rune in mid-air, standing defiantly in the wind, sitting cross-legged, and casting a shield. Solid clean dark gray background."
        },
        {
            "char_id": "char_0017_talisman_weaver",
            "char_name": "符华天师",
            "img_type": "expressionSheet",
            "prompt": "An expression sheet showing 8 bust portraits of the Talisman Weaver in a clean grid: confident smile, angry shouting, closed eyes chanting, laughing, surprised, serious, battle-worn, and a gentle gaze. Clean dark gray background."
        },
        {
            "char_id": "char_0017_talisman_weaver",
            "char_name": "符华天师",
            "img_type": "detailSheet",
            "prompt": "A clean detail sheet showing close-up panels of the Talisman Weaver\'s features: the cinnabar mark on her forehead, the gold cloud embroidery on her collar, the carvings on her peachwood sword, and a yellow talisman paper with glowing red ink. Clean light gray background."
        },
        {
            "char_id": "char_0017_talisman_weaver",
            "char_name": "符华天师",
            "img_type": "materialPalette",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Talisman Weaver (符华天师)\nGender / age impression: young woman, heroic, confident Taoist scribe, exorcist aesthetic\nBody shape: tall, athletic, agile stance\nHair: silver-white hair tied in a high ponytail with a crimson ribbon\nEyes: bright golden eyes\nOutfit: black-and-vermilion-red Taoist robe with gold cloud patterns\nAccessories / weapon: a seven-star peachwood sword, a golden cinnabar brush, leather talisman pouches\nColor palette: cinnabar red, sulfur yellow, charcoal black, silver white\nFixed traits that must never change: silver-white hair, high ponytail, black-and-vermilion robe, floating paper talismans\n\nCurrent asset goal:\nGenerate a material and color palette sheet. Show swatches of black silk, vermilion satin, a silver-white hair sample, peachwood texture, and a yellow paper talisman sample next to a neutral front view of the character.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet, detailed fabric and material rendering, coherent design language, consistent facial identity, production-ready asset.\n\nComposition:\nClean design-board layout showing the character alongside neatly arranged material swatches.\n\nBackground:\nPlain gray background.\n\nConstraints:\nKeep the same face, hairstyle, outfit logic, color palette, body shape, and white hair.\nDo not redesign the character.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."
        },
        {
            "char_id": "char_0017_talisman_weaver",
            "char_name": "符华天师",
            "img_type": "outfitBreakdown",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Talisman Weaver (符华天师)\nGender / age impression: young woman, heroic, confident Taoist scribe, exorcist aesthetic\nBody shape: tall, athletic, agile stance\nHair: silver-white hair tied in a high ponytail with a crimson ribbon\nEyes: bright golden eyes\nOutfit: black-and-vermilion-red Taoist robe with gold cloud patterns\nAccessories / weapon: a seven-star peachwood sword, a golden cinnabar brush, leather talisman pouches\nColor palette: cinnabar red, sulfur yellow, charcoal black, silver white\nFixed traits that must never change: silver-white hair, high ponytail, black-and-vermilion robe, floating paper talismans\n\nCurrent asset goal:\nGenerate an outfit breakdown sheet. Show separate layers and components of her clothing: the outer black-and-vermilion robe, the inner tunic, the seven-star peachwood sword, and a yellow paper talisman.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet, detailed fabric and material rendering, coherent design language, consistent facial identity, production-ready asset.\n\nComposition:\nClean design board layout showing the clothes laid out and separated clearly.\n\nBackground:\nPlain light background.\n\nConstraints:\nKeep all parts consistent with the original character design.\nDo not redesign the character.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."
        },
        {
            "char_id": "char_0017_talisman_weaver",
            "char_name": "符华天师",
            "img_type": "damageState",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Talisman Weaver (符华天师)\nGender / age impression: young woman, heroic, confident Taoist scribe, exorcist aesthetic\nBody shape: tall, athletic, agile stance\nHair: silver-white hair tied in a high ponytail with a crimson ribbon\nEyes: bright golden eyes\nOutfit: black-and-vermilion-red Taoist robe with gold cloud patterns\nAccessories / weapon: a seven-star peachwood sword, a golden cinnabar brush, leather talisman pouches\nColor palette: cinnabar red, sulfur yellow, charcoal black, silver white\nFixed traits that must never change: silver-white hair, high ponytail, black-and-vermilion robe, floating paper talismans\n\nCurrent asset goal:\nGenerate damage state variants. Show 3 full-body versions of the same character: clean/default; battle-worn with torn sleeves and dirt smudges; and heavily damaged with her high ponytail undone releasing her messy white hair, her Taoist robe tattered and stained with blood, and her peachwood sword snapped in half. \n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet, detailed fabric and material rendering, coherent design language, consistent facial identity, production-ready asset.\n\nComposition:\nShow three side-by-side full-body versions of the character.\n\nBackground:\nSolid clean dark gray background.\n\nConstraints:\nDo not change the costume into a new outfit. Keep the same identity.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."
        }
    ]
    underworld_magistrate_plan = [
        {
            "char_id": "char_0018_underworld_magistrate",
            "char_name": "幽冥判官",
            "img_type": "main",
            "prompt": "A breathtaking traditional Chinese ink-wash epic fantasy concept art of the Underworld Magistrate. A mature, powerful East Asian man with sharply chiseled handsome features, cold authoritative dark eyes, and jet-black hair tied tightly into a formal top-knot. He wears an incredibly detailed black silk magistrate robe with sweeping golden flame and cloud embroidery along the cuffs and collar. He stands on the steps of an imposing underworld court gateway. In one hand he grips a massive scarlet-red judgment brush crackling with golden calligraphy energy. Heavy soul-lock chains of dark iron dangle from his waist. Dozens of glowing golden judgment scrolls spiral in the air around him, and spirit lanterns with blue ghost-fire line the ancient stone steps. Background is a towering underworld gate shrouded in black mist and cold blue spirit flames. High-fidelity ink brushstrokes, dramatic volumetric lighting, cinematic masterpiece, 8k."
        },
        {
            "char_id": "char_0018_underworld_magistrate",
            "char_name": "幽冥判官",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up portrait of the exact same Underworld Magistrate character from our conversation. Focus on his face and shoulders, capturing his sharp, cold authoritative features, jet-black hair in a formal top-knot, and black magistrate hat. The cold blue ghost-fire light from spirit lanterns casts a dramatic rim light onto his stern face. Solid, extremely dark, low-contrast studio background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0018_underworld_magistrate",
            "char_name": "幽冥判官",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same Underworld Magistrate character from our conversation. Show him on a solid, clean dark gray background with four different facial expressions side-by-side: one cold and impassive, one stern and commanding with eyes narrowed, one rare cold smile of satisfaction, and one full wrathful shout with golden calligraphy energy blazing around him. High-fidelity details, professional character model sheet, masterpiece, 8k."
        },
        {
            "char_id": "char_0018_underworld_magistrate",
            "char_name": "幽冥判官",
            "img_type": "turnaround",
            "prompt": "Now, draw a professional character turnaround model sheet of the exact same Underworld Magistrate character from our conversation. Show three full-body views: front, side, and back, standing in a neutral authoritative pose. He is wearing his black-and-gold magistrate robe and the soul-lock chains. Solid, clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0018_underworld_magistrate",
            "char_name": "幽冥判官",
            "img_type": "outfit",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Underworld Magistrate (幽冥判官)\nGender / age impression: mature man, authoritative and stern, 35-year appearance\nBody shape: tall, broad-shouldered, commanding presence\nHair: jet-black hair in a formal top-knot\nEyes: cold, dark authoritative eyes\nOutfit: black silk magistrate robe with gold flame embroidery, black official hat\nAccessories / weapon: a scarlet-red giant judgment brush, soul-lock iron chains\nColor palette: jet black, scarlet red, gold foil yellow, ghost-fire blue\nFixed traits that must never change: black magistrate hat, scarlet-and-gold robe, giant red judgment brush, soul-lock chains\n\nCurrent asset goal:\nGenerate an outfit variant image. Show three different outfits side-by-side: on the left, his default black-and-gold magistrate robe; in the middle, his underworld battle armor (dark iron breastplate with gold rune engravings over a black war tunic); on the right, his formal ceremonial robe (deep purple silk robe with silver constellation embroidery and a tall ceremonial crown).\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet.\n\nComposition:\nShow three side-by-side full-body views of the same character standing neutrally.\n\nBackground:\nPlain clean dark gray background.\n\nConstraints:\nKeep the same face, hairstyle, body shape, and cold authoritative bearing.\nDo not redesign the character.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face."
        },
        {
            "char_id": "char_0018_underworld_magistrate",
            "char_name": "幽冥判官",
            "img_type": "prop",
            "prompt": "Now, draw a high-fidelity detailed design sheet of the Underworld Magistrate's signature tools. Show: the giant scarlet judgment brush with gold calligraphy energy crackling at its tip, the heavy soul-lock iron chains with glowing rune links, and a floating golden judgment scroll with ancient spirit writing. Two angles each. Solid, clean dark gray background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0018_underworld_magistrate",
            "char_name": "幽冥判官",
            "img_type": "scene",
            "prompt": "Now, draw a stunning, highly detailed landscape scene concept art. An immense and imposing underworld court built of dark obsidian stone, massive columns carved with spirit rune reliefs, with blue ghost-fire lanterns lining the grand stairways. Glowing golden judgment scrolls drift in the cold dark air. Towering iron gates stand in the background under a starless void sky. Cinematic, hyper-realistic, masterpiece, 8k."
        },
        {
            "char_id": "char_0018_underworld_magistrate",
            "char_name": "幽冥判官",
            "img_type": "cover",
            "prompt": "A cinematic vertical cover art of the Underworld Magistrate standing at the crest of the underworld court steps, raising his scarlet judgment brush high as a tornado of golden glowing judgment scrolls spirals into a black sky. Cold blue ghost-fires frame his silhouette. High polish, dramatic rim lighting, 8k."
        },
        {
            "char_id": "char_0018_underworld_magistrate",
            "char_name": "幽冥判官",
            "img_type": "moodboard",
            "prompt": "A moodboard collage of 4 panels for the Underworld Magistrate: one showing close-up of black silk with gold flame embroidery stitching, one showing glowing golden spirit calligraphy on ancient stone, one showing blue ghost-fire lanterns hanging in the dark, and one showing a rusted iron soul-lock chain with glowing blue rune links. Dark, cold, authoritative tone, 8k."
        },
        {
            "char_id": "char_0018_underworld_magistrate",
            "char_name": "幽冥判官",
            "img_type": "sketch",
            "prompt": "A concept sketch sheet of monochrome pencil drawings showing the Underworld Magistrate in 3 study sketches: writing in mid-air with his judgment brush, standing stoically with soul-lock chains at his side, and unrolling a judgment scroll before him. Clean hand-drawn lines, traditional concept art sketch style, plain light background."
        },
        {
            "char_id": "char_0018_underworld_magistrate",
            "char_name": "幽冥判官",
            "img_type": "fullBody",
            "prompt": "Now, draw a full-body cinematic splash art of the exact same Underworld Magistrate character from our conversation. He stands imposingly in his black-and-gold magistrate robe, soul-lock chains at his hip, giant red judgment brush in hand, cold gaze forward. Solid, extremely dark, low-contrast studio background. Masterpiece, highly detailed, 8k."
        },
        {
            "char_id": "char_0018_underworld_magistrate",
            "char_name": "幽冥判官",
            "img_type": "modelSheet",
            "prompt": "A clean model sheet of the Underworld Magistrate showing full-body front, side, and back views. Standing neutrally in his black-and-gold magistrate robes and official hat. Even lighting, solid clean light gray background, no dramatic shadows, 8k."
        },
        {
            "char_id": "char_0018_underworld_magistrate",
            "char_name": "幽冥判官",
            "img_type": "poseSheet",
            "prompt": "Show 5 poses of the Underworld Magistrate on one clean sheet: writing a judgment verdict in mid-air, sweeping his chains in a wide arc, unrolling a scroll while reading coldly, walking up court steps with authority, and pointing his brush accusingly at the viewer. Solid clean dark gray background."
        },
        {
            "char_id": "char_0018_underworld_magistrate",
            "char_name": "幽冥判官",
            "img_type": "expressionSheet",
            "prompt": "An expression sheet showing 8 bust portraits of the Underworld Magistrate in a clean grid: cold and impassive, stern commanding glare, cold satisfaction smile, furious wrath with golden energy blazing, reading a scroll with concentration, looking away with contempt, surprised, and a rare moment of solemn sorrow. Clean dark gray background."
        },
        {
            "char_id": "char_0018_underworld_magistrate",
            "char_name": "幽冥判官",
            "img_type": "detailSheet",
            "prompt": "A clean detail sheet showing close-up panels of the Underworld Magistrate's features: the gold flame embroidery on his black collar, the rune carvings on his soul-lock chain links, the scarlet tip of his judgment brush crackling with energy, and the ancient spirit-script on a golden judgment scroll. Clean light gray background."
        },
        {
            "char_id": "char_0018_underworld_magistrate",
            "char_name": "幽冥判官",
            "img_type": "materialPalette",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Underworld Magistrate (幽冥判官)\nGender / age impression: mature man, authoritative and stern, 35-year appearance\nBody shape: tall, broad-shouldered, commanding presence\nHair: jet-black hair in a formal top-knot\nEyes: cold, dark authoritative eyes\nOutfit: black silk magistrate robe with gold flame embroidery, black official hat\nAccessories / weapon: a scarlet-red giant judgment brush, soul-lock iron chains\nColor palette: jet black, scarlet red, gold foil yellow, ghost-fire blue\nFixed traits that must never change: black magistrate hat, scarlet-and-gold robe, giant red judgment brush, soul-lock chains\n\nCurrent asset goal:\nGenerate a material and color palette sheet. Show swatches of black silk brocade, gold embroidery thread, scarlet-lacquered brush wood, dark iron chain metal, and a glowing blue ghost-fire sample next to a neutral front view of the character.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet, detailed fabric and material rendering, coherent design language, consistent facial identity, production-ready asset.\n\nComposition:\nClean design-board layout showing the character alongside neatly arranged material swatches.\n\nBackground:\nPlain gray background.\n\nConstraints:\nKeep the same face, hairstyle, outfit logic, color palette, body shape, and cold authoritative bearing.\nDo not redesign the character.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."
        },
        {
            "char_id": "char_0018_underworld_magistrate",
            "char_name": "幽冥判官",
            "img_type": "outfitBreakdown",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Underworld Magistrate (幽冥判官)\nGender / age impression: mature man, authoritative and stern, 35-year appearance\nBody shape: tall, broad-shouldered, commanding presence\nHair: jet-black hair in a formal top-knot\nEyes: cold, dark authoritative eyes\nOutfit: black silk magistrate robe with gold flame embroidery, black official hat\nAccessories / weapon: a scarlet-red giant judgment brush, soul-lock iron chains\nColor palette: jet black, scarlet red, gold foil yellow, ghost-fire blue\nFixed traits that must never change: black magistrate hat, scarlet-and-gold robe, giant red judgment brush, soul-lock chains\n\nCurrent asset goal:\nGenerate an outfit breakdown sheet. Show separate layers and components of his clothing: the outer black silk magistrate robe with gold embroidery, the inner dark tunic, the soul-lock chains, the black official hat, and the scarlet judgment brush.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet, detailed fabric and material rendering, coherent design language, consistent facial identity, production-ready asset.\n\nComposition:\nClean design board layout showing the clothes laid out and separated clearly.\n\nBackground:\nPlain light background.\n\nConstraints:\nKeep all parts consistent with the original character design.\nDo not redesign the character.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."
        },
        {
            "char_id": "char_0018_underworld_magistrate",
            "char_name": "幽冥判官",
            "img_type": "damageState",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Underworld Magistrate (幽冥判官)\nGender / age impression: mature man, authoritative and stern, 35-year appearance\nBody shape: tall, broad-shouldered, commanding presence\nHair: jet-black hair in a formal top-knot\nEyes: cold, dark authoritative eyes\nOutfit: black silk magistrate robe with gold flame embroidery, black official hat\nAccessories / weapon: a scarlet-red giant judgment brush, soul-lock iron chains\nColor palette: jet black, scarlet red, gold foil yellow, ghost-fire blue\nFixed traits that must never change: black magistrate hat, scarlet-and-gold robe, giant red judgment brush, soul-lock chains\n\nCurrent asset goal:\nGenerate damage state variants. Show 3 full-body versions of the same character: clean/default; battle-worn with singed gold embroidery and torn sleeves; and heavily damaged with his official hat knocked off revealing his disheveled top-knot, his black robe scorched and slashed, his soul-lock chains shattered and dragging on the ground, and his judgment brush cracked and leaking golden energy.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet, detailed fabric and material rendering, coherent design language, consistent facial identity, production-ready asset.\n\nComposition:\nShow three side-by-side full-body versions of the character.\n\nBackground:\nSolid clean dark gray background.\n\nConstraints:\nDo not change the costume into a new outfit. Keep the same identity.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."
        }
    ]
    frost_sword_immortal_plan = [
        {
            "char_id": "char_0019_frost_sword_immortal",
            "char_name": "雪魄剑仙",
            "img_type": "main",
            "prompt": "A breathtaking traditional Chinese ink-wash epic fantasy concept art of the Frost Sword Immortal. A young, ethereally beautiful East Asian woman with long flowing snow-white hair drifting freely in a cold wind. Her expression is serene yet razor-sharp. She wears a stunning white-and-silver flowing Hanfu robe with intricate frost-crystal embroidery and pale blue sash. She grips a colossal transparent ice-crystal sword in one hand, its blade pure as glacial ice, glowing faintly with cold pale blue light. Around her, a perfect orbital ring of dozens of smaller floating flying swords rotates slowly, each blade gleaming with icy reflection. Beneath her feet, frost patterns spread outward across the cracked ancient stone platform. Background is a mountain summit at dusk with aurora-like curtains of pale blue and white spiritual energy rippling across the sky. High-fidelity ink brushstrokes, dramatic volumetric lighting, cinematic masterpiece, 8k."
        },
        {
            "char_id": "char_0019_frost_sword_immortal",
            "char_name": "雪魄剑仙",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up portrait of the exact same Frost Sword Immortal character from our conversation. Focus on her face and shoulders, capturing her serene, ice-cold beautiful features and long snow-white hair flowing freely. The pale blue glow of her ice-crystal sword illuminates her cheekbones with a cold ethereal light. Solid, extremely dark, low-contrast studio background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0019_frost_sword_immortal",
            "char_name": "雪魄剑仙",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same Frost Sword Immortal character from our conversation. Show her on a solid, clean dark gray background with four different facial expressions side-by-side: one calm and distant, one cold contemptuous gaze, one rare look of focused battle intensity, and one fleeting gentle smile. High-fidelity details, professional character model sheet, masterpiece, 8k."
        },
        {
            "char_id": "char_0019_frost_sword_immortal",
            "char_name": "雪魄剑仙",
            "img_type": "turnaround",
            "prompt": "Now, draw a professional character turnaround model sheet of the exact same Frost Sword Immortal character from our conversation. Show three full-body views: front, side, and back, standing in a neutral pose. She is wearing her white-and-silver frost Hanfu robe. Solid, clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0019_frost_sword_immortal",
            "char_name": "雪魄剑仙",
            "img_type": "outfit",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Frost Sword Immortal (雪魄剑仙)\nGender / age impression: young woman, ethereally beautiful, cold and distant, 20-year appearance\nBody shape: slender, tall, graceful like snow\nHair: long flowing snow-white hair\nEyes: cold icy pale blue eyes\nOutfit: white-and-silver flowing Hanfu robe with frost-crystal embroidery\nAccessories / weapon: a transparent ice-crystal giant sword, a ring of floating flying swords\nColor palette: frost white, ice blue, silver gray, pale vermilion accent\nFixed traits that must never change: snow-white hair, ice-crystal sword, flying sword array, white-and-silver flowing robe\n\nCurrent asset goal:\nGenerate an outfit variant image. Show three different outfits side-by-side: on the left, her default white-and-silver frost Hanfu robe; in the middle, her battle armor (silver crystalline breastplate over a form-fitting white battle tunic with ice-pattern engravings); on the right, her sect formal robe (a pristine white and pale gold ceremonial robe with silver sword-motif embroidery and a sword-shaped hair pin).\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet.\n\nComposition:\nShow three side-by-side full-body views of the same character standing neutrally.\n\nBackground:\nPlain clean dark gray background.\n\nConstraints:\nKeep the same face, hairstyle, body shape, and cold ethereal bearing.\nDo not redesign the character.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face."
        },
        {
            "char_id": "char_0019_frost_sword_immortal",
            "char_name": "雪魄剑仙",
            "img_type": "prop",
            "prompt": "Now, draw a high-fidelity detailed design sheet of the Frost Sword Immortal's weapons. Show: the colossal transparent ice-crystal sword 'Frost Soul' from two angles showing its glacial blade clarity and cold blue glow, and three floating flying swords of different sizes arranged in the formation ring pattern. Solid, clean dark gray background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0019_frost_sword_immortal",
            "char_name": "雪魄剑仙",
            "img_type": "scene",
            "prompt": "Now, draw a stunning, highly detailed landscape scene concept art. The summit platform of the Void Sword Sect's mountain, a vast flat stone terrace with ancient carved sword runes, high above the clouds at golden dusk. Trails of pale blue frost energy drift in the mountain wind. Hundreds of flying swords are embedded in the cliff faces surrounding the platform, glinting in the last sunlight. Cinematic, hyper-realistic, masterpiece, 8k."
        },
        {
            "char_id": "char_0019_frost_sword_immortal",
            "char_name": "雪魄剑仙",
            "img_type": "cover",
            "prompt": "A cinematic vertical cover art of the Frost Sword Immortal descending from above, her white hair and silver robe trailing in the cold wind, her ice-crystal sword raised overhead while the orbital ring of flying swords spirals outward like a comet trail. Background is a pale blue aurora sky. High polish, dramatic rim lighting, 8k."
        },
        {
            "char_id": "char_0019_frost_sword_immortal",
            "char_name": "雪魄剑仙",
            "img_type": "moodboard",
            "prompt": "A moodboard collage of 4 panels for the Frost Sword Immortal: one showing close-up of transparent ice-crystal sword blade with internal frost fractals, one showing a snow-white silk fabric with silver thread embroidery, one showing pale blue aurora streaks over dark mountain silhouettes, and one showing a frozen mountain spring at dawn. Cold, ethereal, elegant tone, 8k."
        },
        {
            "char_id": "char_0019_frost_sword_immortal",
            "char_name": "雪魄剑仙",
            "img_type": "sketch",
            "prompt": "A concept sketch sheet of monochrome pencil drawings showing the Frost Sword Immortal in 3 study sketches: floating in the air with flying swords orbiting, landing from a descent with ice spreading underfoot, and sheathing her ice-crystal sword gracefully. Clean hand-drawn lines, traditional concept art sketch style, plain light background."
        },
        {
            "char_id": "char_0019_frost_sword_immortal",
            "char_name": "雪魄剑仙",
            "img_type": "fullBody",
            "prompt": "Now, draw a full-body cinematic splash art of the exact same Frost Sword Immortal character from our conversation. She stands gracefully in her white-and-silver Hanfu, holding the ice-crystal sword to her side, flying swords hovering around her, snow-white hair flowing freely. Solid, extremely dark, low-contrast studio background. Masterpiece, highly detailed, 8k."
        },
        {
            "char_id": "char_0019_frost_sword_immortal",
            "char_name": "雪魄剑仙",
            "img_type": "modelSheet",
            "prompt": "A clean model sheet of the Frost Sword Immortal showing full-body front, side, and back views. Standing neutrally in her white-and-silver frost Hanfu robes. Even lighting, solid clean light gray background, no dramatic shadows, 8k."
        },
        {
            "char_id": "char_0019_frost_sword_immortal",
            "char_name": "雪魄剑仙",
            "img_type": "poseSheet",
            "prompt": "Show 5 poses of the Frost Sword Immortal on one clean sheet: floating in mid-air with flying swords spiraling outward, a downward slash with ice-crystal sword, standing cross-armed with cold disdain, somersaulting between sword blades, and kneeling on one knee recovering breath after battle. Solid clean dark gray background."
        },
        {
            "char_id": "char_0019_frost_sword_immortal",
            "char_name": "雪魄剑仙",
            "img_type": "expressionSheet",
            "prompt": "An expression sheet showing 8 bust portraits of the Frost Sword Immortal in a clean grid: cold distant calm, cold contemptuous gaze, battle-focused intensity, fleeting gentle smile, surprised, deep in thought with eyes closed, sorrowful, and a rare determined heroic shout. Clean dark gray background."
        },
        {
            "char_id": "char_0019_frost_sword_immortal",
            "char_name": "雪魄剑仙",
            "img_type": "detailSheet",
            "prompt": "A clean detail sheet showing close-up panels of the Frost Sword Immortal's features: the internal frost fractal pattern inside her ice-crystal sword blade, the delicate silver frost-crystal embroidery on her white robe collar, the tip of a flying sword's blade with its pale blue energy edge, and the texture of her snow-white hair in the wind. Clean light gray background."
        },
        {
            "char_id": "char_0019_frost_sword_immortal",
            "char_name": "雪魄剑仙",
            "img_type": "materialPalette",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Frost Sword Immortal (雪魄剑仙)\nGender / age impression: young woman, ethereally beautiful, cold and distant, 20-year appearance\nBody shape: slender, tall, graceful like snow\nHair: long flowing snow-white hair\nEyes: cold icy pale blue eyes\nOutfit: white-and-silver flowing Hanfu robe with frost-crystal embroidery\nAccessories / weapon: a transparent ice-crystal giant sword, a ring of floating flying swords\nColor palette: frost white, ice blue, silver gray, pale vermilion accent\nFixed traits that must never change: snow-white hair, ice-crystal sword, flying sword array, white-and-silver flowing robe\n\nCurrent asset goal:\nGenerate a material and color palette sheet. Show swatches of white silk fabric, silver thread, transparent ice crystal, pale blue energy glow, and the hair white color next to a neutral front view of the character.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet, detailed fabric and material rendering, coherent design language, consistent facial identity, production-ready asset.\n\nComposition:\nClean design-board layout showing the character alongside neatly arranged material swatches.\n\nBackground:\nPlain gray background.\n\nConstraints:\nKeep the same face, hairstyle, outfit logic, color palette, body shape, and snow-white hair.\nDo not redesign the character.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."
        },
        {
            "char_id": "char_0019_frost_sword_immortal",
            "char_name": "雪魄剑仙",
            "img_type": "outfitBreakdown",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Frost Sword Immortal (雪魄剑仙)\nGender / age impression: young woman, ethereally beautiful, cold and distant, 20-year appearance\nBody shape: slender, tall, graceful like snow\nHair: long flowing snow-white hair\nEyes: cold icy pale blue eyes\nOutfit: white-and-silver flowing Hanfu robe with frost-crystal embroidery\nAccessories / weapon: a transparent ice-crystal giant sword, a ring of floating flying swords\nColor palette: frost white, ice blue, silver gray, pale vermilion accent\nFixed traits that must never change: snow-white hair, ice-crystal sword, flying sword array, white-and-silver flowing robe\n\nCurrent asset goal:\nGenerate an outfit breakdown sheet. Show separate layers and components of her clothing: the outer white silk flowing robe, the inner silver-edged under-robe, the pale blue sash, the ice-crystal sword, and a single flying sword from the array.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet, detailed fabric and material rendering, coherent design language, consistent facial identity, production-ready asset.\n\nComposition:\nClean design board layout showing the clothes laid out and separated clearly.\n\nBackground:\nPlain light background.\n\nConstraints:\nKeep all parts consistent with the original character design.\nDo not redesign the character.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."
        },
        {
            "char_id": "char_0019_frost_sword_immortal",
            "char_name": "雪魄剑仙",
            "img_type": "damageState",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Frost Sword Immortal (雪魄剑仙)\nGender / age impression: young woman, ethereally beautiful, cold and distant, 20-year appearance\nBody shape: slender, tall, graceful like snow\nHair: long flowing snow-white hair\nEyes: cold icy pale blue eyes\nOutfit: white-and-silver flowing Hanfu robe with frost-crystal embroidery\nAccessories / weapon: a transparent ice-crystal giant sword, a ring of floating flying swords\nColor palette: frost white, ice blue, silver gray, pale vermilion accent\nFixed traits that must never change: snow-white hair, ice-crystal sword, flying sword array, white-and-silver flowing robe\n\nCurrent asset goal:\nGenerate damage state variants. Show 3 full-body versions of the same character: clean/default; battle-worn with torn silver embroidery and small bloodstains on her white robe; and heavily damaged with her white robe torn and stained crimson, her flying swords all shattered and fallen, and her ice-crystal sword cracked with pale blue energy leaking from the fracture lines.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet, detailed fabric and material rendering, coherent design language, consistent facial identity, production-ready asset.\n\nComposition:\nShow three side-by-side full-body versions of the character.\n\nBackground:\nSolid clean dark gray background.\n\nConstraints:\nDo not change the costume into a new outfit. Keep the same identity.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."
        }
    ]

    zen_monk_plan = [
        {
            "char_id": "char_0020_zen_monk",
            "char_name": "浮屠圣僧",
            "img_type": "main",
            "prompt": "A breathtaking traditional Chinese ink-wash epic fantasy concept art of the Zen Monk. A young serene East Asian monk with a shaved head and handsome features, his eyes filled with deep compassion. He wears a rustic grey monk robe under a dark gold-patterned cassock. He holds a weathered wooden nine-ring staff, its bronze rings glowing with warm golden light. Behind his head, a circular golden Buddha halo radiates soft energy, driving back the surrounding dark demonic mist. The setting is a ruined ancient temple at dusk, with stone rubble and swirling golden autumn leaves. High-fidelity ink brushstrokes, volumetric lighting, cinematic masterpiece, 8k."
        },
        {
            "char_id": "char_0020_zen_monk",
            "char_name": "浮屠圣僧",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up portrait of the exact same Zen Monk character from our conversation. Focus on his face and shoulders, capturing his serene, shaved-head handsome features and tranquil, compassionate expression. The soft golden glow from his circular Buddha halo illuminates his cheekbones with a warm, peaceful light. Solid, extremely dark, low-contrast studio background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0020_zen_monk",
            "char_name": "浮屠圣僧",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same Zen Monk character from our conversation. Show him on a solid, clean dark gray background with four different facial expressions side-by-side: one serene and peaceful, one with eyes closed in quiet chanting meditation, one showing a powerful wrathful glare (金刚怒目) to subdue demons, and one gentle warm smile of compassion. High-fidelity details, professional character model sheet, masterpiece, 8k."
        },
        {
            "char_id": "char_0020_zen_monk",
            "char_name": "浮屠圣僧",
            "img_type": "turnaround",
            "prompt": "Now, draw a professional character turnaround model sheet of the exact same Zen Monk character from our conversation. Show three full-body views: front, side, and back, standing in a neutral pose. He is wearing his grey monk robe and gold-patterned cassock. Solid, clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0020_zen_monk",
            "char_name": "浮屠圣僧",
            "img_type": "outfit",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Zen Monk (浮屠圣僧)\nGender / age impression: young man, serene and compassionate, 20-year appearance\nBody shape: slender, tall, erect posture\nHair: shaved head, bald\nEyes: calm dark brown eyes\nOutfit: grey monk robe under a rustic cassock with subtle dark golden patterns\nAccessories / weapon: a weathered wooden nine-ring staff, a large string of brown wooden Bodhi beads\nColor palette: withered wood brown, cassock grey, dark gold, buddha-light yellow\nFixed traits that must never change: shaved head, weathered nine-ring staff, large brown Bodhi beads, grey-and-gold monk robe, golden circular halo\n\nCurrent asset goal:\nGenerate an outfit variant image. Show three different outfits side-by-side: on the left, his default grey monk robe with gold-patterned cassock; in the middle, his ascetic traveling robe (a simple patched white-and-grey hemp robe with straw sandals and a conical bamboo hat hanging on his back); on the right, his temple formal vestments (a brilliant saffron-orange silk robe with a splendid gold-woven brocade袈裟 and polished bronze ornaments).\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet.\n\nComposition:\nShow three side-by-side full-body views of the same character standing neutrally.\n\nBackground:\nPlain clean dark gray background.\n\nConstraints:\nKeep the same face, bald head, body shape, and serene bearing.\nDo not redesign the character.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face."
        },
        {
            "char_id": "char_0020_zen_monk",
            "char_name": "浮屠圣僧",
            "img_type": "prop",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Zen Monk (浮屠圣僧)\nGender / age impression: young man, serene and compassionate, 20-year appearance\nBody shape: slender, tall, erect posture\nHair: shaved head, bald\nEyes: calm dark brown eyes\nOutfit: grey monk robe under a rustic cassock with subtle dark golden patterns\nAccessories / weapon: a weathered wooden nine-ring staff, a large string of brown wooden Bodhi beads\nColor palette: withered wood brown, cassock grey, dark gold, buddha-light yellow\nFixed traits that must never change: shaved head, weathered nine-ring staff, large brown Bodhi beads, grey-and-gold monk robe, golden circular halo\n\nCurrent asset goal:\nGenerate a prop and weapon reference sheet. Show details of his signature weapon: the long weathered wooden ring-staff from multiple angles, highlighting the nine bronze rings hanging from the top and the ancient Buddhist runes carved into the dark wood. Also show a close-up of a single brown wooden Bodhi bead from his large string of beads, showing the natural wood grain and a carved lotus motif.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet.\n\nComposition:\nClean design-board layout showing the staff and beads from multiple viewpoints.\n\nBackground:\nSolid plain light gray background.\n\nConstraints:\nNo random extra weapons. Do not redesign the signature items."
        },
        {
            "char_id": "char_0020_zen_monk",
            "char_name": "浮屠圣僧",
            "img_type": "scene",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Zen Monk (浮屠圣僧)\nGender / age impression: young man, serene and compassionate, 20-year appearance\nBody shape: slender, tall, erect posture\nHair: shaved head, bald\nEyes: calm dark brown eyes\nOutfit: grey monk robe under a rustic cassock with subtle dark golden patterns\nAccessories / weapon: a weathered wooden nine-ring staff, a large string of brown wooden Bodhi beads\nColor palette: withered wood brown, cassock grey, dark gold, buddha-light yellow\nFixed traits that must never change: shaved head, weathered nine-ring staff, large brown Bodhi beads, grey-and-gold monk robe, golden circular halo\n\nCurrent asset goal:\nGenerate a scene image featuring the character. Show the Zen Monk standing peacefully inside the ancient ruined hall of the Grand Bodhi Temple at sunset. Massive stone columns are cracked, and wild vines grow on the walls. The warm golden light of the setting sun filters through the collapsed roof, lighting up the dust particles in the air, creating a serene, historic atmosphere.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet.\n\nComposition:\nThe character is visible and placed in the center-right of the temple hall, looking up at the sky.\n\nBackground:\nA ruined ancient temple hall at sunset, rich with historical detail.\n\nConstraints:\nKeep the character identity stable."
        },
        {
            "char_id": "char_0020_zen_monk",
            "char_name": "浮屠圣僧",
            "img_type": "cover",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Zen Monk (浮屠圣僧)\nGender / age impression: young man, serene and compassionate, 20-year appearance\nBody shape: slender, tall, erect posture\nHair: shaved head, bald\nEyes: calm dark brown eyes\nOutfit: grey monk robe under a rustic cassock with subtle dark golden patterns\nAccessories / weapon: a weathered wooden nine-ring staff, a large string of brown wooden Bodhi beads\nColor palette: withered wood brown, cassock grey, dark gold, buddha-light yellow\nFixed traits that must never change: shaved head, weathered nine-ring staff, large brown Bodhi beads, grey-and-gold monk robe, golden circular halo\n\nCurrent asset goal:\nGenerate a cover image. Show a powerful, iconic vertical shot of the Zen Monk striking his nine-ring staff onto the stone floor, sending ripples of golden energy and Sanskrit characters outward. His grey-and-gold robes billow dramatically, and his golden circular halo shines brightly against a background of storming dark demonic clouds.\n\nStyle:\nEastern fantasy key art, high-polish cover illustration.\n\nComposition:\nVertical frame, the character is the main focal point, with a strong silhouette and room for title placement.\n\nBackground:\nA sky filled with dark demonic storm clouds, parted by golden rays of Buddha light."
        },
        {
            "char_id": "char_0020_zen_monk",
            "char_name": "浮屠圣僧",
            "img_type": "moodboard",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Zen Monk (浮屠圣僧)\nGender / age impression: young man, serene and compassionate, 20-year appearance\nBody shape: slender, tall, erect posture\nHair: shaved head, bald\nEyes: calm dark brown eyes\nOutfit: grey monk robe under a rustic cassock with subtle dark golden patterns\nAccessories / weapon: a weathered wooden nine-ring staff, a large string of brown wooden Bodhi beads\nColor palette: withered wood brown, cassock grey, dark gold, buddha-light yellow\nFixed traits that must never change: shaved head, weathered nine-ring staff, large brown Bodhi beads, grey-and-gold monk robe, golden circular halo\n\nCurrent asset goal:\nGenerate a moodboard. Show a collection of textures and colors representing the Zen Monk's world: a weathered ancient Buddhist stone wall with moss, a bowl of clear water reflecting a lotus flower, a golden particle light effect, dark grey fabric texture, and dried brown Bodhi seeds.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet.\n\nComposition:\nA clean collection of textures and visual motifs arranged neatly on a dark gray background."
        },
        {
            "char_id": "char_0020_zen_monk",
            "char_name": "浮屠圣僧",
            "img_type": "sketch",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Zen Monk (浮屠圣僧)\nGender / age impression: young man, serene and compassionate, 20-year appearance\nBody shape: slender, tall, erect posture\nHair: shaved head, bald\nEyes: calm dark brown eyes\nOutfit: grey monk robe under a rustic cassock with subtle dark golden patterns\nAccessories / weapon: a weathered wooden nine-ring staff, a large string of brown wooden Bodhi beads\nColor palette: withered wood brown, cassock grey, dark gold, buddha-light yellow\nFixed traits that must never change: shaved head, weathered nine-ring staff, large brown Bodhi beads, grey-and-gold monk robe, golden circular halo\n\nCurrent asset goal:\nGenerate a clean line art structure sketch. Show a structural study of the Zen Monk's posture, his hand positions for different Mudras (such as the Abhaya Mudra and Vajra Mudra), and how his cassock folds and drapes over his shoulder.\n\nStyle:\nEastern fantasy concept art, clean line art drawing, structural sketch, minimal shading.\n\nComposition:\nMultiple sketch panels arranged on a white background, showing anatomy and drapery lines."
        },
        {
            "char_id": "char_0020_zen_monk",
            "char_name": "浮屠圣僧",
            "img_type": "fullBody",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Zen Monk (浮屠圣僧)\nGender / age impression: young man, serene and compassionate, 20-year appearance\nBody shape: slender, tall, erect posture\nHair: shaved head, bald\nEyes: calm dark brown eyes\nOutfit: grey monk robe under a rustic cassock with subtle dark golden patterns\nAccessories / weapon: a weathered wooden nine-ring staff, a large string of brown wooden Bodhi beads\nColor palette: withered wood brown, cassock grey, dark gold, buddha-light yellow\nFixed traits that must never change: shaved head, weathered nine-ring staff, large brown Bodhi beads, grey-and-gold monk robe, golden circular halo\n\nCurrent asset goal:\nGenerate a full-body standing character art. Show the Zen Monk standing in a calm, balanced pose, holding his wooden nine-ring staff upright in one hand, while his other hand is in a mudra of blessing. His full robes and wooden beads are clearly visible from head to toe.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet.\n\nComposition:\nFull-body front view, standing neutrally, no crop.\n\nBackground:\nPlain light gray studio background."
        },
        {
            "char_id": "char_0020_zen_monk",
            "char_name": "浮屠圣僧",
            "img_type": "modelSheet",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Zen Monk (浮屠圣僧)\nGender / age impression: young man, serene and compassionate, 20-year appearance\nBody shape: slender, tall, erect posture\nHair: shaved head, bald\nEyes: calm dark brown eyes\nOutfit: grey monk robe under a rustic cassock with subtle dark golden patterns\nAccessories / weapon: a weathered wooden nine-ring staff, a large string of brown wooden Bodhi beads\nColor palette: withered wood brown, cassock grey, dark gold, buddha-light yellow\nFixed traits that must never change: shaved head, weathered nine-ring staff, large brown Bodhi beads, grey-and-gold monk robe, golden circular halo\n\nCurrent asset goal:\nGenerate a clean model sheet / standard character design reference. Show the front, side, and back view of the Zen Monk, standing in a neutral pose.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet, even lighting.\n\nComposition:\nThree side-by-side full-body views of the character on a light gray background, no dramatic shadows."
        },
        {
            "char_id": "char_0020_zen_monk",
            "char_name": "浮屠圣僧",
            "img_type": "poseSheet",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Zen Monk (浮屠圣僧)\nGender / age impression: young man, serene and compassionate, 20-year appearance\nBody shape: slender, tall, erect posture\nHair: shaved head, bald\nEyes: calm dark brown eyes\nOutfit: grey monk robe under a rustic cassock with subtle dark golden patterns\nAccessories / weapon: a weathered wooden nine-ring staff, a large string of brown wooden Bodhi beads\nColor palette: withered wood brown, cassock grey, dark gold, buddha-light yellow\nFixed traits that must never change: shaved head, weathered nine-ring staff, large brown Bodhi beads, grey-and-gold monk robe, golden circular halo\n\nCurrent asset goal:\nGenerate a pose sheet for animation. Show 5 poses of the same Zen Monk character on one sheet: standing in deep prayer with hands pressed together; walking slowly with his staff; sitting cross-legged in meditation; striking his staff forward in defense; and standing battle-worn with his hand forming a protective shield seal.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet.\n\nComposition:\nShow 5 poses side-by-side on a plain light gray background.\n\nConstraints:\nKeep the face, bald head, robes, and proportions consistent across all poses."
        },
        {
            "char_id": "char_0020_zen_monk",
            "char_name": "浮屠圣僧",
            "img_type": "expressionSheet",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Zen Monk (浮屠圣僧)\nGender / age impression: young man, serene and compassionate, 20-year appearance\nBody shape: slender, tall, erect posture\nHair: shaved head, bald\nEyes: calm dark brown eyes\nOutfit: grey monk robe under a rustic cassock with subtle dark golden patterns\nAccessories / weapon: a weathered wooden nine-ring staff, a large string of brown wooden Bodhi beads\nColor palette: withered wood brown, cassock grey, dark gold, buddha-light yellow\nFixed traits that must never change: shaved head, weathered nine-ring staff, large brown Bodhi beads, grey-and-gold monk robe, golden circular halo\n\nCurrent asset goal:\nGenerate an expression sheet. Show 8 bust portraits of the Zen Monk in a clean grid: calm and serene, gentle compassionate smile, eyes closed in deep meditation, focused chanting face, alert warning gaze, a stern look of warning, sorrowful reflection, and a determined shout of exorcism.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet.\n\nComposition:\n8 bust portraits in a clean grid on a plain dark gray background.\n\nConstraints:\nKeep the face structure, bald head, eyes, and collar details consistent."
        },
        {
            "char_id": "char_0020_zen_monk",
            "char_name": "浮屠圣僧",
            "img_type": "detailSheet",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Zen Monk (浮屠圣僧)\nGender / age impression: young man, serene and compassionate, 20-year appearance\nBody shape: slender, tall, erect posture\nHair: shaved head, bald\nEyes: calm dark brown eyes\nOutfit: grey monk robe under a rustic cassock with subtle dark golden patterns\nAccessories / weapon: a weathered wooden nine-ring staff, a large string of brown wooden Bodhi beads\nColor palette: withered wood brown, cassock grey, dark gold, buddha-light yellow\nFixed traits that must never change: shaved head, weathered nine-ring staff, large brown Bodhi beads, grey-and-gold monk robe, golden circular halo\n\nCurrent asset goal:\nGenerate a detail sheet showing close-up panels: the bronze ring ornaments on his staff, the Sanskrit characters engraved on his Bodhi beads, the delicate golden thread stitching on his cassock, and his hands held in a complex mudra seal with faint light emanating from the palms.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet.\n\nComposition:\nMultiple close-up panels arranged neatly on a light gray background."
        },
        {
            "char_id": "char_0020_zen_monk",
            "char_name": "浮屠圣僧",
            "img_type": "materialPalette",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Zen Monk (浮屠圣僧)\nGender / age impression: young man, serene and compassionate, 20-year appearance\nBody shape: slender, tall, erect posture\nHair: shaved head, bald\nEyes: calm dark brown eyes\nOutfit: grey monk robe under a rustic cassock with subtle dark golden patterns\nAccessories / weapon: a weathered wooden nine-ring staff, a large string of brown wooden Bodhi beads\nColor palette: withered wood brown, cassock grey, dark gold, buddha-light yellow\nFixed traits that must never change: shaved head, weathered nine-ring staff, large brown Bodhi beads, grey-and-gold monk robe, golden circular halo\n\nCurrent asset goal:\nGenerate a material and color palette sheet. Show swatches of coarse grey cotton fabric, gold embroidered thread, weathered dark wood, polished bronze, and the soft golden light effect, next to a neutral front view of the character.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet.\n\nComposition:\nThe character standing alongside neatly arranged color and material blocks.\n\nBackground:\nPlain light gray background."
        },
        {
            "char_id": "char_0020_zen_monk",
            "char_name": "浮屠圣僧",
            "img_type": "outfitBreakdown",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Zen Monk (浮屠圣僧)\nGender / age impression: young man, serene and compassionate, 20-year appearance\nBody shape: slender, tall, erect posture\nHair: shaved head, bald\nEyes: calm dark brown eyes\nOutfit: grey monk robe under a rustic cassock with subtle dark golden patterns\nAccessories / weapon: a weathered wooden nine-ring staff, a large string of brown wooden Bodhi beads\nColor palette: withered wood brown, cassock grey, dark gold, buddha-light yellow\nFixed traits that must never change: shaved head, weathered nine-ring staff, large brown Bodhi beads, grey-and-gold monk robe, golden circular halo\n\nCurrent asset goal:\nGenerate an outfit breakdown sheet. Show separate layers and components of his clothing: the inner grey linen monk robe, the outer gold-bordered cassock showing how it wraps, the wooden Bodhi beads, and his straw sandals with leg wraps.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet.\n\nComposition:\nSeparated clothing items laid out clearly on a plain background."
        },
        {
            "char_id": "char_0020_zen_monk",
            "char_name": "浮屠圣僧",
            "img_type": "damageState",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Zen Monk (浮屠圣僧)\nGender / age impression: young man, serene and compassionate, 20-year appearance\nBody shape: slender, tall, erect posture\nHair: shaved head, bald\nEyes: calm dark brown eyes\nOutfit: grey monk robe under a rustic cassock with subtle dark golden patterns\nAccessories / weapon: a weathered wooden nine-ring staff, a large string of brown wooden Bodhi beads\nColor palette: withered wood brown, cassock grey, dark gold, buddha-light yellow\nFixed traits that must never change: shaved head, weathered nine-ring staff, large brown Bodhi beads, grey-and-gold monk robe, golden circular halo\n\nCurrent asset goal:\nGenerate damage state variants. Show 3 full-body versions of the same character: clean/default; battle-worn with his cassock torn at the shoulder showing minor cuts and dirt; and heavily damaged in his ascetic final stand: his grey monk robe torn and stained with blood, his wooden Bodhi beads broken and scattered around his feet, his weathered nine-ring staff cracked and splintered, and his body enveloped in a soft golden aura while red spiritual fire leaks from his eyes and hands.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet.\n\nComposition:\nShow three side-by-side full-body versions of the character.\n\nBackground:\nSolid clean dark gray background.\n\nConstraints:\nDo not change the costume into a new outfit. Keep the same identity.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."
        }
    ]
    shadow_puppeteer_plan = [
        {
            "char_id": "char_0021_shadow_puppeteer",
            "char_name": "皮影御灵师",
            "img_type": "main",
            "prompt": "A breathtaking traditional Chinese ink-wash epic fantasy concept art of the Shadow Puppeteer. A young East Asian woman in a black and red traditional opera costume, her eyes glowing vibrant scarlet. Her fingers wrap glowing red silk threads connected to a white paper screen. Behind the screen, massive shadow warriors with glowing red opera masks are projected. Setting is an abandoned wooden theater stage at night under a pale crescent moon, with red silk banners swirling. High-fidelity ink brushstrokes, dramatic volumetric lighting, masterpiece, 8k."
        },
        {
            "char_id": "char_0021_shadow_puppeteer",
            "char_name": "皮影御灵师",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up portrait of the exact same Shadow Puppeteer character from our conversation. Focus on her face and shoulders, capturing her mysterious pale features, glowing scarlet eyes, and black hair in an opera updo with crimson pins. Eerie red lighting from the silk threads illuminates her cheekbones. Solid, extremely dark, low-contrast studio background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0021_shadow_puppeteer",
            "char_name": "皮影御灵师",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same Shadow Puppeteer character from our conversation. Show her on a solid, clean dark gray background with four different facial expressions side-by-side: one mysterious smile, one chanting with eyes closed, one wrathful operatic stare (金刚怒目), and one sorrowful dramatic expression. High-fidelity details, professional character model sheet, masterpiece, 8k."
        },
        {
            "char_id": "char_0021_shadow_puppeteer",
            "char_name": "皮影御灵师",
            "img_type": "turnaround",
            "prompt": "Now, draw a professional character turnaround model sheet of the exact same Shadow Puppeteer character from our conversation. Show three full-body views: front, side, and back, standing in a neutral pose. She is wearing her black-and-red traditional opera costume. Solid, clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0021_shadow_puppeteer",
            "char_name": "皮影御灵师",
            "img_type": "outfit",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Shadow Puppeteer (皮影御灵师)\nGender / age impression: young woman, mysterious and theatrical, 19-year appearance\nBody shape: slender, delicate, classical posture\nHair: black hair in classical opera updo, red hairpins\nEyes: glowing scarlet red eyes\nOutfit: black and crimson traditional Chinese opera costume with flowing water sleeves\nAccessories / weapon: crimson paper-cuts, glowing red silk threads, semi-translucent shadow screen\nColor palette: cinnabar red, opera black, screen white, moonlight grey\nFixed traits that must never change: scarlet glowing eyes, opera updo, black-and-red opera costume, glowing red silk threads, giant shadow screen\n\nCurrent asset goal:\nGenerate an outfit variant image. Show three different outfits side-by-side: on the left, her default black-and-red opera costume; in the middle, her casual traveling Hanfu (a simple dark grey linen robe with red sash and straw sandals); on the right, her ritual ceremonial vestments (a magnificent crimson silk robe with golden phoenix paper-cut embroidery and flowing red water sleeves).\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet.\n\nComposition:\nShow three side-by-side full-body views of the same character standing neutrally.\n\nBackground:\nPlain clean dark gray background.\n\nConstraints:\nKeep the same face, hairstyle, body shape, and mysterious bearing.\nDo not redesign the character.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face."
        },
        {
            "char_id": "char_0021_shadow_puppeteer",
            "char_name": "皮影御灵师",
            "img_type": "prop",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Shadow Puppeteer (皮影御灵师)\nGender / age impression: young woman, mysterious and theatrical, 19-year appearance\nBody shape: slender, delicate, classical posture\nHair: black hair in classical opera updo, red hairpins\nEyes: glowing scarlet red eyes\nOutfit: black and crimson traditional Chinese opera costume with flowing water sleeves\nAccessories / weapon: crimson paper-cuts, glowing red silk threads, semi-translucent shadow screen\nColor palette: cinnabar red, opera black, screen white, moonlight grey\nFixed traits that must never change: scarlet glowing eyes, opera updo, black-and-red opera costume, glowing red silk threads, giant shadow screen\n\nCurrent asset goal:\nGenerate a prop and weapon reference sheet. Show details of his signature weapons: the red-glowing silk threads wrapping around her fingers, the intricate paper-cut patterns of the shadow soldiers on thick cinnabar-dyed paper, and the layout of the folding wooden shadow screen from front and side view.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet.\n\nComposition:\nClean design-board layout showing threads, paper-cuts, and the screen.\n\nBackground:\nSolid plain light gray background.\n\nConstraints:\nNo random extra weapons. Do not redesign the signature items."
        },
        {
            "char_id": "char_0021_shadow_puppeteer",
            "char_name": "皮影御灵师",
            "img_type": "scene",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Shadow Puppeteer (皮影御灵师)\nGender / age impression: young woman, mysterious and theatrical, 19-year appearance\nBody shape: slender, delicate, classical posture\nHair: black hair in classical opera updo, red hairpins\nEyes: glowing scarlet red eyes\nOutfit: black and crimson traditional Chinese opera costume with flowing water sleeves\nAccessories / weapon: crimson paper-cuts, glowing red silk threads, semi-translucent shadow screen\nColor palette: cinnabar red, opera black, screen white, moonlight grey\nFixed traits that must never change: scarlet glowing eyes, opera updo, black-and-red opera costume, glowing red silk threads, giant shadow screen\n\nCurrent asset goal:\nGenerate a scene image featuring the character. Show the Shadow Puppeteer performing on a dilapidated wooden theater stage in an abandoned forest at night. Pale moonlight filters through the trees, casting long shadows. Red silk banners hang torn from the rafters, and her white shadow screen glows with soft red light, creating a mysterious theatrical atmosphere.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet.\n\nComposition:\nA wide-angle landscape shot. Crucially, the character is NOT in the center. The character must be very small and positioned off-center at the far-right third of the frame, silhouetted by the glowing screen. The center of the image must be empty, showcasing the dilapidated stage floorboards and the eerie environment, emphasizing a wide scenery layout.\n\nBackground:\nAn abandoned outdoor wooden theater stage at night, rich with details.\n\nConstraints:\nKeep the character identity stable. The character must be off-center (rule of thirds), not in the center."
        },
        {
            "char_id": "char_0021_shadow_puppeteer",
            "char_name": "皮影御灵师",
            "img_type": "cover",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Shadow Puppeteer (皮影御灵师)\nGender / age impression: young woman, mysterious and theatrical, 19-year appearance\nBody shape: slender, delicate, classical posture\nHair: black hair in classical opera updo, red hairpins\nEyes: glowing scarlet red eyes\nOutfit: black and crimson traditional Chinese opera costume with flowing water sleeves\nAccessories / weapon: crimson paper-cuts, glowing red silk threads, semi-translucent shadow screen\nColor palette: cinnabar red, opera black, screen white, moonlight grey\nFixed traits that must never change: scarlet glowing eyes, opera updo, black-and-red opera costume, glowing red silk threads, giant shadow screen\n\nCurrent asset goal:\nGenerate a cover image. Show a powerful, iconic vertical shot of the Shadow Puppeteer pulling her red silk threads, with massive shadow warriors rising behind her in a whirlwind of crimson paper-cuts and wind. Her opera costume water sleeves billow dramatically, and her scarlet eyes glow intensely under the moonlight.\n\nStyle:\nEastern fantasy key art, high-polish cover illustration.\n\nComposition:\nVertical frame, the character is the main focal point, with a strong silhouette and room for title placement.\n\nBackground:\nA crescent moon in a dark night sky filled with swirling crimson paper-cuts and wind."
        },
        {
            "char_id": "char_0021_shadow_puppeteer",
            "char_name": "皮影御灵师",
            "img_type": "moodboard",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Shadow Puppeteer (皮影御灵师)\nGender / age impression: young woman, mysterious and theatrical, 19-year appearance\nBody shape: slender, delicate, classical posture\nHair: black hair in classical opera updo, red hairpins\nEyes: glowing scarlet red eyes\nOutfit: black and crimson traditional Chinese opera costume with flowing water sleeves\nAccessories / weapon: crimson paper-cuts, glowing red silk threads, semi-translucent shadow screen\nColor palette: cinnabar red, opera black, screen white, moonlight grey\nFixed traits that must never change: scarlet glowing eyes, opera updo, black-and-red opera costume, glowing red silk threads, giant shadow screen\n\nCurrent asset goal:\nGenerate a moodboard. Show a collection of textures and colors representing the Shadow Puppeteer's world: red paper-cuts with hollow patterns, glowing red silk thread texture, dark lacquered wood, white translucent paper, and a crescent moon in a dark night sky.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet.\n\nComposition:\nA clean collection of textures and visual motifs arranged neatly on a dark gray background."
        },
        {
            "char_id": "char_0021_shadow_puppeteer",
            "char_name": "皮影御灵师",
            "img_type": "sketch",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Shadow Puppeteer (皮影御灵师)\nGender / age impression: young woman, mysterious and theatrical, 19-year appearance\nBody shape: slender, delicate, classical posture\nHair: black hair in classical opera updo, red hairpins\nEyes: glowing scarlet red eyes\nOutfit: black and crimson traditional Chinese opera costume with flowing water sleeves\nAccessories / weapon: crimson paper-cuts, glowing red silk threads, semi-translucent shadow screen\nColor palette: cinnabar red, opera black, screen white, moonlight grey\nFixed traits that must never change: scarlet glowing eyes, opera updo, black-and-red opera costume, glowing red silk threads, giant shadow screen\n\nCurrent asset goal:\nGenerate a clean line art structure sketch. Show a structural study of the Shadow Puppeteer's hand gestures for operating the silk threads, the anatomy and posture of the shadow warriors, and the folding mechanism of the screen.\n\nStyle:\nEastern fantasy concept art, clean line art drawing, structural sketch, minimal shading.\n\nComposition:\nMultiple sketch panels arranged on a white background, showing hands, shadows, and screen geometry."
        },
        {
            "char_id": "char_0021_shadow_puppeteer",
            "char_name": "皮影御灵师",
            "img_type": "fullBody",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Shadow Puppeteer (皮影御灵师)\nGender / age impression: young woman, mysterious and theatrical, 19-year appearance\nBody shape: slender, delicate, classical posture\nHair: black hair in classical opera updo, red hairpins\nEyes: glowing scarlet red eyes\nOutfit: black and crimson traditional Chinese opera costume with flowing water sleeves\nAccessories / weapon: crimson paper-cuts, glowing red silk threads, semi-translucent shadow screen\nColor palette: cinnabar red, opera black, screen white, moonlight grey\nFixed traits that must never change: scarlet glowing eyes, opera updo, black-and-red opera costume, glowing red silk threads, giant shadow screen\n\nCurrent asset goal:\nGenerate a full-body standing character art. Show the Shadow Puppeteer standing in a theatrical pose, with one hand holding a crimson paper cutout, and the other hand raising red silk threads. Her full opera costume, updo hair, and shoes are clearly visible from head to toe.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet.\n\nComposition:\nFull-body front view, standing neutrally, no crop.\n\nBackground:\nPlain light gray studio background."
        },
        {
            "char_id": "char_0021_shadow_puppeteer",
            "char_name": "皮影御灵师",
            "img_type": "modelSheet",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Shadow Puppeteer (皮影御灵师)\nGender / age impression: young woman, mysterious and theatrical, 19-year appearance\nBody shape: slender, delicate, classical posture\nHair: black hair in classical opera updo, red hairpins\nEyes: glowing scarlet red eyes\nOutfit: black and crimson traditional Chinese opera costume with flowing water sleeves\nAccessories / weapon: crimson paper-cuts, glowing red silk threads, semi-translucent shadow screen\nColor palette: cinnabar red, opera black, screen white, moonlight grey\nFixed traits that must never change: scarlet glowing eyes, opera updo, black-and-red opera costume, glowing red silk threads, giant shadow screen\n\nCurrent asset goal:\nGenerate a clean model sheet / standard character design reference. Show the front, side, and back view of the Shadow Puppeteer, standing in a neutral pose.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet, even lighting.\n\nComposition:\nThree side-by-side full-body views of the character on a light gray background, no dramatic shadows."
        },
        {
            "char_id": "char_0021_shadow_puppeteer",
            "char_name": "皮影御灵师",
            "img_type": "poseSheet",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Shadow Puppeteer (皮影御灵师)\nGender / age impression: young woman, mysterious and theatrical, 19-year appearance\nBody shape: slender, delicate, classical posture\nHair: black hair in classical opera updo, red hairpins\nEyes: glowing scarlet red eyes\nOutfit: black and crimson traditional Chinese opera costume with flowing water sleeves\nAccessories / weapon: crimson paper-cuts, glowing red silk threads, semi-translucent shadow screen\nColor palette: cinnabar red, opera black, screen white, moonlight grey\nFixed traits that must never change: scarlet glowing eyes, opera updo, black-and-red opera costume, glowing red silk threads, giant shadow screen\n\nCurrent asset goal:\nGenerate a pose sheet for animation. Show 5 poses of the same Shadow Puppeteer character on one sheet: operating threads in a dancing pose; walking with water sleeves flowing; sitting cross-legged cutting paper; jumping backward while throwing paper-cuts; and standing battle-worn behind her screen.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet.\n\nComposition:\nShow 5 poses side-by-side on a plain light gray background.\n\nConstraints:\nKeep the face, hair, costume, and proportions consistent across all poses."
        },
        {
            "char_id": "char_0021_shadow_puppeteer",
            "char_name": "皮影御灵师",
            "img_type": "expressionSheet",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Shadow Puppeteer (皮影御灵师)\nGender / age impression: young woman, mysterious and theatrical, 19-year appearance\nBody shape: slender, delicate, classical posture\nHair: black hair in classical opera updo, red hairpins\nEyes: glowing scarlet red eyes\nOutfit: black and crimson traditional Chinese opera costume with flowing water sleeves\nAccessories / weapon: crimson paper-cuts, glowing red silk threads, semi-translucent shadow screen\nColor palette: cinnabar red, opera black, screen white, moonlight grey\nFixed traits that must never change: scarlet glowing eyes, opera updo, black-and-red opera costume, glowing red silk threads, giant shadow screen\n\nCurrent asset goal:\nGenerate an expression sheet. Show 8 bust portraits of the Shadow Puppeteer in a clean grid: mysterious smile, eyes closed chanting, wrathful operatic glare, sorrowful gaze, malicious grin, alert side-look, screaming in battle, and a serene calm look.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet.\n\nComposition:\n8 bust portraits in a clean grid on a plain dark gray background.\n\nConstraints:\nKeep the face structure, hair, eyes, and collar details consistent."
        },
        {
            "char_id": "char_0021_shadow_puppeteer",
            "char_name": "皮影御灵师",
            "img_type": "detailSheet",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Shadow Puppeteer (皮影御灵师)\nGender / age impression: young woman, mysterious and theatrical, 19-year appearance\nBody shape: slender, delicate, classical posture\nHair: black hair in classical opera updo, red hairpins\nEyes: glowing scarlet red eyes\nOutfit: black and crimson traditional Chinese opera costume with flowing water sleeves\nAccessories / weapon: crimson paper-cuts, glowing red silk threads, semi-translucent shadow screen\nColor palette: cinnabar red, opera black, screen white, moonlight grey\nFixed traits that must never change: scarlet glowing eyes, opera updo, black-and-red opera costume, glowing red silk threads, giant shadow screen\n\nCurrent asset goal:\nGenerate a detail sheet showing close-up panels: the red silk threads wrapping around her fingers, the hollow paper-cut patterns on the cinnabar paper, the detailed embroidery of waves and clouds on her opera collar, and the glowing red theatrical mask of the shadow warrior.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet.\n\nComposition:\nMultiple close-up panels arranged neatly on a light gray background."
        },
        {
            "char_id": "char_0021_shadow_puppeteer",
            "char_name": "皮影御灵师",
            "img_type": "materialPalette",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Shadow Puppeteer (皮影御灵师)\nGender / age impression: young woman, mysterious and theatrical, 19-year appearance\nBody shape: slender, delicate, classical posture\nHair: black hair in classical opera updo, red hairpins\nEyes: glowing scarlet red eyes\nOutfit: black and crimson traditional Chinese opera costume with flowing water sleeves\nAccessories / weapon: crimson paper-cuts, glowing red silk threads, semi-translucent shadow screen\nColor palette: cinnabar red, opera black, screen white, moonlight grey\nFixed traits that must never change: scarlet glowing eyes, opera updo, black-and-red opera costume, glowing red silk threads, giant shadow screen\n\nCurrent asset goal:\nGenerate a material and color palette sheet. Show swatches of black satin silk, crimson embroidery thread, translucent white paper, and red static energy glow, next to a neutral front view of the character.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet.\n\nComposition:\nThe character standing alongside neatly arranged color and material blocks.\n\nBackground:\nPlain light gray background."
        },
        {
            "char_id": "char_0021_shadow_puppeteer",
            "char_name": "皮影御灵师",
            "img_type": "outfitBreakdown",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Shadow Puppeteer (皮影御灵师)\nGender / age impression: young woman, mysterious and theatrical, 19-year appearance\nBody shape: slender, delicate, classical posture\nHair: black hair in classical opera updo, red hairpins\nEyes: glowing scarlet red eyes\nOutfit: black and crimson traditional Chinese opera costume with flowing water sleeves\nAccessories / weapon: crimson paper-cuts, glowing red silk threads, semi-translucent shadow screen\nColor palette: cinnabar red, opera black, screen white, moonlight grey\nFixed traits that must never change: scarlet glowing eyes, opera updo, black-and-red opera costume, glowing red silk threads, giant shadow screen\n\nCurrent asset goal:\nGenerate an outfit breakdown sheet. Show separate layers and components of his clothing: the inner black linen robe, the outer embroidered red opera tunic, the flowing water sleeves, her crimson hairpins, and her embroidered silk shoes.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet.\n\nComposition:\nSeparated clothing items laid out clearly on a plain background."
        },
        {
            "char_id": "char_0021_shadow_puppeteer",
            "char_name": "皮影御灵师",
            "img_type": "damageState",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Shadow Puppeteer (皮影御灵师)\nGender / age impression: young woman, mysterious and theatrical, 19-year appearance\nBody shape: slender, delicate, classical posture\nHair: black hair in classical opera updo, red hairpins\nEyes: glowing scarlet red eyes\nOutfit: black and crimson traditional Chinese opera costume with flowing water sleeves\nAccessories / weapon: crimson paper-cuts, glowing red silk threads, semi-translucent shadow screen\nColor palette: cinnabar red, opera black, screen white, moonlight grey\nFixed traits that must never change: scarlet glowing eyes, opera updo, black-and-red opera costume, glowing red silk threads, giant shadow screen\n\nCurrent asset goal:\nGenerate damage state variants showing progressive battle damage. Show 3 full-body versions of the same character side-by-side: first, default state standing elegantly; second, battle-worn state, standing with her black-and-red gown's sleeves tattered and frayed at the cuffs, showing minor soot smudges, her hairpins slightly loose; third, extreme battle-damaged state, standing defiantly next to a cracked and shattered paper screen, her gown's long flowing water sleeves and hem heavily ripped and shredded, the black and crimson fabric covered in prominent dark ash and scorch marks, and her glowing red silk threads broken and snapping into floating particles. The progressive clothing damage and scorch marks must be highly dramatic and extremely visible, making the three states look distinctly different at a glance.\n\nStyle:\nEastern fantasy concept art, high-fidelity design sheet.\n\nComposition:\nShow three side-by-side full-body views of the character standing. The progression of clothing wear, tattering, and scorch marks must be extremely clear and obvious from left to right.\n\nBackground:\nSolid clean dark gray background.\n\nConstraints:\nDo not change the costume into a new outfit. Keep the same identity. The damage must be represented by clothing rips, soot, and structural damage to props, avoiding any blood or gore. No text, no labels, no words, no subtitles, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."
        }
    ]

    # Apply dynamic expander to first 4 plans
    crimson_plan = expand_character_plan(crimson_plan, 'char_0001_crimson_guardian', '赤衣守城者')
    midnight_plan = expand_character_plan(midnight_plan, 'char_0002_midnight_warden', '午夜值守员')
    sandstorm_plan = expand_character_plan(sandstorm_plan, 'char_0003_sandstorm_pilgrim', '风沙朝圣者')
    neon_plan = expand_character_plan(neon_plan, 'char_0004_neon_hacker', '霓虹潜行者')
    
    # Apply dynamic expander to the new characters
    global red_umbrella_plan, stele_pathfinder_plan, fungal_apothecary_plan, book_wraith_plan, radio_host_plan, blade_wraith_plan, abyssal_dread_plan, thousand_faces_plan, bone_spider_plan, bone_pipa_wraith_plan, withered_daoist_plan
    red_umbrella_plan = expand_character_plan(red_umbrella_plan, 'char_0036_red_umbrella_entity', '红伞执念体')
    stele_pathfinder_plan = expand_character_plan(stele_pathfinder_plan, 'char_0037_stele_pathfinder', '残碑拓荒人')
    fungal_apothecary_plan = expand_character_plan(fungal_apothecary_plan, 'char_0040_fungal_apothecary', '蕈林秘医')
    book_wraith_plan = expand_character_plan(book_wraith_plan, 'char_0041_book_wraith', '禁忌书魂')
    radio_host_plan = expand_character_plan(radio_host_plan, 'char_0042_radio_host', '午夜电台主播')
    spectral_glitch_plan = []
    spectral_glitch_plan = expand_character_plan(spectral_glitch_plan, 'char_0043_spectral_glitch', '频段噬灵')
    blade_wraith_plan = expand_character_plan(blade_wraith_plan, 'char_0043_blade_wraith', '噬魂刀魅')
    abyssal_dread_plan = expand_character_plan(abyssal_dread_plan, 'char_0044_abyssal_dread', '深渊煞魔')
    thousand_faces_plan = expand_character_plan(thousand_faces_plan, 'char_0045_thousand_faces', '千面皮魔')
    bone_spider_plan = expand_character_plan(bone_spider_plan, 'char_0046_bone_spider', '蚀骨蛛后')
    bone_pipa_wraith_plan = expand_character_plan(bone_pipa_wraith_plan, 'char_0047_bone_pipa_wraith', '骨琶怨姬')
    withered_daoist_plan = expand_character_plan(withered_daoist_plan, 'char_0048_withered_daoist', '枯木妖道')

    frostleaf_illusionist_plan = [
        {
            "char_id": "char_0049_frostleaf_illusionist",
            "char_name": "霜叶幻术师",
            "img_type": "main",
            "prompt": "An epic high fantasy concept art of the Frostleaf Illusionist. A graceful and cold winter elf female with pale snow-like skin, long pointed elf ears, and flowing silver-blue hair, wearing an elegant flowy blue and white gradient robe with frost crystalizing on the hems. She is not holding a staff, but instead levitating a large glowing magical polyhedron ice crystal orb above her hands, refracting colorful holographic illusions. The setting is a breathtaking winter elven forest covered in thick white snow, surrounded by glowing blue bioluminescent flora and gentle falling snow. Cinematic rim lighting, hyper-realistic textures, ethereal magic atmosphere, 8k."
        }
    ]
    frostleaf_illusionist_plan = expand_character_plan(frostleaf_illusionist_plan, 'char_0049_frostleaf_illusionist', '霜叶幻术师')

    thorn_executioner_plan = [
        {
            "char_id": "char_0050_thorn_executioner",
            "char_name": "荆棘行刑者",
            "img_type": "main",
            "prompt": "An epic dark fantasy concept art of the Thorn Executioner. A tall, muscular and fierce dark wood elf male warrior with tanned bronze skin and long pointed elf ears. His lower face is hidden behind a half-face mask woven from sharp black thorny briars, revealing only his fierce amber eyes. He wears rugged heavy armor made of thick leather intertwined with dark green and blood-red magical vines, featuring sharp wooden pauldrons. He grips a massive, thick whip made of cursed thorny briars dripping with glowing green poison. The setting is a gloomy, dark deep elven forest filled with twisting massive tree roots and poisonous fog. Cinematic rim lighting, hyper-realistic textures, wild and dangerous atmosphere, 8k."
        }
    ]
    thorn_executioner_plan = expand_character_plan(thorn_executioner_plan, 'char_0050_thorn_executioner', '荆棘行刑者')

    moonphase_templar_plan = [
        {
            "char_id": "char_0051_moonphase_templar",
            "char_name": "月影重装骑士",
            "img_type": "main",
            "prompt": "A breathtaking high fantasy concept art of the Moonphase Templar. A tall and majestic East Asian female moon elf knight with delicate refined East Asian facial features, soft almond-shaped eyes, smooth pale porcelain skin, and long flowing silver hair. She is clad in ornate, glowing silver-and-white plate armor crafted from moonstone, reflecting soft blue moonlight. She holds a massive, semi-translucent shield shaped like a crescent moon, which radiates a holy, protective silver aurora. The setting is a mystical elven forest at night, with bright moonlight filtering through giant ancient leaf canopies. 3D octane render, hyper-realistic textures, 8k, no Caucasian features."
        }
    ]
    moonphase_templar_plan = expand_character_plan(moonphase_templar_plan, 'char_0051_moonphase_templar', '月影重装骑士')

    thunder_talismanist_plan = [
        {
            "char_id": "char_0052_thunder_talismanist",
            "char_name": "雷劫画符师",
            "img_type": "main",
            "prompt": "An epic high fantasy concept art of the Thunder Talismanist. A young, energetic Chinese female Taoist talisman cultivator carrying a large, dark, weathered lightning-struck wooden canvas on her back. She wears a modified yellow and black Taoist robe designed for street mobility. She holds a calligraphy brush in her hand, writing glowing yellow paper talismans in mid-air. Ethereal purple electricity and lightning bolts arc around her and on the ground. The background is a ruined ancient courtyard under dark thunderclouds and heavy rain. Masterpiece, octane render, highly detailed, 8k."
        }
    ]
    thunder_talismanist_plan = expand_character_plan(thunder_talismanist_plan, 'char_0052_thunder_talismanist', '雷劫画符师')

    venom_assassin_plan = [
        {
            "char_id": "char_0053_venom_assassin",
            "char_name": "毒藤魅影",
            "img_type": "main",
            "prompt": "A breathtaking dark fantasy concept art of the Poison-Ivy Assassin. An alluring and deadly female wood elf assassin with tanned bronze skin and long, flowing messy black hair. She wears a skin-tight, seductive outfit woven from dark red leather and thorned dark-green vines. She is controlling slithering, fluorescent green venomous vines in her fingers, standing in a dark poisonous swamp with glowing green spores floating. Masterpiece, unreal engine 5 render, highly detailed, 8k."
        }
    ]
    venom_assassin_plan = expand_character_plan(venom_assassin_plan, 'char_0053_venom_assassin', '毒藤魅影')

    petal_dancer_plan = [
        {
            "char_id": "char_0054_petal_dancer",
            "char_name": "繁花舞姬",
            "img_type": "main",
            "prompt": "A breathtaking high fantasy concept art of the Blossom Dancer. An ethereal and gorgeous female flower elf dancer with fair radiant skin and long flowing pastel-pink hair adorned with flower blossoms. She wears a translucent gossamer dress made of pink rose petals and soft green silk ribbons, showing her graceful body. She is dancing gracefully amidst a whirlwind of sharp, glowing pink flower petals floating in the air. The setting is a magical sunlit elven forest clearing filled with blossoming flowers. Masterpiece, unreal engine 5 render, highly detailed, 8k."
        }
    ]
    petal_dancer_plan = expand_character_plan(petal_dancer_plan, 'char_0054_petal_dancer', '繁花舞姬')

    vermilion_sovereign_plan = [
        {
            "char_id": "char_0055_vermilion_sovereign",
            "char_name": "朱雀天尊·凤仪",
            "img_type": "main",
            "prompt": "A breathtaking high fantasy concept art of the Vermilion Sovereign. A majestic and drop-dead gorgeous East Asian empress goddess with noble refined features, sharp almond eyes, radiant skin, and flowing long black hair accented with glowing golden feather strands. She is clad in an ultra-luxurious flowing crimson-and-gold phoenix-feather gossamer silk robe with delicate gold chest armor and phoenix ornaments. She commands swirling sacred solar flames and a massive glowing golden-red phoenix aura soaring behind her. Floating celestial palace in the sunset sky. 3D octane render, photorealistic, 8k, no Caucasian features."
        }
    ]
    vermilion_sovereign_plan = expand_character_plan(vermilion_sovereign_plan, 'char_0055_vermilion_sovereign', '朱雀天尊·凤仪')

    puppet_artificer_plan = [
        {
            "char_id": "char_0056_puppet_artificer",
            "char_name": "千机偃灵·墨巧",
            "img_type": "main",
            "prompt": "A breathtaking stylized concept art of the Puppet Artificer. A clever and cute young East Asian female mechanical puppet master with delicate porcelain skin and dark brown twin-tails adorned with small bronze gears and red ribbons. She wears an asymmetrical stylish black-and-crimson mechanic short cheongsam with leather utility belts and an ornate bronze mechanical puppet glove on one arm. Glowing blue spirit strings extend from her fingertips, controlling floating intricate wooden clockwork puppets and spinning bronze gear blades around her. Cozy traditional workshop background filled with scrolls and gears. 3D octane render, 8k, no Caucasian features."
        }
    ]
    puppet_artificer_plan = expand_character_plan(puppet_artificer_plan, 'char_0056_puppet_artificer', '千机偃灵·墨巧')

    azure_sword_spirit_plan = [
        {
            "char_id": "char_0057_azure_sword_spirit",
            "char_name": "青霄剑灵·流光",
            "img_type": "main",
            "prompt": "A breathtaking high fantasy concept art of the Azure Sword Spirit. An ethereal and cold immortal East Asian female sword spirit with fair porcelain skin, sharp cyan-blue eyes with sword glint, and long flowing high ponytail hair fading from ink-black to translucent azure-blue with an antique carved jade hairpin. She wears a sleek azure-and-white swordmaster silk tunic with sharp blade-like hem and engraved silver vambraces. She holds a legendary ancient glowing cyan-blue crystalline broadsword, surrounded by 8 floating semi-transparent azure flying daggers arranged in a halo behind her. Floating sword grave mountain pavilion amidst swirling clouds. 3D octane render, 8k, no Caucasian features."
        }
    ]
    azure_sword_spirit_plan = expand_character_plan(azure_sword_spirit_plan, 'char_0057_azure_sword_spirit', '青霄剑灵·流光')

    nether_dragon_shaman_plan = [
        {
            "char_id": "char_0058_nether_dragon_shaman",
            "char_name": "九幽龙巫·刹夜",
            "img_type": "main",
            "prompt": "A breathtaking high fantasy concept art of the Nether Dragon Shaman. A handsome and mysterious young East Asian dragon shaman with obsidian black dragon horns on his forehead, pale skin, heterochromia eyes (left cyan-blue, right dark gold), and a subtle cinnabar dragon tattoo at his eye corner. He is clad in intricate dark embroidered Miao-style shaman robes layered with dark feathers, grand antique silver dragon neck torcs, and bone charms. He wields a carved ancient dragon-bone shaman staff topped with a glowing soul orb, with a translucent ethereal black dragon spirit coiling around him amidst glowing spectral butterflies. Misty ancient tribal dragon shrine at twilight. 3D octane render, 8k, no Caucasian features."
        }
    ]
    nether_dragon_shaman_plan = expand_character_plan(nether_dragon_shaman_plan, 'char_0058_nether_dragon_shaman', '九幽龙巫·刹夜')

    sword_spirit_prime_plan = [
        {
            "char_id": "char_0059_sword_spirit_prime",
            "char_name": "碧水仙剑·灵漪",
            "img_type": "main",
            "prompt": "A breathtaking masterpiece 3D concept art of the Jade Water Celestial Sword Spirit (碧水仙剑·灵漪). An ethereal, transcendent humanoid female spirit avatar of the supreme water celestial sword. She has flawless translucent pale jade-crystalline skin, a glowing emerald-aqua water-sword droplet rune on her forehead, and tranquil luminous aqua-teal eyes filled with pure liquid sword intent. Her liquid crystalline hair shifts from emerald jade-green to translucent aqua-cyan, floating weightlessly like clear waterfall trails. She wears flowing semi-transparent aquatic silk robes with water-ripple hemlines and floating ribbons of glowing aquatic sword qi, levitating weightlessly barefoot on glowing water lotus ripples. Behind her looms a colossal ancient primordial Jade-Water Celestial God-Sword pulsing with emerald-aqua runes, while 8 translucent liquid jade flying blades form a revolving halo around her. Ethereal immortal misty mountain lake domain with glowing water ripples and cosmic starlight. 3D octane render, hyper-detailed, 8k, cinematic lighting, no Caucasian features."
        }
    ]
    sword_spirit_prime_plan = expand_character_plan(sword_spirit_prime_plan, 'char_0059_sword_spirit_prime', '碧水仙剑·灵漪')

    solar_warlord_plan = [
        {
            "char_id": "char_0060_solar_warlord",
            "char_name": "大日战神·烈阳",
            "img_type": "main",
            "prompt": "A breathtaking masterpiece 3D concept art of the Solar Warlord (大日战神·烈阳). A majestic, powerful young East Asian celestial warrior general with resolute handsome features, glowing pure-gold sun flame sigil on his forehead, and blazing golden-amber eyes glowing with divine solar fire. His long jet-black hair is tied in an ornate golden crown with fiery red accents and floating golden flame strands. He wears magnificent radiant golden-and-crimson dragon celestial plate armor with a fiery silk battle mantle and floating solar light ribbons. He holds a massive ancient solar celestial halberd forged from celestial gold dripping with swirling sacred golden flames, and a revolving divine solar halo of 9 radiant miniature suns floats behind his back. Golden celestial divine palace amidst blazing solar clouds and cosmic radiance. 3D octane render, hyper-detailed, 8k, cinematic lighting, no Caucasian features."
        }
    ]
    solar_warlord_plan = expand_character_plan(solar_warlord_plan, 'char_0060_solar_warlord', '大日战神·烈阳')

    nether_moon_arbiter_plan = [
        {
            "char_id": "char_0061_nether_moon_arbiter",
            "char_name": "幽月神女·望舒",
            "img_type": "main",
            "prompt": "A breathtaking masterpiece 3D concept art of the Nether Moon Arbiter (幽月神女·望舒). An ethereal, mysterious and breathtaking young East Asian nether goddess with pale porcelain skin, glowing silver crescent moon rune on her forehead, and tranquil mesmerizing silver-cyan luminous eyes. Her floor-length flowing silvery-white moonlight hair is adorned with carved white jade spider lily hairpins and delicate silver bells. She wears layered flowing translucent gossamer robes of midnight black and frost-silver moonlight with floating ribbons of spectral water mist, holding a delicate antique 9-petaled pure white jade lotus soul lantern emitting cold celestial cyan ghost flames, surrounded by drifting crimson red spider lily petals and ethereal moonbeams. Desolate ancient moonlit nether lotus pond with glowing ethereal waters and celestial aurora. 3D octane render, hyper-detailed, 8k, cinematic lighting, no Caucasian features."
        }
    ]
    nether_moon_arbiter_plan = expand_character_plan(nether_moon_arbiter_plan, 'char_0061_nether_moon_arbiter', '幽月神女·望舒')

    full_plan = (
        crimson_plan + midnight_plan + sandstorm_plan + neon_plan + astrolabe_plan +
        rust_mechanic_plan + rust_sniper_plan + rust_apprentice_plan + rust_nomad_plan +
        rust_warlord_plan + rust_scavenger_queen_plan + boundary_investigator_plan +
        lantern_keeper_plan + mirror_walker_plan + ink_painter_plan +
        abyssal_zitherist_plan + talisman_weaver_plan + underworld_magistrate_plan +
        frost_sword_immortal_plan + zen_monk_plan + shadow_puppeteer_plan +
        siren_plan + tide_warlord_plan + abyssal_stalker_plan +
        bioluminescent_spirit_plan + rule_weaver_plan + sand_sailor_plan +
        dome_botanist_plan + astral_mage_plan + moonshadow_ranger_plan +
        ancient_druid_plan + cyber_samurai_plan + cyber_corporate_plan + dragon_berserker_plan + brass_alchemist_plan + azure_dragon_maiden_plan + crane_celestial_plan + stag_priestess_plan + nine_tailed_fox_plan + red_umbrella_plan + stele_pathfinder_plan +
        fungal_apothecary_plan + book_wraith_plan + radio_host_plan + spectral_glitch_plan + blade_wraith_plan + abyssal_dread_plan + thousand_faces_plan + bone_spider_plan + bone_pipa_wraith_plan + withered_daoist_plan
     + frostleaf_illusionist_plan + thorn_executioner_plan + moonphase_templar_plan + thunder_talismanist_plan + venom_assassin_plan + petal_dancer_plan
     + vermilion_sovereign_plan + puppet_artificer_plan + azure_sword_spirit_plan + nether_dragon_shaman_plan + sword_spirit_prime_plan
     + solar_warlord_plan + nether_moon_arbiter_plan)
    
    # 动态为每一项注入其在对应角色子计划中的绝对位置 absolute_idx
    char_counters = {}
    for t_item in full_plan:
        c_id = t_item["char_id"]
        char_counters.setdefault(c_id, 0)
        t_item["absolute_idx"] = char_counters[c_id]
        char_counters[c_id] += 1
        
    # 动态过滤条件
    if char_id:
        full_plan = [task for task in full_plan if task["char_id"] == char_id]
        logging.info(f"已应用角色过滤条件: {char_id} (当前剩余 {len(full_plan)} 个生成项)")
    if img_type:
        full_plan = [task for task in full_plan if task["img_type"] == img_type]
        logging.info(f"已应用部位类型过滤条件: {img_type} (当前剩余 {len(full_plan)} 个生成项)")
        
    if not full_plan:
        logging.warning("⚠️ 过滤后的生成任务列表为空！请检查 --char-id 或 --type 是否正确。")
        return
        
    if dry_run:
        logging.info("当前处于「干跑模式」，仅打印待生成的过滤部位清单：")
        for idx, item in enumerate(full_plan):
            logging.info(f"  {idx+1}. 角色「{item['char_name']}」 -> 部位: {TYPE_LABEL.get(item['img_type'], item['img_type'])}")
            logging.info(f"     Prompt: {item['prompt'][:80]}...")
        logging.info("干跑结束。")
        return
        
    agent = BrowserAgent(WS_URL)
    if not await agent.connect():
        return
        
    try:
        await agent.init("多维度部位自动化同步流水线")
        
        # 依次执行各部位的生成
        for step_idx, task in enumerate(full_plan):
            logging.info("=" * 60)
            logging.info(f"正在执行任务流水线 [{step_idx + 1}/{len(full_plan)}]")
            
            success = False
            for attempt in range(1, 3):
                try:
                    res = await generate_character_part(
                        agent,
                        task["char_id"],
                        task["char_name"],
                        task["img_type"],
                        task["prompt"],
                        task["absolute_idx"]
                    )
                    if res == "quota_limit":
                        logging.critical("🚨 [额度已达上限] 触发 OpenAI 生图频率或额度限制，系统将直接强行终止并退出整个绘图流水线！")
                        return
                    if res == "policy_violation":
                        logging.critical("🚨 [内容安全策略拦截] 触发内容政策拦截，将直接跳过此项并不再重试。")
                        break
                    if res:
                        success = True
                        break
                    else:
                        logging.warning(f"第 {attempt} 次生成未成功，等待 5 秒后重试...")
                        await asyncio.sleep(5)
                except Exception as ex:
                    logging.error(f"执行发生异常: {ex}", exc_info=True)
                    await asyncio.sleep(5)
            
            # 只有真正执行了生成的项才留出 3 秒缓冲给用户/AI观察
            if res != "skipped":
                await asyncio.sleep(3)
            
        logging.info("=" * 60)
        logging.info("🎉 恭喜！所选角色、部位维度的资产绘图任务已全部完成！")
        
    finally:
        await agent.close()

def main():
    global OUTPUT_ROOT
    parser = argparse.ArgumentParser(description="多部位一致性资产自动生成与回写引擎")
    parser.add_argument("--dry-run", action="store_true", help="干跑模式，仅打印计划")
    parser.add_argument("--char-id", type=str, default=None, help="过滤指定角色 ID (如 char_0001_crimson_guardian)")
    parser.add_argument("--type", type=str, default=None, help="过滤指定图片部位类型 (如 main, portrait, expression)")
    parser.add_argument("--output-root", type=str, default=None, help="覆盖图片输出归档根目录")
    args = parser.parse_args()
    
    if args.output_root:
        OUTPUT_ROOT = args.output_root.replace("\\", "/")
        logging.info(f"✨ 命令行参数指定覆盖输出目录为: {OUTPUT_ROOT}")
    
    try:
        asyncio.run(run_all_pipeline(args.dry_run, args.char_id, args.type))
    except KeyboardInterrupt:
        logging.info("\n用户手动终止。")
    except Exception as e:
        logging.critical(f"严重未捕获错误: {e}", exc_info=True)


# ======================================================
# 🦄 自动生成的角色生图方案 (Module Level)
# ======================================================
siren_plan = [
    {
        "char_id": "char_0016_deep_sea_siren",
        "char_name": "深海歌姬",
        "img_type": "main",
        "prompt": "A masterpiece marine fantasy concept art of the Abyssal Siren. An ethereal, beautiful young mermaid priestess with highly detailed expressive facial features and flowing, wavy bioluminescent aqua-blue hair floating in water. Her eyes are a pure, tear-blue. She wears a semi-translucent marine gown woven from sea-silk, pearls, and coral branches. Her lower body is a sleek, elegant fish tail with scales that shimmer with a gradient of cyan and deep blue bioluminescent light. She is underwater, holding a water-resonance harp that glows with soft teal energy. The background features a deep-sea coral forest with glowing jellyfish and schools of silver fish, lit by shafts of moonlight filtering down through the deep water, casting a magical rim light. Cinematic, hyper-realistic, 8k resolution."
    },
    {
        "char_id": "char_0016_deep_sea_siren",
        "char_name": "深海歌姬",
        "img_type": "portrait",
        "prompt": "Now, draw a close-up portrait of the exact same Abyssal Siren character from our conversation. Focus on her face and shoulders, capturing her flowing wavy aqua-blue bioluminescent hair, her pure tear-blue eyes with a gentle sad expression, and her white pearl shell earrings. She is floating underwater, with tiny bubbles rising around her. Solid, extremely dark, low-contrast studio background. Masterpiece, 8k."
    },
    {
        "char_id": "char_0016_deep_sea_siren",
        "char_name": "深海歌姬",
        "img_type": "expression",
        "prompt": "Now, draw an expression sheet of the exact same Abyssal Siren character from our conversation. Show her on a solid, clean dark gray background with three different facial expressions side-by-side: one serene and calm, one singing with her mouth gently open and sound waves floating around, and one showing a faint, gentle and warm smile. High-fidelity details, masterpiece, 8k."
    },
    {
        "char_id": "char_0016_deep_sea_siren",
        "char_name": "深海歌姬",
        "img_type": "turnaround",
        "prompt": "Now, draw a professional character turnaround model sheet of the exact same Abyssal Siren character. Show three views: front, side, and back, floating in a neutral pose. She is wearing her semi-translucent white-and-aqua gown and showing her elegant fish tail with scales shimmering. Solid, clean dark gray background. High-fidelity details, masterpiece, 8k."
    },
    {
        "char_id": "char_0016_deep_sea_siren",
        "char_name": "深海歌姬",
        "img_type": "outfit",
        "prompt": "Use case: stylized-concept\\nAsset type: character asset for a reusable character pool\\n\\nPrimary request:\\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\\n\\nCharacter lock:\\nName: The Abyssal Siren (深海歌姬)\\nGender / age impression: young woman, ethereal, beautiful mermaid priestess\\nBody shape: slender and elegant mermaid build\\nFace: highly detailed features, pure tear-blue eyes showing gentle sadness\\nHair: wavy bioluminescent aqua-blue hair floating in water, glowing at the tips\\nOutfit: semi-translucent white-and-aqua gown woven from sea-silk, pearls, and coral branches\\nAccessories / weapon: water-resonance harp made of shipwreck wood and glowing water-flow strings, pearl shell earrings\\nColor palette: deep-sea blue, aqua-green, pearl white, bioluminescent cyan, coral pink\\nFixed traits that must never change: wavy aqua-blue bioluminescent hair, tear-blue eyes, pearl shell earrings, water-resonance harp\\n\\nCurrent asset goal:\\nGenerate an outfit variant image. Show three different outfits side-by-side: on the left, her default white-and-aqua gown; in the middle, her coral ritual gown (a majestic dress made of pink coral branches, pearl strings, and golden sea anemone silks); on the right, her battle tide armor (sleek pearl-white shell armor plates covering her torso and shoulders, with bioluminescent blue energy seams, and a silver trident at her side). Keep her pearl shell earrings in all three outfits.\\n\\nStyle:\\nFantasy character concept art, high-fidelity design sheet, detailed fabric and shell material rendering, coherent design language, consistent facial identity, production-ready asset.\\n\\nComposition:\\nShow three side-by-side full-body views of the same character standing/floating neutrally.\\n\\nBackground:\\nPlain clean dark gray background."
    },
    {
        "char_id": "char_0016_deep_sea_siren",
        "char_name": "深海歌姬",
        "img_type": "prop",
        "prompt": "Now, draw a high-fidelity detailed design sheet of the Abyssal Siren's signature gear: her water-resonance harp made of deep-sea shipwreck wood and glowing water-flow strings, and her white pearl shell earrings. Show them from multiple angles. Solid, clean dark gray background. Masterpiece, 8k."
    },
    {
        "char_id": "char_0016_deep_sea_siren",
        "char_name": "深海歌姬",
        "img_type": "scene",
        "prompt": "Now, draw a stunning, highly detailed landscape scene concept art. A majestic, ancient tide temple ruins under deep water, surrounded by giant glowing deep-sea coral forests, luminous jellyfish floating, and moonlight beams filtering through the water surface. Cinematic, hyper-realistic, masterpiece, 8k."
    },
    {
        "char_id": "char_0016_deep_sea_siren",
        "char_name": "深海歌姬",
        "img_type": "fullBody",
        "prompt": "Now, draw a full-body cinematic splash art of the exact same Abyssal Siren character. She floats gracefully in her white-and-aqua gown, holding her water-resonance harp, with schools of small silver fish swimming around her tail. Solid, extremely dark, low-contrast studio background. Masterpiece, highly detailed, 8k."
    },
    {
        "char_id": "char_0016_deep_sea_siren",
        "char_name": "深海歌姬",
        "img_type": "cover",
        "prompt": "Use case: stylized-concept\\nAsset type: character asset for a reusable character pool\\n\\nPrimary request:\\nCreate a high-quality character asset image for the following character.\\n\\nCharacter lock:\\nName: The Abyssal Siren (深海歌姬)\\nGender / age impression: young woman, ethereal, beautiful mermaid priestess\\nHair: wavy bioluminescent aqua-blue hair floating in water\\nEyes: pure tear-blue\\nOutfit: semi-translucent white-and-aqua gown\\nAccessories: water-resonance harp, pearl shell earrings\\n\\nCurrent asset goal:\\nGenerate a cover image. The Siren floats holding her glowing harp inside a majestic underwater tide temple ruins. Bioluminescent coral and drifting jellyfish create an ethereal, dreamlike atmosphere. High polish, vertical framing.\\n\\nStyle:\\nFantasy character concept art, cinematic poster, dramatic lighting, unreal engine 5 render style."
    },
    {
        "char_id": "char_0016_deep_sea_siren",
        "char_name": "深海歌姬",
        "img_type": "moodboard",
        "prompt": "Use case: stylized-concept\\nAsset type: character asset for a reusable character pool\\n\\nCharacter lock:\\nName: The Abyssal Siren (深海歌姬)\\nHair: wavy bioluminescent aqua-blue hair\\n\\nCurrent asset goal:\\nGenerate a moodboard collage. Four panels: one showing glowing blue water-flow harp strings, one showing shimmering fish scales with cyan-blue gradient, one showing white pearl shell earrings on velvet, and one showing deep-sea coral forest under soft blue light. Ethereal mystery tone."
    },
    {
        "char_id": "char_0016_deep_sea_siren",
        "char_name": "深海歌姬",
        "img_type": "sketch",
        "prompt": "Use case: stylized-concept\\nAsset type: character asset for a reusable character pool\\n\\nCharacter lock:\\nName: The Abyssal Siren (深海歌姬)\\n\\nCurrent asset goal:\\nGenerate a concept sketch sheet. Traditional concept pencil sketches showing the Siren in 3 study poses: floating calmly, playing her water harp, and looking up towards the light. Clean hand-drawn lines."
    },
    {
        "char_id": "char_0016_deep_sea_siren",
        "char_name": "深海歌姬",
        "img_type": "modelSheet",
        "prompt": "Use case: stylized-concept\\nAsset type: character asset for a reusable character pool\\n\\nCharacter lock:\\nName: The Abyssal Siren (深海歌姬)\\n\\nCurrent asset goal:\\nGenerate a standard model sheet. Full-body front, side, and back views of the Siren floating neutrally in her white-and-aqua gown."
    },
    {
        "char_id": "char_0016_deep_sea_siren",
        "char_name": "深海歌姬",
        "img_type": "poseSheet",
        "prompt": "Use case: stylized-concept\\nAsset type: character asset for a reusable character pool\\n\\nCharacter lock:\\nName: The Abyssal Siren (深海歌姬)\\n\\nCurrent asset goal:\\nGenerate a pose sheet. Show 5 poses of the Siren on one clean sheet: playing her water harp, casting a tide-shield, swimming downwards, singing, and resting on a giant sea shell."
    },
    {
        "char_id": "char_0016_deep_sea_siren",
        "char_name": "深海歌姬",
        "img_type": "expressionSheet",
        "prompt": "Use case: stylized-concept\\nAsset type: character asset for a reusable character pool\\n\\nCharacter lock:\\nName: The Abyssal Siren (深海歌姬)\\n\\nCurrent asset goal:\\nGenerate an expression sheet. Show 8 bust portraits of the Siren in a clean grid: serene, singing with closed eyes, gentle smile, warning look, crying, focused, surprised, and tired/sad."
    },
    {
        "char_id": "char_0016_deep_sea_siren",
        "char_name": "深海歌姬",
        "img_type": "detailSheet",
        "prompt": "Use case: stylized-concept\\nAsset type: character asset for a reusable character pool\\n\\nCharacter lock:\\nName: The Abyssal Siren (深海歌姬)\\n\\nCurrent asset goal:\\nGenerate a detail sheet. Close-up panels showing her aqua-blue bioluminescent hair strand glow, the shell and pearl details of her gown collar, the shipwreck wood grain of her harp, and the pearl shell pattern of her earrings."
    },
    {
        "char_id": "char_0016_deep_sea_siren",
        "char_name": "深海歌姬",
        "img_type": "materialPalette",
        "prompt": "Use case: stylized-concept\\nAsset type: character asset for a reusable character pool\\n\\nCharacter lock:\\nName: The Abyssal Siren (深海歌姬)\\n\\nCurrent asset goal:\\nGenerate a material and color palette sheet. Show swatches of white sea-silk, aqua-blue bioluminescent hair, pink coral branch, and glowing blue water-flow beside a neutral front view of the character."
    },
    {
        "char_id": "char_0016_deep_sea_siren",
        "char_name": "深海歌姬",
        "img_type": "outfitBreakdown",
        "prompt": "Use case: stylized-concept\\nAsset type: character asset for a reusable character pool\\n\\nCharacter lock:\\nName: The Abyssal Siren (深海歌姬)\\n\\nCurrent asset goal:\\nGenerate an outfit breakdown sheet. Show separate layers of her clothing: the outer white-and-aqua gown, the shell bodice, the coral branch sash, and the pearl string straps."
    },
    {
        "char_id": "char_0016_deep_sea_siren",
        "char_name": "深海歌姬",
        "img_type": "damageState",
        "prompt": "Use case: stylized-concept\\nAsset type: character asset for a reusable character pool\\n\\nCharacter lock:\\nName: The Abyssal Siren (深海歌姬)\\n\\nCurrent asset goal:\\nGenerate damage state variants. Show 3 full-body versions of the Siren: clean/default; battle-worn with seaweed tangles and minor tail scratches; and heavily damaged with her gown torn, her bioluminescent hair dim, tail scales cracked and bleeding, and her water harp strings broken."
    }
]

tide_warlord_plan = [
    {
        "char_id": "char_0017_tide_warlord",
        "char_name": "渊海狂澜",
        "img_type": "main",
        "prompt": "A masterpiece marine fantasy concept art of the Abyssal Warlord. An ethereal, powerful mature mermaid warlord with highly detailed chiseled facial features, glowing golden-amber eyes, and messy sea-foam white-and-gray hair floating in water. He wears heavy dark marine armor plates forged from shipwreck iron and Leviathan bones. His lower body is a thick, sleek dark blue scaled tail. He is underwater, holding his massive Tide-shaking Trident, a classic three-pronged spear made of bone with exactly three prongs (one central vertical spike and two symmetrical side prongs curving slightly outward). The trident radiates vibrant cyan water currents. Background features deep ocean trench ruins with black smokers and hydrothermal vents glowing red, cinematic, hyper-realistic, 8k."
    },
    {
        "char_id": "char_0017_tide_warlord",
        "char_name": "渊海狂澜",
        "img_type": "portrait",
        "prompt": "Now, draw a close-up portrait of the exact same Abyssal Warlord character from our conversation. Focus on his face and shoulders, capturing his chiseled chinned face with battle scars, his glowing golden-amber eyes, and his messy sea-foam hair floating in water. Simple dark gray background. Masterpiece, 8k."
    },
    {
        "char_id": "char_0017_tide_warlord",
        "char_name": "渊海狂澜",
        "img_type": "expression",
        "prompt": "Now, draw an expression sheet of the exact same Abyssal Warlord character from our conversation. Show three facial expressions side-by-side: one stern and silent, one letting out a fierce battle shout with his mouth wide open, and one showing a grim, knowing half-smirk. Plain clean dark gray background. High-fidelity details, masterpiece, 8k."
    },
    {
        "char_id": "char_0017_tide_warlord",
        "char_name": "渊海狂澜",
        "img_type": "turnaround",
        "prompt": "Now, draw a professional character turnaround model sheet of the exact same Abyssal Warlord character. Show three views: front, side, and back, floating in a neutral pose. Clear silhouette from head to tail tip. Plain clean dark gray background. High-fidelity details, masterpiece, 8k."
    },
    {
        "char_id": "char_0017_tide_warlord",
        "char_name": "渊海狂澜",
        "img_type": "outfit",
        "prompt": "Use case: stylized-concept\\nAsset type: character asset for a reusable character pool\\n\\nCharacter lock:\\nName: The Abyssal Warlord (渊海狂澜)\\nGender / age impression: mature man, fierce and commanding, weather-beaten fantasy mermaid presence\\nHair: messy, wavy white-and-gray hair\\nOutfit: heavy bone and shipwreck iron armor\\n\\nCurrent asset goal:\\nGenerate an outfit variant image. Show three different outfits side-by-side: on the left, his default heavy bone armor; in the middle, his ceremonial coral scale armor (shining gold-and-red coral scales with a royal crown-like helm); on the right, his deep-sea wanderer cloak (a flowing dark-green cloak woven from sea kelp and glowing deep-sea anemones). Keep all core features consistent. Any tridents shown must strictly have exactly three prongs (one central vertical spike and two symmetrical side prongs).\\n\\nStyle:\\nFantasy character concept art, high-fidelity design sheet."
    },
    {
        "char_id": "char_0017_tide_warlord",
        "char_name": "渊海狂澜",
        "img_type": "prop",
        "prompt": "Now, draw a prop and weapon reference sheet of the Abyssal Warlord's gear: his massive Tide-shaking Trident forged from elder beast bone, flowing with bright bioluminescent cyan water energy (the trident must strictly have exactly three prongs: one long central spike and two symmetrical side prongs curving slightly outward. Avoid four or five prongs). Show the trident and a detailed close-up of his Leviathan bone chestplate from multiple angles. Clean dark gray background. Masterpiece, 8k."
    },
    {
        "char_id": "char_0017_tide_warlord",
        "char_name": "渊海狂澜",
        "img_type": "scene",
        "prompt": "Now, draw a stunning, highly detailed landscape scene concept art. A deep ocean trench landscape showing towering black hydrothermal vents (black smokers), hydrothermal mineral chimneys glowing with faint red heat, surrounded by deep-sea bioluminescent sea creatures. No character figures. Cinematic, hyper-realistic, masterpiece, 8k."
    },
    {
        "char_id": "char_0017_tide_warlord",
        "char_name": "渊海狂澜",
        "img_type": "fullBody",
        "prompt": "Now, draw a full-body splash art of the Warlord visible from head to his tail tip, floating in an authoritative guardian stance, holding his massive Tide-shaking Trident with both hands. The trident must strictly have exactly three prongs (one central vertical spike and two symmetrical side prongs). Plain clean dark gray background. Masterpiece, highly detailed, 8k."
    },
    {
        "char_id": "char_0017_tide_warlord",
        "char_name": "渊海狂澜",
        "img_type": "cover",
        "prompt": "Use case: stylized-concept\\nAsset type: character asset for a reusable character pool\\n\\nCharacter lock:\\nName: The Abyssal Warlord (渊海狂澜)\\nWeapon: Tide-shaking Trident\\n\\nCurrent asset goal:\\nGenerate a cover image. The Warlord floats in front of a giant kraken silhouette in the dark deep ocean, his trident glowing brightly (the trident must strictly have exactly three prongs: one central vertical spike and two symmetrical side prongs), creating high contrast. Strong vertical framing.\\n\\nStyle:\\nEpic vertical cover poster, dramatic cinematic lighting, unreal engine 5 render style."
    },
    {
        "char_id": "char_0017_tide_warlord",
        "char_name": "渊海狂澜",
        "img_type": "moodboard",
        "prompt": "Use case: stylized-concept\\nAsset type: character asset for a reusable character pool\\n\\nCharacter lock:\\nName: The Abyssal Warlord (渊海狂澜)\\n\\nCurrent asset goal:\\nGenerate a moodboard collage. Four panels: one showing bioluminescent cyan water bubbles, one showing chiseled dark ship iron textures with barnacles, one showing white fossil bone teeth, and one showing deep ocean vents under soft blue light. Ethereal abyssal mystery tone."
    },
    {
        "char_id": "char_0017_tide_warlord",
        "char_name": "渊海狂澜",
        "img_type": "sketch",
        "prompt": "Use case: stylized-concept\\nAsset type: character asset for a reusable character pool\\n\\nCharacter lock:\\nName: The Abyssal Warlord (渊海狂澜)\\n\\nCurrent asset goal:\\nGenerate a concept sketch sheet. Monochrome pencil drawings, clean traditional sketch style showing the Warlord in 3 study sketches: thrusting his trident (the trident must strictly have exactly three prongs: one central vertical spike and two symmetrical side prongs), roaring, and crossing his arms in defense."
    },
    {
        "char_id": "char_0017_tide_warlord",
        "char_name": "渊海狂澜",
        "img_type": "modelSheet",
        "prompt": "Use case: stylized-concept\\nAsset type: character asset for a reusable character pool\\n\\nCharacter lock:\\nName: The Abyssal Warlord (渊海狂澜)\\n\\nCurrent asset goal:\\nGenerate a standard model sheet. Full-body front, side, and back views of the Warlord floating neutrally in his bone armor. Plain clean light gray studio background."
    },
    {
        "char_id": "char_0017_tide_warlord",
        "char_name": "渊海狂澜",
        "img_type": "poseSheet",
        "prompt": "Use case: stylized-concept\\nAsset type: character asset for a reusable character pool\\n\\nCharacter lock:\\nName: The Abyssal Warlord (渊海狂澜)\\n\\nCurrent asset goal:\\nGenerate a pose sheet. Show 5 poses on one clean sheet: guard stance, trident thrusting, swimming downward fast, calling tidal wave, and resting on an iron anchor. In all poses, his trident must strictly have exactly three prongs (one central spike, two side spikes). Solid clean dark gray background."
    },
    {
        "char_id": "char_0017_tide_warlord",
        "char_name": "渊海狂澜",
        "img_type": "expressionSheet",
        "prompt": "Use case: stylized-concept\\nAsset type: character asset for a reusable character pool\\n\\nCharacter lock:\\nName: The Abyssal Warlord (渊海狂澜)\\n\\nCurrent asset goal:\\nGenerate an expression sheet. Show 8 bust portraits in a grid: calm, silent rage, battle roar, grim smirk, exhausted, warning glare, eye closed in pain, focused determination. Clean dark gray background."
    },
    {
        "char_id": "char_0017_tide_warlord",
        "char_name": "渊海狂澜",
        "img_type": "detailSheet",
        "prompt": "Use case: stylized-concept\\nAsset type: character asset for a reusable character pool\\n\\nCharacter lock:\\nName: The Abyssal Warlord (渊海狂澜)\\n\\nCurrent asset goal:\\nGenerate a detail sheet. Close-up panels showing his shoulder scar markings, the bone trident grip wrapping, the leviathan bone chestplate joints, and his glowing eyes close-up. Clean light gray background."
    },
    {
        "char_id": "char_0017_tide_warlord",
        "char_name": "渊海狂澜",
        "img_type": "materialPalette",
        "prompt": "Use case: stylized-concept\\nAsset type: character asset for a reusable character pool\\n\\nCharacter lock:\\nName: The Abyssal Warlord (渊海狂澜)\\n\\nCurrent asset goal:\\nGenerate a material and color palette sheet. Show swatches of bone white, ship iron gray, bioluminescent cyan energy, and deep blue scales next to a neutral front view of the character. If he holds his trident, it must strictly have exactly three prongs (one central spike, two side spikes). Plain gray background."
    },
    {
        "char_id": "char_0017_tide_warlord",
        "char_name": "渊海狂澜",
        "img_type": "outfitBreakdown",
        "prompt": "Use case: stylized-concept\\nAsset type: character asset for a reusable character pool\\n\\nCharacter lock:\\nName: The Abyssal Warlord (渊海狂澜)\\n\\nCurrent asset goal:\\nGenerate an outfit breakdown sheet. Separate layers of his gear: bone chestplate, iron shoulder guards, tide-washed ropes sash, waist scale armor, and trident (the trident must strictly have exactly three prongs: one central vertical spike and two symmetrical side prongs). Plain light background."
    },
    {
        "char_id": "char_0017_tide_warlord",
        "char_name": "渊海狂澜",
        "img_type": "damageState",
        "prompt": "Use case: stylized-concept\\nAsset type: character asset for a reusable character pool\\n\\nCharacter lock:\\nName: The Abyssal Warlord (渊海狂澜)\\n\\nCurrent asset goal:\\nGenerate damage state variants. Show 3 full-body versions: default; battle-worn with cracked armor and kelp tangles; heavily damaged with bone chestplate shattered, tail scales cracked and scarred, trident cracked, and glowing eyes dimming. The trident in all views must strictly have exactly three prongs (one central spike, two side spikes)."
    }
]

abyssal_stalker_plan = [
    {
        "char_id": "char_0018_abyssal_stalker",
        "char_name": "逆潮之锋",
        "img_type": "main",
        "prompt": "A masterpiece marine fantasy concept art of the Abyssal Stalker. An ethereal, stealthy young shark-mermaid hunter with highly detailed sharp facial features, glowing emerald-green eyes, and messy black hair floating in water. She wears a light chestplate made of black sea-shell plates. Her lower body is a sleek, powerful silver-gray shark tail with a distinct dorsal fin. She is underwater in a dark ocean trench, holding dual curved daggers forged from black obsidian that glow with vibrant bioluminescent lime-green energy. The background features deep sea ruins, hydrothermal vents, and glowing jellyfish filtering soft light through the water, cinematic, hyper-realistic, 8k."
    },
    {
        "char_id": "char_0018_abyssal_stalker",
        "char_name": "逆潮之锋",
        "img_type": "portrait",
        "prompt": "Bust portrait of the Abyssal Stalker, face clearly visible. Focus on her sharp facial features, slanted shark-like ears, messy black hair floating in water, and piercing emerald-green eyes. Minimalist dark gray background. Masterpiece, 8k."
    },
    {
        "char_id": "char_0018_abyssal_stalker",
        "char_name": "逆潮之锋",
        "img_type": "expression",
        "prompt": "An expression sheet of the Abyssal Stalker. Show three facial expressions side-by-side: one calm and calculating with closed lips, one snarling with rows of sharp teeth visible, and one focused with narrowed emerald-green eyes during combat. Maintain the same hair and face structure. Plain dark background."
    },
    {
        "char_id": "char_0018_abyssal_stalker",
        "char_name": "逆潮之锋",
        "img_type": "turnaround",
        "prompt": "A professional character turnaround model sheet of the Abyssal Stalker. Show three views: front, side, and back, floating neutrally. Her eyes glow emerald, and her silver-gray shark tail with its dorsal fin is clearly visible. Plain clean light gray studio background. Masterpiece, 8k."
    },
    {
        "char_id": "char_0018_abyssal_stalker",
        "char_name": "逆潮之锋",
        "img_type": "outfit",
        "prompt": "Use case: stylized-concept\\nAsset type: character asset for a reusable character pool\\n\\nCharacter lock:\\nName: The Abyssal Stalker (逆潮之锋)\\n\\nCurrent asset goal:\\nGenerate an outfit variant image showing three outfits side-by-side: left, her default light shell armor; middle, a ritual scale dress made of iridescent dark-blue fish scales; right, a scout wrap made of dark green kelp ribbons and leather straps. All maintain her silver-gray shark tail and glowing green eyes. Clean background."
    },
    {
        "char_id": "char_0018_abyssal_stalker",
        "char_name": "逆潮之锋",
        "img_type": "prop",
        "prompt": "Prop reference sheet of the Abyssal Stalker's gear: her dual curved daggers forged from black obsidian. Show the daggers from multiple angles, highlighting the sharp jagged obsidian edges, the leather cord wrapping on the hilts, and how they connect at the handles to form a double-ended glaive. The blades glow with vibrant lime-green energy lines. Clean studio background, 8k."
    },
    {
        "char_id": "char_0018_abyssal_stalker",
        "char_name": "逆潮之锋",
        "img_type": "scene",
        "prompt": "Landscape scene concept art of a deep-sea hydrothermal trench field. Show active vents venting black smoke, hydrothermal chimneys glowing dull orange-red at their cracks, surrounded by bioluminescent underwater flora and corals. No characters. Cinematic, masterpiece, 8k."
    },
    {
        "char_id": "char_0018_abyssal_stalker",
        "char_name": "逆潮之锋",
        "img_type": "fullBody",
        "prompt": "Full-body standing art of the Abyssal Stalker. She floats neutrally, holding her dual obsidian daggers in a reverse grip. Her sleek silver-gray shark tail, sharp dorsal fin, light black shell breastplate, and glowing emerald-green eyes are fully visible. Clean light gray background."
    },
    {
        "char_id": "char_0018_abyssal_stalker",
        "char_name": "逆潮之锋",
        "img_type": "cover",
        "prompt": "Epic vertical cover art of the Abyssal Stalker. She is shown in a dynamic floating pose in the foreground, dual daggers glowing bright lime-green. The background is the dark abyss of a deep-sea trench with silhouettes of giant kraken tentacles looming. High contrast cinematic lighting, 8k."
    },
    {
        "char_id": "char_0018_abyssal_stalker",
        "char_name": "逆潮之锋",
        "img_type": "moodboard",
        "prompt": "A moodboard collage of the Abyssal Stalker. Four panels: one showing bioluminescent lime-green fluid flowing over black obsidian glass; one showing silver-gray shark scales texture; one showing deep-sea hydrothermic smoke vents; and one showing dense underwater kelp forests in shadows."
    },
    {
        "char_id": "char_0018_abyssal_stalker",
        "char_name": "逆潮之锋",
        "img_type": "sketch",
        "prompt": "Monochrome pencil sketch sheet of the Abyssal Stalker. Show 3 quick study sketches: lunging forward with daggers; hiding behind a coral rock; and standing neutrally holding her connected double-glaive. Clean white studio background."
    },
    {
        "char_id": "char_0018_abyssal_stalker",
        "char_name": "逆潮之锋",
        "img_type": "modelSheet",
        "prompt": "Standard model sheet of the Abyssal Stalker. Full-body front, side, and back views of her floating neutrally with her dual obsidian daggers in hip sheaths. Even lighting, clean light gray background."
    },
    {
        "char_id": "char_0018_abyssal_stalker",
        "char_name": "逆潮之锋",
        "img_type": "poseSheet",
        "prompt": "A pose sheet of the Abyssal Stalker showing 5 poses on one sheet: swimming downwards rapidly; dual daggers crossed in defense; dashing forward in a hunting pose; connecting her daggers into a double-ended glaive; and crouching stealthily on a dark sea rock. Solid dark gray background."
    },
    {
        "char_id": "char_0018_abyssal_stalker",
        "char_name": "逆潮之锋",
        "img_type": "expressionSheet",
        "prompt": "An expression sheet of the Abyssal Stalker showing 8 bust portraits in a grid: calm, calculating, aggressive snarl with sharp shark teeth visible, warning glare, exhausted, breathing heavily in pain, smirking, and deep focus. Clean background."
    },
    {
        "char_id": "char_0018_abyssal_stalker",
        "char_name": "逆潮之锋",
        "img_type": "detailSheet",
        "prompt": "A detail sheet for the Abyssal Stalker: close-ups of her slanted ears, the jagged teeth patterns on her chestplate armor joints, the textured silver-gray scales of her shark tail, and the glowing green toxin trail on the obsidian blade."
    },
    {
        "char_id": "char_0018_abyssal_stalker",
        "char_name": "逆潮之锋",
        "img_type": "materialPalette",
        "prompt": "A material and color palette sheet. Show swatches of black shell plates, silver-gray scales, glowing lime-green poison, and dark seaweed ropes next to a front view of the Abyssal Stalker. Plain background."
    },
    {
        "char_id": "char_0018_abyssal_stalker",
        "char_name": "逆潮之锋",
        "img_type": "outfitBreakdown",
        "prompt": "An outfit breakdown sheet showing the layers of the Abyssal Stalker's gear: the chestplate shell pieces, the waist seaweed sashes, the forearm spike wraps, and the dagger thigh sheaths. Clean light background."
    },
    {
        "char_id": "char_0018_abyssal_stalker",
        "char_name": "逆潮之锋",
        "img_type": "damageState",
        "prompt": "A damage state variant sheet showing 3 views: left, default; middle, battle-worn with shell armor cracked and seaweed wraps torn; right, heavily worn with tail scales fractured and leaking glowing green energy, chestplate cracked, and one dagger broken in half. Clean dark gray background."
    }
]

bioluminescent_spirit_plan = [
    {
        "char_id": "char_0019_bioluminescent_spirit",
        "char_name": "幽萤之灵",
        "img_type": "main",
        "prompt": "A masterpiece marine fantasy concept art of the Bioluminescent Spirit. An ethereal, beautiful young mermaid-jellyfish spirit with highly detailed expressive facial features, glowing pink-blue eyes, and wavy lavender hair floating in water. She wears a translucent pale pink-purple dome veil resembling a jellyfish hood. Her lower body is a sleek dark blue tail with several glowing, translucent pink-purple tentacles drifting. She is underwater, holding a delicate crystal lantern housing a glowing bioluminescent jellyfish. The background features deep-sea ruins with glowing anemones and schools of floating tiny jellyfish, lit by soft shafts of bioluminescent light, cinematic, hyper-realistic, 8k."
    },
    {
        "char_id": "char_0019_bioluminescent_spirit",
        "char_name": "幽萤之灵",
        "img_type": "portrait",
        "prompt": "Bust portrait of the Bioluminescent Spirit, face clearly visible. Focus on her sharp yet delicate facial features, glowing pink-blue eyes, wavy lavender hair floating in water, and the translucent pale pink-purple dome veil over her head. Minimalist dark gray background. Masterpiece, 8k."
    },
    {
        "char_id": "char_0019_bioluminescent_spirit",
        "char_name": "幽萤之灵",
        "img_type": "expression",
        "prompt": "An expression sheet of the Bioluminescent Spirit. Show three facial expressions side-by-side: one serene and calm with closed eyes, one surprised and curious with eyes wide open, and one showing a gentle, warm smile. Maintain the same lavender hair, translucent dome veil, and face structure. Plain dark background."
    },
    {
        "char_id": "char_0019_bioluminescent_spirit",
        "char_name": "幽萤之灵",
        "img_type": "turnaround",
        "prompt": "A professional character turnaround model sheet of the Bioluminescent Spirit. Show three views: front, side, and back, floating neutrally. Her eyes glow pink-blue, and her dark blue fish tail with long, glowing pink-purple tentacles is clearly visible. Plain clean light gray studio background. Masterpiece, 8k."
    },
    {
        "char_id": "char_0019_bioluminescent_spirit",
        "char_name": "幽萤之灵",
        "img_type": "outfit",
        "prompt": "An outfit sheet of the Bioluminescent Spirit. Show three outfit designs side-by-side: left, her default lavender gown; middle, a formal white ceremonial gown; right, a travel wrap of ocean silk. All designs maintain her lavender hair and pink-blue eyes. Solid light gray background."
    },
    {
        "char_id": "char_0019_bioluminescent_spirit",
        "char_name": "幽萤之灵",
        "img_type": "prop",
        "prompt": "Prop reference sheet of the Bioluminescent Spirit's gear: her signature crystal lantern. Show the lantern from multiple angles, highlighting the intricate carvings on the dark crystal frame, the bronze hanging chain, and the glowing bioluminescent jellyfish floating inside. The lantern casts a warm teal-purple light. Clean studio background, 8k."
    },
    {
        "char_id": "char_0019_bioluminescent_spirit",
        "char_name": "幽萤之灵",
        "img_type": "scene",
        "prompt": "Landscape scene concept art of the Tide Temple无光区 (dark zone). Show ancient underwater ruins and archways, filled with giant glowing coral trees, bioluminescent sea anemones, and schools of glowing jellyfish filtering light through the dark water. No characters. Cinematic, masterpiece, 8k."
    },
    {
        "char_id": "char_0019_bioluminescent_spirit",
        "char_name": "幽萤之灵",
        "img_type": "fullBody",
        "prompt": "Full-body standing art of the Bioluminescent Spirit. She floats gracefully in the water, holding her glowing crystal lantern in front of her. Her sleek dark blue fish tail, long pink-purple translucent tentacles, light marine gown, and glowing pink-blue eyes are fully visible. Clean light gray background."
    },
    {
        "char_id": "char_0019_bioluminescent_spirit",
        "char_name": "幽萤之灵",
        "img_type": "cover",
        "prompt": "Epic vertical cover art of the Bioluminescent Spirit. She is shown in a dynamic floating pose in the foreground, holding her glowing crystal lantern which casts a bright light. The background is a mysterious deep-sea temple with silhouettes of giant ancient ruins. High contrast cinematic lighting, 8k."
    },
    {
        "char_id": "char_0019_bioluminescent_spirit",
        "char_name": "幽萤之灵",
        "img_type": "moodboard",
        "prompt": "A moodboard collage of the Bioluminescent Spirit. Four panels: one showing glowing pink-purple jellyfish tentacles underwater; one showing deep-sea dark crystal texture; one showing soft glowing neon teal light in dark water; and one showing delicate white pearls and pink coral grains."
    },
    {
        "char_id": "char_0019_bioluminescent_spirit",
        "char_name": "幽萤之灵",
        "img_type": "sketch",
        "prompt": "Monochrome pencil sketch sheet of the Bioluminescent Spirit. Show 3 quick study sketches: floating peacefully with her lantern; casting a light barrier with her hand; and curling her fish tail neutrally. Clean white studio background."
    },
    {
        "char_id": "char_0019_bioluminescent_spirit",
        "char_name": "幽萤之灵",
        "img_type": "modelSheet",
        "prompt": "Standard model sheet of the Bioluminescent Spirit. Full-body front, side, and back views of her floating neutrally with her crystal lantern. Even lighting, clean light gray background."
    },
    {
        "char_id": "char_0019_bioluminescent_spirit",
        "char_name": "幽萤之灵",
        "img_type": "poseSheet",
        "prompt": "A pose sheet of the Bioluminescent Spirit showing 5 poses on one sheet: floating vertically holding her lantern; casting a micro-glow barrier; swimming downwards with tentacles trailing; sitting on a glowing coral; and curling up defensively. Solid dark gray background."
    },
    {
        "char_id": "char_0019_bioluminescent_spirit",
        "char_name": "幽萤之灵",
        "img_type": "expressionSheet",
        "prompt": "An expression sheet of the Bioluminescent Spirit showing 8 bust portraits in a grid: serene, surprised, gentle smile, worried frown, closed-eyes meditation, focused spellcasting, shy look, and exhausted/tired. Clean background."
    },
    {
        "char_id": "char_0019_bioluminescent_spirit",
        "char_name": "幽萤之灵",
        "img_type": "detailSheet",
        "prompt": "A detail sheet for the Bioluminescent Spirit: close-ups of the translucent texture of her jellyfish dome veil, the detailed glowing patterns in her pink-blue eyes, the pearlescent surface of her dark blue tail scales, and the crystal frame joints of her lantern."
    },
    {
        "char_id": "char_0019_bioluminescent_spirit",
        "char_name": "幽萤之灵",
        "img_type": "materialPalette",
        "prompt": "A material and color palette sheet. Show swatches of translucent pink-purple veil fabric, dark blue scales, glowing teal-purple light, and white coral beads next to a front view of the Bioluminescent Spirit. Plain background."
    },
    {
        "char_id": "char_0019_bioluminescent_spirit",
        "char_name": "幽萤之灵",
        "img_type": "outfitBreakdown",
        "prompt": "An outfit breakdown sheet showing the layers of the Bioluminescent Spirit's gear: the translucent dome veil, the shell bodice, the light silk gown layers, the seaweed waist sash, and the lantern handle attachment. Clean light background."
    },
    {
        "char_id": "char_0019_bioluminescent_spirit",
        "char_name": "幽萤之灵",
        "img_type": "damageState",
        "prompt": "A damage state variant sheet showing 3 views: left, default; middle, battle-worn with dome veil slightly torn and lantern dim; right, heavily worn with veil ripped, tail tentacles fractured and leaking glowing blue energy, gown torn, and her crystal lantern cracked with the inner flame dim. Clean dark gray background."
    }
]

rule_weaver_plan = [
    {
        "char_id": "char_0020_rule_weaver",
        "char_name": "规则编织者",
        "img_type": "main",
        "prompt": "A masterpiece modern urban mystery concept art of the Rule Weaver. A slender, elegant young East Asian woman with highly refined focused facial features, long dark gray hair, wearing a gold-rimmed monocle over one eye, a sleek double-breasted black trench coat, and a dark purple tie. She holds a glowing crimson fountain pen in one hand, writing glowing red rules in the air onto a heavy black leather ledger in her other hand. Ethereal glowing red text runes hover and chain around her in the dark. The background is a dimly lit, atmospheric investigation office with glowing red computer screens and crime files. High-contrast cinematic lighting, hyper-realistic, 8k."
    },
    {
        "char_id": "char_0020_rule_weaver",
        "char_name": "规则编织者",
        "img_type": "portrait",
        "prompt": "Bust portrait of the Rule Weaver, face clearly visible. Focus on her sharp facial features, long dark gray hair, a gold-rimmed monocle over one eye, and her dark purple tie under a black trench coat. She looks cold and focused. Minimalist dark gray background. Masterpiece, 8k."
    },
    {
        "char_id": "char_0020_rule_weaver",
        "char_name": "规则编织者",
        "img_type": "expression",
        "prompt": "An expression sheet of the Rule Weaver. Show three facial expressions side-by-side: one cold and emotionless, one speaking a stern command with eyes narrowed, and one showing a faint tired smirk. Maintain the same dark gray hair, monocle, and face structure. Plain dark background."
    },
    {
        "char_id": "char_0020_rule_weaver",
        "char_name": "规则编织者",
        "img_type": "turnaround",
        "prompt": "A professional character turnaround model sheet of the Rule Weaver. Show three views: front, side, and back, standing neutrally. She wears the double-breasted black trench coat, dark purple tie, and gold monocle. Her long dark gray hair falls down her back. Plain clean light gray studio background. Masterpiece, 8k."
    },
    {
        "char_id": "char_0020_rule_weaver",
        "char_name": "规则编织者",
        "img_type": "outfit",
        "prompt": "An outfit sheet of the Rule Weaver. Show three outfit designs side-by-side: left, her default black trench coat uniform; middle, a formal dark gray investigator blazer; right, a casual black sweater with purple accent scarf. All designs maintain her long dark gray hair and gold monocle. Solid light gray background."
    },
    {
        "char_id": "char_0020_rule_weaver",
        "char_name": "规则编织者",
        "img_type": "prop",
        "prompt": "Prop reference sheet of the Rule Weaver's gear: her signature glowing crimson fountain pen and heavy black leather ledger. Show the pen and the ledger from multiple angles, highlighting the intricate gold engravings on the pen body, the glowing crimson ink at the nib, and the embossed silver symbol on the ledger cover. Clean studio background, 8k."
    },
    {
        "char_id": "char_0020_rule_weaver",
        "char_name": "规则编织者",
        "img_type": "scene",
        "prompt": "Landscape scene concept art of the Paranormal Special Investigation Office. Show a spacious office in deep shadows at midnight, with tables covered in crime files, glowing red screens displaying bizarre data, and floating red neon warning signs. No characters. Cinematic, masterpiece, 8k."
    },
    {
        "char_id": "char_0020_rule_weaver",
        "char_name": "规则编织者",
        "img_type": "fullBody",
        "prompt": "Full-body standing art of the Rule Weaver. She stands tall and elegant, holding her glowing crimson fountain pen and writing on her open black leather ledger. She wears her double-breasted black trench coat, dark purple tie, and gold monocle. Glowing red runes hover around her. Clean light gray background."
    },
    {
        "char_id": "char_0020_rule_weaver",
        "char_name": "规则编织者",
        "img_type": "cover",
        "prompt": "Epic vertical cover art of the Rule Weaver. She is shown in a dynamic pose in the foreground, pointing her glowing crimson fountain pen forward as red glowing chains of text weave around her. The background features a distorted, surreal urban skyline under a blood-red moon. High contrast cinematic lighting, 8k."
    },
    {
        "char_id": "char_0020_rule_weaver",
        "char_name": "规则编织者",
        "img_type": "moodboard",
        "prompt": "A moodboard collage of the Rule Weaver. Four flat panels showing: one of glowing crimson ink droplets spreading in dark water; one of a close-up of a vintage gold-rimmed monocle; one of textured black leather with silver engravings; and one of neon red glowing text runes shining in shadows. Clean grid layout, no borders, no text, no labels, plain background."
    },
    {
        "char_id": "char_0020_rule_weaver",
        "char_name": "规则编织者",
        "img_type": "sketch",
        "prompt": "Monochrome pencil sketch sheet of the Rule Weaver. Show 3 quick study sketches: standing and writing on her ledger; pointing her pen to cast a rule-lock; and standing neutrally looking over her shoulder. Clean white studio background."
    },
    {
        "char_id": "char_0020_rule_weaver",
        "char_name": "规则编织者",
        "img_type": "modelSheet",
        "prompt": "Standard model sheet of the Rule Weaver. Full-body front, side, and back views of her standing neutrally with her black ledger and red pen. Even lighting, clean light gray background."
    },
    {
        "char_id": "char_0020_rule_weaver",
        "char_name": "规则编织者",
        "img_type": "poseSheet",
        "prompt": "A pose sheet of the Rule Weaver showing 5 poses on one sheet: standing vertically writing rules in the air; pointing her glowing red pen forward; holding the closed ledger against her chest; inspecting a floating red rune; and standing in a defense stance with red chains of text surrounding her. Solid dark gray background."
    },
    {
        "char_id": "char_0020_rule_weaver",
        "char_name": "规则编织者",
        "img_type": "expressionSheet",
        "prompt": "An expression sheet of the Rule Weaver showing 8 bust portraits in a grid: cold/emotionless, speaking a command, faint tired smirk, focused concentration, eyes closed in meditation, analytical frown, startled look, and exhausted/fatigued. Clean background."
    },
    {
        "char_id": "char_0020_rule_weaver",
        "char_name": "规则编织者",
        "img_type": "detailSheet",
        "prompt": "A detail sheet for the Rule Weaver: close-ups of the gold-rimmed monocle, the glowing crimson fountain pen nib with red energy, the embossed silver seal on the black ledger, and the dark purple tie knot on the black trench coat collar. Clean light background."
    },
    {
        "char_id": "char_0020_rule_weaver",
        "char_name": "规则编织者",
        "img_type": "materialPalette",
        "prompt": "A material and color palette sheet. Show swatches of black trench coat fabric, gold metal monocle frame, glowing crimson ink, and dark purple tie silk next to a front view of the Rule Weaver. Plain background."
    },
    {
        "char_id": "char_0020_rule_weaver",
        "char_name": "规则编织者",
        "img_type": "outfitBreakdown",
        "prompt": "An outfit breakdown sheet showing the layers of the Rule Weaver's gear: the black trench coat, the investigator shirt, the dark purple tie, the silver badge, and the leather holster. Clean light background."
    },
    {
        "char_id": "char_0020_rule_weaver",
        "char_name": "规则编织者",
        "img_type": "damageState",
        "prompt": "A damage state variant sheet showing 3 views: left, default; middle, battle-worn with trench coat slightly torn and pen glowing dimly; right, heavily worn with trench coat shredded, monocle cracked, ledger torn with burning red pages, and red glowing rules leaking chaotically around her. Clean dark gray background."
    }
]

sand_sailor_plan = [
    {
        "char_id": "char_0021_sand_sailor",
        "char_name": "尘沙领航员",
        "img_type": "main",
        "prompt": "A masterpiece modern wasteland concept art of the Sand Helmsman. A grizzled young man with wind-blown silver hair and brass navigator goggles over his eyes, his skin weathered to a rugged bronze. He wears a dust-caked dark brown captain's coat with a high collar, and a heavy utility harness rigged with ropes and pulleys. He stands at the wooden wheel of a scrap-metal land sailer with patched canvas sails, steering through rolling golden desert dunes under a hazy storm-swept sky. He holds a glowing anemometer, while in the background, the colossal half-buried rusty skeleton of an ancient cargo ship looms on the horizon. Cinematic, hyper-realistic, 8k."
    },
    {
        "char_id": "char_0021_sand_sailor",
        "char_name": "尘沙领航员",
        "img_type": "portrait",
        "prompt": "Bust portrait of the Sand Helmsman, face clearly visible. Focus on his wind-blown silver hair, brass navigator goggles, rugged bronze skin, and the high collar of his dark captain's coat. He looks determined and focused. Minimalist dark gray background. Masterpiece, 8k."
    },
    {
        "char_id": "char_0021_sand_sailor",
        "char_name": "尘沙领航员",
        "img_type": "expression",
        "prompt": "An expression sheet of the Sand Helmsman. Show three facial expressions side-by-side: one calm and squinting into the wind, one laughing heartily, and one battle-hardened with gritted teeth. Maintain the same silver hair, goggles, and captain's coat. Plain dark background."
    },
    {
        "char_id": "char_0021_sand_sailor",
        "char_name": "尘沙领航员",
        "img_type": "turnaround",
        "prompt": "A professional character turnaround model sheet of the Sand Helmsman. Show three views: front, side, and back, standing neutrally. He wears the captain's coat, goggles, and utility harness. Plain clean light gray studio background. Masterpiece, 8k."
    },
    {
        "char_id": "char_0021_sand_sailor",
        "char_name": "尘沙领航员",
        "img_type": "outfit",
        "prompt": "An outfit sheet of the Sand Helmsman. Show three outfit designs side-by-side: left, his default captain's coat; middle, a lighter sleeveless utility vest; right, a heavy protective sand-storm poncho. All designs maintain his silver hair and goggles. Solid light gray background."
    },
    {
        "char_id": "char_0021_sand_sailor",
        "char_name": "尘沙领航员",
        "img_type": "prop",
        "prompt": "Prop reference sheet of the Sand Helmsman's gear: his signature brass anemometer and pneumatic harpoon gun. Show the anemometer and the harpoon gun from multiple angles, highlighting the intricate pressure gauges, copper coils, and rusty scrap metal joints. Clean studio background, 8k."
    },
    {
        "char_id": "char_0021_sand_sailor",
        "char_name": "尘沙领航员",
        "img_type": "scene",
        "prompt": "Landscape scene concept art of the Dune Ocean (无尽沙丘). Show rolling golden desert sand dunes stretching to the horizon under a dusty, orange-tinted storm sky, with half-buried metal ruins of ancient skyscrapers and rusted cargo ships. No characters. Cinematic, masterpiece, 8k."
    },
    {
        "char_id": "char_0021_sand_sailor",
        "char_name": "尘沙领航员",
        "img_type": "fullBody",
        "prompt": "Full-body standing art of the Sand Helmsman. He stands heroically, holding his brass wind-gauge and resting his other hand on a heavy pneumatic harpoon gun. He wears his Captain's coat, goggles, and utility harness. Clean light gray background."
    },
    {
        "char_id": "char_0021_sand_sailor",
        "char_name": "尘沙领航员",
        "img_type": "cover",
        "prompt": "Epic vertical cover art of the Sand Helmsman. He is shown in a dynamic pose in the foreground, steering his land sailer as sand sprays around him. The background features a massive sandstorm wall and a blazing desert sun. High contrast cinematic lighting, 8k."
    },
    {
        "char_id": "char_0021_sand_sailor",
        "char_name": "尘沙领航员",
        "img_type": "moodboard",
        "prompt": "A moodboard collage of the Sand Helmsman. Four flat panels showing: one of dry golden desert sand texture; one of detailed brass gears and navigator goggles; one of weathered dark brown leather captain's coat fabric; and one of a rusty metal ship hull. Clean grid layout, no borders, no text, no labels, plain background."
    },
    {
        "char_id": "char_0021_sand_sailor",
        "char_name": "尘沙领航员",
        "img_type": "sketch",
        "prompt": "Monochrome pencil sketch sheet of the Sand Helmsman. Show 3 quick study sketches: standing at the ship wheel; aiming his harpoon gun; and resting on a scrap pile looking at the sky. Clean white studio background."
    },
    {
        "char_id": "char_0021_sand_sailor",
        "char_name": "尘沙领航员",
        "img_type": "modelSheet",
        "prompt": "Standard model sheet of the Sand Helmsman. Full-body front, side, and back views of him standing neutrally with his captain's coat. Even lighting, clean light gray background."
    },
    {
        "char_id": "char_0021_sand_sailor",
        "char_name": "尘沙领航员",
        "img_type": "poseSheet",
        "prompt": "A pose sheet of the Sand Helmsman showing 5 poses on one sheet: steering the wheel actively; aiming the harpoon gun; looking through a brass telescope; climbing a rope ladder; and standing defiantly against a sandstorm. Solid dark gray background."
    },
    {
        "char_id": "char_0021_sand_sailor",
        "char_name": "尘沙领航员",
        "img_type": "expressionSheet",
        "prompt": "An expression sheet of the Sand Helmsman showing 8 bust portraits in a grid: calm, laughing, gritted teeth, thoughtful frown, squinting eyes, surprised look, shouting commands, and fatigued. Clean background."
    },
    {
        "char_id": "char_0021_sand_sailor",
        "char_name": "尘沙领航员",
        "img_type": "detailSheet",
        "prompt": "A detail sheet for the Sand Helmsman: close-ups of the brass navigator goggles, the pneumatic valve on his harpoon gun, the leather captain's coat stitching, and the anemometer's spinning cups. Clean light background."
    },
    {
        "char_id": "char_0021_sand_sailor",
        "char_name": "尘沙领航员",
        "img_type": "materialPalette",
        "prompt": "A material and color palette sheet. Show swatches of dark captain's coat wool, weathered brown leather, shiny brass plating, and coarse golden sand next to a front view of the Sand Helmsman. Plain background."
    },
    {
        "char_id": "char_0021_sand_sailor",
        "char_name": "尘沙领航员",
        "img_type": "outfitBreakdown",
        "prompt": "An outfit breakdown sheet showing the layers of the Sand Helmsman's gear: the captain's coat, the inner utility shirt, the leather harness, the heavy cargo pants, and the combat boots. Clean light background."
    },
    {
        "char_id": "char_0021_sand_sailor",
        "char_name": "尘沙领航员",
        "img_type": "damageState",
        "prompt": "A damage state variant sheet showing 3 views: left, default; middle, battle-worn with coat torn and goggles cracked; right, heavily worn with captain's coat shredded, harness broken, harpoon gun dented, and bleeding scratches on his face. Clean dark gray background."
    }
]

dome_botanist_plan = [
    {
        "char_id": "char_0022_dome_botanist",
        "char_name": "穹顶植物学家",
        "img_type": "main",
        "prompt": "A masterpiece modern wasteland sci-fi concept art of the Dome Botanist. A young female researcher with messy dark green hair, wearing thick round glasses, a researcher lab coat stained with dirt and green botanical fluids over cargo pants. She carries a large, spherical glass bio-dome backpack housing a single glowing green seedling floating in nutrient gel. She wears heavy protective gloves, using a modified brass watering sprayer to nurture a small glowing blue mutant flower growing from a crack in the concrete wasteland. Vines and patches of glowing green moss drape over the decaying concrete ruins around her. Cinematic, hyper-realistic, 8k."
    },
    {
        "char_id": "char_0022_dome_botanist",
        "char_name": "穹顶植物学家",
        "img_type": "portrait",
        "prompt": "Bust portrait of the Dome Botanist, face clearly visible. Focus on her messy dark green hair, thick round glasses, and the collar of her soiled white lab coat. She looks focused and gentle. Minimalist dark gray background. Masterpiece, 8k."
    },
    {
        "char_id": "char_0022_dome_botanist",
        "char_name": "穹顶植物学家",
        "img_type": "expression",
        "prompt": "An expression sheet of the Dome Botanist. Show three facial expressions side-by-side: one serene with a gentle smile, one focused and squinting through glasses, and one worried with a slight frown. Maintain the same dark green hair, glasses, and lab coat. Plain dark background."
    },
    {
        "char_id": "char_0022_dome_botanist",
        "char_name": "穹顶植物学家",
        "img_type": "turnaround",
        "prompt": "A professional character turnaround model sheet of the Dome Botanist. Show three views: front, side, and back, standing neutrally. She wears the white lab coat and carries the spherical glass bio-dome backpack. Plain clean light gray studio background. Masterpiece, 8k."
    },
    {
        "char_id": "char_0022_dome_botanist",
        "char_name": "穹顶植物学家",
        "img_type": "outfit",
        "prompt": "An outfit sheet of the Dome Botanist. Show three outfit designs side-by-side: left, her default lab coat; middle, a heavy protective bio-suit; right, a casual green sweater and work apron. All designs maintain her dark green hair and glasses. Solid light gray background."
    },
    {
        "char_id": "char_0022_dome_botanist",
        "char_name": "穹顶植物学家",
        "img_type": "prop",
        "prompt": "Prop reference sheet of the Dome Botanist's gear: her signature bio-dome backpack and modified brass watering sprayer. Show the backpack and the sprayer from multiple angles, highlighting the glowing green seedling in the glass orb, pressure tubes, and brass nozzle details. Clean studio background, 8k."
    },
    {
        "char_id": "char_0022_dome_botanist",
        "char_name": "穹顶植物学家",
        "img_type": "scene",
        "prompt": "Landscape scene concept art of the Overgrown Concrete Ruins. Show decaying concrete building ruins overgrown with thick vines, patches of glowing green moss, and strange mutant glowing blue flowers under a gray post-apocalyptic sky. No characters. Cinematic, masterpiece, 8k."
    },
    {
        "char_id": "char_0022_dome_botanist",
        "char_name": "穹顶植物学家",
        "img_type": "fullBody",
        "prompt": "Full-body standing art of the Dome Botanist. She stands carefully, holding her modified brass watering sprayer in front of her. She wears her soiled white lab coat, cargo pants, and carries the glowing glass bio-dome backpack. Clean light gray background."
    },
    {
        "char_id": "char_0022_dome_botanist",
        "char_name": "穹顶植物学家",
        "img_type": "cover",
        "prompt": "Epic vertical cover art of the Dome Botanist. She is shown in a dynamic pose in the foreground, shielding her bio-dome backpack from a toxic green acid rain storm. The background features decaying overgrown factory towers. High contrast cinematic lighting, 8k."
    },
    {
        "char_id": "char_0022_dome_botanist",
        "char_name": "穹顶植物学家",
        "img_type": "moodboard",
        "prompt": "A moodboard collage of the Dome Botanist. Four flat panels showing: one of glowing green seedlings in nutrient gel; one of textured concrete ruins with moss; one of a close-up of vintage round glasses; and one of glowing blue mutant flower petals. Clean grid layout, no borders, no text, no labels, plain background."
    },
    {
        "char_id": "char_0022_dome_botanist",
        "char_name": "穹顶植物学家",
        "img_type": "sketch",
        "prompt": "Monochrome pencil sketch sheet of the Dome Botanist. Show 3 quick study sketches: kneeling and tending to a plant; checking the bio-dome gauges; and standing neutrally looking at a leaf. Clean white studio background."
    },
    {
        "char_id": "char_0022_dome_botanist",
        "char_name": "穹顶植物学家",
        "img_type": "modelSheet",
        "prompt": "Standard model sheet of the Dome Botanist. Full-body front, side, and back views of her standing neutrally with her bio-dome backpack. Even lighting, clean light gray background."
    },
    {
        "char_id": "char_0022_dome_botanist",
        "char_name": "穹顶植物学家",
        "img_type": "poseSheet",
        "prompt": "A pose sheet of the Dome Botanist showing 5 poses on one sheet: kneeling to water a plant; running with her backpack secured; looking at a leaf with a magnifying glass; adjusting dials on her pack; and standing defensively shielding a seedling. Solid dark gray background."
    },
    {
        "char_id": "char_0022_dome_botanist",
        "char_name": "穹顶植物学家",
        "img_type": "expressionSheet",
        "prompt": "An expression sheet of the Dome Botanist showing 8 bust portraits in a grid: gentle smile, focused squint, worried frown, closed-eyes meditation, surprised gasp, happy grin, tired sigh, and determined look. Clean background."
    },
    {
        "char_id": "char_0022_dome_botanist",
        "char_name": "穹顶植物学家",
        "img_type": "detailSheet",
        "prompt": "A detail sheet for the Dome Botanist: close-ups of the thick round glasses, the floating seedling inside the glass backpack, the dirty collar of her lab coat, and the brass nozzle of her sprayer. Clean light background."
    },
    {
        "char_id": "char_0022_dome_botanist",
        "char_name": "穹顶植物学家",
        "img_type": "materialPalette",
        "prompt": "A material and color palette sheet. Show swatches of white lab coat fabric, transparent glass, glowing green fluid, and rough concrete next to a front view of the Dome Botanist. Plain background."
    },
    {
        "char_id": "char_0022_dome_botanist",
        "char_name": "穹顶植物学家",
        "img_type": "outfitBreakdown",
        "prompt": "An outfit breakdown sheet showing the layers of the Dome Botanist's gear: the white lab coat, the cargo shirt, the utility belt, the cargo pants, and the high rain boots. Clean light background."
    },
    {
        "char_id": "char_0022_dome_botanist",
        "char_name": "穹顶植物学家",
        "img_type": "damageState",
        "prompt": "A damage state variant sheet showing 3 views: left, default; middle, battle-worn with lab coat torn and glasses cracked; right, heavily worn with lab coat shredded, glass backpack dome cracked with glowing fluid leaking, and her hands wrapped in bandages. Clean dark gray background."
    }
]

astral_mage_plan = [
    {
        "char_id": "char_0023_astral_mage",
        "char_name": "秘术观星者",
        "img_type": "main",
        "prompt": "A masterpiece modern Western fantasy concept art of the Astral Archmage. A handsome young man with dark navy-blue curly hair and eyes reflecting faint blue starlight. He wears a heavy, deep blue velvet wizard robe intricately embroidered with golden zodiac star charts, the collar and trim glowing with faint starlight embers. He stands on the open balcony of a high Gothic observatory tower under a brilliant, hyper-detailed starry night sky with subtle aurora bands. He holds a rotating, multi-ringed golden brass astrolabe in one hand, projecting a miniature glowing blue galaxy at its center. A few torn parchment scroll sheets with glowing star orbits float around him. High-contrast cinematic lighting, hyper-realistic, 8k."
    },
    {
        "char_id": "char_0023_astral_mage",
        "char_name": "秘术观星者",
        "img_type": "portrait",
        "prompt": "Bust portrait of the Astral Archmage, face clearly visible. Focus on his dark navy-blue curly hair, eyes reflecting faint blue starlight, and the high collar of his starry velvet robe. He looks calm and focused. Minimalist dark background, 8k."
    },
    {
        "char_id": "char_0023_astral_mage",
        "char_name": "秘术观星者",
        "img_type": "expression",
        "prompt": "An expression sheet of the Astral Archmage. Show three facial expressions side-by-side: one calm and calculating, one chanting spell with glowing eyes, and one showing a gentle, knowing smile. Maintain his blue curly hair and starry robe. Solid dark background, 8k."
    },
    {
        "char_id": "char_0023_astral_mage",
        "char_name": "秘术观星者",
        "img_type": "turnaround",
        "prompt": "A professional character turnaround model sheet of the Astral Archmage. Show three views: front, side, and back, standing neutrally. He wears the starry navy-blue velvet robe and holds his astrolabe. Plain clean light gray studio background. Masterpiece, 8k."
    },
    {
        "char_id": "char_0023_astral_mage",
        "char_name": "秘术观星者",
        "img_type": "outfit",
        "prompt": "An outfit sheet of the Astral Archmage. Show three outfit designs side-by-side: left, his default velvet wizard robe; middle, a lighter academic research vest and shirt; right, an ornate celestial high ceremonial robe with large wing-like sleeves. All designs maintain his blue curly hair. Solid light gray background."
    },
    {
        "char_id": "char_0023_astral_mage",
        "char_name": "秘术观星者",
        "img_type": "prop",
        "prompt": "Prop reference sheet of the Astral Archmage's gear: his signature rotating golden brass astrolabe and a leather-bound grimoire. Show the astrolabe and the book from multiple angles, highlighting the intricate stellar engravings, glowing gears, and parchment textures. Clean studio background, 8k."
    },
    {
        "char_id": "char_0023_astral_mage",
        "char_name": "秘术观星者",
        "img_type": "scene",
        "prompt": "Landscape scene concept art of the Starry Observatory Deck (观星露台). Show a high gothic tower balcony overlooking a vast sea of clouds under a breathtaking, cosmic night sky filled with nebulae, shooting stars, and deep blue constellations. No characters. Cinematic, masterpiece, 8k."
    },
    {
        "char_id": "char_0023_astral_mage",
        "char_name": "秘术观星者",
        "img_type": "fullBody",
        "prompt": "Full-body standing art of the Astral Archmage. He stands holding his golden astrolabe in one hand and a glowing parchment sheet in the other. He wears his starry velvet robe and wizard hood. Clean light gray background, 8k."
    },
    {
        "char_id": "char_0023_astral_mage",
        "char_name": "秘术观星者",
        "img_type": "cover",
        "prompt": "Epic vertical cover art of the Astral Archmage. He is shown in a dynamic pose in the foreground, raising his astrolabe as a massive beam of cosmic starlight strikes down from the sky. The background features giant celestial rings and starry portals. High contrast cinematic lighting, 8k."
    },
    {
        "char_id": "char_0023_astral_mage",
        "char_name": "秘术观星者",
        "img_type": "moodboard",
        "prompt": "A moodboard collage of the Astral Archmage. Four flat panels showing: one of sparkling gold stars on deep blue fabric; one of vintage brass astrolabe gear details; one of glowing blue galaxy vortex; and one of ancient parchment papers with hand-drawn constellations. Clean grid layout, no borders, no text, plain background."
    },
    {
        "char_id": "char_0023_astral_mage",
        "char_name": "秘术观星者",
        "img_type": "sketch",
        "prompt": "Monochrome pencil sketch sheet of the Astral Archmage. Show 3 quick study sketches: standing at the telescope; holding a glowing parchment scroll; and sitting at a desk surrounded by astronomical charts. Clean white studio background."
    },
    {
        "char_id": "char_0023_astral_mage",
        "char_name": "秘术观星者",
        "img_type": "modelSheet",
        "prompt": "Standard model sheet of the Astral Archmage. Full-body front, side, and back views of him standing neutrally with his starry velvet robe. Even lighting, clean light gray background."
    },
    {
        "char_id": "char_0023_astral_mage",
        "char_name": "秘术观星者",
        "img_type": "poseSheet",
        "prompt": "A pose sheet of the Astral Archmage showing 5 poses on one sheet: chanting a star spell; pointing his astrolabe forward; examining a glowing map; looking through a telescope; and standing defiantly with wind-blown robes. Solid dark gray background."
    },
    {
        "char_id": "char_0023_astral_mage",
        "char_name": "秘术观星者",
        "img_type": "expressionSheet",
        "prompt": "An expression sheet of the Astral Archmage showing 8 bust portraits in a grid: calm calculation, chanting spell with glowing blue eyes, serene smile, worried frown, surprised look, shouting commands, fatigue, and intense focus. Clean background."
    },
    {
        "char_id": "char_0023_astral_mage",
        "char_name": "秘术观星者",
        "img_type": "detailSheet",
        "prompt": "A detail sheet for the Astral Archmage: close-ups of the rotating rings of his astrolabe, the golden constellation embroidery on his collar, his starlight-reflecting eyes, and the glowing runes on a parchment page. Clean light background."
    },
    {
        "char_id": "char_0023_astral_mage",
        "char_name": "秘术观星者",
        "img_type": "materialPalette",
        "prompt": "A material and color palette sheet. Show swatches of deep blue velvet, polished yellow brass, glowing blue galaxy dust, and ancient dry parchment next to a front view of the Astral Archmage. Plain background."
    },
    {
        "char_id": "char_0023_astral_mage",
        "char_name": "秘术观星者",
        "img_type": "outfitBreakdown",
        "prompt": "An outfit breakdown sheet showing the layers of the Astral Archmage's gear: the velvet outer robe, the inner tunic, the wizard sash, the leather boots, and the astrolabe holster. Clean light background."
    },
    {
        "char_id": "char_0023_astral_mage",
        "char_name": "秘术观星者",
        "img_type": "damageState",
        "prompt": "A damage state variant sheet showing 3 views: left, default; middle, battle-worn with robe torn and astrolabe glowing dimly; right, heavily worn with robes tattered, astrolabe cracked with leaking blue energy, and bleeding scratches on his face. Clean dark gray background."
    }
]

moonshadow_ranger_plan = [
    {
        "char_id": "char_0024_moonshadow_ranger",
        "char_name": "月影游侠",
        "img_type": "main",
        "prompt": "A masterpiece modern forest fantasy concept art of the Moonshadow Ranger. A beautiful young half-elf woman with long silver hair in a high ponytail, wearing a dark green hooded wind-cloak and form-fitting leather armor. She stands on a branch of a massive ancient redwood tree, drawing a glowing oak longbow. The arrow tip radiates soft blue starlight. The background is a dense, atmospheric mystical forest bathed in silver moonlight, with glowing cyan mushrooms and drifting gold fireflies. High-contrast cinematic lighting, hyper-realistic, 8k."
    },
    {
        "char_id": "char_0024_moonshadow_ranger",
        "char_name": "月影游侠",
        "img_type": "portrait",
        "prompt": "Bust portrait of the Moonshadow Ranger, face clearly visible. Focus on her long silver hair in a high ponytail, glowing light-green eyes, and the hood of her dark green wind-cloak. She looks calm and alert. Minimalist dark green background, 8k."
    },
    {
        "char_id": "char_0024_moonshadow_ranger",
        "char_name": "月影游侠",
        "img_type": "expression",
        "prompt": "An expression sheet of the Moonshadow Ranger. Show three facial expressions side-by-side: one calm and quiet, one shouting with focused eyes, and one displaying a rare, serene and gentle smile. Maintain her silver hair and green cloak. Plain dark background."
    },
    {
        "char_id": "char_0024_moonshadow_ranger",
        "char_name": "月影游侠",
        "img_type": "turnaround",
        "prompt": "A professional character turnaround model sheet of the Moonshadow Ranger. Show three views: front, side, and back, standing neutrally with arms relaxed by her sides. She wears the green hooded cloak and leather light armor. No weapons or bow are held to ensure clean posture and anatomical accuracy. Plain clean light gray studio background. Masterpiece, 8k."
    },
    {
        "char_id": "char_0024_moonshadow_ranger",
        "char_name": "月影游侠",
        "img_type": "outfit",
        "prompt": "An outfit sheet of the Moonshadow Ranger. Show three outfit designs side-by-side: left, her default leather armor and cloak; middle, a lighter ranger scouting outfit without the cloak; right, an ornate ceremonial elven leather guardian armor with gold leaf filigree. All designs maintain her silver ponytailed hair. Solid light gray background."
    },
    {
        "char_id": "char_0024_moonshadow_ranger",
        "char_name": "月影游侠",
        "img_type": "prop",
        "prompt": "Prop reference sheet of the Moonshadow Ranger's gear: her leaf-carved oak bow and a leather quiver with moonstone-tipped arrows. Show the bow and the quiver from multiple angles, highlighting the intricate wood grain, leather straps, and glowing blue arrow tip details. Clean studio background, 8k."
    },
    {
        "char_id": "char_0024_moonshadow_ranger",
        "char_name": "月影游侠",
        "img_type": "scene",
        "prompt": "Landscape scene concept art of the Moonlit Pool (月光池塘) in the forest. Show a serene pond reflecting a massive full moon, surrounded by giant ancient weeping trees with glowing leaves and patches of cyan bioluminescent flowers. No characters. Cinematic, masterpiece, 8k."
    },
    {
        "char_id": "char_0024_moonshadow_ranger",
        "char_name": "月影游侠",
        "img_type": "fullBody",
        "prompt": "Full-body standing art of the Moonshadow Ranger. She stands balanced on a mossy log, holding her oak bow in one hand. She wears her dark green hooded cloak, light leather armor, and high leather boots. Clean light gray background, 8k."
    },
    {
        "char_id": "char_0024_moonshadow_ranger",
        "char_name": "月影游侠",
        "img_type": "cover",
        "prompt": "Epic vertical cover art of the Moonshadow Ranger. She is shown in a dynamic mid-air pose in the foreground, firing a glowing blue moonstone arrow down from the canopy. The background features giant redwood branches, swirling glowing leaves, and a huge silver full moon. High contrast cinematic lighting, 8k."
    },
    {
        "char_id": "char_0024_moonshadow_ranger",
        "char_name": "月影游侠",
        "img_type": "moodboard",
        "prompt": "A moodboard collage of the Moonshadow Ranger. Four flat panels showing: one of glowing mint-green leaves; one of weathered brown leather straps; one of glowing blue moonstone texture; and one of a dark misty forest canopy under moonlight. Clean grid layout, no borders, no text, plain background."
    },
    {
        "char_id": "char_0024_moonshadow_ranger",
        "char_name": "月影游侠",
        "img_type": "sketch",
        "prompt": "Monochrome pencil sketch sheet of the Moonshadow Ranger. Show 3 quick study sketches: drawing her bow; tracking a footprint on the ground; and resting against a giant root looking at the moon. Clean white studio background."
    },
    {
        "char_id": "char_0024_moonshadow_ranger",
        "char_name": "月影游侠",
        "img_type": "modelSheet",
        "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Moonshadow Ranger (月影游侠)
Gender / age impression: young half-elf woman, calm and alert, 22-year appearance
Body shape: slender and athletic build, elegant posture
Face: beautiful delicate face, glowing light-green eyes, calm expression
Hair: long silver hair tied in a high ponytail
Eyes: glowing light-green eyes
Outfit: dark green hooded wind-cloak over form-fitting leather armor, high leather boots
Accessories / weapon: leaf-carved oak bow, leather quiver with moonstone-tipped arrows
Color palette: dark green, silver white, leather brown, glowing starlight blue, mint green
Fixed traits that must never change: silver high-ponytail hair, light-green eyes, dark green hooded cloak, leaf-carved oak bow

Current asset goal:
Generate a character model sheet / standard character design reference. Focus on authoritative design reference showing the character standing neutrally in her default costume.

Style:
Modern forest fantasy concept art, 3D octane render, photorealistic 3D character reference design, hyper-detailed material textures, cinematic lighting, high-fidelity production-ready asset.

Composition:
Detailed full-body front view of the character standing in her default costume holding her signature full-sized leaf-carved oak bow (scaled proportionally to her body height). The side of the sheet shows detailed callouts of her bow and arrows. Even lighting, clean light gray background.

Background:
Clean light gray background.

Constraints:
Keep the same face, hairstyle, outfit logic, color palette, body shape, and signature accessories.
Do not redesign the character.
No text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."""
    },
    {
        "char_id": "char_0024_moonshadow_ranger",
        "char_name": "月影游侠",
        "img_type": "poseSheet",
        "prompt": "A pose sheet of the Moonshadow Ranger showing 5 poses on one sheet: drawing the bow to fire; crouching on a high branch; sliding under a root; aiming a dagger; and standing defiantly with wind-blown hair. Solid dark gray background."
    },
    {
        "char_id": "char_0024_moonshadow_ranger",
        "char_name": "月影游侠",
        "img_type": "expressionSheet",
        "prompt": "An expression sheet of the Moonshadow Ranger showing 8 bust portraits in a grid: calm alert, shouting command, gentle smile, focused squint, surprised look, pain, fatigued, and intense focus. Clean background."
    },
    {
        "char_id": "char_0024_moonshadow_ranger",
        "char_name": "月影游侠",
        "img_type": "detailSheet",
        "prompt": "A detail sheet for the Moonshadow Ranger: close-ups of the leaf carving on her oak bow, the glowing moonstone arrow tip, the leather stitching on her shoulder guards, and her starlight-reflecting green eyes. Clean light background."
    },
    {
        "char_id": "char_0024_moonshadow_ranger",
        "char_name": "月影游侠",
        "img_type": "materialPalette",
        "prompt": "A material and color palette sheet. Show swatches of dark green wool cloak fabric, weathered brown leather, glowing blue moonstone, and mossy ancient bark next to a front view of the Moonshadow Ranger. Plain background."
    },
    {
        "char_id": "char_0024_moonshadow_ranger",
        "char_name": "月影游侠",
        "img_type": "outfitBreakdown",
        "prompt": "An outfit breakdown sheet showing the layers of the Moonshadow Ranger's gear: the green wind-cloak, the leather breastplate, the inner linen shirt, the utility belt with daggers, and the high leather boots. No large oak bow or weapons are shown on this sheet to focus purely on the clothing layers. Clean light background."
    },
    {
        "char_id": "char_0024_moonshadow_ranger",
        "char_name": "月影游侠",
        "img_type": "damageState",
        "prompt": "A damage state variant sheet showing 3 views: left, default; middle, battle-worn with cloak torn and armor scuffed; right, heavily worn with cloak shredded, leather armor broken, and bleeding scratches on her cheek. In all views, she holds her signature full-sized leaf-carved oak bow (scaled proportionally to her body height), which is clean on the left, slightly scuffed in the middle, and cracked on the right. Clean dark gray background."
    }
]

frost_necromancer_plan = [
    {
        "char_id": "char_0026_frost_necromancer",
        "char_name": "霜寒通灵师",
        "img_type": "main",
        "prompt": "A masterpiece modern western fantasy concept art of the Frost Necromancer. A beautiful, pale-skinned young woman with flowing silver-white hair and glowing ice-blue eyes, wearing a detailed dark grey necromancer robe. She holds a staff of eternal ice topped with a floating skull enveloped in blue frost flames. Cold mist and glowing snowflakes swirl around her in an ancient gothic icy tomb with rune-carved pillars. Cinematic lighting, masterpiece, 8k."
    },
    {
        "char_id": "char_0026_frost_necromancer",
        "char_name": "霜寒通灵师",
        "img_type": "portrait",
        "prompt": "Bust portrait of the Frost Necromancer, face clearly visible. Focus on her sharp yet delicate facial features, glowing ice-blue eyes, silver-white hair, and the dark silver bone headpiece. Minimalist dark grey background, 8k."
    },
    {
        "char_id": "char_0026_frost_necromancer",
        "char_name": "霜寒通灵师",
        "img_type": "expression",
        "prompt": "An expression sheet of the Frost Necromancer. Show three facial expressions side-by-side: one cold and calm, one reciting spell with focused lips, and one showing a sad, compassionate gaze. Maintain her silver-white hair and bone headpiece. Plain dark background."
    },
    {
        "char_id": "char_0026_frost_necromancer",
        "char_name": "霜寒通灵师",
        "img_type": "turnaround",
        "prompt": "A professional character turnaround model sheet of the Frost Necromancer. Show three views: front, side, and back, standing neutrally with arms relaxed. She wears the dark grey-and-silver robe. No weapons are held to ensure clean posture. Plain clean light gray studio background, 8k."
    },
    {
        "char_id": "char_0026_frost_necromancer",
        "char_name": "霜寒通灵师",
        "img_type": "outfit",
        "prompt": "An outfit sheet of the Frost Necromancer. Show three outfit designs side-by-side: left, her default dark grey necromancer robe; middle, a simpler grey linen ritual robe; right, an elaborate dark silver-plated bone armor tunic with a long flowing train. Solid light gray background."
    },
    {
        "char_id": "char_0026_frost_necromancer",
        "char_name": "霜寒通灵师",
        "img_type": "prop",
        "prompt": "Prop reference sheet of the Frost Necromancer's gear: her ice staff and floating skull. Show the staff and the skull from multiple angles, highlighting the icy crystals, glowing runes, and blue frost fire. Clean studio background, 8k."
    },
    {
        "char_id": "char_0026_frost_necromancer",
        "char_name": "霜寒通灵师",
        "img_type": "scene",
        "prompt": "Landscape scene concept art of the Icy Tomb. Show ancient stone archways covered in thick white frost, with glowing blue runes on the walls and a central frozen ice pedestal. No characters. Cinematic, masterpiece, 8k."
    },
    {
        "char_id": "char_0026_frost_necromancer",
        "char_name": "霜寒通灵师",
        "img_type": "fullBody",
        "prompt": "Full-body standing art of the Frost Necromancer. She stands on a frosted stone path, holding her glowing ice staff. She wears her dark grey necromancer robe. Clean light gray background, 8k."
    },
    {
        "char_id": "char_0026_frost_necromancer",
        "char_name": "霜寒通灵师",
        "img_type": "cover",
        "prompt": "Epic vertical cover art of the Frost Necromancer. She stands in the center of the frame, raising her glowing staff to summon a swirling frost vortex. Shards of ice float in the air. High contrast cinematic lighting, 8k."
    },
    {
        "char_id": "char_0026_frost_necromancer",
        "char_name": "霜寒通灵师",
        "img_type": "moodboard",
        "prompt": "A moodboard collage of the Frost Necromancer. Four flat panels showing: one of glowing blue ice crystals; one of dark grey textured fabric; one of white bone carvings; and one of a frozen misty tomb. Clean grid layout, no borders, no text."
    },
    {
        "char_id": "char_0026_frost_necromancer",
        "char_name": "霜寒通灵师",
        "img_type": "sketch",
        "prompt": "Monochrome pencil sketch sheet of the Frost Necromancer. Show 3 quick study sketches: reciting spell over the staff; meditating with the skull; and standing calmly in the wind. Clean white studio background."
    },
    {
        "char_id": "char_0026_frost_necromancer",
        "char_name": "霜寒通灵师",
        "img_type": "modelSheet",
        "prompt": "Character model sheet of the Frost Necromancer. Show a detailed full-body front view of her standing in her dark grey robe, holding her signature frost staff. Even lighting, clean light gray background."
    },
    {
        "char_id": "char_0026_frost_necromancer",
        "char_name": "霜寒通灵师",
        "img_type": "poseSheet",
        "prompt": "A pose sheet of the Frost Necromancer showing 5 poses on one sheet: raising her staff to freeze; summoning a bone shield; levitating the skull; walking over ice; and standing battle-worn. Solid dark gray background."
    },
    {
        "char_id": "char_0026_frost_necromancer",
        "char_name": "霜寒通灵师",
        "img_type": "expressionSheet",
        "prompt": "An expression sheet of the Frost Necromancer showing 8 bust portraits in a grid: serene look, chanting with closed eyes, cold glare, slight smile, shock, fatigue, grim look, and intense focus. Clean background."
    },
    {
        "char_id": "char_0026_frost_necromancer",
        "char_name": "霜寒通灵师",
        "img_type": "detailSheet",
        "prompt": "A detail sheet for the Frost Necromancer: close-ups of the bone headpiece, the ice textures on the staff, the runic glow on her sleeve, and her cold ice-blue eyes. Clean light background."
    },
    {
        "char_id": "char_0026_frost_necromancer",
        "char_name": "霜寒通灵师",
        "img_type": "materialPalette",
        "prompt": "A material and color palette sheet. Show swatches of dark grey silk, polished silver bone metal, translucent blue ice, and white bone grain next to a front view of the Frost Necromancer. Plain background."
    },
    {
        "char_id": "char_0026_frost_necromancer",
        "char_name": "霜寒通灵师",
        "img_type": "outfitBreakdown",
        "prompt": "An outfit breakdown sheet showing the layers of the Frost Necromancer's gear: the bone headpiece, the dark grey outer robe, the inner silver dress, the leather belt, and the black shoes. Clean light background."
    },
    {
        "char_id": "char_0026_frost_necromancer",
        "char_name": "霜寒通灵师",
        "img_type": "damageState",
        "prompt": "A damage state sheet showing 3 views: left, default; middle, battle-worn with robe sleeves slightly frayed and minor soot; right, extreme battle-damaged state: standing defiantly next to a cracked and shattered ice throne, her robe's sleeves and hem heavily ripped and shredded, covered in dark ash and scorch marks, and her frost staff cracked with its blue flame dim. Clean dark gray background."
    }
]

sun_knight_plan = [
    {
        "char_id": "char_0027_sun_knight",
        "char_name": "烈阳圣骑士",
        "img_type": "main",
        "prompt": "A masterpiece modern western fantasy concept art of the Sun Knight. A handsome young man with clean golden hair and warm amber eyes, clad in glowing gold-and-steel plate armor with intricate sun reliefs. He holds a massive two-handed greatsword engulfed in bright golden solar flames. A heavy golden shield shaped like a rising sun stands beside him. The background features the grand entrance of a medieval cathedral with golden sunbeams filtering through mist. Cinematic lighting, masterpiece, 8k."
    },
    {
        "char_id": "char_0027_sun_knight",
        "char_name": "烈阳圣骑士",
        "img_type": "portrait",
        "prompt": "Bust portrait of the Sun Knight, face clearly visible. Focus on his golden hair, warm amber eyes, and the golden gorget of his plate armor. He looks heroic and noble. Minimalist light gray background, 8k."
    },
    {
        "char_id": "char_0027_sun_knight",
        "char_name": "烈阳圣骑士",
        "img_type": "expression",
        "prompt": "An expression sheet of the Sun Knight. Show three facial expressions side-by-side: one calm and noble, one shouting in battle, and one displaying a rare, serene and warm smile. Maintain his golden hair. Plain dark background."
    },
    {
        "char_id": "char_0027_sun_knight",
        "char_name": "烈阳圣骑士",
        "img_type": "turnaround",
        "prompt": "A professional character turnaround model sheet of the Sun Knight. Show three views: front, side, and back, standing neutrally with arms relaxed. He wears the gold plate armor and white cape. No weapons are held. Plain clean light gray studio background, 8k."
    },
    {
        "char_id": "char_0027_sun_knight",
        "char_name": "烈阳圣骑士",
        "img_type": "outfit",
        "prompt": "An outfit sheet of the Sun Knight. Show three armor designs side-by-side: left, his default gold-and-steel plate armor; middle, a simpler steel guard tunic; right, an elaborate grand paladin armor with golden phoenix engravings and a long white cloak. Solid light gray background."
    },
    {
        "char_id": "char_0027_sun_knight",
        "char_name": "烈阳圣骑士",
        "img_type": "prop",
        "prompt": "Prop reference sheet of the Sun Knight's gear: his flame greatsword and solar shield. Show them from multiple angles, highlighting the gold reliefs, glowing blade, and metallic textures. Clean studio background, 8k."
    },
    {
        "char_id": "char_0027_sun_knight",
        "char_name": "烈阳圣骑士",
        "img_type": "scene",
        "prompt": "Landscape scene concept art of the Cathedral Entrance (圣光殿堂). Show a grand gothic archway with stained glass windows, and soft golden light filtering down through forest mist. No characters. Cinematic, masterpiece, 8k."
    },
    {
        "char_id": "char_0027_sun_knight",
        "char_name": "烈阳圣骑士",
        "img_type": "fullBody",
        "prompt": "Full-body standing art of the Sun Knight. He stands on stone pavement, holding his greatsword. He wears his gold plate armor and white cape. Clean light gray background, 8k."
    },
    {
        "char_id": "char_0027_sun_knight",
        "char_name": "烈阳圣骑士",
        "img_type": "cover",
        "prompt": "Epic vertical cover art of the Sun Knight. He stands in the center of the frame, raising his greatsword to summon a radiant shield of sunbeams. High contrast cinematic lighting, 8k."
    },
    {
        "char_id": "char_0027_sun_knight",
        "char_name": "烈阳圣骑士",
        "img_type": "moodboard",
        "prompt": "A moodboard collage of the Sun Knight. Four flat panels showing: one of glowing gold sunbeams; one of white velvet fabric; one of polished gold steel; and one of bright solar flames. Clean grid layout."
    },
    {
        "char_id": "char_0027_sun_knight",
        "char_name": "烈阳圣骑士",
        "img_type": "sketch",
        "prompt": "Monochrome pencil sketch sheet of the Sun Knight. Show 3 study sketches: holding his sword upright; holding his shield defensively; and standing calmly. Clean white studio background."
    },
    {
        "char_id": "char_0027_sun_knight",
        "char_name": "烈阳圣骑士",
        "img_type": "modelSheet",
        "prompt": "Character model sheet of the Sun Knight. Show a detailed full-body front view of him standing in his plate armor, holding his sun shield. Even lighting, clean light gray background."
    },
    {
        "char_id": "char_0027_sun_knight",
        "char_name": "烈阳圣骑士",
        "img_type": "poseSheet",
        "prompt": "A pose sheet of the Sun Knight showing 5 poses on one sheet: swinging his greatsword; raising his shield to block; walking forward; saluting; and standing battle-worn. Solid dark gray background."
    },
    {
        "char_id": "char_0027_sun_knight",
        "char_name": "烈阳圣骑士",
        "img_type": "expressionSheet",
        "prompt": "An expression sheet of the Sun Knight showing 8 bust portraits in a grid: heroic smile, battle roar, calm look, warning frown, surprise, fatigue, joyous look, and intense focus. Clean background."
    },
    {
        "char_id": "char_0027_sun_knight",
        "char_name": "烈阳圣骑士",
        "img_type": "detailSheet",
        "prompt": "A detail sheet for the Sun Knight: close-ups of the sun engraving on his armor, the hilt of his sword, his warm amber eyes, and the white cloak weave. Clean light background."
    },
    {
        "char_id": "char_0027_sun_knight",
        "char_name": "烈阳圣骑士",
        "img_type": "materialPalette",
        "prompt": "A material and color palette sheet. Show swatches of gold plate metal, white velvet fabric, amber light, and steel next to a front view of the Sun Knight. Plain background."
    },
    {
        "char_id": "char_0027_sun_knight",
        "char_name": "烈阳圣骑士",
        "img_type": "outfitBreakdown",
        "prompt": "An outfit breakdown sheet showing the layers of the Sun Knight's armor: the pauldrons, breastplate, white cloak, arm guards, and greaves. Clean light background."
    },
    {
        "char_id": "char_0027_sun_knight",
        "char_name": "烈阳圣骑士",
        "img_type": "damageState",
        "prompt": "A damage state sheet showing 3 views: left, default; middle, battle-worn with golden armor scratched and cape frayed with minor ash; right, extreme battle-damaged state: standing defiantly next to a broken stone wall, his golden plate armor fractured and missing pieces, his white cape torn to shreds, and his greatsword chipped with its solar flames dim. Clean dark gray background."
    }
]

cyber_samurai_plan = [
    {
        "char_id": "char_0028_cyber_samurai",
        "char_name": "街头义体武士",
        "img_type": "main",
        "prompt": "A masterpiece modern cyberpunk concept art of the Street Cyber-Samurai. A cool, rebellious young man with a bright pink Mohawk haircut and glowing electric-green cybernetic eyes. He wears a matte-black technical leather jacket with glowing neon green accent strips. His right arm is a detailed mechanical carbon-fiber prosthesis. He holds a high-frequency cybernetic katana radiating glowing orange thermal energy. He stands in a rain-drenched cyberpunk alleyway reflecting vibrant pink, cyan, and violet neon billboard lights. Cinematic, photorealistic, 8k."
    },
    {
        "char_id": "char_0028_cyber_samurai",
        "char_name": "街头义体武士",
        "img_type": "portrait",
        "prompt": "Bust portrait of the Cyber-Samurai, face clearly visible. Focus on his pink Mohawk hair, green cybernetic eye, holographic visor, and high collar leather jacket. Minimalist neon-lit background, 8k."
    },
    {
        "char_id": "char_0028_cyber_samurai",
        "char_name": "街头义体武士",
        "img_type": "expression",
        "prompt": "An expression sheet of the Cyber-Samurai. Show three facial expressions side-by-side: one cool smirk, one battle grit with teeth bared, and one focused, alert look. Maintain his pink hair. Plain dark background."
    },
    {
        "char_id": "char_0028_cyber_samurai",
        "char_name": "街头义体武士",
        "img_type": "turnaround",
        "prompt": "A professional character turnaround model sheet of the Cyber-Samurai. Show three views: front, side, and back, standing neutrally with arms relaxed. He wears the black leather jacket and green cybernetic arm. No weapons held. Plain clean light gray studio background, 8k."
    },
    {
        "char_id": "char_0028_cyber_samurai",
        "char_name": "街头义体武士",
        "img_type": "outfit",
        "prompt": "An outfit sheet of the Cyber-Samurai. Show three outfit designs side-by-side: left, his default black leather jacket and harness; middle, a stealth black skin-tight tech-suit with violet seams; right, high-tech armored street Ronin gears with gold armor plates and a visor. Solid light gray background."
    },
    {
        "char_id": "char_0028_cyber_samurai",
        "char_name": "街头义体武士",
        "img_type": "prop",
        "prompt": "Prop reference sheet of the Cyber-Samurai's gear: his thermal katana and holographic visor. Show them from multiple angles, highlighting the orange glow, circuitry, and metal textures. Clean studio background, 8k."
    },
    {
        "char_id": "char_0028_cyber_samurai",
        "char_name": "街头义体武士",
        "img_type": "scene",
        "prompt": "Landscape scene concept art of the Neon Alleyway (霓虹小巷). Show a rain-slicked city alley with glowing pink, purple, and green advertisements, puddles reflecting lights, and cybernetic wiring along the walls. No characters. Cinematic, masterpiece, 8k."
    },
    {
        "char_id": "char_0028_cyber_samurai",
        "char_name": "街头义体武士",
        "img_type": "fullBody",
        "prompt": "Full-body standing art of the Cyber-Samurai. He stands in a cool street pose, holding his high-frequency orange katana. He wears his black leather jacket and holographic visor. Clean light gray background, 8k."
    },
    {
        "char_id": "char_0028_cyber_samurai",
        "char_name": "街头义体武士",
        "img_type": "cover",
        "prompt": "Epic vertical cover art of the Cyber-Samurai. He stands in the center of the frame, slicing his orange katana down, creating a bright thermal slash in the air. Neon city skyline background. High contrast cinematic lighting, 8k."
    },
    {
        "char_id": "char_0028_cyber_samurai",
        "char_name": "街头义体武士",
        "img_type": "moodboard",
        "prompt": "A moodboard collage of the Cyber-Samurai. Four flat panels showing: one of glowing green neon strips; one of carbon-fiber weave; one of bright orange thermal heat; and one of rain-slicked asphalt reflecting lights. Clean grid layout."
    },
    {
        "char_id": "char_0028_cyber_samurai",
        "char_name": "街头义体武士",
        "img_type": "sketch",
        "prompt": "Monochrome pencil sketch sheet of the Cyber-Samurai. Show 3 study sketches: holding his katana in a dynamic strike; adjusting his visor; and leaning against a neon post. Clean white studio background."
    },
    {
        "char_id": "char_0028_cyber_samurai",
        "char_name": "街头义体武士",
        "img_type": "modelSheet",
        "prompt": "Character model sheet of the Cyber-Samurai. Show a detailed full-body front view of him standing in his leather jacket, holding his signature thermal katana. Even lighting, clean light gray background."
    },
    {
        "char_id": "char_0028_cyber_samurai",
        "char_name": "街头义体武士",
        "img_type": "poseSheet",
        "prompt": "A pose sheet of the Cyber-Samurai showing 5 poses on one sheet: dashing with katana trailing; blocking with a cybernetically-glowing barrier; jumping downward; sheathing his katana; and standing battle-worn. Solid dark gray background."
    },
    {
        "char_id": "char_0028_cyber_samurai",
        "char_name": "街头义体武士",
        "img_type": "expressionSheet",
        "prompt": "An expression sheet of the Cyber-Samurai showing 8 bust portraits in a grid: smirking, shouting in battle, calm look, warning frown, surprise, fatigue, laughing, and intense focus. Clean background."
    },
    {
        "char_id": "char_0028_cyber_samurai",
        "char_name": "街头义体武士",
        "img_type": "detailSheet",
        "prompt": "A detail sheet for the Cyber-Samurai: close-ups of the莫霍克 hair details, the carbon-fiber joints on his arm, the micro-chips on his visor, and his green cybernetic eye. Clean light background."
    },
    {
        "char_id": "char_0028_cyber_samurai",
        "char_name": "街头义体武士",
        "img_type": "materialPalette",
        "prompt": "A material and color palette sheet. Show swatches of black leather, carbon-fiber armor, neon green glow, and orange heat next to a front view of the Cyber-Samurai. Plain background."
    },
    {
        "char_id": "char_0028_cyber_samurai",
        "char_name": "街头义体武士",
        "img_type": "outfitBreakdown",
        "prompt": "An outfit breakdown sheet showing the layers of the Cyber-Samurai's gear: the black technical jacket, the inner stealth shirt, the high-polymer pants, the utility harness, and the high-top boots. Clean light background."
    },
    {
        "char_id": "char_0028_cyber_samurai",
        "char_name": "街头义体武士",
        "img_type": "damageState",
        "prompt": "A damage state sheet showing 3 views: left, default; middle, combat-worn with leather jacket sleeves slightly frayed and minor dust; right, extreme combat-worn state: standing defiantly next to a broken neon billboard, his carbon-fiber forearm armor plating cracked showing glowing circuit lines, his jacket sleeves tattered, and his thermal katana's orange blade cracked and flickering. Clean dark gray background."
    }
]

cyber_corporate_plan = [
    {
        "char_id": "char_0029_cyber_corporate",
        "char_name": "霓虹极道",
        "img_type": "main",
        "prompt": "A masterpiece modern cyberpunk concept art of the Neon Yakuza. A beautiful, high-cold young woman with a straight black bob and cold crimson eyes, wearing a fitted charcoal-gray corporate tech-suit. Luminous purple digital circuit tattoos glow on her neck and cuffs. She channels glowing purple monowire filaments from her wrists, wrapping around the air. A compact submachine gun with a holographic sight is held in her other hand. The background is a luxury glass-walled high-rise office overlooking a vast night skyline of neon skyscrapers. Cinematic, photorealistic, 8k."
    },
    {
        "char_id": "char_0029_cyber_corporate",
        "char_name": "霓虹极道",
        "img_type": "portrait",
        "prompt": "Bust portrait of the Neon Yakuza, face clearly visible. Focus on her straight black bob hair, cold crimson eyes, high-tech suit collar, and purple circuit tattoos on her neck. Minimalist corporate glass background, 8k."
    },
    {
        "char_id": "char_0029_cyber_corporate",
        "char_name": "霓虹极道",
        "img_type": "expression",
        "prompt": "An expression sheet of the Neon Yakuza. Show three facial expressions side-by-side: one cold and expressionless, one with eyes slightly narrowed in warning, and one showing a subtle, dangerous smile. Maintain her black bob hair. Plain dark background."
    },
    {
        "char_id": "char_0029_cyber_corporate",
        "char_name": "霓虹极道",
        "img_type": "turnaround",
        "prompt": "A professional character turnaround model sheet of the Neon Yakuza. Show three views: front, side, and back, standing neutrally with arms relaxed. She wears the charcoal-gray high-tech suit. No weapons held. Plain clean light gray studio background, 8k."
    },
    {
        "char_id": "char_0029_cyber_corporate",
        "char_name": "霓虹极道",
        "img_type": "outfit",
        "prompt": "An outfit sheet of the Neon Yakuza. Show three outfit designs side-by-side: left, her default charcoal-gray corporate tech-suit; middle, a stealthy dark micro-tunic trench coat; right, an elegant purple-trimmed silk kimono dress with integrated cybernetic light lines. Solid light gray background."
    },
    {
        "char_id": "char_0029_cyber_corporate",
        "char_name": "霓虹极道",
        "img_type": "prop",
        "prompt": "Prop reference sheet of the Cyber Corporate Security Officer's gear: her glowing purple digital wrist-worn controller and high-tech communication device. Show them from multiple angles, highlighting the purple circuit lines, holographic projection display, and polished chrome textures. Clean studio background, 8k."
    },
    {
        "char_id": "char_0029_cyber_corporate",
        "char_name": "霓虹极道",
        "img_type": "scene",
        "prompt": "Landscape scene concept art of the Luxury Penthouse Office (公司高层办公室). Show a grand room with minimalist design, dark marble floor, a glass desk, and a giant floor-to-ceiling window overlooking a massive night skyline of a neon city. No characters. Cinematic, masterpiece, 8k."
    },
    {
        "char_id": "char_0029_cyber_corporate",
        "char_name": "霓虹极道",
        "img_type": "fullBody",
        "prompt": "Full-body standing art of the Neon Yakuza. She stands in a calm, lethal pose, holding her submachine gun, with purple monowire filaments extending from her wrist. She wears her charcoal-gray corporate suit. Clean light gray background, 8k."
    },
    {
        "char_id": "char_0029_cyber_corporate",
        "char_name": "霓虹极道",
        "img_type": "cover",
        "prompt": "Epic vertical cover art of the Neon Yakuza. She is shown in a dynamic action pose, whipping her glowing purple monowire in a sweeping arc. Broken glass shards float in the air. High contrast cinematic lighting, 8k."
    },
    {
        "char_id": "char_0029_cyber_corporate",
        "char_name": "霓虹极道",
        "img_type": "moodboard",
        "prompt": "A moodboard collage of the Neon Yakuza. Four flat panels showing: one of glowing purple monowire filaments; one of sleek charcoal-gray suit fabric; one of cold crimson red light; and one of neon skyscrapers seen through glass. Clean grid layout."
    },
    {
        "char_id": "char_0029_cyber_corporate",
        "char_name": "霓虹极道",
        "img_type": "sketch",
        "prompt": "Monochrome pencil sketch sheet of the Neon Yakuza. Show 3 study sketches: whipping the monowire; aiming her submachine gun; and standing calmly in a corporate setting. Clean white studio background."
    },
    {
        "char_id": "char_0029_cyber_corporate",
        "char_name": "霓虹极道",
        "img_type": "modelSheet",
        "prompt": "Character model sheet of the Neon Yakuza. Show a detailed full-body front view of her standing in her corporate suit, holding her monowire whip. Even lighting, clean light gray background."
    },
    {
        "char_id": "char_0029_cyber_corporate",
        "char_name": "霓虹极道",
        "img_type": "poseSheet",
        "prompt": "A pose sheet of the Neon Yakuza showing 5 poses on one sheet: whipping monowire; aiming submachine gun silently; sliding under fire; standing in a defensive stance; and standing battle-worn. Solid dark gray background."
    },
    {
        "char_id": "char_0029_cyber_corporate",
        "char_name": "霓虹极道",
        "img_type": "expressionSheet",
        "prompt": "An expression sheet of the Neon Yakuza showing 8 bust portraits in a grid: cold calm, warning glare, dangerous smile, focused alarm, pain, meditation, slight frown, and intense concentration. Clean background."
    },
    {
        "char_id": "char_0029_cyber_corporate",
        "char_name": "霓虹极道",
        "img_type": "detailSheet",
        "prompt": "A detail sheet for the Neon Corporate Agent: close-ups of her bob haircut, the purple circuit tattoos on her neck, the monowire wrist launcher, and her cold crimson eyes. Clean light background."
    },
    {
        "char_id": "char_0029_cyber_corporate",
        "char_name": "霓虹极道",
        "img_type": "materialPalette",
        "prompt": "A material and color palette sheet. Show swatches of charcoal-gray suit wool, purple neon light, crimson red light, and sleek steel next to a front view of the Neon Corporate Agent. Plain background."
    },
    {
        "char_id": "char_0029_cyber_corporate",
        "char_name": "霓虹极道",
        "img_type": "outfitBreakdown",
        "prompt": "An outfit breakdown sheet showing the layers of the Neon Corporate Agent's gear: the tech-suit jacket, the inner formal blouse, the fitted trousers, the waist holster belt, and high-tech leather shoes. Clean light background."
    },
    {
        "char_id": "char_0029_cyber_corporate",
        "char_name": "霓虹极道",
        "img_type": "damageState",
        "prompt": "A damage state sheet showing 3 views: left, default; middle, combat-worn with suit sleeves frayed and minor dust; right, extreme combat-worn state: standing defiantly next to a cracked glass window, her tech-suit fabric torn and scorched at the hem, her monowire whip broken and sparking purple fire. Clean dark gray background."
    }
]

ancient_druid_plan = [
    {
        "char_id": "char_0025_ancient_druid",
        "char_name": "森之大德鲁伊",
        "img_type": "main",
        "prompt": "A masterpiece modern forest fantasy concept art of the Elven Druid. A beautiful high elf priestess with long flowing platinum hair, wearing an elegant white gown woven with green vines and leaves. She stands barefoot on a glowing emerald sacred spring, holding a twisted wooden staff topped with antlers and a glowing gemstone. Mystical glowing butterflies and deer float around her. The background features giant ancient trees with glowing moss and soft morning light beams filtering through the canopy. High-contrast cinematic lighting, hyper-realistic, 8k."
    },
    {
        "char_id": "char_0025_ancient_druid",
        "char_name": "森之大德鲁伊",
        "img_type": "portrait",
        "prompt": "Bust portrait of the Elven Druid, face clearly visible. Focus on her flowing platinum hair, flower-and-leaf crown, small white antlers, and gentle green eyes. She looks serene and divine. Minimalist light green background, 8k."
    },
    {
        "char_id": "char_0025_ancient_druid",
        "char_name": "森之大德鲁伊",
        "img_type": "expression",
        "prompt": "An expression sheet of the Elven Druid. Show three facial expressions side-by-side: one serene and smiling, one chanting spell with closed eyes, and one showing a sad, compassionate gaze. Maintain her platinum hair and leaf crown. Plain dark background."
    },
    {
        "char_id": "char_0025_ancient_druid",
        "char_name": "森之大德鲁伊",
        "img_type": "turnaround",
        "prompt": "A professional character turnaround model sheet of the Elven Druid. Show three views: front, side, and back, standing neutrally with arms relaxed by her sides. She wears the white-and-green vine gown. No staff or weapons are held to ensure clean posture and anatomical accuracy. Plain clean light gray studio background. Masterpiece, 8k."
    },
    {
        "char_id": "char_0025_ancient_druid",
        "char_name": "森之大德鲁伊",
        "img_type": "outfit",
        "prompt": "An outfit sheet of the Elven Druid. Show three outfit designs side-by-side: left, her default vine white gown; middle, a simpler linen ritual robe; right, an elaborate golden-leaf elder priestess gown with a long flowing train. All designs maintain her platinum hair. Solid light gray background."
    },
    {
        "char_id": "char_0025_ancient_druid",
        "char_name": "森之大德鲁伊",
        "img_type": "prop",
        "prompt": "Prop reference sheet of the Elven Druid's gear: her antler staff and a carved wooden cup filled with sacred spring water. Show the staff and the cup from multiple angles, highlighting the organic bark textures, glowing green gemstone, and floating water ripples. Clean studio background, 8k."
    },
    {
        "char_id": "char_0025_ancient_druid",
        "char_name": "森之大德鲁伊",
        "img_type": "scene",
        "prompt": "Landscape scene concept art of the Sacred Elven Spring (圣泉祭坛). Show a crystal-clear glowing green pool under a giant hollow ancient tree trunk, with soft golden Tyndall light rays filtering down, creating mist and floating light spores. No characters. Cinematic, masterpiece, 8k."
    },
    {
        "char_id": "char_0025_ancient_druid",
        "char_name": "森之大德鲁伊",
        "img_type": "fullBody",
        "prompt": "Full-body standing art of the Elven Druid. She stands barefoot on mossy grass, holding her antler staff. She wears her elegant white vine-woven gown and a leaf crown. Clean light gray background, 8k."
    },
    {
        "char_id": "char_0025_ancient_druid",
        "char_name": "森之大德鲁伊",
        "img_type": "cover",
        "prompt": "Epic vertical cover art of the Elven Druid. She stands in the center of the frame, raising her glowing staff to summon a protective barrier of giant redwood roots. Bioluminescent green energy waves ripple across the ground. High contrast cinematic lighting, 8k."
    },
    {
        "char_id": "char_0025_ancient_druid",
        "char_name": "森之大德鲁伊",
        "img_type": "moodboard",
        "prompt": "A moodboard collage of the Elven Druid. Four flat panels showing: one of glowing green spring water; one of soft white flower petals with dew; one of twisted ancient tree roots; and one of bright green moss with glowing fireflies. Clean grid layout, no borders, no text, plain background."
    },
    {
        "char_id": "char_0025_ancient_druid",
        "char_name": "森之大德鲁伊",
        "img_type": "sketch",
        "prompt": "Monochrome pencil sketch sheet of the Elven Druid. Show 3 quick study sketches: tending to a wounded deer; holding her staff to grow a flower; and kneeling in prayer by the sacred spring. Clean white studio background."
    },
    {
        "char_id": "char_0025_ancient_druid",
        "char_name": "森之大德鲁伊",
        "img_type": "modelSheet",
        "prompt": "Character model sheet of the Elven Druid. Show a detailed full-body front view of her standing in her vine-woven white gown, holding her signature full-sized antler staff (scaled proportionally to her body height). The side of the sheet shows detailed callouts of her staff and green gemstone. Even lighting, clean light gray background."
    },
    {
        "char_id": "char_0025_ancient_druid",
        "char_name": "森之大德鲁伊",
        "img_type": "poseSheet",
        "prompt": "A pose sheet of the Elven Druid showing 5 poses on one sheet: raising her staff to heal; kneeling to touch the moss; whispering to a butterfly; defending with a root barrier; and standing serenely on water. Solid dark gray background."
    },
    {
        "char_id": "char_0025_ancient_druid",
        "char_name": "森之大德鲁伊",
        "img_type": "expressionSheet",
        "prompt": "An expression sheet of the Elven Druid showing 8 bust portraits in a grid: serene smile, chanting with closed eyes, compassionate sadness, surprise, warning frown, fatigue, joyous laughter, and intense focus. Clean background."
    },
    {
        "char_id": "char_0025_ancient_druid",
        "char_name": "森之大德鲁伊",
        "img_type": "detailSheet",
        "prompt": "A detail sheet for the Elven Druid: close-ups of the leaf crown, the antler shape on her staff, the delicate glowing runes on her wrist, and her gentle light-green eyes. Clean light background."
    },
    {
        "char_id": "char_0025_ancient_druid",
        "char_name": "森之大德鲁伊",
        "img_type": "materialPalette",
        "prompt": "A material and color palette sheet. Show swatches of soft white silk, green ivy leaves, rough oak wood, and glowing green emerald crystal next to a front view of the Elven Druid. Plain background."
    },
    {
        "char_id": "char_0025_ancient_druid",
        "char_name": "森之大德鲁伊",
        "img_type": "outfitBreakdown",
        "prompt": "An outfit breakdown sheet showing the layers of the Elven Druid's gear: the ivy leaf crown, the white outer shroud, the inner green linen dress, the woven grass belt, and the bare feet. No staff or weapons are shown on this sheet to focus purely on the clothing layers. Clean light background."
    },
    {
        "char_id": "char_0025_ancient_druid",
        "char_name": "森之大德鲁伊",
        "img_type": "damageState",
        "prompt": "A damage state variant sheet showing 3 views: left, default; middle, battle-worn with gown torn; right, heavily worn with white gown shredded, and her hands wrapped in bandages, with a sad but resolute expression. In all views, she holds her signature full-sized antler staff (scaled proportionally to her body height), which is clean on the left, slightly scratched in the middle, and cracked on the right. Clean dark gray background."
    }
]


dragon_berserker_plan = [
    {
        "char_id": "char_0030_dragon_berserker",
        "char_name": "龙血狂战士",
        "img_type": "main",
        "prompt": "A masterpiece modern western fantasy concept art of the Dragonblood Berserker. A beautiful young woman with refined East Asian facial features, flowing fiery-red hair, and glowing golden dragon slit eyes. Fine dark-red dragon scales adorn her cheeks and arms. She wears custom dark dragon-leather armor with a majestic golden scaled tail. She wields twin axes glowing with molten flame. She stands in a volcanic cavern with slow-flowing lava rivers and floating sparks. Cinematic lighting, masterpiece, 8k."
    },
    {
        "char_id": "char_0030_dragon_berserker",
        "char_name": "龙血狂战士",
        "img_type": "portrait",
        "prompt": "Bust portrait of the Dragonblood Berserker, face clearly visible. Focus on her refined East Asian features, glowing golden dragon eyes, fiery-red hair, and fine red dragon scales on her cheeks. Minimalist dark volcanic cave background, 8k."
    },
    {
        "char_id": "char_0030_dragon_berserker",
        "char_name": "龙血狂战士",
        "img_type": "expression",
        "prompt": "An expression sheet of the Dragonblood Berserker showing three facial expressions side-by-side: one cold and calm, one with a fierce battle expression showing small fangs, and one tired with a proud smile. Maintain her red hair and gold eyes. Plain dark background."
    },
    {
        "char_id": "char_0030_dragon_berserker",
        "char_name": "龙血狂战士",
        "img_type": "turnaround",
        "prompt": "A professional character turnaround model sheet of the Dragonblood Berserker. Show three views: front, side, and back, standing neutrally with arms relaxed. She wears the dark dragon-leather armor. No weapons held. Plain clean light gray studio background, 8k."
    },
    {
        "char_id": "char_0030_dragon_berserker",
        "char_name": "龙血狂战士",
        "img_type": "outfit",
        "prompt": "An outfit sheet of the Dragonblood Berserker. Show three outfit designs side-by-side: left, her default dark dragon-leather armor; middle, a simpler red dragon-nest tunic; right, a ceremonial dragon-scale plate armor with gold ornaments. Solid light gray background."
    },
    {
        "char_id": "char_0030_dragon_berserker",
        "char_name": "龙血狂战士",
        "img_type": "prop",
        "prompt": "Prop reference sheet of the Dragonblood Berserker's gear: her two heavy twin dragon-tooth axes with glowing volcanic lava runes on the blades, and her dragon-scale arm guards. Show them from multiple angles. Clean studio background, 8k."
    },
    {
        "char_id": "char_0030_dragon_berserker",
        "char_name": "龙血狂战士",
        "img_type": "scene",
        "prompt": "Landscape scene concept art of the Volcanic Dragon Lair (巨龙熔岩古道). Show a volcanic cavern with glowing red lava streams, dark volcanic rock pillars, floating embers, and crystal ore deposits. No characters. Cinematic, masterpiece, 8k."
    },
    {
        "char_id": "char_0030_dragon_berserker",
        "char_name": "龙血狂战士",
        "img_type": "fullBody",
        "prompt": "Full-body standing art of the Dragonblood Berserker. She stands in a powerful, ready stance holding her dragon-tooth axes. She wears her dark dragon-leather armor with the gold-scaled tail visible. Clean light gray background, 8k."
    },
    {
        "char_id": "char_0030_dragon_berserker",
        "char_name": "龙血狂战士",
        "img_type": "cover",
        "prompt": "Epic vertical cover art of the Dragonblood Berserker in a dynamic combat pose, swinging her fiery axes in a sweeping arc. Molten rock shards float in the air. High contrast cinematic lighting, 8k."
    },
    {
        "char_id": "char_0030_dragon_berserker",
        "char_name": "龙血狂战士",
        "img_type": "moodboard",
        "prompt": "A moodboard collage of the Dragonblood Berserker. Four flat panels showing: one of flowing red lava; one of black dragon leather fabric; one of glowing amber gold light; and one of volcanic rock crystals. Clean grid layout."
    },
    {
        "char_id": "char_0030_dragon_berserker",
        "char_name": "龙血狂战士",
        "img_type": "sketch",
        "prompt": "Monochrome pencil sketch sheet of the Dragonblood Berserker. Show 3 study sketches: swinging her axes in battle; resting on a volcanic rock; and looking over a lava cliff. Clean white studio background."
    },
    {
        "char_id": "char_0030_dragon_berserker",
        "char_name": "龙血狂战士",
        "img_type": "modelSheet",
        "prompt": "Character model sheet of the Dragonblood Berserker. Show a detailed full-body front view of her standing in her dragon-leather armor, holding one axe. Even lighting, clean light gray background."
    },
    {
        "char_id": "char_0030_dragon_berserker",
        "char_name": "龙血狂战士",
        "img_type": "poseSheet",
        "prompt": "A pose sheet of the Dragonblood Berserker showing 5 poses on one sheet: leaping to strike; defending with crossed axes; standing in a wind-blown pose; crouching to trace a lava flow; and standing battle-worn. Solid dark gray background."
    },
    {
        "char_id": "char_0030_dragon_berserker",
        "char_name": "龙血狂战士",
        "img_type": "expressionSheet",
        "prompt": "An expression sheet of the Dragonblood Berserker showing 8 bust portraits in a grid: cold calm, war shout, proud smile, alarm, battle fatigue, meditation, slight frown, and intense concentration. Clean background."
    },
    {
        "char_id": "char_0030_dragon_berserker",
        "char_name": "龙血狂战士",
        "img_type": "detailSheet",
        "prompt": "A detail sheet for the Dragonblood Berserker: close-ups of her gold dragon eyes, the red dragon scales on her arm, the lava runes on her axe, and her black leather shoulder guards. Clean light background."
    },
    {
        "char_id": "char_0030_dragon_berserker",
        "char_name": "龙血狂战士",
        "img_type": "materialPalette",
        "prompt": "A material and color palette sheet. Show swatches of black dragon-leather, glowing molten lava red, shiny gold scale metal, and dark volcanic rock next to a front view of the Dragonblood Berserker (a beautiful young woman with refined East Asian features, fiery-red hair, and glowing golden dragon slit eyes). Plain background."
    },
    {
        "char_id": "char_0030_dragon_berserker",
        "char_name": "龙血狂战士",
        "img_type": "outfitBreakdown",
        "prompt": "An outfit breakdown sheet showing the layers of the Dragonblood Berserker's gear: the leather breastplate, the inner tunic, the dragon-scale belt, the iron arm bracers, and the dragon-leather boots. Clean light background."
    },
    {
        "char_id": "char_0030_dragon_berserker",
        "char_name": "龙血狂战士",
        "img_type": "damageState",
        "prompt": "A damage state sheet showing 3 views: left, default; middle, combat-worn with leather armor scuffed and hair slightly messy; right, extreme combat-worn state: standing next to a cracked volcanic wall, her dragon-leather armor torn and scorched, her dragon tail scales chipped, and her axes cracked and glowing with weak sparks. Clean dark gray background."
    }
]

brass_alchemist_plan = [
    {
        "char_id": "char_0031_brass_alchemist",
        "char_name": "机械义肢炼金师",
        "img_type": "main",
        "prompt": "A masterpiece modern western fantasy concept art of the Alchemist of Brass. A beautiful young woman with auburn hair in a high ponytail and a single brass monocle over her left eye. Her right arm is a highly detailed, intricate brass mechanical prosthesis venting light steam. She wears a sturdy leather apron with slots for chemical vials. She holds a glowing neon-green potion vial. She stands in a Victorian-style steam lab with copper pipes and boiling retorts. Cinematic lighting, masterpiece, 8k."
    },
    {
        "char_id": "char_0031_brass_alchemist",
        "char_name": "机械义肢炼金师",
        "img_type": "portrait",
        "prompt": "Bust portrait of the Alchemist of Brass, face clearly visible. Focus on her focused expression, single brass monocle, green eye, and auburn ponytail. Minimalist steam laboratory background, 8k."
    },
    {
        "char_id": "char_0031_brass_alchemist",
        "char_name": "机械义肢炼金师",
        "img_type": "expression",
        "prompt": "An expression sheet of the Alchemist of Brass showing three facial expressions side-by-side: one calm and focused, one looking through her lens with a surprised grin, and one tired but satisfied with a smudge of soot on her cheek. Plain dark background."
    },
    {
        "char_id": "char_0031_brass_alchemist",
        "char_name": "机械义肢炼金师",
        "img_type": "turnaround",
        "prompt": "A professional character turnaround model sheet of the Alchemist of Brass. Show three views: front, side, and back, standing neutrally with arms relaxed. She wears the leather apron over a white shirt. No weapons held. Plain clean light gray studio background, 8k."
    },
    {
        "char_id": "char_0031_brass_alchemist",
        "char_name": "机械义肢炼金师",
        "img_type": "outfit",
        "prompt": "An outfit sheet of the Alchemist of Brass. Show three outfit designs side-by-side: left, her default leather work apron; middle, a simpler linen scholar gown; right, a formal academic tunic with intricate brass embroidery and gear-shaped medals. Solid light gray background."
    },
    {
        "char_id": "char_0031_brass_alchemist",
        "char_name": "机械义肢炼金师",
        "img_type": "prop",
        "prompt": "Prop reference sheet of the Alchemist of Brass's gear: her intricate brass mechanical arm showing rotating gear details, and a set of glowing green potion vials. Show them from multiple angles. Clean studio background, 8k."
    },
    {
        "char_id": "char_0031_brass_alchemist",
        "char_name": "机械义肢炼金师",
        "img_type": "scene",
        "prompt": "Landscape scene concept art of the Steampunk Brass Workshop (黄铜工坊). Show a room filled with copper pipes, bubbling glass boilers, pressure gauges, steam valves, and brass gears. No characters. Cinematic, masterpiece, 8k."
    },
    {
        "char_id": "char_0031_brass_alchemist",
        "char_name": "机械义肢炼金师",
        "img_type": "fullBody",
        "prompt": "Full-body standing art of the Alchemist of Brass. She stands in a focused pose holding a potion vial. She wears her leather apron with her brass mechanical arm visible. Clean light gray background, 8k."
    },
    {
        "char_id": "char_0031_brass_alchemist",
        "char_name": "机械义肢炼金师",
        "img_type": "cover",
        "prompt": "Epic vertical cover art of the Alchemist of Brass in a dynamic pose, throwing a potion vial that explodes into colorful glowing steam. High contrast cinematic lighting, 8k."
    },
    {
        "char_id": "char_0031_brass_alchemist",
        "char_name": "机械义肢炼金师",
        "img_type": "moodboard",
        "prompt": "A moodboard collage of the Alchemist of Brass. Four flat panels showing: one of glowing green liquid; one of polished brass gears; one of dark brown work leather; and one of white steam escaping a valve. Clean grid layout."
    },
    {
        "char_id": "char_0031_brass_alchemist",
        "char_name": "机械义肢炼金师",
        "img_type": "sketch",
        "prompt": "Monochrome pencil sketch sheet of the Alchemist of Brass. Show 3 study sketches: adjusting her mechanical arm; pouring a potion carefully; and writing equations on a blackboard. Clean white studio background."
    },
    {
        "char_id": "char_0031_brass_alchemist",
        "char_name": "机械义肢炼金师",
        "img_type": "modelSheet",
        "prompt": "Character model sheet of the Alchemist of Brass. Show a detailed full-body front view of her standing in her apron, showing details of her brass mechanical arm. Even lighting, clean light gray background."
    },
    {
        "char_id": "char_0031_brass_alchemist",
        "char_name": "机械义肢炼金师",
        "img_type": "poseSheet",
        "prompt": "A pose sheet of the Alchemist of Brass showing 5 poses on one sheet: throwing a flask; adjusting her monocle lens; checking a gauge; standing in a defensive pose; and standing battle-worn. Solid dark gray background."
    },
    {
        "char_id": "char_0031_brass_alchemist",
        "char_name": "机械义肢炼金师",
        "img_type": "expressionSheet",
        "prompt": "An expression sheet of the Alchemist of Brass showing 8 bust portraits in a grid: deep focus, surprised grin, satisfied smile, alarm, exhaustion, meditation, slight frown, and intense concentration. Clean background."
    },
    {
        "char_id": "char_0031_brass_alchemist",
        "char_name": "机械义肢炼金师",
        "img_type": "detailSheet",
        "prompt": "A detail sheet for the Alchemist of Brass: close-ups of her brass monocle, the gear mechanism of her elbow joint, the chemical tubes in her apron, and her green eye. Clean light background."
    },
    {
        "char_id": "char_0031_brass_alchemist",
        "char_name": "机械义肢炼金师",
        "img_type": "materialPalette",
        "prompt": "A material and color palette sheet. Show swatches of polished brass, dark leather, glowing green liquid, and white cotton fabric next to a front view of the Alchemist of Brass. Plain background."
    },
    {
        "char_id": "char_0031_brass_alchemist",
        "char_name": "机械义肢炼金师",
        "img_type": "outfitBreakdown",
        "prompt": "An outfit breakdown sheet showing the layers of the Alchemist of Brass's gear: the leather work apron, the inner white shirt, the trousers, the utility belt, and the high-top work boots. Clean light background."
    },
    {
        "char_id": "char_0031_brass_alchemist",
        "char_name": "机械义肢炼金师",
        "img_type": "damageState",
        "prompt": "A damage state sheet showing 3 views: left, default; middle, combat-worn with apron scuffed and minor soot stains; right, extreme combat-worn state: standing next to a broken glass boiler, her leather apron torn, her white shirt sleeves scorched, and her brass mechanical arm showing cracked metal plating and venting white steam. Clean dark gray background."
    }
]


azure_dragon_maiden_plan = [
    {
        "char_id": "char_0032_azure_dragon_maiden",
        "char_name": "青澜龙女",
        "img_type": "main",
        "prompt": "A masterpiece of Eastern fantasy concept art of the Azure Waves Dragon Maiden. A beautiful young Eastern dragon princess with delicate light-cyan dragon horns on her head, and glowing turquoise eyes. She is dressed in an elegant white-and-sky-blue gradient flowing silk robe with long water-sleeves. She holds a glowing cyan dragon pearl in her hands, casting soft light ripples. She stands on a cliff overlooking a mystical churning jade ocean with sea mist and clouds. Cinematic rim light, masterpiece, 8k."
    },
    {
        "char_id": "char_0032_azure_dragon_maiden",
        "char_name": "青澜龙女",
        "img_type": "portrait",
        "prompt": "Bust portrait of the Azure Waves Dragon Maiden, face clearly visible. Focus on her delicate light-cyan dragon horns, glowing turquoise eyes, long wavy blue hair, and gentle princess expression. Soft mist background, 8k."
    },
    {
        "char_id": "char_0032_azure_dragon_maiden",
        "char_name": "青澜龙女",
        "img_type": "expression",
        "prompt": "An expression sheet of the Azure Waves Dragon Maiden showing three facial expressions side-by-side: one calm and gentle, one showing a soft warm smile, and one with a focused determined look. Maintain her blue horns and blue hair. Solid gray background."
    },
    {
        "char_id": "char_0032_azure_dragon_maiden",
        "char_name": "青澜龙女",
        "img_type": "turnaround",
        "prompt": "A professional character turnaround model sheet of the Azure Waves Dragon Maiden. Show three views: front, side, and back, standing neutrally with arms relaxed. She wears the white-and-sky-blue flowing silk robe. Plain light gray studio background, 8k."
    },
    {
        "char_id": "char_0032_azure_dragon_maiden",
        "char_name": "青澜龙女",
        "img_type": "outfit",
        "prompt": "An outfit sheet of the Azure Waves Dragon Maiden. Show three outfits side-by-side: left, her default gradient flowing robe; middle, a formal sea-palace ritual gown with shell embroidery; right, a lightweight dragon-scale leather battle suit. Solid light gray background."
    },
    {
        "char_id": "char_0032_azure_dragon_maiden",
        "char_name": "青澜龙女",
        "img_type": "prop",
        "prompt": "Prop reference sheet of the Azure Waves Dragon Maiden's gear: her glowing cyan dragon pearl, her white jade hair crown, and her flowing silk ribbons. Show them from multiple angles. Clean studio background, 8k."
    },
    {
        "char_id": "char_0032_azure_dragon_maiden",
        "char_name": "青澜龙女",
        "img_type": "scene",
        "prompt": "Landscape scene concept art of the East Sea Dragon Palace (东海龙宫). Show a majestic undersea palace made of coral reefs and glowing pearls, with schools of fish swimming around and light beams filtering from the surface. Cinematic, 8k."
    },
    {
        "char_id": "char_0032_azure_dragon_maiden",
        "char_name": "青澜龙女",
        "img_type": "fullBody",
        "prompt": "Full-body standing art of the Azure Waves Dragon Maiden. She stands elegantly holding her glowing dragon pearl. She wears her white-and-blue gradient flowing robe with her long blue hair blowing in a sea breeze. Plain light gray background, 8k."
    },
    {
        "char_id": "char_0032_azure_dragon_maiden",
        "char_name": "青澜龙女",
        "img_type": "cover",
        "prompt": "Epic vertical cover art of the Azure Waves Dragon Maiden in a dynamic pose, waving her long water-sleeves to summon a giant water dragon rising from a churning sea. High contrast dramatic lighting, 8k."
    },
    {
        "char_id": "char_0032_azure_dragon_maiden",
        "char_name": "青澜龙女",
        "img_type": "moodboard",
        "prompt": "A moodboard collage of the Azure Waves Dragon Maiden. Four flat panels showing: one of sparkling sea waves; one of white silk fabric; one of glowing cyan pearls; and one of ocean corals. Clean grid layout."
    },
    {
        "char_id": "char_0032_azure_dragon_maiden",
        "char_name": "青澜龙女",
        "img_type": "sketch",
        "prompt": "Monochrome pencil sketch sheet of the Azure Waves Dragon Maiden. Show 3 study sketches: meditating under water; floating on waves; and holding her dragon pearl. Clean white studio background."
    },
    {
        "char_id": "char_0032_azure_dragon_maiden",
        "char_name": "青澜龙女",
        "img_type": "modelSheet",
        "prompt": "Character model sheet of the Azure Waves Dragon Maiden. Show a detailed full-body front view of her standing in her default gradient robe, holding her dragon pearl. Clean light gray background."
    },
    {
        "char_id": "char_0032_azure_dragon_maiden",
        "char_name": "青澜龙女",
        "img_type": "poseSheet",
        "prompt": "A pose sheet of the Azure Waves Dragon Maiden showing 5 poses on one sheet: summoning waves; dancing with silk ribbons; floating in water; standing in a wind-blown pose; and looking serene. Solid dark gray background."
    },
    {
        "char_id": "char_0032_azure_dragon_maiden",
        "char_name": "青澜龙女",
        "img_type": "expressionSheet",
        "prompt": "An expression sheet of the Azure Waves Dragon Maiden showing 8 bust portraits in a grid: gentle smile, surprise, serious concentration, laughter, fatigue, meditation, slight frown, and deep focus. Clean background."
    },
    {
        "char_id": "char_0032_azure_dragon_maiden",
        "char_name": "青澜龙女",
        "img_type": "detailSheet",
        "prompt": "A detail sheet for the Azure Waves Dragon Maiden: close-ups of her dragon horns, the glowing water ripples around her dragon pearl, the jade crown in her hair, and the embroidery on her collar. Clean background."
    },
    {
        "char_id": "char_0032_azure_dragon_maiden",
        "char_name": "青澜龙女",
        "img_type": "materialPalette",
        "prompt": "A material and color palette sheet. Show swatches of white silk fabric, turquoise silk fabric, glowing water element light, and polished jade stones next to a front view of the Azure Waves Dragon Maiden. Plain background."
    },
    {
        "char_id": "char_0032_azure_dragon_maiden",
        "char_name": "青澜龙女",
        "img_type": "outfitBreakdown",
        "prompt": "An outfit breakdown sheet showing the layers of the Azure Waves Dragon Maiden's gear: the outer flowing robe, the inner tunic, the jade waist belt, and the soft silk shoes. Clean light background."
    },
    {
        "char_id": "char_0032_azure_dragon_maiden",
        "char_name": "青澜龙女",
        "img_type": "damageState",
        "prompt": "A damage state sheet showing 3 views: left, default; middle, combat-worn with her robe slightly torn and hair messy; right, extreme combat-worn state: standing in front of a cracked ocean coral, her gradient robe torn, her dragon pearl glowing with dim sparks, and minor scuffs on her face. Clean dark gray background."
    }
]

crane_celestial_plan = [
    {
        "char_id": "char_0033_crane_celestial",
        "char_name": "九霄鹤仙人",
        "img_type": "main",
        "prompt": "A masterpiece of Eastern fantasy concept art of the Celestial Crane Ascetic. An elegant young Taoist immortal with long black hair secured by a white jade crown. He wears a flowing white-and-light-blue Taoist robe. He holds a glowing white jade fly-whisk in his left hand, and a majestic red-crowned crane stands beside him. They are standing on a pine-decked stone platform above a vast sea of clouds with mist-shrouded mountain peaks at sunrise. Warm golden lighting, masterpiece, 8k."
    },
    {
        "char_id": "char_0033_crane_celestial",
        "char_name": "九霄鹤仙人",
        "img_type": "portrait",
        "prompt": "Bust portrait of the Celestial Crane Ascetic, face clearly visible. Focus on his refined immortal features, calm black eyes, long black hair secured by a jade crown, and clean white collar. Soft mountain mist background, 8k."
    },
    {
        "char_id": "char_0033_crane_celestial",
        "char_name": "九霄鹤仙人",
        "img_type": "expression",
        "prompt": "An expression sheet of the Celestial Crane Ascetic showing three facial expressions side-by-side: one serene and calm, one with a gentle warm smile, and one showing focused concentration. Maintain his white-and-blue robe and jade crown. Solid gray background."
    },
    {
        "char_id": "char_0033_crane_celestial",
        "char_name": "九霄鹤仙人",
        "img_type": "turnaround",
        "prompt": "A professional character turnaround model sheet of the Celestial Crane Ascetic. Show three views: front, side, and back, standing neutrally with arms relaxed. He wears the white-and-light-blue Taoist robe. No fly-whisk held. Plain light gray studio background, 8k."
    },
    {
        "char_id": "char_0033_crane_celestial",
        "char_name": "九霄鹤仙人",
        "img_type": "outfit",
        "prompt": "An outfit sheet of the Celestial Crane Ascetic. Show three outfits side-by-side: left, his default white-and-blue Taoist robe; middle, a formal crane-embroidered cassock; right, a simpler white cultivation tunic. Solid light gray background."
    },
    {
        "char_id": "char_0033_crane_celestial",
        "char_name": "九霄鹤仙人",
        "img_type": "prop",
        "prompt": "Prop reference sheet of the Celestial Crane Ascetic's gear: his white jade fly-whisk, his jade hairpin, and his ancient bagua compass. Show them from multiple angles. Clean studio background, 8k."
    },
    {
        "char_id": "char_0033_crane_celestial",
        "char_name": "九霄鹤仙人",
        "img_type": "scene",
        "prompt": "Landscape scene concept art of the Qingwei Celestial Mountain (清微仙山). Show high mist-shrouded mountain peaks with ancient pine trees, cloud waterfalls, and a soaring red-crowned crane under a soft morning sun. Cinematic, 8k."
    },
    {
        "char_id": "char_0033_crane_celestial",
        "char_name": "九霄鹤仙人",
        "img_type": "fullBody",
        "prompt": "Full-body standing art of the Celestial Crane Ascetic. He stands calmly holding his white jade fly-whisk, with a majestic red-crowned crane standing beside him on a stone ledge. Plain light gray background, 8k."
    },
    {
        "char_id": "char_0033_crane_celestial",
        "char_name": "九霄鹤仙人",
        "img_type": "cover",
        "prompt": "Epic vertical cover art of the Celestial Crane Ascetic in a dynamic pose, swinging his fly-whisk to summon a giant glowing yin-yang taiji diagram in the sky above a sea of clouds. High contrast dramatic lighting, 8k."
    },
    {
        "char_id": "char_0033_crane_celestial",
        "char_name": "九霄鹤仙人",
        "img_type": "moodboard",
        "prompt": "A moodboard collage of the Celestial Crane Ascetic. Four flat panels showing: one of soft white crane feathers; one of light-blue Taoist silk; one of polished white jade; and one of mist-covered pine needles. Clean grid layout."
    },
    {
        "char_id": "char_0033_crane_celestial",
        "char_name": "九霄鹤仙人",
        "img_type": "sketch",
        "prompt": "Monochrome pencil sketch sheet of the Celestial Crane Ascetic. Show 3 study sketches: meditating under a pine tree; playing go; and riding on the back of a giant crane. Clean white studio background."
    },
    {
        "char_id": "char_0033_crane_celestial",
        "char_name": "九霄鹤仙人",
        "img_type": "modelSheet",
        "prompt": "Character model sheet of the Celestial Crane Ascetic. Show a detailed full-body front view of him standing in his default Taoist robe, holding his fly-whisk. Clean light gray background."
    },
    {
        "char_id": "char_0033_crane_celestial",
        "char_name": "九霄鹤仙人",
        "img_type": "poseSheet",
        "prompt": "A pose sheet of the Celestial Crane Ascetic showing 5 poses on one sheet: swinging his fly-whisk; meditating in mid-air; playing go; standing with hands behind back; and standing in a wind-blown pose. Solid dark gray background."
    },
    {
        "char_id": "char_0033_crane_celestial",
        "char_name": "九霄鹤仙人",
        "img_type": "expressionSheet",
        "prompt": "An expression sheet of the Celestial Crane Ascetic showing 8 bust portraits in a grid: calm peace, gentle smile, deep focus, surprise, fatigue, meditation, slight frown, and intense concentration. Clean background."
    },
    {
        "char_id": "char_0033_crane_celestial",
        "char_name": "九霄鹤仙人",
        "img_type": "detailSheet",
        "prompt": "A detail sheet for the Celestial Crane Ascetic: close-ups of his jade hairpin, the soft fly-whisk bristles, the water-ink crane embroidery on his robe, and his star-like eyes. Clean background."
    },
    {
        "char_id": "char_0033_crane_celestial",
        "char_name": "九霄鹤仙人",
        "img_type": "materialPalette",
        "prompt": "A material and color palette sheet. Show swatches of white cotton fabric, light-blue silk fabric, polished white jade, and weathered dark wood next to a front view of the Celestial Crane Ascetic. Plain background."
    },
    {
        "char_id": "char_0033_crane_celestial",
        "char_name": "九霄鹤仙人",
        "img_type": "outfitBreakdown",
        "prompt": "An outfit breakdown sheet showing the layers of the Celestial Crane Ascetic's gear: the outer Taoist robe, the inner tunic, the jade sash belt, and the black cotton shoes. Clean light background."
    },
    {
        "char_id": "char_0033_crane_celestial",
        "char_name": "九霄鹤仙人",
        "img_type": "damageState",
        "prompt": "A damage state sheet showing 3 views: left, default; middle, combat-worn with his robe slightly dusty and hair a bit loose; right, extreme combat-worn state: standing in front of a shattered stone altar, his Taoist robe torn and scorched, his white fly-whisk broken, and minor scratches on his face. Clean dark gray background."
    }
]


stag_priestess_plan = [
    {
        "char_id": "char_0034_stag_priestess",
        "char_name": "绿誓神鹿祭司",
        "img_type": "main",
        "prompt": "A masterpiece of mystical forest fantasy concept art of the Green-vow Stag Priestess. A beautiful young half-elf priestess with delicate pointed ears and small golden deer horns adorned with tiny glowing leaves. She has long curly light-golden hair woven with small wildflowers and vines. Her eyes are a warm, gentle emerald green. She is dressed in an elegant white-and-mint-green gradient flowing robe with a gold vine belt. She stands in a mystical ancient forest beside a tall, majestic starlight white stag whose horns glow softly. She holds a natural oak branch staff with a glowing green crystal at its tip. Soft sunbeams filter down through giant tree canopies, illuminating glowing leaf particles. Masterpiece, 8k."
    },
    {
        "char_id": "char_0034_stag_priestess",
        "char_name": "绿誓神鹿祭司",
        "img_type": "portrait",
        "prompt": "Bust portrait of the Green-vow Stag Priestess, face clearly visible. Focus on her delicate pointed ears, small golden horns, warm emerald green eyes, and light-golden hair woven with wildflowers. Minimalist soft green forest mist background, 8k."
    },
    {
        "char_id": "char_0034_stag_priestess",
        "char_name": "绿誓神鹿祭司",
        "img_type": "expression",
        "prompt": "An expression sheet of the Green-vow Stag Priestess showing three facial expressions side-by-side: one serene and calm, one with a soft warm smile, and one showing focused determination. Maintain her gold horns and gold hair. Solid gray background."
    },
    {
        "char_id": "char_0034_stag_priestess",
        "char_name": "绿誓神鹿祭司",
        "img_type": "turnaround",
        "prompt": "A professional character turnaround model sheet of the Green-vow Stag Priestess. Show three views: front, side, and back, standing neutrally with arms relaxed. She wears the white-and-mint-green gradient robe. Plain light gray studio background, 8k."
    },
    {
        "char_id": "char_0034_stag_priestess",
        "char_name": "绿誓神鹿祭司",
        "img_type": "outfit",
        "prompt": "An outfit sheet of the Green-vow Stag Priestess. Show three outfits side-by-side: left, her default gradient ceremonial robe; middle, a simpler green linen woodland tunic; right, a formal leaf-patterned golden plate armor for sacred guardian rituals. Solid light gray background."
    },
    {
        "char_id": "char_0034_stag_priestess",
        "char_name": "绿誓神鹿祭司",
        "img_type": "prop",
        "prompt": "Prop reference sheet of the Green-vow Stag Priestess's gear: her natural oak branch staff with a glowing green crystal, her gold vine belt, and her wildflower hair ornaments. Show them from multiple angles. Clean studio background, 8k."
    },
    {
        "char_id": "char_0034_stag_priestess",
        "char_name": "绿誓神鹿祭司",
        "img_type": "scene",
        "prompt": "Landscape scene concept art of the Green-vow Sacred Grove (绿誓圣所). Show a clearing in a giant ancient forest with sunbeams filtering down, a crystal-clear spring pool, glowing forest flowers, and ancient mossy stone pillars. No characters. Cinematic, 8k."
    },
    {
        "char_id": "char_0034_stag_priestess",
        "char_name": "绿誓神鹿祭司",
        "img_type": "fullBody",
        "prompt": "Full-body standing art of the Green-vow Stag Priestess. She stands elegantly holding her oak staff, with a majestic white stag standing beside her on a mossy ledge. Plain light gray background, 8k."
    },
    {
        "char_id": "char_0034_stag_priestess",
        "char_name": "绿誓神鹿祭司",
        "img_type": "cover",
        "prompt": "Epic vertical cover art of the Green-vow Stag Priestess in a dynamic pose, raising her glowing staff to summon a protective barrier of giant glowing green leaves and vine roots around her. High contrast dramatic lighting, 8k."
    },
    {
        "char_id": "char_0034_stag_priestess",
        "char_name": "绿誓神鹿祭司",
        "img_type": "moodboard",
        "prompt": "A moodboard collage of the Green-vow Stag Priestess. Four flat panels showing: one of glowing mint-green moss; one of white linen fabric; one of polished gold tree leaves; and one of rough ancient oak bark. Clean grid layout."
    },
    {
        "char_id": "char_0034_stag_priestess",
        "char_name": "绿誓神鹿祭司",
        "img_type": "sketch",
        "prompt": "Monochrome pencil sketch sheet of the Green-vow Stag Priestess. Show 3 study sketches: meditating on a mossy rock; healing a small forest bird; and riding her starlight white stag. Clean white studio background."
    },
    {
        "char_id": "char_0034_stag_priestess",
        "char_name": "绿誓神鹿祭司",
        "img_type": "modelSheet",
        "prompt": "Character model sheet of the Green-vow Stag Priestess. Show a detailed full-body front view of her standing in her default gradient robe, holding her oak staff. Clean light gray background."
    },
    {
        "char_id": "char_0034_stag_priestess",
        "char_name": "绿誓神鹿祭司",
        "img_type": "poseSheet",
        "prompt": "A pose sheet of the Green-vow Stag Priestess showing 5 poses on one sheet: casting a healing spell; whispering to her stag; walking gracefully; kneeling to touch a sprout; and standing in a wind-blown pose. Solid dark gray background."
    },
    {
        "char_id": "char_0034_stag_priestess",
        "char_name": "绿誓神鹿祭司",
        "img_type": "expressionSheet",
        "prompt": "An expression sheet of the Green-vow Stag Priestess showing 8 bust portraits in a grid: gentle smile, surprised delight, serious focus, warm laughter, fatigue, meditation, slight frown, and intense concentration. Clean background."
    },
    {
        "char_id": "char_0034_stag_priestess",
        "char_name": "绿誓神鹿祭司",
        "img_type": "detailSheet",
        "prompt": "A detail sheet for the Green-vow Stag Priestess: close-ups of her gold deer horns with glowing leaves, the jade crystal on her staff tip, her pointed elf ear, and the vine belt embroidery. Clean background."
    },
    {
        "char_id": "char_0034_stag_priestess",
        "char_name": "绿誓神鹿祭司",
        "img_type": "materialPalette",
        "prompt": "A material and color palette sheet. Show swatches of white cotton fabric, mint-green silk fabric, glowing emerald light, and natural oak wood next to a front view of the Green-vow Stag Priestess. Plain background."
    },
    {
        "char_id": "char_0034_stag_priestess",
        "char_name": "绿誓神鹿祭司",
        "img_type": "outfitBreakdown",
        "prompt": "An outfit breakdown sheet showing the layers of the Green-vow Stag Priestess's gear: the outer gradient robe, the inner leaf-pattern tunic, the gold vine sash, and the soft leather sandals. Clean light background."
    },
    {
        "char_id": "char_0034_stag_priestess",
        "char_name": "绿誓神鹿祭司",
        "img_type": "damageState",
        "prompt": "A damage state sheet showing 3 views: left, default; middle, combat-worn with her robe slightly torn and hair messy; right, extreme combat-worn state: standing in front of a scorched tree stump, her green robe torn and dirty, her oak staff cracked with dim green light, and minor scratches on her cheek. Clean dark gray background."
    }
]

nine_tailed_fox_plan = [
    {
        "char_id": "char_0035_nine_tailed_fox",
        "char_name": "九尾赤狐",
        "img_type": "main",
        "prompt": "A masterpiece of Eastern fantasy concept art of the Nine-tailed Scarlet Fox. A beautiful and enchanting young fox lady with fluffy red fox ears and nine majestic scarlet tails unfolding like a fan. She has long flowing black hair styled with golden hairpins. Her eyes are a captivating bright gold with slit pupils. She is dressed in an elegant off-shoulder red-and-black ancient Chinese flowing robe with a gold vine belt. She stands on a crimson stone bridge at night under a full moon, holding a glowing red-lotus lantern that emits warm orange-red light. Scattered autumn red maple leaves drift in the gentle breeze around her, with traditional dark tiled Chinese roofs in the foggy background. Masterpiece, 8k."
    },
    {
        "char_id": "char_0035_nine_tailed_fox",
        "char_name": "九尾赤狐",
        "img_type": "portrait",
        "prompt": "Bust portrait of the Nine-tailed Scarlet Fox, face clearly visible. Focus on her enchanting face, bright gold eyes with slit pupils, and fluffy red fox ears. Her black hair is pinned with a delicate gold hairpin. Solid dark gray studio background with a hint of warm red backlight, 8k."
    },
    {
        "char_id": "char_0035_nine_tailed_fox",
        "char_name": "九尾赤狐",
        "img_type": "expression",
        "prompt": "An expression sheet of the Nine-tailed Scarlet Fox showing three facial expressions side-by-side: left, a mysterious gentle smile; middle, an angry glare with faint red aura; right, a curious head-tilt with a playful wink. Keep her fox ears and gold hairpins consistent. Solid light gray background."
    },
    {
        "char_id": "char_0035_nine_tailed_fox",
        "char_name": "九尾赤狐",
        "img_type": "turnaround",
        "prompt": "A professional character turnaround model sheet of the Nine-tailed Scarlet Fox. Show three views: front, side, and back, standing neutrally with arms relaxed. She wears the red-and-black ceremonial ancient robe, and her nine red tails are visible. Plain light gray studio background, 8k."
    },
    {
        "char_id": "char_0035_nine_tailed_fox",
        "char_name": "九尾赤狐",
        "img_type": "outfit",
        "prompt": "An outfit reference sheet of the Nine-tailed Scarlet Fox. Show three outfits side-by-side: left, her default red-and-black wide-sleeve robe; middle, a simpler dark red linen traveling tunic; right, a formal gold-embroidered battle robe with scale armor plates. Solid light gray background."
    },
    {
        "char_id": "char_0035_nine_tailed_fox",
        "char_name": "九尾赤狐",
        "img_type": "prop",
        "prompt": "Prop reference sheet of the Nine-tailed Scarlet Fox's gear: her red-lotus (red lotus fox-fire lantern), her gold hairpins with crimson silk tassels, and her jade-tasseled black belt. Show them from multiple angles. Clean studio background, 8k."
    },
    {
        "char_id": "char_0035_nine_tailed_fox",
        "char_name": "九尾赤狐",
        "img_type": "scene",
        "prompt": "Landscape scene concept art of the Tushan Secret Sanctuary (涂山秘境). Show a mystical valley under a starry night sky with a huge glowing ancient peach tree in full pink blossom, floating red-lotus lanterns drifting down a sparkling river, and mist-shrouded traditional pavilions. No characters. Cinematic, 8k."
    },
    {
        "char_id": "char_0035_nine_tailed_fox",
        "char_name": "九尾赤狐",
        "img_type": "fullBody",
        "prompt": "Full-body standing art of the Nine-tailed Scarlet Fox. She stands elegantly holding her red-lotus lantern, with her nine red tails fanned out majestically behind her. Plain light gray background, 8k."
    },
    {
        "char_id": "char_0035_nine_tailed_fox",
        "char_name": "九尾赤狐",
        "img_type": "cover",
        "prompt": "Epic vertical cover art of the Nine-tailed Scarlet Fox in a dynamic pose, raising her hands to summon a giant swirling vortex of crimson fox-fire and flying red maple leaves. High contrast dramatic theatrical lighting, 8k."
    },
    {
        "char_id": "char_0035_nine_tailed_fox",
        "char_name": "九尾赤狐",
        "img_type": "moodboard",
        "prompt": "A moodboard collage of the Nine-tailed Scarlet Fox's aesthetic. Four flat panels showing: one of glowing red-lotus fox-fire; one of fine black silk fabric with gold dragon embroidery; one of falling autumn red maple leaves; and one of smooth black river pebbles. Clean grid layout."
    },
    {
        "char_id": "char_0035_nine_tailed_fox",
        "char_name": "九尾赤狐",
        "img_type": "sketch",
        "prompt": "Monochrome pencil sketch sheet of the Nine-tailed Scarlet Fox. Show 3 study sketches: meditating under a peach blossom tree; releasing a small fox-fire spark; and sitting gracefully on a stone wall. Clean white studio background."
    },
    {
        "char_id": "char_0035_nine_tailed_fox",
        "char_name": "九尾赤狐",
        "img_type": "modelSheet",
        "prompt": "Character model sheet of the Nine-tailed Scarlet Fox. Show a detailed full-body front view of her standing in her default red-and-black robe, holding her lotus lantern. Clean light gray background."
    },
    {
        "char_id": "char_0035_nine_tailed_fox",
        "char_name": "九尾赤狐",
        "img_type": "poseSheet",
        "prompt": "A pose sheet of the Nine-tailed Scarlet Fox showing 5 poses on one sheet: floating gracefully; conjuring a spell; walking with a sly smile; kneeling to offer the lantern; and standing in a dynamic wind-blown combat pose. Solid dark gray background."
    },
    {
        "char_id": "char_0035_nine_tailed_fox",
        "char_name": "九尾赤狐",
        "img_type": "expressionSheet",
        "prompt": "An expression sheet of the Nine-tailed Scarlet Fox showing 8 bust portraits in a grid: confident smirk, shocked anger, playful wink, calm focus, cold glare, joyful smile, absolute sorrow, and mysterious fatigue. Clean background."
    },
    {
        "char_id": "char_0035_nine_tailed_fox",
        "char_name": "九尾赤狐",
        "img_type": "detailSheet",
        "prompt": "A detail sheet for the Nine-tailed Scarlet Fox: close-ups of her gold-inlaid red-lotus lantern, her fluffy red fox ears, her glowing gold eye, and the gold-threaded embroidery on her black sash. Clean background."
    },
    {
        "char_id": "char_0035_nine_tailed_fox",
        "char_name": "九尾赤狐",
        "img_type": "materialPalette",
        "prompt": "A material and color palette sheet next to a front view of the Nine-tailed Scarlet Fox. Show swatches of crimson silk, dark gold metal, black brocade with gold threads, and a glowing red fox-fire particle. Plain background."
    },
    {
        "char_id": "char_0035_nine_tailed_fox",
        "char_name": "九尾赤狐",
        "img_type": "outfitBreakdown",
        "prompt": "An outfit breakdown sheet showing the layers of the Nine-tailed Scarlet Fox's gear: the outer red wide-sleeved coat, the inner black wrap dress, the black-and-gold sash, and the black leather shoes. Clean light background."
    },
    {
        "char_id": "char_0035_nine_tailed_fox",
        "char_name": "九尾赤狐",
        "img_type": "damageState",
        "prompt": "A damage state sheet showing 3 views of the Nine-tailed Scarlet Fox: left, default; middle, combat-worn: her sleeve slightly torn, hair messy, and a scratch on her shoulder; right, extreme combat-worn: standing in front of a ruined stone archway, her red-and-black dress heavily torn and soiled with ash, her tails singed and dusty, her lantern broken but holding a flickering red fire in her bare hand. Clean dark gray background."
    }
]

red_umbrella_plan = [
    {
        "char_id": "char_0036_red_umbrella_entity",
        "char_name": "红伞执念体",
        "img_type": "main",
        "prompt": "A masterpiece cinematic concept art of the Red Umbrella Entity. A beautiful slender young East Asian woman with delicate handsome facial features and long, flowing pitch-black hair cascading to her waist. She wears an elegant vintage dark crimson silk dress with subtle glowing spider lily patterns embroidered on the hem. She stands on a wet, rain-slicked street in a modern metropolis under a dark rainy night. In one hand, she holds a highly detailed, glowing red oil-paper umbrella that casts a warm, soft scarlet radiance onto her serene face and slightly translucent ethereal figure. The background features towering skyscrapers with vibrant blue and cyan neon advertisements reflecting beautifully on the wet asphalt and puddles. Delicate rain drops shimmer in the air, creating a rich Tyndall lighting effect. Photorealistic textures, octane render, 8k resolution."
    }
]

stele_pathfinder_plan = [
    {
        "char_id": "char_0037_stele_pathfinder",
        "char_name": "残碑拓荒人",
        "img_type": "main",
        "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Stele Rubbing Pathfinder (残碑拓荒人)
Gender / age impression: young man, handsome, scholarly and calm presence
Body shape: slender, tall, graceful scholarly posture
Face: handsome refined features, focused expression, smudged with ink stains
Hair: silver-and-black hair tied up in a simple wooden hairpin
Eyes: focused dark eyes
Outfit: simple gray-and-white scholar robe smudged with ink stains, carrying a rustic leather scroll-case on his back
Accessories / weapon: giant iron calligraphy brush as tall as himself dripping with glowing black ink, and a leather scroll-case
Color palette: ink black, scholar robe white, iron grey, crumbling stone beige, sky grey
Fixed traits that must never change: silver-and-black hair in wooden hairpin, gray-and-white robe, giant iron calligraphy brush, leather scroll-case

Current asset goal:
Generate a main visual key art image. Focus on strong first impression, world mood, signature outfit, weapon, and emotional identity.

Style:
Eastern fantasy character concept art, cinematic fantasy concept art, 3D octane render, photorealistic 3D character reference design, hyper-detailed material textures, cinematic lighting, high-fidelity production-ready asset.

Composition:
Cinematic action pose. The scholar is dynamically waving his giant iron calligraphy brush in a sweeping motion, releasing a beautiful arc of flowing wet black calligraphy ink across the air. He is looking ahead with a focused, sharp gaze. Full-body or three-quarter character view, cinematic but readable, the character is the clear focal point.

Background:
An atmospheric desolate ancient ruined field of massive wind-eroded crumbling stone steles and monuments. Sun rays pierce through heavy overcast clouds, casting a majestic and historic lighting onto the desolate landscape.

Constraints:
Keep the same face, hairstyle, outfit logic, color palette, body shape, and signature accessories.
Do not redesign the character.
No text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."""
    },
    {
        "char_id": "char_0037_stele_pathfinder",
        "char_name": "残碑拓荒人",
        "img_type": "cover",
        "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Stele Rubbing Pathfinder (残碑拓荒人)
Gender / age impression: young man, handsome, scholarly and calm presence
Body shape: slender, tall, graceful scholarly posture
Face: handsome refined features, focused expression, smudged with ink stains
Hair: silver-and-black hair tied up in a simple wooden hairpin
Eyes: focused dark eyes
Outfit: simple gray-and-white scholar robe smudged with ink stains, carrying a rustic leather scroll-case on his back
Accessories / weapon: giant iron calligraphy brush as tall as himself dripping with glowing black ink, and a leather scroll-case
Color palette: ink black, scholar robe white, iron grey, crumbling stone beige, sky grey
Fixed traits that must never change: silver-and-black hair in wooden hairpin, gray-and-white robe, giant iron calligraphy brush, leather scroll-case

Current asset goal:
Generate a cover image. Focus on iconic character presence in a dynamic pose, high emotional hook, dramatic lighting, and vertical composition suitable for a card banner or cover poster.

Style:
Eastern fantasy character concept art, cinematic promotional key art, 3D octane render, photorealistic 3D character reference design, hyper-detailed material textures, cinematic lighting, high-fidelity production-ready asset.

Composition:
Strong vertical cover framing. The scholar is captured in a dynamic action pose in the center of the frame, drawing massive floating calligraphy characters in mid-air with his giant calligraphy brush. Flowing ink particles and glowing dust swirl around him. High contrast cinematic lighting, highly detailed, 8k.

Background:
Desolate ancient ruined field under a dramatic stormy sky, matching the world mood.

Constraints:
Keep the same face, hairstyle, outfit logic, color palette, body shape, and signature accessories.
Do not redesign the character.
No text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."""
    },
    {
        "char_id": "char_0037_stele_pathfinder",
        "char_name": "残碑拓荒人",
        "img_type": "outfit",
        "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Stele Rubbing Pathfinder (残碑拓荒人)
Gender / age impression: young man, handsome, scholarly and calm presence
Body shape: slender, tall, graceful scholarly posture
Face: handsome refined features, focused expression, smudged with ink stains
Hair: silver-and-black hair tied up in a simple wooden hairpin
Eyes: focused dark eyes
Outfit: simple gray-and-white scholar robe smudged with ink stains, carrying a rustic leather scroll-case on his back
Accessories / weapon: giant iron calligraphy brush as tall as himself dripping with glowing black ink, and a leather scroll-case
Color palette: ink black, scholar robe white, iron grey, crumbling stone beige, sky grey
Fixed traits that must never change: silver-and-black hair in wooden hairpin, gray-and-white robe, giant iron calligraphy brush, leather scroll-case

Current asset goal:
Generate an outfit variant reference sheet. Focus on showing three very different outfits side-by-side while preserving the same face and hairstyle.

Style:
Eastern fantasy character concept art, high-fidelity design sheet, detailed fabric material rendering, coherent design language, consistent facial identity, production-ready asset.

Composition:
Show three different outfits side-by-side of the exact same character standing neutrally:
1. On the left: His default outfit (simple gray-and-white scholar robe smudged with black ink stains, leather scroll-case on back).
2. In the middle: His martial scouting outfit (fitted black martial artist robe with leather arm guards, carrying his giant brush on his back).
3. On the right: His pristine court scholar gown (a high-status pure white and silver silk robe with fine crane embroidery, completely clean without any ink stains).
Keep the character's face, silver-and-black hair, and body proportions identical across all three views.

Background:
Plain clean dark gray background.

Constraints:
Keep the same face, hairstyle, outfit logic, color palette, body shape, and signature accessories.
Do not redesign the character.
No text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."""
    },
    {
        "char_id": "char_0037_stele_pathfinder",
        "char_name": "残碑拓荒人",
        "img_type": "detailSheet",
        "prompt": """Use case: stylized-concept
Asset type: character asset for a reusable character pool

Primary request:
Create a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.

Character lock:
Name: The Stele Rubbing Pathfinder (残碑拓荒人)
Gender / age impression: young man, handsome, scholarly and calm presence
Body shape: slender, tall, graceful scholarly posture
Face: handsome refined features, focused expression, smudged with ink stains
Hair: silver-and-black hair tied up in a simple wooden hairpin
Eyes: focused dark eyes
Outfit: simple gray-and-white scholar robe smudged with ink stains, carrying a rustic leather scroll-case on his back
Accessories / weapon: giant iron calligraphy brush as tall as himself dripping with glowing black ink, and a leather scroll-case
Color palette: ink black, scholar robe white, iron grey, crumbling stone beige, sky grey
Fixed traits that must never change: silver-and-black hair in wooden hairpin, gray-and-white robe, giant iron calligraphy brush, leather scroll-case

Current asset goal:
Generate a fully colored detail sheet / close-up reference. Focus on close-up panels of the character's features: colored hair details, colored face close-up, colored costume embroidery, and realistic signature prop texture.

Style:
Eastern fantasy character concept art, 3D octane render, photorealistic 3D character reference design, hyper-detailed material textures, cinematic lighting, high-fidelity production-ready asset.

Composition:
Close-up panels arranged neatly on a plain background. All panels must be fully colored, rendered, and detailed.

Background:
Clean light gray background.

Constraints:
Keep the same face, hairstyle, outfit logic, color palette, body shape, and signature accessories.
Do not redesign the character.
All panels must be fully colored and rendered. Avoid line art, monochrome sketches, outline drawings, and black and white diagrams.
No text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."""
    }
]

fungal_apothecary_plan = [
    {
        "char_id": "char_0040_fungal_apothecary",
        "char_name": "蕈林秘医",
        "img_type": "main",
        "prompt": "A masterpiece cinematic concept art of the Fungal Grove Apothecary. A beautiful young elf woman with translucent pale skin and glowing mint-green eyes. She wears an elegant dark-green herbalist robe woven with moss and vines, and a unique hood shaped like a giant glowing, semi-translucent purple mushroom cap. She stands in a mystical dark cave filled with massive glowing bioluminescent mushrooms and drifting cyan spores. In her hands, she carefully holds a wooden mortar and pestle, grinding a luminous purple fungus that emits a soft mist. A leather bandoleer across her shoulder holds several glowing glass flasks filled with colorful spores. Ethereal forest lighting, highly detailed textures of bark, moss, and glowing gills, octane render, 8k resolution."
    }
]

book_wraith_plan = [
    {
        "char_id": "char_0041_book_wraith",
        "char_name": "禁忌书魂",
        "img_type": "main",
        "prompt": "A breathtaking epic fantasy concept art of the Bound Book-Wraith. An ethereal, semi-translucent spectral figure floating in the air of a massive, cavernous ancient library vault. The figure wears tattered, dusty dark archivist robes with a deep hood obscuring its face, showing only two glowing golden eyes. Swirling in a chaotic vortex around its body are hundreds of floating, aged parchment book pages inscribed with glowing gold and blue runes and ink calligraphy. The library background features towering dark wooden bookshelves stretching into the shadows, with dust motes catching shaft of magical light from high stained-glass windows. Octane render, cinematic fantasy illustration, 8k."
    }
]

radio_host_plan = [
    {
        "char_id": "char_0042_radio_host",
        "char_name": "午夜电台主播",
        "img_type": "main",
        "prompt": "A masterpiece cinematic concept art of the Midnight Radio Host. A young woman in oversized futuristic streetwear and a black windbreaker. Her head is replaced by a vintage retro cassette tape-player helmet with spinning reels glowing with radioactive neon green and hot pink light inside. She sits in a cozy, dimly lit radio booth surrounded by vinyl records, glowing audio mixers, and dark soundproofing foam. In her right hand, she holds a heavy vintage silver condenser microphone, and in her left, a glowing neon-pink cassette tape. Outside the window, a dark moody city is shrouded in misty blue and warm amber neon glows. Atmospheric fog, Octane render, highly detailed, 8k resolution."
    }
]

blade_wraith_plan = [
    {
        "char_id": "char_0043_blade_wraith",
        "char_name": "噬魂刀魅",
        "img_type": "main",
        "prompt": "A masterpiece concept art of the Soul-Devouring Blade-Wraith. A terrifying Eastern fantasy monster. A shattered ancient bronze curved saber floats in the air, its blade covered in dark rust and glowing crimson veins of light. Behind the saber, a tall, shadowy phantom of a general in dilapidated black iron armor emerges from the hilt, with two chilling green flames glowing inside its helmet as eyes. Swirling around the saber are torn white talisman paper bands with gold scriptures. The background is a devastated ancient battlefield under a blood-red sunset, with broken weapons scattered on the ground. Epic dramatic lighting, highly detailed ink-wash fantasy style, 8k resolution."
    }
]

abyssal_dread_plan = [
    {
        "char_id": "char_0044_abyssal_dread",
        "char_name": "深渊煞魔",
        "img_type": "main",
        "prompt": "A masterpiece concept art of the Abyssal Dread-Fiend. A terrifying Eastern fantasy monster. It has no physical face; instead, its head is a floating, burning sphere of dark purple and black malice flames with two glowing red eyes shining from within. Its body is composed of jagged black bone plates and sharp basalt claws, wrapped in broken golden sealing chains with faint glowing runes. It stands on the ruins of a broken ancient Great Wall with withered vines under a pale moonlight, dark fog swirling around. High contrast dramatic lighting, cinematic framing, highly detailed ink-wash fantasy style, 8k resolution."
    }
]

thousand_faces_plan = [
    {
        "char_id": "char_0045_thousand_faces",
        "char_name": "千面皮魔",
        "img_type": "main",
        "prompt": "A masterpiece fantasy concept art of the Thousand-Faced Skin-Wraith. A terrifying and artistic Eastern fantasy monster. An ethereal, faceless female figure in layered, tattered semi-translucent white hemp robes floats in the air. Her face is a horrifying patchwork of stitched human face skins, sewn together with delicate silver thread. Behind her, a massive, worn ancient Chinese silk scroll unrolls horizontally, filled with ink-wash paintings of screaming human faces and rising black mist. In her right hand, she holds a long, slender bone needle threaded with glowing silver thread. The background is a desolate ruins of a bamboo forest under a dark red sky, with paper talismans and autumn leaves scattering in the wind. High contrast atmospheric lighting, highly detailed ink-wash fantasy style, 8k resolution."
    }
]

bone_spider_plan = [
    {
        "char_id": "char_0046_bone_spider",
        "char_name": "蚀骨蛛后",
        "img_type": "main",
        "prompt": "An epic dark fantasy concept art of the Bone-Corroding Broodmother. A colossal spider monster. Its body is made of cracked, glossy black obsidian shell, with a distinct white human skull pattern on its back. Dozens of glowing green eyes line its head. Its bulbous translucent dark-green abdomen glows faintly, showing silhouettes of squirming eggs inside. It crawls on a massive spiderweb woven from thick sticky silk and bones. The background is a dark cavern under the ruins of an ancient great wall, with faint glowing green mineral veins and poisonous purple fog. Cinematic rim lighting, hyper-realistic textures of stone and chitin shell, ink-wash style blend, 8k."
    }
]

bone_pipa_wraith_plan = [
    {
        "char_id": "char_0047_bone_pipa_wraith",
        "char_name": "骨琶怨姬",
        "img_type": "main",
        "prompt": "An epic dark fantasy concept art of the Bone-Pipa Wraith. A beautiful but cold-faced blindfolded young female musician with long flowing white hair, wearing an elegant flowy dark-purple and ink-black traditional Chinese silk robe, with a white translucent silk ribbon covering her eyes. She holds an ivory bone pipa with glowing purple strings, releasing soundwave ripples. The scene is a ruined traditional Chinese stone pavilion under a large dark red moon at night, surrounded by withered red spider lily flowers and floating purple embers. Cinematic rim lighting, hyper-realistic textures, ink-wash style blend, 8k."
    }
]

withered_daoist_plan = [
    {
        "char_id": "char_0048_withered_daoist",
        "char_name": "枯木妖道",
        "img_type": "main",
        "prompt": "An epic dark fantasy concept art of the Withered Wood Daoist. An eerie, thin ancient Chinese Daoist priest wearing tattered and burnt dark purple robes, his face hidden behind a sinister wooden mask carved from lightning-struck wood with only one glowing purple eye visible. He holds a decaying dark peach-wood sword dripping with thick black corrosion fluid, surrounded by dozens of floating black paper talismans with glowing purple scriptures. The setting is a scorched and dead withered forest under dark thunderclouds, with purple lightning flashing in the heavy mist and broken swords scattered on the ground. Cinematic rim lighting, hyper-realistic textures, ink-wash style blend, 8k."
    }
]

if __name__ == "__main__":
    main()

