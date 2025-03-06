import os
import secrets

# Trendyol API bilgileri
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
SUPPLIER_ID = os.getenv("SUPPLIER_ID")  # SATICI ID

# Webhook güvenlik anahtarı (eğer çevre değişkeni yoksa rastgele oluştur)
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET") or secrets.token_hex(16)

# Trendyol API için temel URL
BASE_URL = "https://api.trendyol.com/sapigw/"

# Webhook URL'leri
# Replit'in web URL'sini almak için os.environ'dan Replit domain'ini alıyoruz
REPLIT_SLUG = os.getenv("REPL_SLUG", "")
REPLIT_OWNER = os.getenv("REPL_OWNER", "")
# Eğer Replit ortamındaysak Replit URL'ini kullan, değilse çevre değişkeninden oku
if REPLIT_SLUG and REPLIT_OWNER:
    WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", f"https://{REPLIT_SLUG}.{REPLIT_OWNER}.repl.co")
else:
    WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "https://your-domain.com")

ORDER_WEBHOOK_URL = f"{WEBHOOK_BASE_URL}/webhook/orders"
PRODUCT_WEBHOOK_URL = f"{WEBHOOK_BASE_URL}/webhook/products"
