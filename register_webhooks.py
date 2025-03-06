import os
import requests
import json
import base64
import time
from logger_config import app_logger
import traceback

# Log ayarları
logger = app_logger

# API yapılandırması
BASE_URL = os.environ.get("TRENDYOL_API_URL", "https://api.trendyol.com/sapigw/")
SUPPLIER_ID = os.environ.get("TRENDYOL_SUPPLIER_ID", "123456")
API_KEY = os.environ.get("TRENDYOL_API_KEY", "test_api_key")
API_SECRET = os.environ.get("TRENDYOL_API_SECRET", "test_api_secret")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "webhook_secret_token")

# Webhook URL'leri - Dinamik olarak uygulama URL'sinden oluştur
def get_base_url():
    """Mevcut uygulamanın URL'sini belirler"""
    # Replit'te çalışırken
    if 'REPL_SLUG' in os.environ and 'REPL_OWNER' in os.environ:
        return f"https://{os.environ.get('REPL_SLUG')}.{os.environ.get('REPL_OWNER')}.repl.co"

    # Çevreden veya varsayılan
    return os.environ.get("APP_URL", "https://siparis-yonetim.repl.co")

ORDER_WEBHOOK_URL = os.environ.get("ORDER_WEBHOOK_URL", f"{get_base_url()}/webhook/orders")
PRODUCT_WEBHOOK_URL = os.environ.get("PRODUCT_WEBHOOK_URL", f"{get_base_url()}/webhook/products")


def get_registered_webhooks():
    """
    Trendyol API'sine kayıtlı webhook'ları getirir
    """
    logger.info("Kayıtlı webhook'lar getiriliyor")

    try:
        # Authentication header'ı oluştur (Base64 ile kodlanmış)
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')

        # API endpointi ve headers (Yeni Trendyol API formatı)
        url = f"{BASE_URL}sellers/{SUPPLIER_ID}/webhooks"
        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json"
        }

        # Yeniden deneme mekanizması
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                # API isteği gönder
                response = requests.get(url, headers=headers, timeout=15)

                # Başarılı yanıt kontrolü
                if response.status_code == 200:
                    try:
                        webhook_data = response.json()
                        return {
                            "success": True,
                            "webhooks": webhook_data,
                            "message": "Webhook'lar başarıyla alındı"
                        }
                    except json.JSONDecodeError as e:
                        logger.error(f"Webhook yanıtı JSON formatında değil: {e}")
                        return {
                            "success": False,
                            "message": "Webhook yanıtı JSON formatında değil",
                            "error": str(e)
                        }
                else:
                    logger.warning(f"Webhook'lar getirilemedi! Durum kodu: {response.status_code}, Yanıt: {response.text}")
                    return {
                        "success": False,
                        "message": f"Webhook'lar getirilemedi. Durum kodu: {response.status_code}",
                        "error": response.text
                    }

            except requests.exceptions.RequestException as e:
                retry_count += 1
                logger.warning(f"Webhook'lar getirilemedi (Servis Kullanılamıyor)! Yeniden deneme: {retry_count}/{max_retries}")

                if retry_count >= max_retries:
                    logger.error(f"Webhook'lar getirilemedi! Maksimum yeniden deneme sayısına ({max_retries}) ulaşıldı.")
                    return {
                        "success": False,
                        "message": "Servis geçici olarak kullanılamıyor.",
                        "error": str(e)
                    }

                # Yeniden denemeden önce bekleyin (her seferinde daha uzun süre bekleyin)
                time.sleep(retry_count * 2)

        return {
            "success": False,
            "message": "Webhook'lar alınamadı"
        }

    except Exception as e:
        logger.error(f"Webhook'lar getirilirken hata oluştu: {str(e)}")
        logger.debug(f"Traceback: {traceback.format_exc()}")
        return {
            "success": False,
            "message": "Webhook'lar alınırken bir hata oluştu.",
            "error": str(e)
        }


def register_webhook(webhook_type, webhook_url):
    """
    Belirli tipte bir webhook'u API'ye kaydeder

    Args:
        webhook_type (str): Webhook tipi ("order" veya "product")
        webhook_url (str): Webhook'un gönderileceği URL

    Returns:
        dict: İşlem sonucu
    """
    logger.info(f"{webhook_type.title()} webhook kaydı yapılıyor: {webhook_url}")

    try:
        # Authentication header'ı oluştur
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')

        # API endpointi ve headers (Yeni Trendyol API formatı)
        url = f"{BASE_URL}sellers/{SUPPLIER_ID}/webhooks"
        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json"
        }

        # Webhook tipine göre olayları belirle
        if webhook_type.lower() == "order":
            webhook_name = "OrderWebhook"
            events = ["OrderCreated", "OrderStatusChanged", "PackageStatusChanged"]
        elif webhook_type.lower() == "product":
            webhook_name = "ProductWebhook"
            events = ["ProductCreated", "ProductUpdated", "PriceChanged", "StockChanged"]
        else:
            logger.error(f"Geçersiz webhook tipi: {webhook_type}")
            return {
                "success": False,
                "message": f"Geçersiz webhook tipi: {webhook_type}"
            }

        # Webhook payload'ı oluştur
        payload = {
            "name": webhook_name,
            "url": webhook_url,
            "authToken": WEBHOOK_SECRET,
            "events": events
        }

        try:
            # API isteği gönder - yeniden deneme mekanizması
            max_retries = 3
            retry_count = 0
            retry_delay = 2  # saniye

            while retry_count < max_retries:
                try:
                    logger.info(f"{webhook_type.title()} webhook kaydı için API isteği gönderiliyor (Deneme: {retry_count+1}/{max_retries})")
                    response = requests.post(url, headers=headers, json=payload, timeout=15)

                    # Başarı durumu kontrolü
                    if response.status_code in [200, 201]:
                        logger.info(f"{webhook_type.title()} webhook başarıyla kaydedildi")
                        return {
                            "success": True,
                            "message": f"{webhook_type.title()} webhook başarıyla kaydedildi",
                            "response": response.json() if response.text else {}
                        }
                    # Servis Kullanılamıyor hatası - yeniden dene
                    elif response.status_code == 556:
                        retry_count += 1
                        error_msg = f"{webhook_type.title()} webhook kaydı başarısız: Servis Kullanılamıyor (556). "

                        if retry_count < max_retries:
                            error_msg += f"Yeniden deneniyor ({retry_count}/{max_retries})..."
                            logger.warning(error_msg)
                            time.sleep(retry_delay * retry_count)  # Her seferinde daha uzun bekleme
                        else:
                            error_msg += "Maksimum deneme sayısına ulaşıldı."
                            logger.error(error_msg)
                            return {
                                "success": False,
                                "message": f"{webhook_type.title()} webhook kaydedilemedi - Servis Kullanılamıyor",
                                "error": response.text,
                                "status_code": response.status_code
                            }
                    # Diğer hata durumları
                    else:
                        logger.error(f"{webhook_type.title()} webhook kaydedilemedi. Durum: {response.status_code}, Yanıt: {response.text}")
                        return {
                            "success": False,
                            "message": f"{webhook_type.title()} webhook kaydedilemedi",
                            "error": response.text,
                            "status_code": response.status_code
                        }
                except requests.exceptions.RequestException as req_err:
                    retry_count += 1
                    if retry_count >= max_retries:
                        logger.error(f"API isteği başarısız: {str(req_err)}")
                        return {
                            "success": False,
                            "message": f"API bağlantı hatası: {str(req_err)}",
                            "error": str(req_err)
                        }
                    logger.warning(f"API bağlantı hatası, yeniden deneme {retry_count}/{max_retries}: {str(req_err)}")
                    time.sleep(retry_delay * retry_count)
        except Exception as e:
            logger.error(f"{webhook_type.title()} webhook kaydı sırasında beklenmeyen hata: {str(e)}")
            return {
                "success": False,
                "message": f"{webhook_type.title()} webhook kaydı sırasında beklenmeyen hata",
                "error": str(e)
            }

    except Exception as e:
        logger.error(f"{webhook_type.title()} webhook kaydedilirken hata: {str(e)}")
        logger.debug(f"Traceback: {traceback.format_exc()}")
        return {
            "success": False,
            "message": f"{webhook_type.title()} webhook kaydedilemedi",
            "error": str(e)
        }