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
        # Replit URL veya IP'yi alma girişimi
        replit_domain = os.getenv("REPL_SLUG")
        replit_owner = os.getenv("REPL_OWNER")
        
        if replit_domain and replit_owner:
            return f"https://{replit_domain}-{replit_owner}.repl.co"
        
        # Alternatif olarak, genel IP adresi kullanma
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return f"http://{ip}"
    except:
        return "https://sadasdadsa-apdurrahmankuli.replit.app"  # Varsayılan değer

WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", get_public_ip())
ORDER_WEBHOOK_URL = f"{WEBHOOK_BASE_URL}/webhook/orders"
PRODUCT_WEBHOOK_URL = f"{WEBHOOK_BASE_URL}/webhook/products"

# Güncel endpoint temeli (Nisan 2024 sonrası)
API_BASE_URL = "https://apigw.trendyol.com/integration/webhook/sellers/"
