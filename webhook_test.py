
import requests
import json
import logging
from datetime import datetime
import argparse

# Log yapılandırması
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('webhook_test')

def test_webhook_connection(webhook_url, secret_key):
    """
    Webhook bağlantısını test eder
    """
    logger.info(f"Webhook bağlantı testi başlatılıyor: {webhook_url}")
    
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": secret_key
    }
    
    # Basit bir test mesajı
    test_data = {
        "test": True,
        "timestamp": datetime.now().isoformat(),
        "message": "Bu bir test bildirimdir"
    }
    
    try:
        response = requests.post(webhook_url, json=test_data, headers=headers)
        logger.info(f"Yanıt: HTTP {response.status_code} - {response.text}")
        
        if response.status_code == 200:
            logger.info("✅ Webhook bağlantı testi başarılı!")
            return True
        else:
            logger.error(f"❌ Webhook bağlantı testi başarısız: HTTP {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"❌ Bağlantı hatası: {str(e)}")
        return False

def test_order_webhook(webhook_url, secret_key):
    """
    Sipariş webhook'unu test eder
    """
    logger.info(f"Sipariş webhook testi başlatılıyor: {webhook_url}")
    
    # Webhook API key başlığı ekle
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": secret_key
    }
    
    # Örnek bir sipariş webhook verisi
    order_data = {
        "orderNumber": f"TEST{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "shipmentPackageStatus": "CREATED",
        "order": {
            "id": f"TEST{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "orderNumber": f"TEST{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "status": "Created",
            "orderDate": int(datetime.now().timestamp() * 1000),
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

    try:
        response = requests.post(webhook_url, json=order_data, headers=headers)
        logger.info(f"Yanıt: HTTP {response.status_code} - {response.text[:200]}")
        
        if response.status_code == 200:
            logger.info("✅ Sipariş webhook testi başarılı!")
            return True
        else:
            logger.error(f"❌ Sipariş webhook testi başarısız: HTTP {response.status_code}")
            if response.status_code == 401:
                logger.error("   Kimlik doğrulama hatası - API Key kontrol edin")
            return False
    except Exception as e:
        logger.error(f"❌ Webhook test hatası: {str(e)}")
        return False

def test_product_webhook(webhook_url, secret_key):
    """
    Ürün webhook'unu test eder
    """
    logger.info(f"Ürün webhook testi başlatılıyor: {webhook_url}")
    
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": secret_key
    }
    
    # Örnek bir ürün webhook verisi
    product_data = {
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

    try:
        response = requests.post(webhook_url, json=product_data, headers=headers)
        logger.info(f"Yanıt: HTTP {response.status_code} - {response.text[:200]}")
        
        if response.status_code == 200:
            logger.info("✅ Ürün webhook testi başarılı!")
            return True
        else:
            logger.error(f"❌ Ürün webhook testi başarısız: HTTP {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"❌ Webhook test hatası: {str(e)}")
        return False

def view_webhook_status():
    """
    Webhook durumunu görüntüler
    """
    try:
        from trendyol_api import WEBHOOK_SECRET
        from webhook_service import app_logger
        import register_webhooks
        
        logger.info("Webhook durumu kontrol ediliyor...")
        
        # Kayıtlı webhook'ları al
        webhooks = register_webhooks.get_registered_webhooks()
        logger.info(f"Toplam {len(webhooks)} webhook kayıtlı")
        
        for webhook in webhooks:
            webhook_id = webhook.get('id', '')
            webhook_status = webhook.get('status', '')
            webhook_url = webhook.get('url', '')
            
            logger.info(f"Webhook ID: {webhook_id}")
            logger.info(f"Durum: {webhook_status}")
            logger.info(f"URL: {webhook_url}")
            
            # URL aktif mi kontrol et
            if webhook_url:
                test_webhook_connection(webhook_url, WEBHOOK_SECRET)
        
        return True
    except Exception as e:
        logger.error(f"Webhook durumu görüntülenemedi: {str(e)}")
        return False

def deactivate_all_webhooks():
    """
    Tüm webhook'ları devre dışı bırakır
    """
    try:
        import register_webhooks
        
        webhooks = register_webhooks.get_registered_webhooks()
        logger.info(f"Toplam {len(webhooks)} webhook devre dışı bırakılacak")
        
        for webhook in webhooks:
            webhook_id = webhook.get('id', '')
            if webhook_id:
                result = register_webhooks.deactivate_webhook(webhook_id)
                if result:
                    logger.info(f"Webhook başarıyla devre dışı bırakıldı: {webhook_id}")
                else:
                    logger.error(f"Webhook devre dışı bırakılamadı: {webhook_id}")
        
        return True
    except Exception as e:
        logger.error(f"Webhook'lar devre dışı bırakılırken hata: {str(e)}")
        return False

def activate_all_webhooks():
    """
    Tüm webhook'ları aktifleştirir
    """
    try:
        import register_webhooks
        
        webhooks = register_webhooks.get_registered_webhooks()
        logger.info(f"Toplam {len(webhooks)} webhook aktifleştirilecek")
        
        for webhook in webhooks:
            webhook_id = webhook.get('id', '')
            if webhook_id:
                result = register_webhooks.activate_webhook(webhook_id)
                if result:
                    logger.info(f"Webhook başarıyla aktifleştirildi: {webhook_id}")
                else:
                    logger.error(f"Webhook aktifleştirilemedi: {webhook_id}")
        
        return True
    except Exception as e:
        logger.error(f"Webhook'lar aktifleştirilirken hata: {str(e)}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Trendyol Webhook Test Aracı')
    parser.add_argument('--status', action='store_true', help='Webhook durumunu görüntüle')
    parser.add_argument('--test-order', action='store_true', help='Sipariş webhook\'unu test et')
    parser.add_argument('--test-product', action='store_true', help='Ürün webhook\'unu test et')
    parser.add_argument('--deactivate', action='store_true', help='Tüm webhook\'ları devre dışı bırak')
    parser.add_argument('--activate', action='store_true', help='Tüm webhook\'ları aktifleştir')
    parser.add_argument('--url', help='Webhook URL\'i (varsayılan olarak trendyol_api.py\'den alınır)')
    parser.add_argument('--secret', help='API Key (varsayılan olarak trendyol_api.py\'den alınır)')
    
    args = parser.parse_args()
    
    # Parametreler için trendyol_api modülünü yükle
    from trendyol_api import ORDER_WEBHOOK_URL, PRODUCT_WEBHOOK_URL, WEBHOOK_SECRET
    
    webhook_order_url = args.url if args.url else ORDER_WEBHOOK_URL
    webhook_product_url = args.url if args.url else PRODUCT_WEBHOOK_URL
    secret_key = args.secret if args.secret else WEBHOOK_SECRET
    
    if args.status:
        view_webhook_status()
    
    if args.deactivate:
        deactivate_all_webhooks()
    
    if args.activate:
        activate_all_webhooks()
    
    if args.test_order:
        test_order_webhook(webhook_order_url, secret_key)
    
    if args.test_product:
        test_product_webhook(webhook_product_url, secret_key)
    
    # Hiçbir argüman verilmemişse interaktif menü göster
    if not any(vars(args).values()):
        print("=============================================")
        print("   TRENDYOL WEBHOOK TEST ARACI   ")
        print("=============================================")
        print("1. Webhook durumunu görüntüle")
        print("2. Sipariş webhook testi")
        print("3. Ürün webhook testi")
        print("4. Tüm webhook'ları devre dışı bırak")
        print("5. Tüm webhook'ları aktifleştir")
        print("q. Çıkış")
        
        choice = input("\nSeçiminiz (1/2/3/4/5/q): ")
        
        if choice == "1":
            view_webhook_status()
        elif choice == "2":
            test_order_webhook(webhook_order_url, secret_key)
        elif choice == "3":
            test_product_webhook(webhook_product_url, secret_key)
        elif choice == "4":
            deactivate_all_webhooks()
        elif choice == "5":
            activate_all_webhooks()
        elif choice.lower() == "q":
            print("Programdan çıkılıyor...")
        else:
            print("Geçersiz seçim!")
