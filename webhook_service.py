
from flask import Blueprint, request, jsonify, current_app, render_template
import json
import logging
from datetime import datetime
from models import db, Order, Product
from logger_config import app_logger

# Logger yapılandırması
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.FileHandler('webhook_service.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

webhook_bp = Blueprint('webhook_bp', __name__)

# Webhook olaylarını izlemek için listeleri
order_events = []
product_events = []

@webhook_bp.route('/webhook-dashboard')
def webhook_dashboard():
    """
    Webhook izleme dashboardu
    """
    from trendyol_api import ORDER_WEBHOOK_URL, PRODUCT_WEBHOOK_URL, API_KEY, API_SECRET, SUPPLIER_ID
    
    # API durumunu kontrol et
    api_status = {
        "api_key_set": bool(API_KEY),
        "api_secret_set": bool(API_SECRET),
        "supplier_id_set": bool(SUPPLIER_ID),
        "order_webhook_url": ORDER_WEBHOOK_URL,
        "product_webhook_url": PRODUCT_WEBHOOK_URL,
    }
    
    # Log dosyasının son 100 satırını oku
    try:
        with open('webhook_service.log', 'r') as f:
            logs = f.readlines()[-100:]
        logs = ''.join(logs)
    except:
        logs = "Log dosyası bulunamadı."
    
    # Webhook olayları
    order_event_list = order_events[-20:] if order_events else []
    product_event_list = product_events[-20:] if product_events else []

@webhook_bp.route('/api/test-trendyol-connection')
def test_trendyol_connection():
    """
    Trendyol API bağlantısını test eder
    """
    try:
        import requests
        import base64
        from trendyol_api import API_KEY, API_SECRET, BASE_URL
        
        # API kimlik bilgilerini kontrol et
        if not API_KEY or not API_SECRET:
            return jsonify({
                'success': False, 
                'message': 'API kimlik bilgileri tanımlı değil.',
                'details': {
                    'api_key_set': bool(API_KEY),
                    'api_secret_set': bool(API_SECRET)
                }
            })
        
        # Basit bir API çağrısı yap (suppliers endpoints)
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')
        
        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json"
        }
        
        logger.info("Trendyol API bağlantı testi yapılıyor...")
        response = requests.get(f"{BASE_URL}suppliers", headers=headers, timeout=5)
        
        if response.status_code == 200:
            logger.info("Trendyol API bağlantı testi başarılı!")
            return jsonify({
                'success': True,
                'message': 'Trendyol API bağlantısı başarılı!',
                'status_code': response.status_code
            })
        else:
            logger.error(f"Trendyol API bağlantı testi başarısız! Durum kodu: {response.status_code}")
            return jsonify({
                'success': False,
                'message': f'Trendyol API bağlantısı başarısız: {response.status_code}',
                'response': response.text,
                'status_code': response.status_code
            })
    
    except Exception as e:
        logger.error(f"Trendyol API bağlantı testi hatası: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Bağlantı hatası: {str(e)}',
            'error': str(e)
        })

    
    return render_template('webhook_dashboard.html', 
                          order_webhook_url=ORDER_WEBHOOK_URL,
                          product_webhook_url=PRODUCT_WEBHOOK_URL,
                          order_events=order_event_list, 
                          product_events=product_event_list,
                          logs=logs,
                          api_status=api_status)

@webhook_bp.route('/api/webhook-status')
def webhook_status():
    """
    Webhook durum bilgilerini döndürür
    """
    # Webhook'ların durumunu kontrol et
    try:
        import register_webhooks
        webhooks = register_webhooks.get_registered_webhooks()
        
        order_webhook_active = any(w.get('name') == 'OrderWebhook' for w in webhooks)
        product_webhook_active = any(w.get('name') == 'ProductWebhook' for w in webhooks)
        
        return jsonify({
            'order_webhook_active': order_webhook_active,
            'product_webhook_active': product_webhook_active,
            'recent_order_events': order_events[-20:],
            'recent_product_events': product_events[-20:]
        })
    except Exception as e:
        logger.error(f"Webhook durumu kontrol edilirken hata: {str(e)}")
        return jsonify({
            'order_webhook_active': False,
            'product_webhook_active': False,
            'recent_order_events': [],
            'recent_product_events': [],
            'error': str(e)
        })

@webhook_bp.route('/api/register-webhooks', methods=['POST'])
def api_register_webhooks():
    """
    Webhook'ları kaydeder
    """
    try:
        import register_webhooks
        
        # Önce mevcut webhook'ları al
        existing_webhooks = register_webhooks.get_registered_webhooks()
        
        # Mevcut webhook'ları sil
        for webhook in existing_webhooks:
            webhook_id = webhook.get('id')
            if webhook_id:
                register_webhooks.delete_webhook(webhook_id)
        
        # Yeni webhook'ları kaydet
        from trendyol_api import ORDER_WEBHOOK_URL, PRODUCT_WEBHOOK_URL
        order_result = register_webhooks.register_webhook('order', ORDER_WEBHOOK_URL)
        product_result = register_webhooks.register_webhook('product', PRODUCT_WEBHOOK_URL)
        
        if order_result and product_result:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Webhook kayıt işlemi başarısız'})
    except Exception as e:
        logger.error(f"Webhook kayıt hatası: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@webhook_bp.route('/api/webhook-logs')
def webhook_logs():
    """
    Webhook loglarını döndürür
    """
    log_type = request.args.get('type', 'all')
    
    try:
        with open('webhook_service.log', 'r') as f:
            all_logs = f.readlines()
        
        # Log tipine göre filtreleme
        if log_type == 'order':
            filtered_logs = [log for log in all_logs if 'order' in log.lower() or 'sipariş' in log.lower()]
        elif log_type == 'product':
            filtered_logs = [log for log in all_logs if 'product' in log.lower() or 'ürün' in log.lower()]
        elif log_type == 'error':
            filtered_logs = [log for log in all_logs if 'error' in log.lower() or 'hata' in log.lower()]
        else:
            filtered_logs = all_logs
        
        # Son 200 log satırı döndür
        logs = ''.join(filtered_logs[-200:])
        
        return jsonify({'logs': logs})
    except Exception as e:
        logger.error(f"Log dosyası okunurken hata: {str(e)}")
        return jsonify({'logs': f"Log dosyası okunamadı: {str(e)}"})

def verify_webhook_signature(request):
    """
    Webhook imzasını doğrula (güvenlik için)
    Not: Trendyol'un dokümantasyonuna göre bu kısım düzenlenmelidir
    """
    # Örnek: Trendyol'dan gelen özel bir header ile doğrulama
    signature = request.headers.get('X-Trendyol-Signature', '')
    webhook_secret = current_app.config.get('WEBHOOK_SECRET', '')
    
    # Gerçek implementasyonda imza doğrulama algoritması kullanılmalıdır
    # Bu örnek sadece basit bir kontrol sağlar
    if not signature or signature != webhook_secret:
        logger.warning(f"Webhook imza doğrulaması başarısız: {signature}")
        return False
    
    return True

@webhook_bp.route('/webhook/orders', methods=['POST'])
def handle_order_webhook():
    """
    Trendyol'dan gelen sipariş webhook'larını işler
    """
    try:
        logger.info("Sipariş webhook'u alındı")
        
        # İsteğin içeriğini logla (debug için)
        logger.debug(f"Webhook İçeriği: {request.data.decode('utf-8')}")
        
        # İmza doğrulama (opsiyonel güvenlik)
        # if not verify_webhook_signature(request):
        #     return jsonify({"status": "error", "message": "Webhook imzası doğrulanamadı"}), 401
        
        # JSON verisini al
        webhook_data = request.json
        if not webhook_data:
            logger.error("Webhook verisi boş veya geçersiz JSON formatında")
            return jsonify({"status": "error", "message": "Geçersiz veri formatı"}), 400
        
        event_type = webhook_data.get('type', '')
        logger.info(f"Webhook Tipi: {event_type}")
        
        # Olay tipine göre işlem
        if event_type == 'OrderCreated':
            handle_order_created(webhook_data)
        elif event_type == 'OrderStatusChanged':
            handle_order_status_changed(webhook_data)
        elif event_type == 'PackageStatusChanged':
            handle_package_status_changed(webhook_data)
        else:
            logger.warning(f"Bilinmeyen webhook tipi: {event_type}")
        
        return jsonify({"status": "success", "message": "Webhook başarıyla işlendi"}), 200
        
    except Exception as e:
        logger.error(f"Sipariş webhook işleme hatası: {str(e)}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

@webhook_bp.route('/webhook/products', methods=['POST'])
def handle_product_webhook():
    """
    Trendyol'dan gelen ürün webhook'larını işler
    """
    try:
        logger.info("Ürün webhook'u alındı")
        
        # İsteğin içeriğini logla (debug için)
        logger.debug(f"Webhook İçeriği: {request.data.decode('utf-8')}")
        
        # İmza doğrulama (opsiyonel güvenlik)
        # if not verify_webhook_signature(request):
        #     return jsonify({"status": "error", "message": "Webhook imzası doğrulanamadı"}), 401
        
        # JSON verisini al
        webhook_data = request.json
        if not webhook_data:
            logger.error("Webhook verisi boş veya geçersiz JSON formatında")
            return jsonify({"status": "error", "message": "Geçersiz veri formatı"}), 400
            
        event_type = webhook_data.get('type', '')
        logger.info(f"Webhook Tipi: {event_type}")
        
        # Olay tipine göre işlem
        if event_type == 'ProductCreated':
            handle_product_created(webhook_data)
        elif event_type == 'ProductUpdated':
            handle_product_updated(webhook_data)
        elif event_type == 'PriceChanged':
            handle_price_changed(webhook_data)
        elif event_type == 'StockChanged':
            handle_stock_changed(webhook_data)
        else:
            logger.warning(f"Bilinmeyen webhook tipi: {event_type}")
        
        return jsonify({"status": "success", "message": "Webhook başarıyla işlendi"}), 200
        
    except Exception as e:
        logger.error(f"Ürün webhook işleme hatası: {str(e)}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

def handle_order_created(data):
    """
    Yeni sipariş oluşturulduğunda çalışır
    """
    try:
        order_data = data.get('order', {})
        order_number = str(order_data.get('orderNumber') or order_data.get('id', ''))
        
        # Bu olayı order_events listesine ekle
        from datetime import datetime
        order_events.append({
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'type': 'OrderCreated',
            'order_number': order_number,
            'status': order_data.get('status', 'Created')
        })
        
        # Listeyi maksimum 100 olayla sınırla
        if len(order_events) > 100:
            order_events.pop(0)
        
        if not order_number:
            logger.error("Sipariş numarası bulunamadı")
            return
            
        # Sipariş veritabanında var mı kontrol et
        existing_order = Order.query.filter_by(order_number=order_number).first()
        if existing_order:
            logger.info(f"Sipariş zaten mevcut: {order_number}, güncelleniyor")
            # Mevcut siparişi güncelle (order_service.py'daki update_existing_order fonksiyonunu çağır)
            from order_service import update_existing_order, create_order_details
            update_existing_order(existing_order, order_data, order_data.get('status', 'Created'))
        else:
            logger.info(f"Yeni sipariş oluşturuluyor: {order_number}")
            # Yeni sipariş oluştur (order_service.py'daki combine_line_items fonksiyonunu çağır)
            from order_service import combine_line_items
            combined_order = combine_line_items(order_data, order_data.get('status', 'Created'))
            new_order = Order(**combined_order)
            db.session.add(new_order)
            
        db.session.commit()
        logger.info(f"Sipariş başarıyla kaydedildi: {order_number}")
            
    except Exception as e:
        db.session.rollback()
        logger.error(f"Sipariş oluşturma hatası: {str(e)}", exc_info=True)

def handle_order_status_changed(data):
    """
    Sipariş durumu değiştiğinde çalışır
    """
    try:
        order_data = data.get('order', {})
        order_number = str(order_data.get('orderNumber') or order_data.get('id', ''))
        new_status = order_data.get('status')
        
        # Bu olayı order_events listesine ekle
        from datetime import datetime
        order_events.append({
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'type': 'OrderStatusChanged',
            'order_number': order_number,
            'status': new_status
        })
        
        # Listeyi maksimum 100 olayla sınırla
        if len(order_events) > 100:
            order_events.pop(0)
        
        if not order_number or not new_status:
            logger.error("Sipariş numarası veya durum bulunamadı")
            return
            
        # Siparişi bul ve durumunu güncelle
        order = Order.query.filter_by(order_number=order_number).first()
        if order:
            logger.info(f"Sipariş durumu güncelleniyor: {order_number}, Yeni durum: {new_status}")
            order.status = new_status
            db.session.commit()
            logger.info(f"Sipariş durumu güncellendi: {order_number}")
        else:
            logger.warning(f"Güncellenmek istenen sipariş bulunamadı: {order_number}")
            
    except Exception as e:
        db.session.rollback()
        logger.error(f"Sipariş durumu güncelleme hatası: {str(e)}", exc_info=True)

def handle_package_status_changed(data):
    """
    Paket durumu değiştiğinde çalışır
    """
    try:
        package_data = data.get('package', {})
        package_id = str(package_data.get('id', ''))
        new_status = package_data.get('status')
        
        if not package_id or not new_status:
            logger.error("Paket ID veya durum bulunamadı")
            return
            
        # Pakete ait siparişi bul
        order = Order.query.filter_by(package_number=package_id).first()
        if order:
            logger.info(f"Paket durumu güncelleniyor: {package_id}, Yeni durum: {new_status}")
            order.status = new_status
            db.session.commit()
            logger.info(f"Paket durumu güncellendi: {package_id}")
        else:
            logger.warning(f"Güncellenmek istenen paket bulunamadı: {package_id}")
            
    except Exception as e:
        db.session.rollback()
        logger.error(f"Paket durumu güncelleme hatası: {str(e)}", exc_info=True)

def handle_product_created(data):
    """
    Yeni ürün oluşturulduğunda çalışır
    """
    try:
        product_data = data.get('product', {})
        barcode = product_data.get('barcode', '')
        
        # Bu olayı product_events listesine ekle
        from datetime import datetime
        product_events.append({
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'type': 'ProductCreated',
            'barcode': barcode,
            'action': 'Yeni ürün eklendi'
        })
        
        # Listeyi maksimum 100 olayla sınırla
        if len(product_events) > 100:
            product_events.pop(0)
        
        if not barcode:
            logger.error("Ürün barkodu bulunamadı")
            return
            
        # Ürün veritabanında var mı kontrol et
        existing_product = Product.query.filter_by(barcode=barcode).first()
        if existing_product:
            logger.info(f"Ürün zaten mevcut: {barcode}, güncelleniyor")
            # Ürün bilgilerini güncelle
            update_product_details(existing_product, product_data)
        else:
            logger.info(f"Yeni ürün oluşturuluyor: {barcode}")
            # Yeni ürün oluştur
            new_product = Product(
                barcode=barcode,
                title=product_data.get('title', ''),
                product_main_id=str(product_data.get('productMainId', '')),
                category_id=str(product_data.get('categoryId', '')),
                category_name=product_data.get('categoryName', ''),
                quantity=product_data.get('quantity', 0),
                list_price=product_data.get('listPrice', 0),
                sale_price=product_data.get('salePrice', 0),
                vat_rate=product_data.get('vatRate', 0),
                brand=product_data.get('brand', ''),
                color=product_data.get('color', ''),
                size=product_data.get('size', ''),
                stock_code=product_data.get('stockCode', ''),
                images=product_data.get('images', [''])[0] if product_data.get('images') else '',
                last_update_date=datetime.now()
            )
            db.session.add(new_product)
            
        db.session.commit()
        logger.info(f"Ürün başarıyla kaydedildi: {barcode}")
            
    except Exception as e:
        db.session.rollback()
        logger.error(f"Ürün oluşturma hatası: {str(e)}", exc_info=True)

def handle_product_updated(data):
    """
    Ürün güncellendiğinde çalışır
    """
    try:
        product_data = data.get('product', {})
        barcode = product_data.get('barcode', '')
        
        if not barcode:
            logger.error("Ürün barkodu bulunamadı")
            return
            
        # Ürünü bul ve bilgilerini güncelle
        product = Product.query.filter_by(barcode=barcode).first()
        if product:
            logger.info(f"Ürün güncelleniyor: {barcode}")
            update_product_details(product, product_data)
            db.session.commit()
            logger.info(f"Ürün bilgileri güncellendi: {barcode}")
        else:
            logger.warning(f"Güncellenmek istenen ürün bulunamadı: {barcode}")
            
    except Exception as e:
        db.session.rollback()
        logger.error(f"Ürün güncelleme hatası: {str(e)}", exc_info=True)

def handle_price_changed(data):
    """
    Ürün fiyatı değiştiğinde çalışır
    """
    try:
        price_data = data.get('priceChange', {})
        barcode = price_data.get('barcode', '')
        new_sale_price = price_data.get('salePrice')
        new_list_price = price_data.get('listPrice')
        
        if not barcode or (new_sale_price is None and new_list_price is None):
            logger.error("Ürün barkodu veya fiyat bilgisi bulunamadı")
            return
            
        # Ürünü bul ve fiyatını güncelle
        product = Product.query.filter_by(barcode=barcode).first()
        if product:
            logger.info(f"Ürün fiyatı güncelleniyor: {barcode}")
            if new_sale_price is not None:
                product.sale_price = new_sale_price
            if new_list_price is not None:
                product.list_price = new_list_price
            product.last_update_date = datetime.now()
            db.session.commit()
            logger.info(f"Ürün fiyatı güncellendi: {barcode}")
        else:
            logger.warning(f"Güncellenmek istenen ürün bulunamadı: {barcode}")
            
    except Exception as e:
        db.session.rollback()
        logger.error(f"Ürün fiyat güncelleme hatası: {str(e)}", exc_info=True)

def handle_stock_changed(data):
    """
    Ürün stok durumu değiştiğinde çalışır
    """
    try:
        stock_data = data.get('stockChange', {})
        barcode = stock_data.get('barcode', '')
        new_quantity = stock_data.get('quantity')
        
        if not barcode or new_quantity is None:
            logger.error("Ürün barkodu veya stok bilgisi bulunamadı")
            return
            
        # Ürünü bul ve stok durumunu güncelle
        product = Product.query.filter_by(barcode=barcode).first()
        if product:
            logger.info(f"Ürün stok durumu güncelleniyor: {barcode}")
            product.quantity = new_quantity
            product.last_update_date = datetime.now()
            db.session.commit()
            logger.info(f"Ürün stok durumu güncellendi: {barcode}")
        else:
            logger.warning(f"Güncellenmek istenen ürün bulunamadı: {barcode}")
            
    except Exception as e:
        db.session.rollback()
        logger.error(f"Ürün stok güncelleme hatası: {str(e)}", exc_info=True)

def update_product_details(product, product_data):
    """
    Ürün detaylarını günceller
    """
    product.title = product_data.get('title', product.title)
    product.product_main_id = str(product_data.get('productMainId', product.product_main_id))
    product.category_id = str(product_data.get('categoryId', product.category_id))
    product.category_name = product_data.get('categoryName', product.category_name)
    product.quantity = product_data.get('quantity', product.quantity)
    product.list_price = product_data.get('listPrice', product.list_price)
    product.sale_price = product_data.get('salePrice', product.sale_price)
    product.vat_rate = product_data.get('vatRate', product.vat_rate)
    product.brand = product_data.get('brand', product.brand)
    product.color = product_data.get('color', product.color)
    product.size = product_data.get('size', product.size)
    product.stock_code = product_data.get('stockCode', product.stock_code)
    
    if product_data.get('images'):
        product.images = product_data.get('images', [''])[0]
        
    product.last_update_date = datetime.now()
