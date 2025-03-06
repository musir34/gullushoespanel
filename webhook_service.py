
from flask import Blueprint, render_template, request, jsonify
from logger_config import app_logger
import traceback
import requests
import json
from datetime import datetime

# Blueprint tanımı
webhook_bp = Blueprint('webhook_bp', __name__)

# Log yapılandırması
logger = app_logger

# Webhook olay kaydedicileri (in-memory storage)
order_events = []
product_events = []
logs = []
api_status = {"status": "unknown", "last_checked": None}

# Webhook endpoint tanımları
# Uygulama URL'sini otomatik olarak al - böylece her ortamda çalışacak şekilde
import os
from flask import request

def get_base_url():
    """Mevcut uygulamanın URL'sini belirler"""
    # Replit'te çalışırken
    if 'REPL_SLUG' in os.environ and 'REPL_OWNER' in os.environ:
        return f"https://{os.environ.get('REPL_SLUG')}.{os.environ.get('REPL_OWNER')}.repl.co"
    
    # Değilse, request'ten elde et
    return os.environ.get("APP_URL", request.host_url.rstrip('/'))

# Dinamik webhook URL'leri
def get_order_webhook_url():
    return f"{get_base_url()}/webhook/orders"

def get_product_webhook_url():
    return f"{get_base_url()}/webhook/products"

ORDER_WEBHOOK_URL = get_order_webhook_url()
PRODUCT_WEBHOOK_URL = get_product_webhook_url()

# Maksimum log sayısı
MAX_LOGS = 100

@webhook_bp.route('/webhook-dashboard')
def webhook_dashboard():
    """Webhook durumunu ve logları gösteren dashboard"""
    logger.debug("Webhook dashboard sayfası açılıyor")
    
    # Webhook olayları
    order_event_list = order_events[-20:] if order_events else []
    product_event_list = product_events[-20:] if product_events else []
    
    return render_template('webhook_dashboard.html', 
                          order_webhook_url=ORDER_WEBHOOK_URL,
                          product_webhook_url=PRODUCT_WEBHOOK_URL,
                          order_events=order_event_list, 
                          product_events=product_event_list,
                          logs=logs,
                          api_status=api_status)

@webhook_bp.route('/api/test-trendyol-connection')
def test_trendyol_connection():
    """Trendyol API bağlantısını test etme endpoint'i"""
    from trendyol_api import test_connection
    
    try:
        result = test_connection()
        return jsonify(result)
    except Exception as e:
        logger.error(f"Trendyol bağlantı testi başarısız: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Bağlantı hatası: {str(e)}"
        })

@webhook_bp.route('/webhook/orders', methods=['POST'])
def order_webhook():
    """Sipariş webhook'u - Trendyol'dan sipariş olaylarını alır"""
    try:
        event_data = request.json
        
        # Alınan olay verisini işle
        event = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": event_data,
            "headers": dict(request.headers)
        }
        
        # Olay kaydını tut
        order_events.append(event)
        
        # Log ekle
        add_log("info", f"Sipariş olayı alındı: {event_data.get('orderId', 'ID bulunamadı')}")
        
        # Burada siparişi işlemek için gerekli kodlar eklenebilir
        # ...
        
        return jsonify({"success": True, "message": "Olay alındı"})
    
    except Exception as e:
        error_msg = f"Sipariş webhook hatası: {str(e)}"
        logger.error(error_msg)
        logger.debug(traceback.format_exc())
        add_log("error", error_msg)
        return jsonify({"success": False, "error": str(e)}), 500

@webhook_bp.route('/webhook/products', methods=['POST'])
def product_webhook():
    """Ürün webhook'u - Trendyol'dan ürün olaylarını alır"""
    try:
        event_data = request.json
        
        # Alınan olay verisini işle
        event = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": event_data,
            "headers": dict(request.headers)
        }
        
        # Olay kaydını tut
        product_events.append(event)
        
        # Log ekle
        add_log("info", f"Ürün olayı alındı: {event_data.get('productId', 'ID bulunamadı')}")
        
        # Burada ürünü işlemek için gerekli kodlar eklenebilir
        # ...
        
        return jsonify({"success": True, "message": "Olay alındı"})
    
    except Exception as e:
        error_msg = f"Ürün webhook hatası: {str(e)}"
        logger.error(error_msg)
        logger.debug(traceback.format_exc())
        add_log("error", error_msg)
        return jsonify({"success": False, "error": str(e)}), 500

@webhook_bp.route('/api/webhook-logs')
def get_webhook_logs():
    """Webhook loglarını getiren API endpoint'i"""
    log_type = request.args.get('type', 'all')
    
    if log_type == 'all':
        return jsonify(logs[-100:] if logs else [])
    elif log_type == 'error':
        error_logs = [log for log in logs if log['level'] == 'error']
        return jsonify(error_logs[-100:] if error_logs else [])
    elif log_type == 'info':
        info_logs = [log for log in logs if log['level'] == 'info']
        return jsonify(info_logs[-100:] if info_logs else [])
    else:
        return jsonify({"error": "Geçersiz log tipi"}), 400

@webhook_bp.route('/api/webhook-status')
def get_webhook_status():
    """Webhook durumunu getiren API endpoint'i"""
    from register_webhooks import get_registered_webhooks
    
    result = get_registered_webhooks()
    
    # API durumunu güncelle
    global api_status
    api_status = {
        "status": "active" if result.get("success", False) else "inactive",
        "last_checked": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "message": result.get("message", "")
    }
    
    return jsonify({
        "status": api_status,
        "webhooks": result.get("webhooks", [])
    })

@webhook_bp.route('/api/register-webhooks', methods=['POST'])
def register_webhooks_api():
    """Webhook'ları kaydetmek için API endpoint'i"""
    from register_webhooks import register_webhook
    import time

    # API erişilebilirliğini kontrol et 
    from register_webhooks import get_registered_webhooks
    api_check = get_registered_webhooks()
    
    # API erişilemiyorsa uyarı ver
    if not api_check.get("success", False):
        if "556" in str(api_check.get("error", "")) or "Service Unavailable" in str(api_check.get("error", "")):
            logger.warning("Trendyol API şu anda erişilemez durumda. Webhook kaydı yine de deneniyor...")
            # API'nin toparlanması için kısa bir bekleme ekle
            time.sleep(2)
    
    # Order webhook'unu kaydet
    logger.info(f"Order webhook kaydı başlatılıyor: {ORDER_WEBHOOK_URL}")
    order_result = register_webhook("order", ORDER_WEBHOOK_URL)
    
    # Kısa bir bekleme ekle (rate limiting'den kaçınmak için)
    time.sleep(1)
    
    # Product webhook'unu kaydet
    logger.info(f"Product webhook kaydı başlatılıyor: {PRODUCT_WEBHOOK_URL}")
    product_result = register_webhook("product", PRODUCT_WEBHOOK_URL)
    
    # Sonuçları ekstra bilgilerle birlikte döndür
    result = {
        "success": order_result["success"] and product_result["success"],
        "order_webhook": order_result,
        "product_webhook": product_result,
        "message": "Webhook kayıt işlemleri tamamlandı",
        "api_status": "Erişilebilir" if api_check.get("success", False) else "Erişilemez",
    }
    
    if not result["success"]:
        result["error_details"] = {
            "api_check_result": api_check.get("message", ""),
            "suggestion": "Trendyol API servisi geçici olarak kullanılamıyor olabilir. Daha sonra tekrar deneyin."
        }
    
    logger.info(f"Webhook kayıt sonuçları: {result['success']}")
    return jsonify(result)

def add_log(level, message):
    """Webhook loglarına yeni bir log ekler"""
    log = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "level": level,
        "message": message
    }
    
    logs.append(log)
    
    # Log sayısı maksimum değeri aşarsa en eskisini sil
    if len(logs) > MAX_LOGS:
        logs.pop(0)
