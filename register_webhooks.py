
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

def register_webhook(webhook_type, webhook_url, max_retries=3):
    """
    Trendyol API'sine webhook kaydı yapar
    
    Args:
        webhook_type: Webhook tipi ('order' veya 'product')
        webhook_url: Webhook URL'i
        max_retries: Maksimum yeniden deneme sayısı
    
    Returns:
        bool: İşlem başarılıysa True, değilse False
    """
    retry_count = 0
    while retry_count < max_retries:
        try:
            # API kimlik bilgilerini kontrol et
            if not API_KEY or not API_SECRET or not SUPPLIER_ID:
                logger.error("API kimlik bilgileri tanımlanmamış. Lütfen API_KEY, API_SECRET ve SUPPLIER_ID değerlerini kontrol edin.")
                return False
                
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
            logger.debug(f"API URL: {url}")
            
            # POST isteği gönder
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            
            # Yanıtı kontrol et
            if response.status_code in (200, 201):
                logger.info(f"Webhook kaydı başarılı: {webhook_type}")
                logger.debug(f"API Yanıtı: {response.json() if response.text else 'Boş yanıt'}")
                return True
            elif response.status_code == 556:  # Service Unavailable
                retry_count += 1
                logger.warning(f"Webhook kaydı yapılamadı (Servis Kullanılamıyor)! Yeniden deneme: {retry_count}/{max_retries}")
                # Yeniden denemeden önce bekle
                import time
                time.sleep(2 ** retry_count)  # Exponential backoff
                continue
            else:
                logger.error(f"Webhook kaydı başarısız! Durum kodu: {response.status_code}")
                logger.error(f"API Yanıtı: {response.text}")
                return False
                
        except requests.exceptions.Timeout:
            retry_count += 1
            logger.warning(f"Webhook kaydı zaman aşımına uğradı. Yeniden deneme: {retry_count}/{max_retries}")
            import time
            time.sleep(2)
        except Exception as e:
            logger.error(f"Webhook kaydında hata: {str(e)}")
            return False
    
    logger.error(f"Webhook kaydı yapılamadı! Maksimum yeniden deneme sayısına ({max_retries}) ulaşıldı.")
    return False

def get_registered_webhooks(max_retries=3):
    """
    Mevcut kayıtlı webhook'ları listeler
    
    Args:
        max_retries: Maksimum yeniden deneme sayısı
    
    Returns:
        list: Kayıtlı webhook listesi veya hata durumunda boş liste
    """
    retry_count = 0
    while retry_count < max_retries:
        try:
            # Authentication header'ı oluştur
            auth_str = f"{API_KEY}:{API_SECRET}"
            b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')
            
            # API kimlik bilgilerini kontrol et
            if not API_KEY or not API_SECRET or not SUPPLIER_ID:
                logger.error("API kimlik bilgileri tanımlanmamış. Lütfen API_KEY, API_SECRET ve SUPPLIER_ID değerlerini kontrol edin.")
                logger.debug(f"API_KEY: {'Tanımlı' if API_KEY else 'Tanımlı değil'}")
                logger.debug(f"API_SECRET: {'Tanımlı' if API_SECRET else 'Tanımlı değil'}")
                logger.debug(f"SUPPLIER_ID: {'Tanımlı' if SUPPLIER_ID else 'Tanımlı değil'}")
                return []
            
            # API endpointi ve headers
            url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/webhooks"
            headers = {
                "Authorization": f"Basic {b64_auth_str}",
                "Content-Type": "application/json"
            }
            
            # GET isteği gönder
            logger.info("Kayıtlı webhook'lar getiriliyor")
            logger.debug(f"API URL: {url}")
            logger.debug(f"Headers: {headers}")
            
            response = requests.get(url, headers=headers, timeout=10)
            
            # Yanıtı kontrol et
            if response.status_code == 200:
                webhooks = response.json()
                logger.info(f"Toplam {len(webhooks)} webhook bulundu")
                return webhooks
            elif response.status_code == 556:  # Service Unavailable
                retry_count += 1
                logger.warning(f"Webhook'lar getirilemedi (Servis Kullanılamıyor)! Yeniden deneme: {retry_count}/{max_retries}")
                # Yeniden denemeden önce bekle (exponential backoff)
                import time
                time.sleep(2 ** retry_count)
                continue
            else:
                logger.error(f"Webhook'lar getirilemedi! Durum kodu: {response.status_code}")
                logger.error(f"API Yanıtı: {response.text}")
                return []
                
        except requests.exceptions.Timeout:
            retry_count += 1
            logger.warning(f"Webhook isteği zaman aşımına uğradı. Yeniden deneme: {retry_count}/{max_retries}")
            import time
            time.sleep(2)
        except Exception as e:
            logger.error(f"Webhook'ları getirirken hata: {str(e)}")
            return []
    
    logger.error(f"Webhook'lar getirilemedi! Maksimum yeniden deneme sayısına ({max_retries}) ulaşıldı.")
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
