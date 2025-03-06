
import requests
import json
import os
from dotenv import load_dotenv
import logging
from trendyol_api import API_BASE_URL, SUPPLIER_ID, API_KEY, API_SECRET, ORDER_WEBHOOK_URL, PRODUCT_WEBHOOK_URL, WEBHOOK_SECRET

# Logger yapılandırması
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.FileHandler('webhook_service.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Çevre değişkenlerini yükle
load_dotenv()

def get_auth_headers():
    """
    Trendyol API için kimlik doğrulama başlıkları oluşturur
    """
    import base64
    auth_str = f"{API_KEY}:{API_SECRET}"
    auth_bytes = auth_str.encode('utf-8')
    auth_b64 = base64.b64encode(auth_bytes).decode('utf-8')
    
    return {
        "Authorization": f"Basic {auth_b64}",
        "Content-Type": "application/json"
    }

def get_registered_webhooks():
    """
    Trendyol'da kayıtlı webhook'ları listeler
    """
    try:
        url = f"{API_BASE_URL}{SUPPLIER_ID}/webhooks"
        headers = get_auth_headers()
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            webhooks = response.json()
            logger.info(f"Kayıtlı webhook'lar başarıyla alındı. Toplam: {len(webhooks)}")
            return webhooks
        else:
            logger.error(f"Webhook'lar alınırken hata: Status: {response.status_code}, Yanıt: {response.text}")
            return []
            
    except Exception as e:
        logger.error(f"Webhook'lar listelenirken hata: {str(e)}")
        return []

def delete_webhook(webhook_id):
    """
    Belirli bir webhook'u siler
    """
    try:
        url = f"{API_BASE_URL}{SUPPLIER_ID}/webhooks/{webhook_id}"
        headers = get_auth_headers()
        
        response = requests.delete(url, headers=headers)
        
        if response.status_code == 200:
            logger.info(f"Webhook başarıyla silindi. ID: {webhook_id}")
            return True
        else:
            logger.error(f"Webhook silinemedi: Status: {response.status_code}, Yanıt: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Webhook silinirken hata: {str(e)}")
        return False

def register_webhook(webhook_type, webhook_url):
    """
    Yeni bir webhook kaydeder
    
    webhook_type: "order" veya "product" olabilir
    webhook_url: Webhook URL'i
    """
    try:
        url = f"{API_BASE_URL}{SUPPLIER_ID}/webhooks"
        headers = get_auth_headers()
        
        # Webhook tipi için ayarlar
        if webhook_type.lower() == "order":
            name = "OrderWebhook"
            statuses = ["CREATED", "PICKING", "INVOICED", "SHIPPED", "CANCELLED", 
                        "DELIVERED", "UNDELIVERED", "RETURNED", "UNSUPPLIED", 
                        "AWAITING", "UNPACKED", "AT_COLLECTION_POINT", "VERIFIED"]
        elif webhook_type.lower() == "product":
            name = "ProductWebhook"
            # Trendyol API'si ürün webhook'larında da sipariş statülerini bekliyor, belgelemeye göre düzeltildi
            statuses = ["CREATED", "PICKING", "INVOICED", "SHIPPED"]
        else:
            logger.error(f"Geçersiz webhook tipi: {webhook_type}")
            return False
        
        # API isteği için veri
        data = {
            "name": name,
            "url": webhook_url,
            "authenticationType": "API_KEY",
            "apiKey": WEBHOOK_SECRET,
            "subscribedStatuses": statuses
        }
        
        logger.info(f"Webhook kaydediliyor: Tip: {webhook_type}, URL: {webhook_url}")
        logger.debug(f"İstek verisi: {data}")
        
        response = requests.post(url, headers=headers, json=data)
        
        # 200 veya 201 her ikisi de başarı kabul edilir
        if response.status_code in [200, 201]:
            logger.info(f"Webhook başarıyla kaydedildi: {webhook_type}")
            webhook_id = response.json().get("id")
            logger.info(f"Webhook ID: {webhook_id}")
            return webhook_id
        else:
            logger.error(f"Webhook kayıt hatası: Status: {response.status_code}, Yanıt: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Webhook kayıt hatası: {str(e)}")
        return False

def activate_webhook(webhook_id):
    """
    Belirli bir webhook'u aktif hale getirir
    """
    try:
        url = f"{API_BASE_URL}{SUPPLIER_ID}/webhooks/{webhook_id}/activate"
        headers = get_auth_headers()
        
        response = requests.put(url, headers=headers)
        
        if response.status_code == 200:
            logger.info(f"Webhook başarıyla aktifleştirildi. ID: {webhook_id}")
            return True
        else:
            logger.error(f"Webhook aktifleştirilemedi: Status: {response.status_code}, Yanıt: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Webhook aktifleştirme hatası: {str(e)}")
        return False

def deactivate_webhook(webhook_id):
    """
    Belirli bir webhook'u deaktif hale getirir
    """
    try:
        url = f"{API_BASE_URL}{SUPPLIER_ID}/webhooks/{webhook_id}/deactivate"
        headers = get_auth_headers()
        
        response = requests.put(url, headers=headers)
        
        if response.status_code == 200:
            logger.info(f"Webhook başarıyla deaktifleştirildi. ID: {webhook_id}")
            return True
        else:
            logger.error(f"Webhook deaktifleştirilemedi: Status: {response.status_code}, Yanıt: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Webhook deaktifleştirme hatası: {str(e)}")
        return False

def check_webhook_status():
    """
    Kayıtlı webhook'ların durumunu kontrol eder
    """
    try:
        webhooks = get_registered_webhooks()
        
        order_webhook_active = False
        product_webhook_active = False
        webhook_details = []
        
        logger.info(f"Webhook durumu kontrolü başladı - Toplam {len(webhooks)} webhook")
        
        for webhook in webhooks:
            webhook_id = webhook.get("id", "")
            webhook_name = webhook.get("name", "")
            webhook_status = webhook.get("status", "")
            webhook_url = webhook.get("url", "")
            
            logger.info(f"Webhook bilgisi: ID: {webhook_id}, İsim: {webhook_name}, Durum: {webhook_status}, URL: {webhook_url}")
            
            webhook_details.append({
                "id": webhook_id,
                "name": webhook_name,
                "status": webhook_status,
                "url": webhook_url
            })
            
            # Durum kontrolü - API yanıtlarından gelen değerleri kontrol et
            # Webhook adı veya URL'ye göre tür belirle
            is_order_webhook = webhook_name == "OrderWebhook" or "webhook/orders" in webhook_url
            is_product_webhook = webhook_name == "ProductWebhook" or "webhook/products" in webhook_url
            
            # Statü kontrolü
            if str(webhook_status).upper() == "ACTIVE":
                if is_order_webhook:
                    order_webhook_active = True
                    logger.info(f"Sipariş webhook'u aktif olarak işaretlendi. Durum: {webhook_status}")
                elif is_product_webhook:
                    product_webhook_active = True
                    logger.info(f"Ürün webhook'u aktif olarak işaretlendi. Durum: {webhook_status}")
                else:
                    logger.warning(f"Tanımlanamayan aktif webhook bulundu: {webhook_name}, URL: {webhook_url}")
        
        result = {
            "order_webhook_active": order_webhook_active,
            "product_webhook_active": product_webhook_active,
            "total_webhooks": len(webhooks),
            "webhook_details": webhook_details
        }
        
        logger.info(f"Webhook durumu: {result}")
        return result
            
    except Exception as e:
        logger.error(f"Webhook durumu kontrol edilirken hata: {str(e)}", exc_info=True)
        return {
            "order_webhook_active": False,
            "product_webhook_active": False,
            "total_webhooks": 0,
            "error": str(e)
        }

if __name__ == "__main__":
    # Test amacıyla webhook'ları listele
    print("Kayıtlı webhook'lar:")
    webhooks = get_registered_webhooks()
    for webhook in webhooks:
        print(f"ID: {webhook.get('id')}, Ad: {webhook.get('name')}, Durum: {webhook.get('status')}")
    
    # Komut satırından argüman alarak webhook oluşturma örneği
    import sys
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "register-order":
            result = register_webhook("order", ORDER_WEBHOOK_URL)
            print(f"Sipariş webhook kaydı sonucu: {result}")
            
        elif command == "register-product":
            result = register_webhook("product", PRODUCT_WEBHOOK_URL)
            print(f"Ürün webhook kaydı sonucu: {result}")
            
        elif command == "delete-all":
            webhooks = get_registered_webhooks()
            for webhook in webhooks:
                delete_webhook(webhook.get("id"))
            print("Tüm webhook'lar silindi")
