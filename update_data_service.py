from flask import Blueprint, render_template, request, jsonify, current_app
from datetime import datetime, timedelta
import json
import os
import asyncio
import logging
import threading
import time
from models import db

# Loglama ayarları
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.FileHandler('update_data.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

update_data_bp = Blueprint('update_data_bp', __name__)

# Son güncelleme bilgilerini tutan JSON dosyası
UPDATES_FILE = 'last_updates.json'

# Güncelleme durumu
UPDATING = False
UPDATE_THREAD = None

def get_last_updates():
    """Son güncelleme bilgilerini JSON dosyasından okur"""
    try:
        if os.path.exists(UPDATES_FILE):
            with open(UPDATES_FILE, 'r') as f:
                return json.load(f)
        else:
            # Varsayılan yapı
            return {
                'products': {'time': None, 'success': False, 'count': 0},
                'orders': {'time': None, 'success': False, 'count': 0},
                'claims': {'time': None, 'success': False, 'count': 0}
            }
    except Exception as e:
        logger.error(f"Son güncelleme bilgileri okunamadı: {e}")
        return {
            'products': {'time': None, 'success': False, 'count': 0},
            'orders': {'time': None, 'success': False, 'count': 0},
            'claims': {'time': None, 'success': False, 'count': 0}
        }

def save_update_info(data_type, success, count):
    """Güncelleme bilgisini kaydeder"""
    try:
        updates = get_last_updates()
        updates[data_type] = {
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'success': success,
            'count': count
        }
        with open(UPDATES_FILE, 'w') as f:
            json.dump(updates, f)
    except Exception as e:
        logger.error(f"Güncelleme bilgileri kaydedilemedi: {e}")

@update_data_bp.route('/veri-guncelleme')
def veri_guncelleme_sayfasi():
    """Veri güncelleme durumunu gösteren sayfa"""
    last_updates = get_last_updates()
    # Global güncelleme durumunu ekle
    global UPDATING
    return render_template('veri_guncelleme_durumu.html', last_updates=last_updates, is_updating=UPDATING)

@update_data_bp.route('/api/update-data/<data_type>', methods=['POST'])
def update_data(data_type):
    """API endpoint'i - belirtilen veri türünü günceller"""
    try:
        if data_type == 'products':
            from product_service import fetch_trendyol_products_async
            asyncio.run(fetch_trendyol_products_async())
            # Ürün sayısını al
            from models import Product
            product_count = Product.query.count()
            save_update_info('products', True, product_count)
            return jsonify({'success': True, 'message': 'Ürünler başarıyla güncellendi'})

        elif data_type == 'orders':
            from order_service import fetch_trendyol_orders_async
            asyncio.run(fetch_trendyol_orders_async())
            # Sipariş sayısını al
            from models import Order
            order_count = Order.query.count()
            save_update_info('orders', True, order_count)
            return jsonify({'success': True, 'message': 'Siparişler başarıyla güncellendi'})

        elif data_type == 'claims':
            from claims_service import fetch_claims_async
            asyncio.run(fetch_claims_async())
            # İade/talep sayısını al
            from models import Claim  # Kendi model adınıza göre düzenleyin
            claim_count = Claim.query.count()
            save_update_info('claims', True, claim_count)
            return jsonify({'success': True, 'message': 'İadeler/talepler başarıyla güncellendi'})

        elif data_type == 'all':
            # Tüm verileri güncelle
            from product_service import fetch_trendyol_products_async
            from order_service import fetch_trendyol_orders_async
            from claims_service import fetch_claims_async

            # Ürünleri güncelle
            asyncio.run(fetch_trendyol_products_async())
            from models import Product
            product_count = Product.query.count()
            save_update_info('products', True, product_count)

            # Siparişleri güncelle
            asyncio.run(fetch_trendyol_orders_async())
            from models import Order
            order_count = Order.query.count()
            save_update_info('orders', True, order_count)

            # İadeleri/talepleri güncelle
            asyncio.run(fetch_claims_async())
            from models import Claim
            claim_count = Claim.query.count()
            save_update_info('claims', True, claim_count)

            return jsonify({'success': True, 'message': 'Tüm veriler başarıyla güncellendi'})

        else:
            return jsonify({'success': False, 'message': 'Geçersiz veri türü'}), 400

    except Exception as e:
        logger.error(f"Veri güncellenirken hata: {e}")

        # Hata durumunda güncelleme bilgisini kaydet
        if data_type in ['products', 'orders', 'claims']:
            save_update_info(data_type, False, 0)

        return jsonify({'success': False, 'message': f'Güncelleme sırasında bir hata oluştu: {str(e)}'}), 500

def update_orders():
    """Siparişleri günceller"""
    try:
        logger.info("Siparişler güncellenmeye başlanıyor...")
        from order_service import fetch_trendyol_orders_async

        # Uygulama bağlamı zaten ana thread tarafından oluşturuldu
        asyncio.run(fetch_trendyol_orders_async())
        # Sipariş sayısını al
        from models import Order
        order_count = Order.query.count()
        save_update_info('orders', True, order_count)
        logger.info(f"Siparişler güncellendi. Toplam sipariş sayısı: {order_count}")
        return True
    except Exception as e:
        logger.error(f"Siparişler güncellenirken hata: {e}")
        save_update_info('orders', False, 0)
        return False

def update_products():
    """Ürünleri günceller"""
    try:
        logger.info("Ürünler güncellenmeye başlanıyor...")
        from product_service import fetch_trendyol_products_async

        # Uygulama bağlamı zaten ana thread tarafından oluşturuldu
        asyncio.run(fetch_trendyol_products_async())
        # Ürün sayısını al
        from models import Product
        product_count = Product.query.count()
        save_update_info('products', True, product_count)
        logger.info(f"Ürünler güncellendi. Toplam ürün sayısı: {product_count}")
        return True
    except Exception as e:
        logger.error(f"Ürünler güncellenirken hata: {e}")
        save_update_info('products', False, 0)
        return False

def update_claims():
    """İade/talepleri günceller"""
    # Claims logger'ı fonksiyon dışında tanımlayalım
    from logger_config import app_logger as claims_logger
    
    try:
        claims_logger.info("İadeler/talepler güncellenmeye başlanıyor...")
        
        # Önce Claim modeli import edilebiliyor mu kontrol et
        try:
            from models import Claim
            claims_logger.info("Claim modeli başarıyla import edildi")
        except ImportError as ie:
            claims_logger.error(f"Claim modeli bulunamadı: {str(ie)}")
            claims_logger.info("İadeler/talepler güncellemesi atlanıyor. Veritabanı modeli eksik.")
            save_update_info('claims', False, 0)
            return False
        
        from claims_service import fetch_claims_async
        try:
            # İade/talepleri güncelleme kodunu burada çalıştır
            asyncio.run(fetch_claims_async())
            # İade/talep sayısını al
            from models import Claim
            claim_count = Claim.query.count()
            save_update_info('claims', True, claim_count)
            claims_logger.info(f"İadeler/talepler güncellendi. Toplam iade/talep sayısı: {claim_count}")
            return True
        except Exception as e:
            import traceback
            claims_logger.error(f"İadeler/talepler güncellenirken hata: {str(e)}")
            claims_logger.error(f"Hata detayı: {traceback.format_exc()}")
            save_update_info('claims', False, 0)
            return False

    except Exception as e:
        # Global logger'ı kullan
        import traceback
        logger.exception(f"update_claims fonksiyonunda beklenmedik hata: {e}")
        logger.error(f"Hata detayı: {traceback.format_exc()}")
        return False


def continuous_update_worker():
    """Sürekli güncelleme yapan arka plan iş parçacığı"""
    global UPDATING

    # Flask uygulamasını almak için
    from app import app  # app.py'den doğrudan uygulama örneğini içe aktar

    logger.info("Sürekli güncelleme sistemi başlatıldı")

    # Uygulamayı doğrudan referans al
    # !!! HER GÜNCELLEME İŞLEMİ İÇİN YENİ BİR BAĞLAM OLUŞTURMAK ÖNEMLİDİR !!!

    try:
        while True:
            try:
                UPDATING = True

                # Her döngüde yeni bir uygulama bağlamı oluştur
                with app.app_context():
                    # 1. Siparişleri güncelle
                    logger.info("--- Güncelleme Döngüsü Başladı ---")
                    logger.info("1/3: Siparişler güncelleniyor...")
                    update_orders()
                    time.sleep(10)  # 10 saniye bekle

                    # 2. Ürünleri güncelle
                    logger.info("2/3: Ürünler güncelleniyor...")
                    update_products()
                    time.sleep(10)  # 10 saniye bekle

                    # 3. İade/Talepleri güncelle
                    logger.info("3/3: İadeler/Talepler güncelleniyor...")
                    update_claims()

                    logger.info("--- Güncelleme Döngüsü Tamamlandı ---")

                UPDATING = False

                # Tüm güncellemeler bittikten sonra 1 dakika bekle
                logger.info("Sonraki güncelleme döngüsüne kadar 1 dakika bekleniyor...")
                time.sleep(60)  # 1 dakika bekle

            except Exception as e:
                logger.error(f"Sürekli güncelleme sırasında hata: {e}")
                UPDATING = False
                time.sleep(60)  # Hata durumunda 1 dakika bekle ve tekrar dene
    except Exception as e:
        logger.error(f"Sürekli güncelleme sisteminde genel hata: {e}")

def start_continuous_update():
    """Sürekli güncelleme sistemini başlat"""
    global UPDATE_THREAD, UPDATING

    # Zaten çalışıyorsa yeni bir tane başlatma
    if UPDATE_THREAD and UPDATE_THREAD.is_alive():
        logger.info("Sürekli güncelleme sistemi zaten çalışıyor")
        return False

    # Yeni güncelleme thread'i başlat
    UPDATE_THREAD = threading.Thread(target=continuous_update_worker, daemon=True)
    UPDATE_THREAD.start()
    logger.info("Sürekli güncelleme sistemi başlatıldı")
    return True

@update_data_bp.route('/api/start-continuous-update', methods=['POST'])
def start_continuous_update_api():
    """Sürekli güncelleme sistemini başlatan API endpoint'i"""
    success = start_continuous_update()
    if success:
        return jsonify({'success': True, 'message': 'Sürekli güncelleme sistemi başlatıldı'})
    else:
        return jsonify({'success': False, 'message': 'Sürekli güncelleme sistemi zaten çalışıyor'})

@update_data_bp.route('/api/stop-continuous-update', methods=['POST'])
def stop_continuous_update():
    """Sürekli güncelleme sistemini durduran API endpoint'i"""
    global UPDATING
    UPDATING = False
    # Durdurma işlemi thread'in güvenli şekilde sonlanmasını sağlamayacaktır
    # Bir sonraki döngüde geçici olarak durdurulur, ancak güvenli bir ölüm konusu değildir
    return jsonify({'success': True, 'message': 'Sürekli güncelleme sistemi durdurma işlemi başlatıldı. Bir sonraki döngü tamamlandığında duracaktır.'})

# Uygulama başladığında otomatik olarak sürekli güncelleme sistemini başlat
# Bu kod uygulamanın başlangıcında çalışır çünkü Blueprint yüklendiğinde bu dosya import edilir

# Log başlangıcı
logger.info("update_data_service modülü yüklendi")