"""
E-Commerce Deals Bot v4 — Fixed deal detection + Telegram
"""
import os, re, json, time, logging, urllib.request, urllib.parse, urllib.error
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")
EARNKARO_API_KEY    = os.environ.get("EARNKARO_API_KEY", "")
MIN_DISCOUNT = 40

# ── HTTP ──────────────────────────────────────────────────────────────────────
def http_get(url, timeout=20):
    try:
        req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode('utf-8', errors='ignore')
    except Exception as e:
        logger.error(f"GET {url[:50]}: {e}")
        return None

def http_post(url, data, headers=None):
    try:
        body = json.dumps(data).encode()
        h = {'Content-Type':'application/json'}
        if headers: h.update(headers)
        req = urllib.request.Request(url, data=body, headers=h, method='POST')
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        logger.error(f"POST {e.code}: {err}")
        return {"ok": False, "description": err}
    except Exception as e:
        logger.error(f"POST error: {e}")
        return {"ok": False}

# ── TELEGRAM ──────────────────────────────────────────────────────────────────
def tg_validate():
    html = http_get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe")
    if html:
        d = json.loads(html)
        if d.get("ok"):
            logger.info(f"✅ Bot OK: @{d['result']['username']}")
            return True
    logger.error(f"❌ Bot token invalid!")
    return False

def tg_send(text, photo=None):
    if photo:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        r = http_post(url, {"chat_id": TELEGRAM_CHANNEL_ID, "photo": photo,
                            "caption": text[:1024], "parse_mode": "HTML"})
        if not r.get("ok"):
            # fallback without photo
            return tg_send(text)
    else:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        r = http_post(url, {"chat_id": TELEGRAM_CHANNEL_ID, "text": text[:4096],
                            "parse_mode": "HTML", "disable_web_page_preview": True})
    if r.get("ok"):
        logger.info("✅ Sent to Telegram")
        return True
    logger.error(f"❌ Telegram failed: {r}")
    return False

# ── AFFILIATE ─────────────────────────────────────────────────────────────────
def affiliate(url):
    if not EARNKARO_API_KEY or not url: return url
    r = http_post("https://api.earnkaro.com/v2/getAffiliateLink",
                  {"url": url}, {"Authorization": f"Bearer {EARNKARO_API_KEY}"})
    if r and r.get("status") == "success":
        return r.get("affiliateUrl", url)
    return url

# ── PRICE EXTRACTION — IMPROVED ───────────────────────────────────────────────
def extract_discount(text):
    """
    Returns (original, discounted, pct) using multiple strategies
    """
    # Clean HTML
    clean = re.sub(r'<[^>]+>', ' ', text)

    # Strategy 1: explicit % off
    pct_matches = re.findall(r'(\d+)\s*%\s*(?:off|discount|cashback|savings?)', clean, re.I)
    pct = max([int(p) for p in pct_matches if 10 <= int(p) <= 99], default=None)

    # Strategy 2: two prices (MRP vs sale)
    price_matches = re.findall(r'(?:₹|Rs\.?|MRP|INR)\s*(\d[\d,]*)', clean, re.I)
    prices = sorted(set(int(p.replace(',','')) for p in price_matches if int(p.replace(',','')) > 0))

    orig = disc = None
    if len(prices) >= 2:
        orig = max(prices)
        disc = min(prices)
        if not pct and orig > disc:
            pct = int(((orig - disc) / orig) * 100)
    elif len(prices) == 1:
        disc = prices[0]

    # Strategy 3: "was X now Y" pattern
    was_now = re.search(r'(?:was|MRP|original)[^\d]*(\d[\d,]+)[^\d]+(?:now|offer|sale)[^\d]*(\d[\d,]+)', clean, re.I)
    if was_now:
        o, d = int(was_now.group(1).replace(',','')), int(was_now.group(2).replace(',',''))
        if o > d > 0:
            orig, disc = o, d
            pct = int(((o - d) / o) * 100)

    return orig, disc, pct

def detect_platform(text):
    t = text.lower()
    for k, v in [("amazon","🛒 Amazon"),("flipkart","🛍️ Flipkart"),
                  ("myntra","👗 Myntra"),("meesho","🛒 Meesho"),
                  ("ajio","👔 Ajio"),("nykaa","💄 Nykaa"),
                  ("zepto","⚡ Zepto"),("blinkit","🟡 Blinkit"),
                  ("jiomart","🔵 JioMart"),("bigbasket","🟢 BigBasket"),
                  ("tatacliq","🔷 Tata Cliq"),("snapdeal","💢 Snapdeal")]:
        if k in t: return v
    return "🛒 Online Store"

def detect_combo(text):
    for k in ["buy 1 get 1","bogo","combo","bundle","pack of","2 in 1",
              "free with","buy 2","value pack","buy one get"]:
        if k in text.lower(): return k.upper()
    return None

def get_image(entry_text):
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', entry_text, re.I)
    return m.group(1) if m else ""

# ── FEED SOURCES ──────────────────────────────────────────────────────────────
FEEDS = [
    ("Desidime",   "https://www.desidime.com/deals.rss"),
    ("Dealnloot",  "https://www.dealnloot.com/feed"),
    ("Dealsucker", "https://dealsucker.in/feed/"),
    ("Slickdeals", "https://slickdeals.net/newsearch.php?mode=frontpage&searcharea=deals&searchin=first&rss=1"),
]

def parse_feed(name, url):
    deals = []
    xml = http_get(url)
    if not xml:
        logger.warning(f"{name}: no response")
        return deals

    # Extract all items
    items = re.findall(r'<item>(.*?)</item>', xml, re.DOTALL)
    logger.info(f"{name}: {len(items)} items in feed")

    for item in items[:50]:
        # Title
        t = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', item, re.DOTALL)
        title = re.sub(r'<[^>]+>', '', t.group(1)).strip() if t else ""

        # Link
        l = re.search(r'<link>(https?://[^\s<]+)</link>', item)
        if not l:
            l = re.search(r'<guid[^>]*>(https?://[^\s<]+)</guid>', item)
        link = l.group(1).strip() if l else ""

        # Description
        d = re.search(r'<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>', item, re.DOTALL)
        desc = d.group(1) if d else ""

        full = f"{title} {desc}"
        image = get_image(desc)

        orig, disc, pct = extract_discount(full)
        is_one_rs = disc and disc <= 2
        valid = (pct and pct >= MIN_DISCOUNT) or is_one_rs

        if valid:
            logger.info(f"  ✅ DEAL: {title[:60]} | {pct}% off | ₹{disc}")
            deals.append({
                "title": title[:250], "link": link, "image": image,
                "orig": orig, "disc": disc, "pct": pct,
                "is_one_rs": is_one_rs,
                "platform": detect_platform(full + link),
                "combo": detect_combo(full),
                "source": name
            })
        else:
            logger.debug(f"  skip: {title[:50]} | pct={pct} disc={disc}")

    return deals

# ── FORMAT ────────────────────────────────────────────────────────────────────
def fmt(deal, badge="💰 <b>DEAL ALERT</b>"):
    p = deal
    lines = [badge, "", f"<b>{p['title']}</b>", "", f"🏪 {p['platform']}"]

    if p.get('is_one_rs'):
        lines.append(f"💰 Price: <b>₹{p['disc']} 🤯 ALMOST FREE!</b>")
    elif p.get('disc') and p.get('orig') and p['orig'] != p['disc']:
        lines.append(f"💰 <s>₹{p['orig']}</s> → <b>₹{p['disc']}</b>")
    elif p.get('disc'):
        lines.append(f"💰 Price: <b>₹{p['disc']}</b>")

    if p.get('pct'):
        e = "🔥" if p['pct'] >= 70 else "💥" if p['pct'] >= 50 else "📉"
        lines.append(f"{e} Discount: <b>{p['pct']}% OFF</b>")

    if p.get('combo'):
        lines.append(f"🎁 Deal: <b>{p['combo']}</b>")

    lnk = affiliate(p['link']) if p.get('link') else "#"
    lines += ["", f"🔗 <a href='{lnk}'>👉 GRAB THIS DEAL</a>", "",
              f"📦 Source: {p['source']}",
              f"⏰ {datetime.now().strftime('%d %b %Y %I:%M %p IST')}",
              "#deals #sale #discount"]
    return "\n".join(lines)

# ── TRENDING ──────────────────────────────────────────────────────────────────
def run_trending():
    logger.info("Fetching Google Trends...")
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl='en-IN', tz=330, timeout=(10,25))
        df = pt.trending_searches(pn='india')
        if df is None or df.empty:
            logger.warning("No trends data"); return

        skip = ['ipl','match','vs','election','news','death','accident','score','weather']
        trends = [t for t in df[0].tolist()[:15]
                  if not any(s in t.lower() for s in skip)]
        if not trends:
            logger.warning("No product trends"); return

        top = trends[0]
        link = affiliate(f"https://www.amazon.in/s?k={urllib.parse.quote(top)}")
        others = ", ".join(trends[1:5])

        msg = f"""🔥 <b>TRENDING IN INDIA TODAY</b> 🔥

📈 <b>#{top.replace(' ','_')}</b> is trending on Google India!

🛒 Shop now:
🔗 <a href='{link}'>👉 {top.upper()} — Best Deals</a>

📊 Also trending: {others}

⏰ {datetime.now().strftime('%d %b %Y %I:%M %p IST')}
#trending #googletrends #dealstoday"""
        tg_send(msg)
        logger.info(f"Trending sent: {top}")
    except Exception as e:
        logger.error(f"Trending error: {e}")

# ── MAIN ──────────────────────────────────────────────────────────────────────
def run_deals():
    logger.info("="*50)
    logger.info("E-COMMERCE DEALS BOT STARTING")
    logger.info(f"TOKEN  : {'SET' if TELEGRAM_BOT_TOKEN else '❌ MISSING'}")
    logger.info(f"CHANNEL: {TELEGRAM_CHANNEL_ID or '❌ MISSING'}")
    logger.info(f"EARNKARO: {'SET' if EARNKARO_API_KEY else 'not set'}")
    logger.info("="*50)

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
        raise ValueError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHANNEL_ID!")

    if not tg_validate():
        raise ValueError("Bot token is INVALID — update the secret on GitHub!")

    # Startup ping
    tg_send(f"🤖 <b>Deals Bot Running!</b>\n⏰ {datetime.now().strftime('%d %b %Y %I:%M %p IST')}\n🔍 Scanning deals now...")

    # Fetch from all feeds
    all_deals = []
    for name, url in FEEDS:
        try:
            found = parse_feed(name, url)
            all_deals += found
            logger.info(f"{name}: {len(found)} qualifying deals")
        except Exception as e:
            logger.error(f"{name} error: {e}")

    # Remove duplicates by title similarity
    seen = set()
    unique = []
    for d in all_deals:
        key = d['title'][:40].lower()
        if key not in seen:
            seen.add(key)
            unique.append(d)

    logger.info(f"Total unique deals: {len(unique)}")

    if not unique:
        tg_send("ℹ️ <b>No deals</b> matching 40%+ discount found this run.\n🔄 Next check in 30 minutes.")
        return

    # Sort: ₹1 first, then by discount %
    unique.sort(key=lambda x: (not x.get('is_one_rs'), -(x.get('pct') or 0)))

    sent = 0
    for deal in unique[:15]:
        try:
            if deal.get('is_one_rs'):
                badge = "🤯 <b>₹1 DEAL — ALMOST FREE!</b>"
            elif (deal.get('pct') or 0) >= 80:
                badge = "🔥 <b>MEGA DEAL — 80%+ OFF!</b>"
            elif (deal.get('pct') or 0) >= 60:
                badge = "💥 <b>HOT DEAL ALERT</b>"
            else:
                badge = "💰 <b>DEAL ALERT</b>"

            ok = tg_send(fmt(deal, badge), deal.get('image') or None)
            if ok:
                sent += 1
                time.sleep(2)
        except Exception as e:
            logger.error(f"Send error: {e}")

    tg_send(f"✅ <b>Done!</b> Sent <b>{sent} deals</b> this run.\n🕐 Next check in 30 mins.")
    logger.info(f"Finished: {sent}/{len(unique)} sent")

if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "deals"
    if mode == "trending":
        if tg_validate(): run_trending()
    elif mode == "combo":
        if tg_validate():
            all_d = []
            for n, u in FEEDS:
                all_d += parse_feed(n, u)
            combos = [d for d in all_d if d.get('combo')]
            if combos:
                best = sorted(combos, key=lambda x: x.get('pct') or 0, reverse=True)[0]
                tg_send(fmt(best, "🎁 <b>COMBO / BOGO DEAL OF THE DAY</b> 🎁"), best.get('image'))
            else:
                logger.info("No combo deals today")
    else:
        run_deals()
