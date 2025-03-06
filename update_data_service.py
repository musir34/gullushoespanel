
from flask import Blueprint, render_template, request, jsonify, current_app
from datetime import datetime
import json
import os
import asyncio
import logging
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
    return render_template('veri_guncelleme_durumu.html', last_updates=last_updates)

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
