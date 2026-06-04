"""
E-Commerce Deals Bot v5
- Indian platforms only (Amazon.in, Flipkart, Myntra, Ajio, Tata Cliq, Blinkit, Zepto etc.)
- Product images included
- Better deal detection
"""
import os, re, json, time, logging, urllib.request, urllib.parse, urllib.error
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")
EARNKARO_API_KEY    = os.environ.get("EARNKARO_API_KEY", "")
MIN_DISCOUNT = 40

# ── INDIAN PLATFORMS WHITELIST ────────────────────────────────────────────────
INDIAN_PLATFORMS = {
    "amazon.in":        "🛒 Amazon India",
    "flipkart.com":     "🛍️ Flipkart",
    "myntra.com":       "👗 Myntra",
    "ajio.com":         "👔 Ajio",
    "tatacliq.com":     "🔷 Tata Cliq",
    "blinkit.com":      "🟡 Blinkit",
    "zepto.com":        "⚡ Zepto",
    "zeptonow.com":     "⚡ Zepto",
    "swiggy.com":       "🟠 Swiggy Instamart",
    "bigbasket.com":    "🟢 BigBasket",
    "jiomart.com":      "🔵 JioMart",
    "nykaa.com":        "💄 Nykaa",
    "meesho.com":       "🛒 Meesho",
    "snapdeal.com":     "💢 Snapdeal",
    "shopsy.in":        "🛍️ Shopsy",
    "reliancedigital.in":"📱 Reliance Digital",
    "croma.com":        "📱 Croma",
    "vijaysales.com":   "📱 Vijay Sales",
    "firstcry.com":     "👶 FirstCry",
    "purplle.com":      "💜 Purplle",
    "boat-lifestyle.com":"🎧 boAt",
    "mamaearth.in":     "🌿 Mamaearth",
    "lenskart.com":     "👓 Lenskart",
    "pepperfry.com":    "🛋️ Pepperfry",
    "fabindia.com":     "🧵 FabIndia",
    "tanishq.co.in":    "💎 Tanishq",
    "nykaafashion.com": "👗 Nykaa Fashion",
    "clovia.com":       "👙 Clovia",
    "beardo.in":        "🧔 Beardo",
    "mcaffeine.in":     "☕ mCaffeine",
    "mivi.in":          "🎧 Mivi",
    "noise.com":        "⌚ Noise",
    "fastrack.in":      "⌚ Fastrack",
    "bewakoof.com":     "👕 Bewakoof",
    "zivame.com":       "👙 Zivame",
    "healthkart.com":   "💪 HealthKart",
    "1mg.com":          "💊 1mg",
    "pharmeasy.in":     "💊 PharmEasy",
    "netmeds.com":      "💊 Netmeds",
    "decathlonsports.in":"🏃 Decathlon",
    "reebok.in":        "👟 Reebok India",
    "adidas.co.in":     "👟 Adidas India",
    "nike.com/in":      "👟 Nike India",
    "woodland.in":      "🥾 Woodland",
    "bata.in":          "👞 Bata India",
    "amazon":           "🛒 Amazon India",  # fallback keyword
    "flipkart":         "🛍️ Flipkart",
    "myntra":           "👗 Myntra",
    "ajio":             "👔 Ajio",
    "tatacliq":         "🔷 Tata Cliq",
    "blinkit":          "🟡 Blinkit",
    "zepto":            "⚡ Zepto",
    "meesho":           "🛒 Meesho",
    "nykaa":            "💄 Nykaa",
    "jiomart":          "🔵 JioMart",
    "bigbasket":        "🟢 BigBasket",
    "snapdeal":         "💢 Snapdeal",
    "croma":            "📱 Croma",
    "instamart":        "🟠 Swiggy Instamart",
}

# ── HTTP ──────────────────────────────────────────────────────────────────────
def http_get(url, timeout=20):
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode('utf-8', errors='ignore')
    except Exception as e:
        logger.error(f"GET {url[:60]}: {e}")
        return None

def http_post(url, data, headers=None):
    try:
        body = json.dumps(data).encode()
        h = {'Content-Type': 'application/json'}
        if headers: h.update(headers)
        req = urllib.request.Request(url, data=body, headers=h, method='POST')
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        logger.error(f"POST {e.code}: {err[:200]}")
        return {"ok": False, "description": err}
    except Exception as e:
        logger.error(f"POST: {e}")
        return {"ok": False}

# ── TELEGRAM ──────────────────────────────────────────────────────────────────
def tg_validate():
    html = http_get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe")
    if html:
        d = json.loads(html)
        if d.get("ok"):
            logger.info(f"✅ Bot: @{d['result']['username']}")
            return True
    logger.error("❌ Bot token invalid!")
    return False

def tg_send_photo(photo_url, caption):
    """Send photo with caption"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    r = http_post(url, {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "photo": photo_url,
        "caption": caption[:1024],
        "parse_mode": "HTML"
    })
    if r.get("ok"):
        logger.info("✅ Photo sent")
        return True
    logger.warning(f"Photo failed: {r.get('description','')[:100]} — trying text")
    return False

def tg_send_text(text):
    """Send text message"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    r = http_post(url, {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "text": text[:4096],
        "parse_mode": "HTML",
        "disable_web_page_preview": False  # shows link preview with image
    })
    if r.get("ok"):
        logger.info("✅ Text sent")
        return True
    logger.error(f"❌ Text failed: {r}")
    return False

def tg_send(caption, photo_url=None):
    """Try photo first, fallback to text with link preview"""
    if photo_url and photo_url.startswith("http"):
        ok = tg_send_photo(photo_url, caption)
        if ok:
            return True
    return tg_send_text(caption)

# ── AFFILIATE ─────────────────────────────────────────────────────────────────
def affiliate(url):
    if not EARNKARO_API_KEY or not url:
        return url
    r = http_post(
        "https://api.earnkaro.com/v2/getAffiliateLink",
        {"url": url},
        {"Authorization": f"Bearer {EARNKARO_API_KEY}"}
    )
    if r and r.get("status") == "success":
        aff = r.get("affiliateUrl", url)
        logger.info(f"✅ Affiliate link generated")
        return aff
    logger.warning(f"EarnKaro: {r}")
    return url

# ── INDIAN PLATFORM DETECTION ─────────────────────────────────────────────────
def get_indian_platform(text, url=""):
    combined = (text + " " + url).lower()
    for key, label in INDIAN_PLATFORMS.items():
        if key in combined:
            return label
    return None  # None = NOT an Indian platform

def is_indian_deal(text, url=""):
    return get_indian_platform(text, url) is not None

# ── PRICE EXTRACTION ──────────────────────────────────────────────────────────
def extract_discount(text):
    clean = re.sub(r'<[^>]+>', ' ', text)

    # % off patterns
    pct_matches = re.findall(r'(\d+)\s*%\s*(?:off|discount|cashback|savings?|sale)', clean, re.I)
    pct = max([int(p) for p in pct_matches if 10 <= int(p) <= 99], default=None)

    # Price patterns: ₹, Rs., MRP, INR
    price_matches = re.findall(r'(?:₹|Rs\.?|MRP\.?|INR)\s*(\d[\d,]*)', clean, re.I)
    prices = sorted(set(int(p.replace(',','')) for p in price_matches if 0 < int(p.replace(',','')) < 10000000))

    orig = disc = None
    if len(prices) >= 2:
        orig = max(prices)
        disc = min(prices)
        if not pct and orig > disc > 0:
            pct = int(((orig - disc) / orig) * 100)
    elif len(prices) == 1:
        disc = prices[0]

    # "was X now Y" pattern
    m = re.search(r'(?:was|mrp|original)\D{0,10}(\d[\d,]+)\D{0,20}(?:now|offer|sale|only)\D{0,10}(\d[\d,]+)', clean, re.I)
    if m:
        o, d = int(m.group(1).replace(',','')), int(m.group(2).replace(',',''))
        if o > d > 0:
            orig, disc = o, d
            pct = int(((o - d) / o) * 100)

    return orig, disc, pct

def detect_combo(text):
    for k in ["buy 1 get 1","bogo","combo","bundle","pack of 2","pack of 3",
              "2 in 1","free with","buy 2 get 1","buy one get one","value pack"]:
        if k in text.lower():
            return k.upper()
    return None

# ── IMAGE EXTRACTION — IMPROVED ───────────────────────────────────────────────
def extract_image(html_text, link=""):
    """Try multiple ways to get a good product image"""
    if not html_text:
        return ""

    # Look for og:image or product images first (best quality)
    patterns = [
        r'og:image["\s]+content=["\']([^"\']+)["\']',
        r'content=["\']([^"\']+)["\'][^>]+og:image',
        r'<img[^>]+src=["\']([^"\']+(?:product|item|deal|thumb|img)[^"\']*)["\']',
        r'<img[^>]+src=["\']([^"\']+\.(?:jpg|jpeg|png|webp))["\']',
    ]
    for pat in patterns:
        m = re.search(pat, html_text, re.I)
        if m:
            img = m.group(1).strip()
            if img.startswith("http") and len(img) > 10:
                # Skip tiny images, icons, logos
                if not any(x in img.lower() for x in ['logo','icon','banner','1x1','pixel','track']):
                    return img

    # Fallback: any image
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html_text, re.I)
    if m:
        img = m.group(1).strip()
        if img.startswith("http"):
            return img

    return ""

# ── INDIAN DEAL FEEDS ─────────────────────────────────────────────────────────
# These are Indian deal aggregators that focus on Indian e-commerce
INDIAN_FEEDS = [
    ("Desidime",     "https://www.desidime.com/deals.rss"),
    ("Dealnloot",    "https://www.dealnloot.com/feed"),
    ("Dealsucker",   "https://dealsucker.in/feed/"),
    ("CouponDunia",  "https://www.coupondunia.in/blog/feed/"),
    ("GrabOn",       "https://www.grabon.in/deals/feed/"),
]

def parse_feed(name, url):
    deals = []
    xml = http_get(url)
    if not xml:
        logger.warning(f"{name}: no response")
        return deals

    items = re.findall(r'<item>(.*?)</item>', xml, re.DOTALL)
    logger.info(f"{name}: {len(items)} total items")

    indian_count = 0
    for item in items[:60]:
        # Title
        t = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', item, re.DOTALL)
        title = re.sub(r'<[^>]+>', '', t.group(1)).strip() if t else ""
        title = re.sub(r'\s+', ' ', title)

        # Link
        l = re.search(r'<link>(https?://[^\s<]+)</link>', item)
        if not l:
            l = re.search(r'<guid[^>]*>(https?://[^\s<]+)</guid>', item)
        link = l.group(1).strip() if l else ""

        # Description
        d = re.search(r'<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>', item, re.DOTALL)
        desc = d.group(1) if d else ""

        full_text = f"{title} {desc} {link}"

        # ── FILTER: INDIAN PLATFORMS ONLY ────────────────────────────────────
        platform = get_indian_platform(full_text)
        if not platform:
            logger.debug(f"  SKIP (foreign): {title[:50]}")
            continue

        indian_count += 1

        # Extract image from description
        image = extract_image(desc, link)

        # Extract prices
        orig, disc, pct = extract_discount(full_text)
        is_one_rs = disc and disc <= 2
        valid = (pct and pct >= MIN_DISCOUNT) or is_one_rs

        if valid:
            logger.info(f"  ✅ [{platform}] {title[:50]} | {pct}% | ₹{disc}")
            deals.append({
                "title": title[:250],
                "link": link,
                "image": image,
                "orig": orig,
                "disc": disc,
                "pct": pct,
                "is_one_rs": is_one_rs,
                "platform": platform,
                "combo": detect_combo(full_text),
                "source": name
            })
        else:
            logger.debug(f"  SKIP (low disc {pct}%): {title[:40]}")

    logger.info(f"{name}: {indian_count} indian deals, {len(deals)} qualifying")
    return deals

# ── FORMAT MESSAGE ────────────────────────────────────────────────────────────
def fmt(deal, badge="💰 <b>DEAL ALERT</b>"):
    lines = [badge, ""]
    lines.append(f"<b>{deal['title']}</b>")
    lines.append("")
    lines.append(f"🏪 <b>{deal['platform']}</b>")

    if deal.get('is_one_rs'):
        lines.append(f"💰 Price: <b>₹{deal['disc']} 🤯 ALMOST FREE!</b>")
    elif deal.get('disc') and deal.get('orig') and deal['orig'] != deal['disc']:
        lines.append(f"💰 <s>₹{deal['orig']}</s> ➡️ <b>₹{deal['disc']}</b>")
    elif deal.get('disc'):
        lines.append(f"💰 Price: <b>₹{deal['disc']}</b>")

    if deal.get('pct'):
        e = "🔥" if deal['pct'] >= 70 else "💥" if deal['pct'] >= 50 else "📉"
        lines.append(f"{e} <b>{deal['pct']}% OFF!</b>")

    if deal.get('combo'):
        lines.append(f"🎁 <b>{deal['combo']}</b>")

    lnk = affiliate(deal['link']) if deal.get('link') else "#"
    lines.append("")
    lines.append(f"🔗 <a href='{lnk}'>👉 GRAB THIS DEAL NOW</a>")
    lines.append("")
    lines.append(f"⏰ {datetime.now().strftime('%d %b %Y %I:%M %p IST')}")
    lines.append(f"#deals #sale #india #{deal['platform'].split()[-1].replace('🛒','').replace('🛍️','').strip().lower()}")
    return "\n".join(lines)

# ── TRENDING ──────────────────────────────────────────────────────────────────
def run_trending():
    logger.info("Fetching Google Trends India...")
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl='en-IN', tz=330, timeout=(10, 25))
        df = pt.trending_searches(pn='india')
        if df is None or df.empty:
            logger.warning("No trends"); return

        skip = ['ipl','match','vs','election','news','death','accident',
                'score','cricket','weather','today','result','live']
        trends = [t for t in df[0].tolist()[:20]
                  if not any(s in t.lower() for s in skip)]
        if not trends:
            logger.warning("No product trends"); return

        top = trends[0]
        aff = affiliate(f"https://www.amazon.in/s?k={urllib.parse.quote(top)}")
        flip = affiliate(f"https://www.flipkart.com/search?q={urllib.parse.quote(top)}")
        others = " | ".join(f"#{t.replace(' ','_')}" for t in trends[1:5])

        msg = f"""🔥 <b>TRENDING IN INDIA TODAY</b> 🔥

📈 <b>#{top.replace(' ','_')}</b> is on 🔝 Google Trends India!

🛒 Shop on Amazon:
🔗 <a href='{aff}'>👉 {top.upper()} — Amazon.in</a>

🛍️ Shop on Flipkart:
🔗 <a href='{flip}'>👉 {top.upper()} — Flipkart</a>

📊 Also trending today:
{others}

⏰ {datetime.now().strftime('%d %b %Y %I:%M %p IST')}
#trending #googletrends #dealstoday #india"""
        tg_send(msg)
        logger.info(f"Trending sent: {top}")
    except Exception as e:
        logger.error(f"Trending error: {e}")

# ── MAIN DEALS ────────────────────────────────────────────────────────────────
def run_deals():
    logger.info("=" * 55)
    logger.info("E-COMMERCE DEALS BOT v5 — INDIAN PLATFORMS ONLY")
    logger.info(f"TOKEN   : {'SET ✅' if TELEGRAM_BOT_TOKEN else '❌ MISSING'}")
    logger.info(f"CHANNEL : {TELEGRAM_CHANNEL_ID or '❌ MISSING'}")
    logger.info(f"EARNKARO: {'SET ✅' if EARNKARO_API_KEY else 'not set'}")
    logger.info("=" * 55)

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
        raise ValueError("Missing credentials!")

    if not tg_validate():
        raise ValueError("Bot token INVALID!")

    tg_send(f"🤖 <b>Deals Bot Running!</b>\n"
            f"🇮🇳 Scanning Indian platforms...\n"
            f"⏰ {datetime.now().strftime('%d %b %Y %I:%M %p IST')}")

    # Fetch all deals
    all_deals = []
    for name, url in INDIAN_FEEDS:
        try:
            found = parse_feed(name, url)
            all_deals += found
        except Exception as e:
            logger.error(f"{name}: {e}")

    # Deduplicate
    seen, unique = set(), []
    for d in all_deals:
        key = d['title'][:40].lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(d)

    logger.info(f"Unique Indian deals: {len(unique)}")

    if not unique:
        tg_send("ℹ️ <b>No Indian deals</b> (40%+ off) found this run.\n🔄 Next check in 30 mins.")
        return

    # Sort: ₹1 first → highest discount first
    unique.sort(key=lambda x: (not x.get('is_one_rs'), -(x.get('pct') or 0)))

    sent = 0
    for deal in unique[:20]:
        try:
            pct = deal.get('pct') or 0
            if deal.get('is_one_rs'):
                badge = "🤯 <b>₹1 DEAL — ALMOST FREE!</b>"
            elif pct >= 80:
                badge = f"🔥 <b>MEGA DEAL — {pct}% OFF!</b> 🔥"
            elif pct >= 60:
                badge = f"💥 <b>HOT DEAL — {pct}% OFF</b>"
            elif deal.get('combo'):
                badge = "🎁 <b>COMBO DEAL ALERT</b>"
            else:
                badge = f"💰 <b>DEAL ALERT — {pct}% OFF</b>"

            caption = fmt(deal, badge)
            image = deal.get('image') or ""

            logger.info(f"Sending: {deal['title'][:50]} | img={'YES' if image else 'NO'}")
            ok = tg_send(caption, image if image else None)

            if ok:
                sent += 1
                time.sleep(2)
        except Exception as e:
            logger.error(f"Send error: {e}")

    tg_send(f"✅ <b>Done!</b> Sent <b>{sent} Indian deals</b>.\n🕐 Next check in 30 mins.")
    logger.info(f"Complete: {sent}/{len(unique)} sent")

# ── ENTRY ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "deals"

    if mode == "trending":
        if tg_validate(): run_trending()
    elif mode == "combo":
        if tg_validate():
            all_d = []
            for n, u in INDIAN_FEEDS:
                all_d += parse_feed(n, u)
            combos = [d for d in all_d if d.get('combo')]
            if combos:
                best = sorted(combos, key=lambda x: x.get('pct') or 0, reverse=True)[0]
                tg_send(fmt(best, "🎁 <b>COMBO / BOGO DEAL OF THE DAY</b> 🎁"), best.get('image'))
                logger.info(f"Combo sent: {best['title'][:50]}")
            else:
                tg_send("ℹ️ No combo deals found today on Indian platforms.")
    else:
        run_deals()
