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

# Webhook URL'leri (otomatik domain adı algılama)
import socket
def get_public_ip():
    try:
        # Replit URL kullanma
        return "https://sadasdadsa-apdurrahmankuli.replit.app"
    except:
        return "https://sadasdadsa-apdurrahmankuli.replit.app"  # Varsayılan değer

WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", get_public_ip())
ORDER_WEBHOOK_URL = f"{WEBHOOK_BASE_URL}/webhook/orders"
PRODUCT_WEBHOOK_URL = f"{WEBHOOK_BASE_URL}/webhook/products"

# Güncel endpoint temeli (Nisan 2024 sonrası)
API_BASE_URL = "https://apigw.trendyol.com/integration/webhook/sellers/"
