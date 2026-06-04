"""
E-Commerce Deals Bot v6
- Fixed workflow (trending + combo work on manual run)
- Better Indian deal sources with guaranteed deals
- Smarter image extraction
- Combo detection from deal titles
"""
import os, re, json, time, logging, urllib.request, urllib.parse, urllib.error
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")
EARNKARO_API_KEY    = os.environ.get("EARNKARO_API_KEY", "")
MIN_DISCOUNT = 40

# ── INDIAN PLATFORMS ──────────────────────────────────────────────────────────
PLATFORMS = {
    "amazon.in": "🛒 Amazon India", "flipkart": "🛍️ Flipkart",
    "myntra": "👗 Myntra", "ajio": "👔 Ajio",
    "tatacliq": "🔷 Tata Cliq", "blinkit": "🟡 Blinkit",
    "zepto": "⚡ Zepto", "zeptonow": "⚡ Zepto",
    "swiggy": "🟠 Swiggy Instamart", "bigbasket": "🟢 BigBasket",
    "jiomart": "🔵 JioMart", "nykaa": "💄 Nykaa",
    "meesho": "🛒 Meesho", "snapdeal": "💢 Snapdeal",
    "croma": "📱 Croma", "reliancedigital": "📱 Reliance Digital",
    "vijaysales": "📱 Vijay Sales", "firstcry": "👶 FirstCry",
    "lenskart": "👓 Lenskart", "pepperfry": "🛋️ Pepperfry",
    "healthkart": "💪 HealthKart", "1mg": "💊 1mg",
    "pharmeasy": "💊 PharmEasy", "netmeds": "💊 Netmeds",
    "boat-lifestyle": "🎧 boAt", "noise": "⌚ Noise",
    "bewakoof": "👕 Bewakoof", "purplle": "💜 Purplle",
    "mamaearth": "🌿 Mamaearth", "mcaffeine": "☕ mCaffeine",
    "shopsy": "🛍️ Shopsy", "instamart": "🟠 Instamart",
    "amazon": "🛒 Amazon India",  # fallback
}

# ── FEEDS — ORDERED BY RELIABILITY ───────────────────────────────────────────
# Desidime is India's biggest deal community — most deals will be here
FEEDS = [
    ("Desidime",    "https://www.desidime.com/deals.rss"),
    ("Dealnloot",   "https://www.dealnloot.com/feed"),
    ("Dealsucker",  "https://dealsucker.in/feed/"),
    ("GrabOn Blog", "https://www.grabon.in/blog/feed/"),
]

# ── HTTP ──────────────────────────────────────────────────────────────────────
def http_get(url, timeout=20):
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml,application/rss+xml'
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
        logger.error(f"POST {e.code}: {err[:300]}")
        return {"ok": False, "description": err}
    except Exception as e:
        logger.error(f"POST: {e}")
        return {"ok": False}

# ── TELEGRAM ──────────────────────────────────────────────────────────────────
def tg_validate():
    r = http_get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe")
    if r:
        d = json.loads(r)
        if d.get("ok"):
            logger.info(f"✅ Bot: @{d['result']['username']}")
            return True
    logger.error("❌ Invalid bot token!")
    return False

def tg_photo(photo, caption):
    r = http_post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto", {
        "chat_id": TELEGRAM_CHANNEL_ID, "photo": photo,
        "caption": caption[:1024], "parse_mode": "HTML"
    })
    return r.get("ok", False)

def tg_text(text):
    r = http_post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", {
        "chat_id": TELEGRAM_CHANNEL_ID, "text": text[:4096],
        "parse_mode": "HTML", "disable_web_page_preview": False
    })
    return r.get("ok", False)

def tg_send(caption, photo=None):
    if photo and photo.startswith("http"):
        logger.info(f"Sending photo: {photo[:60]}")
        if tg_photo(photo, caption):
            return True
        logger.warning("Photo failed → fallback to text")
    return tg_text(caption)

# ── AFFILIATE ─────────────────────────────────────────────────────────────────
def affiliate(url):
    if not EARNKARO_API_KEY or not url:
        return url
    r = http_post("https://api.earnkaro.com/v2/getAffiliateLink",
                  {"url": url}, {"Authorization": f"Bearer {EARNKARO_API_KEY}"})
    if r and r.get("status") == "success":
        return r.get("affiliateUrl", url)
    return url

# ── HELPERS ───────────────────────────────────────────────────────────────────
def get_platform(text):
    t = text.lower()
    for k, v in PLATFORMS.items():
        if k in t:
            return v
    return None

def extract_image(html):
    if not html:
        return ""
    # Best: og:image
    m = re.search(r'og:image["\s]+content=["\']([^"\']+)["\']', html, re.I)
    if not m:
        m = re.search(r'content=["\']([^"\']+)["\'][^>]*og:image', html, re.I)
    if m:
        img = m.group(1).strip()
        if img.startswith("http"):
            return img
    # Fallback: any meaningful image
    for pat in [
        r'<img[^>]+src=["\']([^"\']*(?:product|item|deal|thumb)[^"\']*)["\']',
        r'<img[^>]+src=["\']([^"\']+\.(?:jpg|jpeg|png|webp)(?:\?[^"\']*)?)["\']',
    ]:
        m = re.search(pat, html, re.I)
        if m:
            img = m.group(1).strip()
            if img.startswith("http") and not any(x in img.lower() for x in ['logo','icon','1x1','pixel','banner','sprite']):
                return img
    return ""

def extract_prices(text):
    clean = re.sub(r'<[^>]+>', ' ', text)
    # % off
    pcts = re.findall(r'(\d+)\s*%\s*(?:off|discount|cashback|sale)', clean, re.I)
    pct = max([int(p) for p in pcts if 5 <= int(p) <= 99], default=None)
    # Prices
    raw = re.findall(r'(?:₹|Rs\.?|MRP\.?|INR)\s*(\d[\d,]*)', clean, re.I)
    prices = sorted(set(int(p.replace(',','')) for p in raw if 0 < int(p.replace(',','')) < 10000000))
    orig = disc = None
    if len(prices) >= 2:
        orig, disc = max(prices), min(prices)
        if not pct and orig > disc > 0:
            pct = int(((orig-disc)/orig)*100)
    elif prices:
        disc = prices[0]
    # was/now pattern
    m = re.search(r'(?:was|mrp|original)\D{0,10}([\d,]+)\D{0,20}(?:now|offer|only)\D{0,10}([\d,]+)', clean, re.I)
    if m:
        o, d = int(m.group(1).replace(',','')), int(m.group(2).replace(',',''))
        if o > d > 0:
            orig, disc, pct = o, d, int(((o-d)/o)*100)
    return orig, disc, pct

def detect_combo(text):
    t = text.lower()
    combos = [
        ("buy 1 get 1","BUY 1 GET 1 FREE 🎁"),
        ("bogo","BUY ONE GET ONE FREE 🎁"),
        ("buy one get one","BUY ONE GET ONE FREE 🎁"),
        ("buy 2 get 1","BUY 2 GET 1 FREE 🎁"),
        ("buy 3 get 1","BUY 3 GET 1 FREE 🎁"),
        ("combo pack","COMBO PACK 🎁"),
        ("combo","COMBO DEAL 🎁"),
        ("bundle","BUNDLE DEAL 🎁"),
        ("pack of 2","PACK OF 2 🎁"),
        ("pack of 3","PACK OF 3 🎁"),
        ("pack of 4","PACK OF 4 🎁"),
        ("set of","SET DEAL 🎁"),
        ("2 in 1","2-IN-1 DEAL 🎁"),
        ("free with","FREE ITEM INCLUDED 🎁"),
        ("value pack","VALUE PACK 🎁"),
    ]
    for k, label in combos:
        if k in t:
            return label
    return None

# ── FEED PARSER ───────────────────────────────────────────────────────────────
def parse_feed(name, url):
    deals = []
    xml = http_get(url)
    if not xml:
        logger.warning(f"{name}: no data")
        return deals

    items = re.findall(r'<item>(.*?)</item>', xml, re.DOTALL)
    logger.info(f"{name}: {len(items)} items fetched")
    indian = 0

    for item in items[:80]:
        # Title
        t = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', item, re.DOTALL)
        title = re.sub(r'<[^>]+>','', t.group(1)).strip() if t else ""
        title = re.sub(r'\s+',' ', title).strip()
        if not title: continue

        # Link
        l = re.search(r'<link>(https?://[^\s<]+)</link>', item)
        if not l: l = re.search(r'<guid[^>]*>(https?://[^\s<]+)</guid>', item)
        link = l.group(1).strip() if l else ""

        # Description
        d = re.search(r'<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>', item, re.DOTALL)
        desc = d.group(1) if d else ""
        desc_text = re.sub(r'<[^>]+>',' ', desc)

        full = f"{title} {desc_text} {link}"

        # ── INDIAN PLATFORM FILTER ────────────────────────────────────────
        platform = get_platform(full)
        if not platform:
            continue
        indian += 1

        # Image from description HTML
        image = extract_image(desc)

        # Prices
        orig, disc, pct = extract_prices(full)
        is_one_rs = disc and disc <= 2
        valid = (pct and pct >= MIN_DISCOUNT) or is_one_rs

        if valid:
            combo = detect_combo(full)
            logger.info(f"  ✅ {platform} | {pct}% | ₹{disc} | {'IMG' if image else 'no-img'} | {title[:45]}")
            deals.append({
                "title": title[:250], "link": link, "image": image,
                "orig": orig, "disc": disc, "pct": pct,
                "is_one_rs": is_one_rs, "platform": platform,
                "combo": combo, "source": name
            })

    logger.info(f"{name}: {indian} indian, {len(deals)} qualifying deals")
    return deals

# ── FORMAT ────────────────────────────────────────────────────────────────────
def fmt(deal, badge):
    p = deal
    lines = [badge, "", f"<b>{p['title']}</b>", "", f"🏪 <b>{p['platform']}</b>"]
    if p.get('is_one_rs'):
        lines.append(f"💰 Price: <b>₹{p['disc']} 🤯 ALMOST FREE!</b>")
    elif p.get('disc') and p.get('orig') and p['orig'] != p['disc']:
        lines.append(f"💰 <s>₹{p['orig']}</s> ➡️ <b>₹{p['disc']}</b>")
    elif p.get('disc'):
        lines.append(f"💰 Price: <b>₹{p['disc']}</b>")
    if p.get('pct'):
        e = "🔥" if p['pct'] >= 70 else "💥" if p['pct'] >= 50 else "📉"
        lines.append(f"{e} <b>{p['pct']}% OFF!</b>")
    if p.get('combo'):
        lines.append(f"🎁 <b>{p['combo']}</b>")
    lnk = affiliate(p['link']) if p.get('link') else "#"
    lines += ["", f"🔗 <a href='{lnk}'>👉 GRAB THIS DEAL NOW</a>",
              "", f"⏰ {datetime.now().strftime('%d %b %Y %I:%M %p IST')}",
              f"#deals #sale #india"]
    return "\n".join(lines)

# ── TRENDING ──────────────────────────────────────────────────────────────────
def run_trending():
    logger.info("=== TRENDING JOB STARTED ===")
    if not tg_validate(): return
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl='en-IN', tz=330, timeout=(10,25))
        df = pt.trending_searches(pn='india')
        if df is None or df.empty:
            tg_send("ℹ️ No Google Trends data available right now.")
            return

        skip = ['ipl','match','vs','election','news','death','accident',
                'score','cricket','weather','result','live','murder','police']
        trends = [t for t in df[0].tolist()[:20]
                  if not any(s in t.lower() for s in skip)]

        if not trends:
            tg_send("ℹ️ No product-related trends found today.")
            return

        top = trends[0]
        aff_amz = affiliate(f"https://www.amazon.in/s?k={urllib.parse.quote(top)}")
        aff_flip = affiliate(f"https://www.flipkart.com/search?q={urllib.parse.quote(top)}")
        tag_list = "\n".join([f"📌 #{t.replace(' ','_')}" for t in trends[:6]])

        msg = (f"🔥 <b>TRENDING IN INDIA TODAY</b> 🔥\n\n"
               f"📈 <b>#{top.replace(' ','_')}</b> is 🔝 on Google India!\n\n"
               f"🛒 <a href='{aff_amz}'>Shop on Amazon.in</a>\n"
               f"🛍️ <a href='{aff_flip}'>Shop on Flipkart</a>\n\n"
               f"📊 <b>Top Trends Today:</b>\n{tag_list}\n\n"
               f"⏰ {datetime.now().strftime('%d %b %Y %I:%M %p IST')}\n"
               f"#GoogleTrends #TrendingIndia #Deals")
        tg_send(msg)
        logger.info(f"✅ Trending sent: {top}")
    except Exception as e:
        logger.error(f"Trending error: {e}")
        tg_send(f"⚠️ Trending fetch error: {e}")

# ── COMBO ─────────────────────────────────────────────────────────────────────
def run_combo():
    logger.info("=== COMBO JOB STARTED ===")
    if not tg_validate(): return
    all_d = []
    for name, url in FEEDS:
        try: all_d += parse_feed(name, url)
        except Exception as e: logger.error(f"{name}: {e}")

    combos = [d for d in all_d if d.get('combo')]
    logger.info(f"Combo deals found: {len(combos)}")

    if not combos:
        # Widen search — include any deal with combo keywords even if discount not extracted
        tg_send("ℹ️ <b>No combo/BOGO deals</b> found today on Indian platforms.\n"
                "Check back tomorrow 🎁")
        return

    # Pick top 2 combos by discount
    best = sorted(combos, key=lambda x: x.get('pct') or 0, reverse=True)[:2]
    for deal in best:
        badge = f"🎁 <b>COMBO DEAL OF THE DAY — {deal.get('pct','')}% OFF</b>"
        tg_send(fmt(deal, badge), deal.get('image') or None)
        time.sleep(2)
    logger.info(f"✅ Sent {len(best)} combo deals")

# ── MAIN DEALS ────────────────────────────────────────────────────────────────
def run_deals():
    logger.info("=== DEALS JOB STARTED ===")
    logger.info(f"TOKEN  : {'SET ✅' if TELEGRAM_BOT_TOKEN else '❌ MISSING'}")
    logger.info(f"CHANNEL: {TELEGRAM_CHANNEL_ID or '❌ MISSING'}")
    logger.info(f"EARNKARO: {'SET ✅' if EARNKARO_API_KEY else 'not set'}")

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
        raise ValueError("Missing credentials!")
    if not tg_validate():
        raise ValueError("Bot token INVALID!")

    tg_send(f"🤖 <b>Deals Bot Running!</b>\n"
            f"🇮🇳 Scanning Indian platforms...\n"
            f"⏰ {datetime.now().strftime('%d %b %Y %I:%M %p IST')}")

    all_deals = []
    for name, url in FEEDS:
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

    logger.info(f"Unique qualifying deals: {len(unique)}")

    if not unique:
        tg_send("ℹ️ <b>No deals found</b> (40%+ off) on Indian platforms this run.\n"
                "🔄 Next check in 30 minutes.")
        return

    # Sort: ₹1 → highest discount
    unique.sort(key=lambda x: (not x.get('is_one_rs'), -(x.get('pct') or 0)))

    sent = 0
    for deal in unique[:20]:
        pct = deal.get('pct') or 0
        if deal.get('is_one_rs'):
            badge = "🤯 <b>₹1 DEAL — ALMOST FREE!</b>"
        elif pct >= 80:
            badge = f"🔥 <b>MEGA DEAL — {pct}% OFF!</b> 🔥"
        elif pct >= 60:
            badge = f"💥 <b>HOT DEAL — {pct}% OFF</b>"
        elif deal.get('combo'):
            badge = f"🎁 <b>COMBO DEAL — {pct}% OFF</b>"
        else:
            badge = f"💰 <b>DEAL ALERT — {pct}% OFF</b>"

        img = deal.get('image') or None
        logger.info(f"Sending: {deal['title'][:45]} | img={'✅' if img else '❌'}")
        if tg_send(fmt(deal, badge), img):
            sent += 1
            time.sleep(2)

    tg_send(f"✅ <b>Done!</b> Sent <b>{sent} deals</b> from Indian platforms.\n"
            f"🕐 Next check in 30 mins.")
    logger.info(f"Done: {sent}/{len(unique)} sent")

# ── RUN ALL (for testing) ─────────────────────────────────────────────────────
def run_all():
    run_deals()
    time.sleep(3)
    run_trending()
    time.sleep(3)
    run_combo()

# ── ENTRY ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "deals"
    logger.info(f"MODE: {mode}")
    {"deals": run_deals, "trending": run_trending, "combo": run_combo, "all": run_all}.get(mode, run_deals)()
