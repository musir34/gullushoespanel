
import base64
import requests
import logging
from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID, BASE_URL, ORDER_WEBHOOK_URL, PRODUCT_WEBHOOK_URL, WEBHOOK_SECRET

# Loglama ayarları
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def webhook_kaydet():
    """
    Trendyol API'sine webhook kaydı yapar
    """
    try:
        # Authentication header'ı oluştur (Base64 ile kodlanmış)
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')
        
        # API endpointi ve headers
        url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/webhooks"
        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json"
        }
        
        # Sipariş webhook'u için veri
        siparis_payload = {
            "name": "OrderWebhook",
            "url": ORDER_WEBHOOK_URL,
            "authToken": WEBHOOK_SECRET,  # Webhook güvenlik anahtarı
            "events": ["OrderCreated", "OrderStatusChanged", "PackageStatusChanged"]
        }
        
        # Ürün webhook'u için veri
        urun_payload = {
            "name": "ProductWebhook",
            "url": PRODUCT_WEBHOOK_URL,
            "authToken": WEBHOOK_SECRET,  # Webhook güvenlik anahtarı
            "events": ["ProductCreated", "ProductUpdated", "PriceChanged", "StockChanged"]
        }
        
        # Sipariş webhook'unu kaydet
        logger.info(f"Sipariş webhook kaydı yapılıyor: {ORDER_WEBHOOK_URL}")
        siparis_response = requests.post(url, headers=headers, json=siparis_payload)
        
        # Ürün webhook'unu kaydet
        logger.info(f"Ürün webhook kaydı yapılıyor: {PRODUCT_WEBHOOK_URL}")
        urun_response = requests.post(url, headers=headers, json=urun_payload)
        
        # Yanıtları kontrol et
        if siparis_response.status_code in (200, 201):
            logger.info("Sipariş webhook kaydı başarılı")
            print(f"Sipariş webhook kaydı başarılı: {siparis_response.json()}")
        else:
            logger.error(f"Sipariş webhook kaydı başarısız! Durum kodu: {siparis_response.status_code}")
            print(f"Sipariş webhook kaydı başarısız: {siparis_response.text}")
        
        if urun_response.status_code in (200, 201):
            logger.info("Ürün webhook kaydı başarılı")
            print(f"Ürün webhook kaydı başarılı: {urun_response.json()}")
        else:
            logger.error(f"Ürün webhook kaydı başarısız! Durum kodu: {urun_response.status_code}")
            print(f"Ürün webhook kaydı başarısız: {urun_response.text}")
            
    except Exception as e:
        logger.error(f"Webhook kaydında hata: {str(e)}")
        print(f"Webhook kaydında hata: {str(e)}")

if __name__ == "__main__":
    print("Trendyol webhook'ları kaydediliyor...")
    webhook_kaydet()
    print("İşlem tamamlandı!")
