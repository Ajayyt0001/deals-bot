"""
E-Commerce Deals Telegram Bot
Monitors deals from multiple platforms and sends notifications
"""

import os
import re
import json
import time
import logging
import requests
import feedparser
from datetime import datetime, timedelta
from pytrends.request import TrendReq

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ─── CONFIG (set as GitHub Secrets / Environment Variables) ───────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")
EARNKARO_API_KEY = os.environ.get("EARNKARO_API_KEY", "")

MIN_DISCOUNT = 40       # Minimum discount % to alert
MAX_DISCOUNT = 99       # Maximum discount % to alert
ONE_RUPEE_THRESHOLD = 2 # Alert if price <= ₹1 (use 2 for safety margin)

# ─── DEAL SOURCES (RSS Feeds — no API key needed) ────────────────────────────
DEAL_FEEDS = [
    {
        "name": "Desidime",
        "url": "https://www.desidime.com/deals.rss",
        "type": "rss"
    },
    {
        "name": "Dealnloot", 
        "url": "https://www.dealnloot.com/feed",
        "type": "rss"
    },
    {
        "name": "Dealsucker",
        "url": "https://dealsucker.in/feed/",
        "type": "rss"
    },
    {
        "name": "GrabOn",
        "url": "https://www.grabon.in/deals/feed/",
        "type": "rss"
    },
]

# ─── PLATFORM KEYWORDS ────────────────────────────────────────────────────────
PLATFORM_KEYWORDS = {
    "amazon": "🛒 Amazon",
    "flipkart": "🛍️ Flipkart",
    "myntra": "👗 Myntra",
    "meesho": "🛒 Meesho",
    "ajio": "👔 Ajio",
    "nykaa": "💄 Nykaa",
    "zepto": "⚡ Zepto",
    "blinkit": "🟡 Blinkit",
    "instamart": "🟠 Instamart",
    "jiomart": "🔵 JioMart",
    "tatacliq": "🔷 Tata Cliq",
    "snapdeal": "💢 Snapdeal",
    "bigbasket": "🟢 BigBasket",
    "shein": "✨ SHEIN",
}

COMBO_KEYWORDS = [
    "buy 1 get 1", "bogo", "buy one get one", "combo", "bundle",
    "pack of 2", "pack of 3", "pack of 4", "set of", "2 in 1",
    "free with", "get free", "combo pack", "value pack",
    "buy 2 get 1", "buy 3 get 1", "buy 2 get 2"
]

# ─── EARNKARO AFFILIATE LINK CONVERTER ───────────────────────────────────────
def get_affiliate_link(product_url: str) -> str:
    """Convert product URL to EarnKaro affiliate link"""
    try:
        if not EARNKARO_API_KEY:
            return product_url
        
        api_url = "https://api.earnkaro.com/v2/getAffiliateLink"
        headers = {
            "Authorization": f"Bearer {EARNKARO_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {"url": product_url}
        
        resp = requests.post(api_url, json=payload, headers=headers, timeout=10)
        data = resp.json()
        
        if data.get("status") == "success" and data.get("affiliateUrl"):
            return data["affiliateUrl"]
        else:
            logger.warning(f"EarnKaro API: {data}")
            return product_url
    except Exception as e:
        logger.error(f"EarnKaro error: {e}")
        return product_url

# ─── PRICE PARSER ─────────────────────────────────────────────────────────────
def extract_prices(text: str):
    """Extract original price, discounted price, and discount % from text"""
    # Find prices like ₹999, Rs.999, INR 999
    price_pattern = r'(?:₹|Rs\.?|INR\s*)\s*(\d+(?:,\d+)*(?:\.\d+)?)'
    prices = re.findall(price_pattern, text, re.IGNORECASE)
    prices = [int(p.replace(',', '').split('.')[0]) for p in prices]
    
    # Find discount % like 50% off, 75% discount
    discount_pattern = r'(\d+)\s*%\s*(?:off|discount|cashback)'
    discounts = re.findall(discount_pattern, text, re.IGNORECASE)
    discounts = [int(d) for d in discounts]
    
    original_price = max(prices) if prices else None
    discounted_price = min(prices) if len(prices) > 1 else None
    discount_pct = max(discounts) if discounts else None
    
    # Calculate discount if not found
    if original_price and discounted_price and not discount_pct:
        if original_price > 0:
            discount_pct = int(((original_price - discounted_price) / original_price) * 100)
    
    return original_price, discounted_price, discount_pct

# ─── DETECT PLATFORM ──────────────────────────────────────────────────────────
def detect_platform(text: str, url: str = "") -> str:
    combined = (text + " " + url).lower()
    for key, label in PLATFORM_KEYWORDS.items():
        if key in combined:
            return label
    return "🛒 Online Store"

# ─── DETECT COMBO DEAL ────────────────────────────────────────────────────────
def is_combo_deal(text: str) -> tuple:
    text_lower = text.lower()
    for keyword in COMBO_KEYWORDS:
        if keyword in text_lower:
            return True, keyword.upper()
    return False, None

# ─── FETCH IMAGE FROM URL ─────────────────────────────────────────────────────
def extract_image_from_entry(entry) -> str:
    """Try to get image URL from RSS entry"""
    # Try media content
    if hasattr(entry, 'media_content') and entry.media_content:
        return entry.media_content[0].get('url', '')
    
    # Try enclosures
    if hasattr(entry, 'enclosures') and entry.enclosures:
        for enc in entry.enclosures:
            if 'image' in enc.get('type', ''):
                return enc.get('url', '')
    
    # Try to extract from summary HTML
    if hasattr(entry, 'summary'):
        img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', entry.summary)
        if img_match:
            return img_match.group(1)
    
    return ""

# ─── SEND TELEGRAM MESSAGE ────────────────────────────────────────────────────
def send_telegram_photo(image_url: str, caption: str):
    """Send photo with caption to Telegram channel"""
    try:
        if image_url:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            payload = {
                "chat_id": TELEGRAM_CHANNEL_ID,
                "photo": image_url,
                "caption": caption,
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            }
        else:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": TELEGRAM_CHANNEL_ID,
                "text": caption,
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            }
        
        resp = requests.post(url, json=payload, timeout=15)
        result = resp.json()
        
        if not result.get("ok"):
            # If photo fails, fall back to text
            if image_url and "wrong file identifier" in str(result):
                return send_telegram_photo("", caption)
            logger.error(f"Telegram error: {result}")
            return False
        return True
    except Exception as e:
        logger.error(f"Telegram send error: {e}")
        return False

# ─── FORMAT DEAL MESSAGE ──────────────────────────────────────────────────────
def format_deal_message(title, platform, original_price, discounted_price, 
                         discount_pct, affiliate_link, badge="", deal_type=""):
    lines = []
    
    if badge:
        lines.append(badge)
    
    lines.append(f"<b>{title[:200]}</b>")
    lines.append(f"")
    lines.append(f"🏪 Platform: {platform}")
    
    if discounted_price and discounted_price <= 1:
        lines.append(f"💰 Price: <b>₹{discounted_price} 🤯 (ALMOST FREE!)</b>")
    elif discounted_price:
        lines.append(f"💰 Price: <s>₹{original_price}</s> → <b>₹{discounted_price}</b>")
    elif original_price:
        lines.append(f"💰 Price: <b>₹{original_price}</b>")
    
    if discount_pct:
        if discount_pct >= 80:
            lines.append(f"🔥 Discount: <b>{discount_pct}% OFF</b> 🔥")
        elif discount_pct >= 60:
            lines.append(f"💥 Discount: <b>{discount_pct}% OFF</b>")
        else:
            lines.append(f"📉 Discount: <b>{discount_pct}% OFF</b>")
    
    if deal_type:
        lines.append(f"🎁 Deal Type: <b>{deal_type}</b>")
    
    lines.append(f"")
    lines.append(f"🔗 <a href='{affiliate_link}'>👉 GRAB THIS DEAL</a>")
    lines.append(f"")
    lines.append(f"⏰ {datetime.now().strftime('%d %b %Y, %I:%M %p')}")
    lines.append(f"#deals #discount #sale #{platform.split()[-1].lower()}")
    
    return "\n".join(lines)

# ─── FETCH & PROCESS DEALS ────────────────────────────────────────────────────
def fetch_deals():
    """Fetch deals from all RSS feeds and filter by discount"""
    all_deals = []
    
    for source in DEAL_FEEDS:
        try:
            logger.info(f"Fetching from {source['name']}...")
            feed = feedparser.parse(source['url'])
            
            for entry in feed.entries[:30]:  # Check last 30 entries per feed
                title = entry.get('title', '')
                summary = entry.get('summary', '')
                link = entry.get('link', '')
                image = extract_image_from_entry(entry)
                
                full_text = f"{title} {summary}"
                
                # Extract prices and discount
                original_price, discounted_price, discount_pct = extract_prices(full_text)
                
                # Check ₹1 deal
                is_one_rupee = discounted_price and discounted_price <= ONE_RUPEE_THRESHOLD
                
                # Check discount range
                is_valid_discount = discount_pct and MIN_DISCOUNT <= discount_pct <= MAX_DISCOUNT
                
                if is_valid_discount or is_one_rupee:
                    platform = detect_platform(full_text, link)
                    is_combo, combo_type = is_combo_deal(full_text)
                    
                    all_deals.append({
                        "title": title,
                        "summary": summary,
                        "link": link,
                        "image": image,
                        "platform": platform,
                        "original_price": original_price,
                        "discounted_price": discounted_price,
                        "discount_pct": discount_pct,
                        "is_one_rupee": is_one_rupee,
                        "is_combo": is_combo,
                        "combo_type": combo_type,
                        "source": source['name']
                    })
            
            time.sleep(1)  # Polite delay between feeds
            
        except Exception as e:
            logger.error(f"Error fetching {source['name']}: {e}")
    
    return all_deals

# ─── GOOGLE TRENDING PRODUCT ──────────────────────────────────────────────────
def get_trending_product():
    """Get top Google trending product in India and find a deal for it"""
    try:
        pytrends = TrendReq(hl='en-IN', tz=330, timeout=(10, 25))
        
        # Get trending searches in India
        trending = pytrends.trending_searches(pn='india')
        
        if trending is None or trending.empty:
            return None
        
        # Filter for product-like trends (exclude news/events)
        trending_list = trending[0].tolist()[:10]
        
        product_keywords = []
        for term in trending_list:
            term_lower = term.lower()
            # Skip news/sports/political terms
            skip_words = ['ipl', 'match', 'vs', 'election', 'news', 'death', 'accident', 'weather']
            if not any(skip in term_lower for skip in skip_words):
                product_keywords.append(term)
        
        if not product_keywords:
            return None
        
        top_trend = product_keywords[0]
        logger.info(f"Top trending: {top_trend}")
        
        # Search for this product on Amazon via affiliate search URL
        amazon_search = f"https://www.amazon.in/s?k={top_trend.replace(' ', '+')}"
        affiliate_link = get_affiliate_link(amazon_search)
        
        return {
            "keyword": top_trend,
            "search_link": affiliate_link,
            "all_trends": trending_list[:5]
        }
    except Exception as e:
        logger.error(f"Google Trends error: {e}")
        return None

# ─── SEND TRENDING ALERT ──────────────────────────────────────────────────────
def send_trending_alert():
    """Send daily trending product alert"""
    trend = get_trending_product()
    if not trend:
        logger.warning("No trending data found")
        return
    
    other_trends = ", ".join(trend['all_trends'][1:5])
    
    message = f"""🔥 <b>TRENDING IN INDIA TODAY</b> 🔥

📈 <b>#{trend['keyword']}</b> is trending on Google!

🛒 Find the best deals for this product:
🔗 <a href='{trend['search_link']}'>👉 SHOP {trend['keyword'].upper()}</a>

📊 Also trending: {other_trends}

⏰ {datetime.now().strftime('%d %b %Y, %I:%M %p')}
#trending #google #dealstoday"""
    
    send_telegram_photo("", message)
    logger.info("Trending alert sent!")

# ─── SEND COMBO DEAL ALERT ────────────────────────────────────────────────────
def send_combo_alert(deals: list):
    """Pick best combo deal and send daily alert"""
    combo_deals = [d for d in deals if d['is_combo']]
    
    if not combo_deals:
        logger.info("No combo deals found today")
        return
    
    # Pick best combo (highest discount)
    best_combo = sorted(combo_deals, key=lambda x: x.get('discount_pct') or 0, reverse=True)[0]
    
    affiliate_link = get_affiliate_link(best_combo['link'])
    
    message = format_deal_message(
        title=best_combo['title'],
        platform=best_combo['platform'],
        original_price=best_combo['original_price'],
        discounted_price=best_combo['discounted_price'],
        discount_pct=best_combo['discount_pct'],
        affiliate_link=affiliate_link,
        badge="🎁 <b>COMBO DEAL OF THE DAY</b> 🎁",
        deal_type=best_combo['combo_type']
    )
    
    send_telegram_photo(best_combo['image'], message)
    logger.info("Combo deal alert sent!")

# ─── MAIN RUNNER ──────────────────────────────────────────────────────────────
def run_deal_alerts():
    """Main function — fetch deals and send alerts"""
    logger.info("Starting deal fetch...")
    deals = fetch_deals()
    logger.info(f"Found {len(deals)} qualifying deals")
    
    sent_count = 0
    
    for deal in deals:
        try:
            affiliate_link = get_affiliate_link(deal['link'])
            
            if deal['is_one_rupee']:
                badge = "🤯 <b>₹1 DEAL ALERT!</b> 🤯"
            elif deal.get('discount_pct', 0) >= 80:
                badge = "🔥 <b>MEGA DEAL ALERT</b> 🔥"
            else:
                badge = "💰 <b>DEAL ALERT</b>"
            
            message = format_deal_message(
                title=deal['title'],
                platform=deal['platform'],
                original_price=deal['original_price'],
                discounted_price=deal['discounted_price'],
                discount_pct=deal['discount_pct'],
                affiliate_link=affiliate_link,
                badge=badge
            )
            
            success = send_telegram_photo(deal['image'], message)
            
            if success:
                sent_count += 1
                logger.info(f"Sent deal: {deal['title'][:50]}")
                time.sleep(3)  # Avoid Telegram rate limiting
            
        except Exception as e:
            logger.error(f"Error sending deal: {e}")
    
    logger.info(f"Done! Sent {sent_count} deal alerts")
    return sent_count

def run_trending():
    """Run trending product alert (called at 9 AM)"""
    logger.info("Running trending alert...")
    send_trending_alert()

def run_combo(deals=None):
    """Run combo deal alert (called at 2 PM)"""
    logger.info("Running combo deal alert...")
    if deals is None:
        deals = fetch_deals()
    send_combo_alert(deals)

# ─── ENTRY POINT ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    
    mode = sys.argv[1] if len(sys.argv) > 1 else "deals"
    
    if mode == "trending":
        run_trending()
    elif mode == "combo":
        run_combo()
    elif mode == "deals":
        run_deal_alerts()
    elif mode == "all":
        deals = fetch_deals()
        send_trending_alert()
        send_combo_alert(deals)
        # Send all deals
        for deal in deals:
            try:
                affiliate_link = get_affiliate_link(deal['link'])
                message = format_deal_message(
                    title=deal['title'],
                    platform=deal['platform'],
                    original_price=deal['original_price'],
                    discounted_price=deal['discounted_price'],
                    discount_pct=deal['discount_pct'],
                    affiliate_link=affiliate_link,
                    badge="💰 <b>DEAL ALERT</b>"
                )
                send_telegram_photo(deal['image'], message)
                time.sleep(3)
            except Exception as e:
                logger.error(f"Error: {e}")
