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

# İşlenen ürün kodlarını takip etmek için set
product_events_processed = set()

@webhook_bp.route('/webhook-dashboard')
def webhook_dashboard():
    """
    Webhook izleme dashboardu
    """
    from trendyol_api import ORDER_WEBHOOK_URL, PRODUCT_WEBHOOK_URL

    # Log dosyasının son 100 satırını oku
    try:
        with open('webhook_service.log', 'r') as f:
            logs = f.readlines()[-100:]
        logs = ''.join(logs)
    except:
        logs = "Log dosyası bulunamadı."

    return render_template('webhook_kurulum.html', 
                          order_webhook_url=ORDER_WEBHOOK_URL,
                          product_webhook_url=PRODUCT_WEBHOOK_URL,
                          order_events=order_events[-20:],  # Son 20 olay
                          product_events=product_events[-20:],  # Son 20 olay
                          logs=logs)

@webhook_bp.route('/api/webhook-status')
def webhook_status():
    """
    Webhook durum bilgilerini döndürür
    """
    # Webhook'ların durumunu kontrol et
    try:
        import register_webhooks
        status_info = register_webhooks.check_webhook_status()

        # Sonuçlar ve olayları birleştir
        response_data = {
            'order_webhook_active': status_info.get('order_webhook_active', False),
            'product_webhook_active': status_info.get('product_webhook_active', False),
            'total_webhooks': status_info.get('total_webhooks', 0),
            'webhook_details': status_info.get('webhook_details', []),
            'recent_order_events': order_events[-20:],  # Son 20 olay
            'recent_product_events': product_events[-20:]  # Son 20 olay
        }

        # Durumu loglama
        logger.info(f"API webhook durumu yanıtı: {response_data}")

        # Hata varsa ekle
        if 'error' in status_info:
            response_data['error'] = status_info['error']

        return jsonify(response_data)
    except Exception as e:
        logger.error(f"Webhook durumu kontrol edilirken hata: {str(e)}", exc_info=True)
        return jsonify({
            'order_webhook_active': False,
            'product_webhook_active': False,
            'total_webhooks': 0,
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
        logger.info(f"Mevcut webhook sayısı: {len(existing_webhooks)}")

        # Mevcut webhook'ları sil
        deleted_count = 0
        for webhook in existing_webhooks:
            webhook_id = webhook.get('id')
            if webhook_id:
                result = register_webhooks.delete_webhook(webhook_id)
                if result:
                    deleted_count += 1

        logger.info(f"Silinen webhook sayısı: {deleted_count}")

        # Yeni webhook'ları kaydet
        from trendyol_api import ORDER_WEBHOOK_URL, PRODUCT_WEBHOOK_URL

        logger.info(f"Sipariş webhook URL: {ORDER_WEBHOOK_URL}")
        order_result = register_webhooks.register_webhook('order', ORDER_WEBHOOK_URL)

        logger.info(f"Ürün webhook URL: {PRODUCT_WEBHOOK_URL}")
        product_result = register_webhooks.register_webhook('product', PRODUCT_WEBHOOK_URL)

        order_webhook_activated = False
        product_webhook_activated = False

        if order_result:
            if register_webhooks.activate_webhook(order_result):
                order_webhook_activated = True

        if product_result:
            if register_webhooks.activate_webhook(product_result):
                product_webhook_activated = True

        # Trendyol'un sadece 1 webhook sınırlaması
        if order_webhook_activated:
            logger.info("Webhook'lar başarıyla kaydedildi ve aktifleştirildi")
            return jsonify({
                'success': True, 
                'message': 'Sipariş webhook\'u başarıyla kaydedildi',
                'note': 'Trendyol API sadece bir webhook desteklemektedir, ürün webhook\'u yerine sipariş webhook\'u kullanılacaktır. Bu Trendyol\'un kısıtlamasıdır ve değiştirilemez.'
            })
        elif product_webhook_activated:
            logger.info("Ürün webhook'u başarıyla kaydedildi ve aktifleştirildi")
            return jsonify({
                'success': True, 
                'message': 'Ürün webhook\'u başarıyla kaydedildi',
                'note': 'Trendyol API sadece bir webhook desteklemektedir'
            })
        else:
            logger.warning(f"Webhook kayıt işlemi başarısız: Sipariş: {order_webhook_activated}, Ürün: {product_webhook_activated}")
            return jsonify({'success': False, 'error': 'Webhook kayıt işlemi başarısız oldu'})


    except Exception as e:
        logger.error(f"Webhook kayıt hatası: {str(e)}", exc_info=True)
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
    # Trendyol, webhook'larda genellikle Signature veya API Key ile doğrulama yapar
    # Ancak Nisan 2024 sonrası değişikliklerle bu yapı değişmiş olabilir
    
    # API Key doğrulama (headers'da olabilir)
    api_key = request.headers.get('X-API-Key', '')
    webhook_secret = current_app.config.get('WEBHOOK_SECRET', '')
    
    # Trendyol, belirli durumlarda API Key olmadan da webhook gönderebilir
    # Veya farklı bir header kullanabilir, bu yüzden loglayalım
    logger.info(f"Gelen webhook bilgileri: Headers: {dict(request.headers)}")
    logger.info(f"Webhook veri içeriği: {request.data[:500] if request.data else 'Veri yok'}")
    
    # Eğer API Key kontrolü yapmak istemiyorsak, her zaman True döndürebiliriz
    # Bu güvenlik riski oluşturabilir ama test aşamasında kullanışlı olabilir
    # return True
    
    if api_key and api_key == webhook_secret:
        return True
    
    logger.warning(f"Webhook API Key doğrulaması başarısız: Gelen: {api_key}")
    return False

@webhook_bp.route('/webhook/orders', methods=['POST'])
def handle_order_webhook():
    """
    Trendyol'dan gelen sipariş webhook'larını işler
    """
    try:
        logger.info("===== Sipariş webhook'u alındı =====")

        # İsteğin tüm içeriğini detaylı logla
        logger.info(f"Webhook Headers: {dict(request.headers)}")
        request_data = request.data.decode('utf-8') if request.data else "Veri yok"
        logger.info(f"Webhook RAW İçeriği: {request_data[:1000]}")
        
        # Content type kontrolü
        content_type = request.headers.get('Content-Type', '')
        logger.info(f"Webhook Content-Type: {content_type}")

        # API Key doğrulama
        api_key = request.headers.get('X-API-Key')
        webhook_secret = current_app.config.get('WEBHOOK_SECRET', 'test_api_key')
        
        logger.info(f"Gelen API Key: {api_key}")
        logger.info(f"Beklenen API Key: {webhook_secret}")
        
        # Trendyol'dan gelen isteklerde API Key olmayabilir
        # Bu yüzden API Key kontrolünü esnek yapıyoruz
        
        # Eğer API Key Header'ı var ve doğru değilse ret et
        if api_key and api_key != webhook_secret:
            logger.warning(f"Webhook API Key doğrulaması başarısız: {api_key}")
            return jsonify({"status": "error", "message": "Geçersiz API Key"}), 401
        elif api_key and api_key == webhook_secret:
            logger.info("API Key doğrulaması başarılı")
        else:
            # API Key yok, ama gelen isteği kontrol et
            # Trendyol'dan gelen isteklerde bazı özel alanlar mutlaka bulunur
            if request.is_json:
                data = request.json
                # Trendyol siparişlerinde bu alanlar bulunur
                has_order_number = data.get('orderNumber') or (data.get('order') and data.get('order').get('orderNumber'))
                has_status = data.get('shipmentPackageStatus') or (data.get('order') and data.get('order').get('status'))
                
                if has_order_number and has_status:
                    logger.info("Trendyol siparişi olarak doğrulandı - API Key olmaksızın kabul edildi")
                else:
                    logger.warning("API Key yok ve Trendyol siparişi olarak doğrulanamadı")
                    return jsonify({"status": "error", "message": "Doğrulama başarısız"}), 401
            else:
                logger.warning("API Key yok ve JSON verisi değil - ret edildi")
                return jsonify({"status": "error", "message": "Geçersiz istek formatı"}), 400
                
            logger.info("API Key kontrolü esnek modda çalışıyor, Trendyol istekleri için kabul edildi")

        # JSON verisini al
        try:
            webhook_data = request.json
            logger.info(f"Parsed JSON data: {webhook_data}")
        except Exception as e:
            logger.error(f"JSON parse hatası: {str(e)}")
            return jsonify({"status": "error", "message": f"JSON parse hatası: {str(e)}"}), 400
            
        if not webhook_data:
            logger.error("Webhook verisi boş veya geçersiz JSON formatında")
            return jsonify({"status": "error", "message": "Geçersiz veri formatı"}), 400

        # Sipariş durumu doğrudan webhook_data üzerinden alınabilir
        status = webhook_data.get('shipmentPackageStatus', '')
        order_number = webhook_data.get('orderNumber', '')
        logger.info(f"Sipariş Numarası: {order_number}, Durumu: {status}")

        # Webhook içeriğini kaydet (izleme için)
        order_events.append({
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'status': status,
            'order_number': order_number,
            'data': webhook_data
        })

        # Listeyi maksimum 100 olayla sınırla
        if len(order_events) > 100:
            order_events.pop(0)

        # Test siparişi mi kontrol et
        is_test = order_number.startswith('TEST')
        if is_test:
            logger.info("Bu bir test siparişi, veritabanına kaydedilmeyecek")
            return jsonify({"status": "success", "message": "Test webhook başarıyla işlendi"}), 200

        # Sipariş durumuna göre işlem
        if status == "CREATED":
            logger.info(f"Yeni sipariş (CREATED) işleniyor: {order_number}")
            handle_order_created(webhook_data)
        elif status in ["PICKING", "INVOICED", "SHIPPED", "CANCELLED", "DELIVERED", 
                     "UNDELIVERED", "RETURNED", "UNSUPPLIED", "AWAITING", 
                     "UNPACKED", "AT_COLLECTION_POINT", "VERIFIED"]:
            logger.info(f"Sipariş durum değişikliği ({status}) işleniyor: {order_number}")
            handle_order_status_changed(webhook_data)
        else:
            logger.warning(f"Bilinmeyen sipariş durumu: {status}")

        logger.info(f"Webhook başarıyla işlendi: {order_number}")
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

        # API Key doğrulama
        api_key = request.headers.get('X-API-Key')
        webhook_secret = current_app.config.get('WEBHOOK_SECRET', '')

        if api_key != webhook_secret:
            logger.warning(f"Webhook API Key doğrulaması başarısız: {api_key}")
            return jsonify({"status": "error", "message": "Geçersiz API Key"}), 401

        # JSON verisini al
        webhook_data = request.json
        if not webhook_data:
            logger.error("Webhook verisi boş veya geçersiz JSON formatında")
            return jsonify({"status": "error", "message": "Geçersiz veri formatı"}), 400

        # Webhook olayının tipini belirle
        event_type = None

        # Ürün yaratma/güncelleme bilgisi varsa
        if 'product' in webhook_data:
            if webhook_data.get('productCode', '') not in product_events_processed:
                event_type = 'ProductCreated'
            else:
                event_type = 'ProductUpdated'

        # Fiyat değişikliği bilgisi varsa
        elif 'price' in webhook_data or 'salePrice' in webhook_data or 'listPrice' in webhook_data:
            event_type = 'PriceChanged'

        # Stok değişikliği bilgisi varsa
        elif 'quantity' in webhook_data or 'stock' in webhook_data:
            event_type = 'StockChanged'

        logger.info(f"Belirlenen webhook tipi: {event_type}")

        # Webhook içeriğini kaydet (izleme için)
        product_events.append({
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'type': event_type,
            'barcode': webhook_data.get('barcode', ''),
            'data': webhook_data
        })

        # Listeyi maksimum 100 olayla sınırla
        if len(product_events) > 100:
            product_events.pop(0)

        # Olay tipine göre işlem
        if event_type == 'ProductCreated':
            handle_product_created(webhook_data)
            # İşlenen ürün kodlarını takip et
            if webhook_data.get('productCode'):
                product_events_processed.add(webhook_data.get('productCode'))
        elif event_type == 'ProductUpdated':
            handle_product_updated(webhook_data)
        elif event_type == 'PriceChanged':
            handle_price_changed(webhook_data)
        elif event_type == 'StockChanged':
            handle_stock_changed(webhook_data)
        else:
            logger.warning(f"Bilinmeyen webhook içeriği: {webhook_data}")

        return jsonify({"status": "success", "message": "Webhook başarıyla işlendi"}), 200

    except Exception as e:
        logger.error(f"Ürün webhook işleme hatası: {str(e)}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

def handle_order_created(data):
    """
    Yeni sipariş oluşturulduğunda çalışır
    """
    try:
        # Log raw data for debugging
        logger.info(f"Sipariş webhook verileri: {json.dumps(data, indent=2)}")
        
        # Check if data has the order node or is itself the order data
        order_data = data.get('order', {})
        if not order_data and 'orderNumber' in data:
            order_data = data
            
        order_number = str(order_data.get('orderNumber') or order_data.get('id', ''))

        # Bu olayı order_events listesine ekle
        from datetime import datetime
        order_event = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'type': 'OrderCreated',
            'order_number': order_number,
            'status': order_data.get('status', 'Created')
        }
        order_events.append(order_event)
        logger.info(f"Sipariş olayı kaydedildi: {order_event}")

        # Listeyi maksimum 100 olayla sınırla
        if len(order_events) > 100:
            order_events.pop(0)

        if not order_number:
            logger.error("Sipariş numarası bulunamadı")
            return

        # Log sipariş bilgileri
        logger.info(f"İşlenen sipariş: Numara={order_number}, Durum={order_data.get('status', 'Created')}")
        
        # Sipariş ürünleri
        lines = order_data.get('lines', [])
        if lines:
            logger.info(f"Sipariş ürünleri: {len(lines)} adet ürün")
            for i, line in enumerate(lines):
                logger.info(f"Ürün {i+1}: {line.get('title')} - {line.get('barcode')} - {line.get('quantity')} adet")

        # Sipariş veritabanında var mı kontrol et
        try:
            existing_order = Order.query.filter_by(order_number=order_number).first()
            if existing_order:
                logger.info(f"Sipariş zaten mevcut: {order_number}, güncelleniyor")
                # Mevcut siparişi güncelle
                from order_service import update_existing_order
                update_existing_order(existing_order, order_data, order_data.get('status', 'Created'))
            else:
                logger.info(f"Yeni sipariş oluşturuluyor: {order_number}")
                # Yeni sipariş oluştur
                from order_service import combine_line_items
                combined_order = combine_line_items(order_data, order_data.get('status', 'Created'))
                new_order = Order(**combined_order)
                db.session.add(new_order)

            db.session.commit()
            logger.info(f"Sipariş başarıyla kaydedildi: {order_number}")
        except Exception as inner_e:
            logger.error(f"Sipariş veritabanı işlemi hatası: {str(inner_e)}", exc_info=True)
            db.session.rollback()
            
    except Exception as e:
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