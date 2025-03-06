
import requests
import json
import logging
from datetime import datetime
import sys
import os

# Log yapılandırması
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('webhook_test')
handler = logging.FileHandler('webhook_test.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Webhook URL'leri
REPLIT_DOMAIN = os.environ.get("REPL_SLUG")
REPLIT_OWNER = os.environ.get("REPL_OWNER")
BASE_URL = f"https://{REPLIT_DOMAIN}-{REPLIT_OWNER}.repl.co" if REPLIT_DOMAIN and REPLIT_OWNER else "https://sadasdadsa-apdurrahmankuli.replit.app"

ORDER_WEBHOOK_URL = f"{BASE_URL}/webhook/orders"
PRODUCT_WEBHOOK_URL = f"{BASE_URL}/webhook/products"

# Webhook API Key
API_KEY = "test_api_key"  # webhook_service.py dosyasında belirtilen WEBHOOK_SECRET ile aynı olmalı

def check_webhook_status():
    """
    Webhook'ların durumunu kontrol eder
    """
    logger.info("Webhook durumu kontrol ediliyor...")
    
    try:
        import register_webhooks
        status_info = register_webhooks.check_webhook_status()
        
        logger.info(f"Toplam {status_info.get('total_webhooks', 0)} webhook kayıtlı")
        
        # Webhook detaylarını göster
        webhook_details = status_info.get('webhook_details', [])
        for webhook in webhook_details:
            logger.info(f"Webhook ID: {webhook.get('id')}")
            logger.info(f"Durum: {webhook.get('status')}")
            logger.info(f"URL: {webhook.get('url')}")
        
        # Bağlantı testi
        if webhook_details and webhook_details[0].get('url'):
            webhook_url = webhook_details[0].get('url')
            logger.info(f"Webhook bağlantı testi başlatılıyor: {webhook_url}")
            
            try:
                response = requests.get(webhook_url.replace('/orders', ''), timeout=5)
                logger.info(f"Bağlantı yanıtı: HTTP {response.status_code}")
                
                if response.status_code == 200:
                    logger.info("✅ Webhook endpoint'i erişilebilir")
                else:
                    logger.error(f"❌ Webhook endpoint'i hata döndürdü: HTTP {response.status_code}")
            except Exception as e:
                logger.error(f"❌ Bağlantı hatası: {str(e)}")
                
        return status_info
        
    except Exception as e:
        logger.error(f"Webhook durumu kontrol edilirken hata: {str(e)}")
        return None

def test_order_webhook():
    """
    Sipariş webhook'unu test eder
    """
    logger.info(f"Sipariş webhook testi başlatılıyor: {ORDER_WEBHOOK_URL}")
    
    # Örnek bir sipariş webhook verisi
    data = {
        "orderNumber": f"TEST{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "shipmentPackageStatus": "CREATED",
        "order": {
            "id": f"TEST{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "orderNumber": f"TEST{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "status": "Created",
            "orderDate": datetime.now().isoformat(),
            "customerEmail": "test@example.com",
            "customerFirstName": "Test",
            "customerLastName": "User",
            "customerPhone": "5551234567",
            "totalPrice": 150.0,
            "totalDiscount": 0,
            "invoiceAddress": {
                "address": "Test Adres",
                "city": "İstanbul",
                "district": "Kadıköy",
                "fullName": "Test User"
            },
            "lines": [
                {
                    "lineId": "123456",
                    "quantity": 1,
                    "salesCampaignId": 0,
                    "merchantId": 123,
                    "merchantSku": "TEST-SKU-001",
                    "productSize": "M",
                    "productColor": "Siyah",
                    "price": 150.0,
                    "barcode": "TEST-BARCODE-001",
                    "title": "Test Ürün"
                }
            ]
        }
    }

    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }

    logger.info(f"Test webhook verisi gönderiliyor: {data}")

    try:
        response = requests.post(ORDER_WEBHOOK_URL, json=data, headers=headers, timeout=10)
        logger.info(f"Webhook yanıtı: Status {response.status_code}, Yanıt: {response.text}")
        
        if response.status_code == 200:
            logger.info("✅ Sipariş webhook testi başarılı!")
            return True
        else:
            logger.error(f"❌ Sipariş webhook testi başarısız. Status: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"⚠️ Sipariş webhook test hatası: {str(e)}")
        return False

def test_product_webhook():
    """
    Ürün webhook'unu test eder
    """
    logger.info(f"Ürün webhook testi başlatılıyor: {PRODUCT_WEBHOOK_URL}")
    
    # Örnek bir ürün webhook verisi
    data = {
        "product": {
            "barcode": f"TEST-BARCODE-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "title": "Test Ürün",
            "productMainId": "12345",
            "categoryId": "1001",
            "categoryName": "Test Kategori",
            "quantity": 10,
            "listPrice": 200.0,
            "salePrice": 180.0,
            "vatRate": 18,
            "brand": "Test Marka",
            "color": "Siyah",
            "size": "M",
            "stockCode": "TEST-STOCK-001",
            "images": ["https://example.com/test-image.jpg"]
        }
    }

    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }
    
    logger.info(f"Test ürün webhook verisi gönderiliyor: {data}")
    
    try:
        response = requests.post(PRODUCT_WEBHOOK_URL, json=data, headers=headers, timeout=10)
        logger.info(f"Ürün webhook yanıtı: Status {response.status_code}, Yanıt: {response.text}")
        
        if response.status_code == 200:
            logger.info("✅ Ürün webhook testi başarılı!")
            return True
        else:
            logger.error(f"❌ Ürün webhook testi başarısız. Status: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"⚠️ Ürün webhook test hatası: {str(e)}")
        return False

def check_dns_resolution(domain):
    """
    Belirtilen domain'in DNS çözümlemesini test eder
    """
    import socket
    logger.info(f"DNS çözümleme testi: {domain}")
    
    try:
        ip = socket.gethostbyname(domain)
        logger.info(f"✅ DNS çözümleme başarılı: {domain} -> {ip}")
        return True
    except socket.gaierror:
        logger.error(f"❌ DNS çözümleme hatası: {domain}")
        return False

def check_direct_connectivity():
    """
    Replit URL'nin doğrudan erişilebilirliğini test eder
    """
    domain = BASE_URL.replace("https://", "")
    
    import socket
    logger.info(f"Doğrudan bağlantı testi: {domain}")
    
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((domain, 443))
        s.close()
        logger.info(f"✅ Doğrudan bağlantı başarılı: {domain}:443")
        return True
    except Exception as e:
        logger.error(f"❌ Doğrudan bağlantı hatası: {str(e)}")
        return False

def update_webhook_url_in_database():
    """
    Webhook URL'lerini veritabanında günceller
    """
    try:
        import register_webhooks
        order_webhook = register_webhooks.register_webhook('order', ORDER_WEBHOOK_URL)
        
        if order_webhook:
            if register_webhooks.activate_webhook(order_webhook):
                logger.info(f"✅ Webhook kaydedildi ve aktifleştirildi: {ORDER_WEBHOOK_URL}")
                return True
            else:
                logger.error("❌ Webhook aktifleştirilemedi")
        else:
            logger.error("❌ Webhook kaydedilemedi")
        
        return False
    except Exception as e:
        logger.error(f"❌ Webhook URL güncelleme hatası: {str(e)}")
        return False

if __name__ == "__main__":
    print("=============================================")
    print("   TRENDYOL WEBHOOK TEST ARACI   ")
    print("=============================================")
    print(f"Kullanılan ana URL: {BASE_URL}")
    print(f"Sipariş webhook URL: {ORDER_WEBHOOK_URL}")
    print(f"Ürün webhook URL: {PRODUCT_WEBHOOK_URL}")
    print("=============================================")
    print("1. Webhook durumunu kontrol et")
    print("2. Sipariş webhook testi")
    print("3. Ürün webhook testi")
    print("4. Her iki webhook'u da test et")
    print("5. Tüm bağlantı testlerini çalıştır")
    print("6. Webhook URL'lerini güncelle")
    print("q. Çıkış")
    
    choice = input("\nSeçiminiz (1/2/3/4/5/6/q): ")
    
    if choice == "1":
        check_webhook_status()
    elif choice == "2":
        test_order_webhook()
    elif choice == "3":
        test_product_webhook()
    elif choice == "4":
        test_order_webhook()
        print("\n")
        test_product_webhook()
    elif choice == "5":
        domain = BASE_URL.replace("https://", "")
        check_dns_resolution(domain)
        check_direct_connectivity()
        check_webhook_status()
        test_order_webhook()
        test_product_webhook()
    elif choice == "6":
        update_webhook_url_in_database()
    elif choice.lower() == "q":
        print("Programdan çıkılıyor...")
    else:
        print("Geçersiz seçim!")
