
import requests
import base64
import json
import logging
from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID, BASE_URL, ORDER_WEBHOOK_URL, PRODUCT_WEBHOOK_URL, WEBHOOK_SECRET

# Loglama ayarları
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='webhook_registration.log'
)
logger = logging.getLogger(__name__)

def register_webhook(webhook_type, webhook_url):
    """
    Trendyol API'sine webhook kaydı yapar
    
    Args:
        webhook_type: Webhook tipi ('order' veya 'product')
        webhook_url: Webhook URL'i
    
    Returns:
        bool: İşlem başarılıysa True, değilse False
    """
    try:
        # Authentication header'ı oluştur
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')
        
        # API endpointi ve headers
        url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/webhooks"
        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json"
        }
        
        # Webhook tipi için uygun API payload'ını oluştur
        if webhook_type == 'order':
            events = ["OrderCreated", "OrderStatusChanged", "PackageStatusChanged"]
            name = "OrderWebhook"
        elif webhook_type == 'product':
            events = ["ProductCreated", "ProductUpdated", "PriceChanged", "StockChanged"]
            name = "ProductWebhook"
        else:
            logger.error(f"Bilinmeyen webhook tipi: {webhook_type}")
            return False
        
        # API isteği için veri
        payload = {
            "name": name,
            "url": webhook_url,
            "authToken": WEBHOOK_SECRET,  # Webhook güvenlik anahtarı
            "events": events
        }
        
        logger.info(f"Webhook kaydı yapılıyor: {webhook_type} - {webhook_url}")
        logger.debug(f"Payload: {payload}")
        
        # POST isteği gönder
        response = requests.post(url, headers=headers, json=payload)
        
        # Yanıtı kontrol et
        if response.status_code in (200, 201):
            logger.info(f"Webhook kaydı başarılı: {webhook_type}")
            logger.debug(f"API Yanıtı: {response.json()}")
            return True
        else:
            logger.error(f"Webhook kaydı başarısız! Durum kodu: {response.status_code}")
            logger.error(f"API Yanıtı: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Webhook kaydında hata: {str(e)}")
        return False

def get_registered_webhooks():
    """
    Mevcut kayıtlı webhook'ları listeler
    
    Returns:
        list: Kayıtlı webhook listesi veya hata durumunda boş liste
    """
    try:
        # Authentication header'ı oluştur
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')
        
        # API endpointi ve headers
        url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/webhooks"
        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json"
        }
        
        # GET isteği gönder
        logger.info("Kayıtlı webhook'lar getiriliyor")
        response = requests.get(url, headers=headers)
        
        # Yanıtı kontrol et
        if response.status_code == 200:
            webhooks = response.json()
            logger.info(f"Toplam {len(webhooks)} webhook bulundu")
            return webhooks
        else:
            logger.error(f"Webhook'lar getirilemedi! Durum kodu: {response.status_code}")
            logger.error(f"API Yanıtı: {response.text}")
            return []
            
    except Exception as e:
        logger.error(f"Webhook'ları getirirken hata: {str(e)}")
        return []

def delete_webhook(webhook_id):
    """
    Kayıtlı bir webhook'u siler
    
    Args:
        webhook_id: Silinecek webhook ID'si
    
    Returns:
        bool: İşlem başarılıysa True, değilse False
    """
    try:
        # Authentication header'ı oluştur
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')
        
        # API endpointi ve headers
        url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/webhooks/{webhook_id}"
        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json"
        }
        
        # DELETE isteği gönder
        logger.info(f"Webhook siliniyor: {webhook_id}")
        response = requests.delete(url, headers=headers)
        
        # Yanıtı kontrol et
        if response.status_code == 200:
            logger.info(f"Webhook başarıyla silindi: {webhook_id}")
            return True
        else:
            logger.error(f"Webhook silinemedi! Durum kodu: {response.status_code}")
            logger.error(f"API Yanıtı: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Webhook silinirken hata: {str(e)}")
        return False

if __name__ == "__main__":
    # Mevcut webhook'ları listele
    print("Mevcut webhook'lar listeleniyor...")
    webhooks = get_registered_webhooks()
    for i, webhook in enumerate(webhooks, 1):
        print(f"{i}. {webhook.get('name')} - {webhook.get('url')}")
        print(f"   Olaylar: {', '.join(webhook.get('events', []))}")
        print(f"   ID: {webhook.get('id')}")
        print("-" * 50)
    
    # Yeni webhook'ları kaydet
    print("\nYeni webhook'lar kaydediliyor...")
    
    # Sipariş webhook'u
    order_result = register_webhook('order', ORDER_WEBHOOK_URL)
    print(f"Sipariş webhook kaydı: {'Başarılı' if order_result else 'Başarısız'}")
    
    # Ürün webhook'u
    product_result = register_webhook('product', PRODUCT_WEBHOOK_URL)
    print(f"Ürün webhook kaydı: {'Başarılı' if product_result else 'Başarısız'}")
    
    print("\nİşlem tamamlandı!")
