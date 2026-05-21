"""
PartSelect deep scraper using Playwright non-headless (bypasses Akamai).
Collects parts from category pages + individual part detail pages + repair guides.

Run: python -m app.data.scraper
"""
import asyncio
import json
import re
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, BrowserContext, Page

BASE_URL = "https://www.partselect.com"
OUTPUT_DIR = Path(__file__).parent / "raw"

REPAIR_PAGES = [
    ("refrigerator", f"{BASE_URL}/Repair/Refrigerator/"),
    ("dishwasher",   f"{BASE_URL}/Repair/Dishwasher/"),
]

# Max repair guide detail pages per category
MAX_GUIDES_PER_CATEGORY = 40

# Curated seed URLs — high-traffic parts covering the questions the agent must answer.
# Category listing pages always return the same 10 featured parts regardless of pagination,
# so we seed directly from known part URLs instead.
SEED_PART_URLS: list[tuple[str, str]] = [
    # ── REFRIGERATOR — Ice maker & water system ───────────────────────────────
    ("refrigerator", "https://www.partselect.com/PS11765620-Whirlpool-W10884390-Refrigerator-Ice-Maker-Assembly.htm"),
    ("refrigerator", "https://www.partselect.com/PS11738120-Whirlpool-W10873791-Refrigerator-Ice-Maker.htm"),
    ("refrigerator", "https://www.partselect.com/PS12364147-Frigidaire-241798231-Refrigerator-Ice-Maker-Assembly.htm"),
    ("refrigerator", "https://www.partselect.com/PS12115595-Samsung-DA97-15217D-Ice-Maker-Assembly.htm"),
    ("refrigerator", "https://www.partselect.com/PS2121513-Whirlpool-D7824706Q-Replacement-Ice-Maker.htm"),
    ("refrigerator", "https://www.partselect.com/PS3497634-Whirlpool-W10408179-Water-Inlet-Valve.htm"),
    ("refrigerator", "https://www.partselect.com/PS7784018-Frigidaire-242252702-Refrigerator-Water-Inlet-Valve.htm"),
    ("refrigerator", "https://www.partselect.com/PS16226572-GE-WR57X33326-WATER-VALVE-WITH-GUARD.htm"),
    ("refrigerator", "https://www.partselect.com/PS11749668-Whirlpool-WPW10179146-Water-Inlet-Valve.htm"),
    ("refrigerator", "https://www.partselect.com/PS11701542-Whirlpool-EDR1RXD1-Refrigerator-Ice-and-Water-Filter.htm"),
    ("refrigerator", "https://www.partselect.com/PS11704498-Frigidaire-EPTWFU01-Refrigerator-Water-Filter-White.htm"),
    ("refrigerator", "https://www.partselect.com/PS16217433-GE-XWFE-Refrigerator-Water-Filter.htm"),
    ("refrigerator", "https://www.partselect.com/PS11722130-Whirlpool-EDR4RXD1-Refrigerator-Water-Filter.htm"),
    # ── REFRIGERATOR — Cooling, defrost & electrical ──────────────────────────
    ("refrigerator", "https://www.partselect.com/PS12364199-Frigidaire-242126602-Refrigerator-Door-Shelf-Bin.htm"),
    ("refrigerator", "https://www.partselect.com/PS11739119-Whirlpool-WP2188656-Refrigerator-Crisper-Drawer-with-Humidity-Control.htm"),
    ("refrigerator", "https://www.partselect.com/PS11739091-Whirlpool-WP2187172-Refrigerator-Door-Shelf-Bin-White.htm"),
    ("refrigerator", "https://www.partselect.com/PS734935-Frigidaire-240534901-Door-Shelf-Retainer-Bar.htm"),
    ("refrigerator", "https://www.partselect.com/PS734936-Frigidaire-240534701-Door-Shelf-Retainer-Bar.htm"),
    ("refrigerator", "https://www.partselect.com/PS429868-Frigidaire-240337901-Refrigerator-Door-Shelf-Retainer-Bin.htm"),
    ("refrigerator", "https://www.partselect.com/PS429724-Frigidaire-240323001-Refrigerator-Door-Bin.htm"),
    ("refrigerator", "https://www.partselect.com/PS2358880-Frigidaire-241993101-Crisper-Cover-Support-Front.htm"),
    # ── DISHWASHER — Pumps ────────────────────────────────────────────────────
    ("dishwasher", "https://www.partselect.com/PS16744934-Whirlpool-W11612326-Circulation-Pump.htm"),
    ("dishwasher", "https://www.partselect.com/PS11753379-Whirlpool-WPW10348269-Dishwasher-Drain-Pump.htm"),
    ("dishwasher", "https://www.partselect.com/PS11724988-Bosch-12008381-Dishwasher-Circulation-Pump-with-Heater.htm"),
    ("dishwasher", "https://www.partselect.com/PS16744935-Whirlpool-W11612327-Circulation-Pump.htm"),
    ("dishwasher", "https://www.partselect.com/PS11704799-Bosch-00631200-PUMP-DRAIN.htm"),
    # ── DISHWASHER — Door & latch ─────────────────────────────────────────────
    ("dishwasher", "https://www.partselect.com/PS11748729-Whirlpool-WPW10130695-Dishwasher-Door-Handle-And-Latch-Assembly-with-Switch.htm"),
    ("dishwasher", "https://www.partselect.com/PS16218716-Frigidaire-5304525218-Latch.htm"),
    ("dishwasher", "https://www.partselect.com/PS6447681-GE-WD21X10490-Door-Latch.htm"),
    ("dishwasher", "https://www.partselect.com/PS11756967-Whirlpool-WPW10653840-Door-Latch-Black.htm"),
    # ── DISHWASHER — Spray arms ───────────────────────────────────────────────
    ("dishwasher", "https://www.partselect.com/PS12585623-Frigidaire-5304517203-Lower-Spray-Arm.htm"),
    ("dishwasher", "https://www.partselect.com/PS17137081-GE-WD22X33499-LOWER-SPRAY-ARM.htm"),
    ("dishwasher", "https://www.partselect.com/PS11770610-Frigidaire-5304507158-Lower-Spray-Arm.htm"),
    ("dishwasher", "https://www.partselect.com/PS11755592-Whirlpool-WPW10491331-Dishwasher-Lower-Spray-Arm.htm"),
    # ── DISHWASHER — Dispensers ───────────────────────────────────────────────
    ("dishwasher", "https://www.partselect.com/PS11731570-Whirlpool-W10861000-Detergent-Dispenser.htm"),
    ("dishwasher", "https://www.partselect.com/PS11750167-Whirlpool-WPW10199696-Dishwasher-Detergent-Dispenser-Assembly.htm"),
    ("dishwasher", "https://www.partselect.com/PS17137025-GE-WD12X32798-DETERGENT-MODULE.htm"),
    ("dishwasher", "https://www.partselect.com/PS11770487-Frigidaire-5304506521-Detergent-Dispenser.htm"),
    # ── DISHWASHER — Racks ────────────────────────────────────────────────────
    ("dishwasher", "https://www.partselect.com/PS10064063-Whirlpool-W10712394-Dishwasher-Dish-Rack-Adjuster-Kit-Left-and-Right-Side.htm"),
    ("dishwasher", "https://www.partselect.com/PS10057160-Whirlpool-W10728159-Lower-Dishrack.htm"),
    ("dishwasher", "https://www.partselect.com/PS3406971-Whirlpool-W10195416-Dishwasher-Lower-Dishrack-Wheel.htm"),
    ("dishwasher", "https://www.partselect.com/PS10065979-Whirlpool-W10712395-Dishwasher-Upper-Rack-Adjuster-Kit.htm"),
    ("dishwasher", "https://www.partselect.com/PS11746591-Whirlpool-WP8565925-Dishwasher-Rack-Track-Stop.htm"),
    ("dishwasher", "https://www.partselect.com/PS11756150-Whirlpool-WPW10546503-Dishwasher-Upper-Rack-Adjuster.htm"),
    ("dishwasher", "https://www.partselect.com/PS16217024-GE-WD12X26146-Dishwasher-Lower-Rack-Roller.htm"),
    ("dishwasher", "https://www.partselect.com/PS8727387-Bosch-00611475-Dishrack-Roller-Grey.htm"),
    # ── DISHWASHER — Heating & electrical ────────────────────────────────────
    ("dishwasher", "https://www.partselect.com/PS8260087-Whirlpool-W10518394-Dishwasher-Heating-Element.htm"),
]


async def make_context(pw) -> tuple:
    browser = await pw.chromium.launch(
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
    )
    ctx = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 900},
        locale="en-US",
        timezone_id="America/New_York",
    )
    await ctx.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    # Block images & media to speed up (keep JS + CSS so page renders)
    await ctx.route("**/*", lambda route: (
        route.abort() if route.request.resource_type in ("image", "media", "font")
        else route.continue_()
    ))
    return browser, ctx


async def get_page_html(ctx: BrowserContext, url: str, wait_sel: Optional[str] = None, delay: float = 1.5) -> Optional[str]:
    page: Page = await ctx.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        if wait_sel:
            try:
                await page.wait_for_selector(wait_sel, timeout=8000)
            except Exception:
                pass
        await asyncio.sleep(delay)
        return await page.content()
    except Exception as e:
        print(f"    [warn] {url}: {e}")
        return None
    finally:
        await page.close()



# ── Individual part page parser ───────────────────────────────────────────────

def parse_part_page(html: str, url: str, appliance_type: str) -> Optional[dict]:
    soup = BeautifulSoup(html, "lxml")

    # Part number from URL first, then page text
    pn_match = re.search(r"PS\d{6,}", url)
    part_number = pn_match.group(0) if pn_match else ""
    if not part_number:
        for tag in soup.find_all(string=re.compile(r"PS\d{6,}")):
            m = re.search(r"PS\d{6,}", str(tag))
            if m:
                part_number = m.group(0)
                break
    if not part_number:
        return None

    # Title
    h1 = soup.select_one("h1")
    title = h1.get_text(strip=True) if h1 else part_number

    # Price — [itemprop='price'] is most reliable
    price = ""
    el = soup.select_one("[itemprop='price']")
    if el:
        raw = el.get_text(" ", strip=True).replace("\n", " ").strip()
        # "$ 94.45" → "$94.45"
        price = re.sub(r'\$\s+', '$', raw).split()[0] if "$" in raw else ""
    if not price:
        for sel in ["[class*='price__main']", ".js-partPrice"]:
            el = soup.select_one(sel)
            if el:
                raw = el.get_text(" ", strip=True)
                if "$" in raw:
                    price = re.sub(r'\$\s+', '$', raw).split()[0]
                    break

    # Description — #ProductDescription section sibling contains .pd__description
    desc = ""
    pd_header = soup.find(id="ProductDescription")
    if pd_header:
        sib = pd_header.find_next_sibling()
        if sib:
            desc_el = sib.select_one(".pd__description, [itemprop='description']")
            if desc_el:
                desc = desc_el.get_text(" ", strip=True)
    if not desc:
        meta = soup.find("meta", {"name": "description"}) or soup.find("meta", {"property": "og:description"})
        if meta:
            desc = meta.get("content", "")

    # Image
    image_url = ""
    for sel in ["#MagicZoom-PartImage-Images img", ".pd__image img", "img[itemprop='image']", "img.js-main-img"]:
        img = soup.select_one(sel)
        if img:
            src = img.get("src") or img.get("data-src", "")
            if src and ("partselect" in src or src.startswith("//")):
                image_url = ("https:" + src) if src.startswith("//") else src
                break
    # Fallback: PartSelect CDN image by part number
    if not image_url:
        image_url = f"https://www.partselect.com/assets/api/imageRetrieve?num={part_number}&type=product"

    # Compatible models — from #ModelCrossReference section
    compat_models: list[str] = []
    mc_header = soup.find(id="ModelCrossReference")
    if mc_header:
        sib = mc_header.find_next_sibling()
        if sib:
            for a in sib.select("a[href*='/Models/']"):
                model = a.get_text(strip=True)
                if model and re.match(r'^[A-Z0-9]{3,}', model):
                    compat_models.append(model)

    # Symptoms — from #Troubleshooting section list items
    symptoms: list[str] = []
    ts_header = soup.find(id="Troubleshooting")
    if ts_header:
        sib = ts_header.find_next_sibling()
        if sib:
            for li in sib.select("li"):
                t = li.get_text(strip=True)
                if t and 5 < len(t) < 120 and t.lower() not in ("refrigerator", "dishwasher"):
                    symptoms.append(t)

    # Installation instructions — from #InstallationInstructions repair stories
    install_text = ""
    ii_header = soup.find(id="InstallationInstructions")
    if ii_header:
        sib = ii_header.find_next_sibling()
        if sib:
            container = sib.select_one(".js-dataContainer")
            if container:
                # Grab first 2 repair stories as install guidance
                stories = []
                for story_row in container.select(".row, [class*='repair']")[:6]:
                    t = story_row.get_text(" ", strip=True)
                    if len(t) > 80:
                        stories.append(t)
                if stories:
                    install_text = " | ".join(stories[:2])[:2000]

    return {
        "part_number": part_number,
        "title": title or part_number,
        "price": price,
        "description": desc,
        "install_instructions": install_text,
        "image_url": image_url,
        "appliance_type": appliance_type,
        "compatible_models": list(dict.fromkeys(compat_models))[:80],
        "symptoms": list(dict.fromkeys(symptoms))[:20],
        "url": url,
    }


# ── Repair guide parser ───────────────────────────────────────────────────────

def extract_guide_links(html: str, index_url: str) -> list[str]:
    """Extract symptom/repair sub-page links from a repair index page."""
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href: str = a["href"].split("?")[0].split("#")[0]
        full = BASE_URL + href if href.startswith("/") else href
        if (
            full.startswith(BASE_URL)
            and full != index_url
            and full not in seen
            # Target symptom pages and repair sub-pages
            and re.search(r"/Repair/|/repair-|/Refrigerator/|/Dishwasher/", full)
        ):
            seen.add(full)
            links.append(full)
    return links


def parse_guide(html: str, url: str, appliance_type: str) -> Optional[dict]:
    soup = BeautifulSoup(html, "lxml")
    content_el = (
        soup.select_one(".repair-story__content")
        or soup.select_one(".repair-story")
        or soup.select_one("article.repair")
        or soup.select_one(".content-section")
        or soup.select_one("article")
        or soup.select_one("main")
    )
    if not content_el:
        return None
    content = content_el.get_text(" ", strip=True)
    if len(content) < 150:
        return None
    h1 = soup.select_one("h1")
    title = h1.get_text(strip=True) if h1 else url
    # Also grab any part numbers mentioned in the guide
    mentioned_parts = list(set(re.findall(r"PS\d{6,}", content)))
    return {
        "title": title,
        "url": url,
        "appliance_type": appliance_type,
        "content": content[:5000],
        "mentioned_parts": mentioned_parts,
    }


# ── Main orchestration ────────────────────────────────────────────────────────

async def scrape_parts_from_urls(ctx: BrowserContext, seed_urls: list[tuple[str, str]]) -> list[dict]:
    """Scrape part detail pages from a curated list of (appliance_type, url) tuples."""
    print(f"\n{'='*60}")
    print(f"  SCRAPING {len(seed_urls)} SEED PART URLS")
    print(f"{'='*60}")

    parts: list[dict] = []
    seen_pn: set[str] = set()
    for i, (appliance_type, url) in enumerate(seed_urls):
        print(f"  [{i+1:>3}/{len(seed_urls)}] {url.split('/')[-1][:60]}")
        html = await get_page_html(ctx, url, wait_sel="h1", delay=1.2)
        if html:
            parsed = parse_part_page(html, url, appliance_type)
            if parsed and parsed["title"] != parsed["part_number"] and parsed["part_number"] not in seen_pn:
                seen_pn.add(parsed["part_number"])
                parts.append(parsed)
                print(f"         ✓ {parsed['title'][:55]} | {parsed['price']} | {len(parsed['compatible_models'])} models | {len(parsed['symptoms'])} symptoms")
            elif not parsed:
                print(f"         ✗ parse failed")
        await asyncio.sleep(0.8)

    print(f"\n  ✓ {len(parts)} parts scraped total")
    return parts


async def scrape_guides(ctx: BrowserContext, appliance_type: str, index_url: str) -> list[dict]:
    print(f"\n{'='*60}")
    print(f"  {appliance_type.upper()} REPAIR GUIDES  —  {index_url}")
    print(f"{'='*60}")

    html = await get_page_html(ctx, index_url, delay=1.5)
    if not html:
        return []

    guide_links = extract_guide_links(html, index_url)
    print(f"  Found {len(guide_links)} guide links, fetching up to {MAX_GUIDES_PER_CATEGORY}...")

    guides: list[dict] = []
    for i, url in enumerate(guide_links[:MAX_GUIDES_PER_CATEGORY]):
        print(f"  [{i+1:>2}/{min(len(guide_links), MAX_GUIDES_PER_CATEGORY)}] {url}")
        g_html = await get_page_html(ctx, url, wait_sel="h1", delay=1.0)
        if g_html:
            parsed = parse_guide(g_html, url, appliance_type)
            if parsed:
                guides.append(parsed)
                print(f"        ✓ {parsed['title'][:70]}")
        await asyncio.sleep(0.6)

    print(f"\n  ✓ {len(guides)} repair guides scraped for {appliance_type}")
    return guides


async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Starting PartSelect scraper (non-headless Chromium)")
    print(f"Seed parts: {len(SEED_PART_URLS)} | Repair guides: up to {MAX_GUIDES_PER_CATEGORY}/category\n")

    async with async_playwright() as pw:
        browser, ctx = await make_context(pw)
        try:
            all_parts = await scrape_parts_from_urls(ctx, SEED_PART_URLS)

            all_guides: list[dict] = []
            for appliance_type, url in REPAIR_PAGES:
                guides = await scrape_guides(ctx, appliance_type, url)
                all_guides.extend(guides)
        finally:
            await browser.close()

    parts_path = OUTPUT_DIR / "parts.json"
    guides_path = OUTPUT_DIR / "repair_guides.json"

    with open(parts_path, "w") as f:
        json.dump(all_parts, f, indent=2)
    with open(guides_path, "w") as f:
        json.dump(all_guides, f, indent=2)

    print(f"\n{'='*60}")
    print(f"  DONE")
    print(f"  {len(all_parts)} parts  →  {parts_path}")
    print(f"  {len(all_guides)} guides →  {guides_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
