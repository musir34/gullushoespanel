import logging
from datetime import datetime
from flask import Blueprint, render_template
import json
import os
import traceback
from models import Order, Product

# Logging ayarları
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from flask import Blueprint, render_template, redirect, url_for
home_bp = Blueprint('home_bp', __name__)

@home_bp.route('/')
def home():
    try:
        order_data = get_home()
        return render_template('home.html', **order_data)
    except Exception as e:
        logging.error(f"Anasayfa yüklenirken hata: {str(e)}")
        return render_template('home.html', **default_order_data())

def get_home():
    """
    Ana sayfa için gerekli sipariş verilerini hazırlar.
    """
    try:
        # En eski 'Created' statüsündeki siparişi veritabanından çekelim
        oldest_order = Order.query.filter_by(status='Created').order_by(Order.order_date).first()

        if oldest_order:
            logging.info("En eski 'Created' statüsündeki sipariş işleniyor.")

            shipping_barcode = oldest_order.shipping_barcode
            remaining_time = calculate_remaining_time(oldest_order.agreed_delivery_date)

            # Sipariş detaylarını alalım
            details_json = oldest_order.details or '[]'  # 'details' alanı eksikse varsayılan olarak boş liste
            logging.info(f"Sipariş detayları: {details_json}")

            # details_json tipini kontrol edelim
            if isinstance(details_json, str):
                try:
                    details_list = json.loads(details_json)
                except json.JSONDecodeError as e:
                    logging.error(f"JSON çözümleme hatası: {e}")
                    details_list = []
            elif isinstance(details_json, list):
                details_list = details_json
            else:
                logging.warning("details alanı beklenmeyen bir tipte.")
                details_list = []

            # Barkodları çıkaralım
            barcodes = [detail.get('barcode', '') for detail in details_list if 'barcode' in detail]

            # İlgili ürünleri veritabanından çekelim
            if barcodes:
                products_list = Product.query.filter(Product.barcode.in_(barcodes)).all()
                products_dict = {product.barcode: product for product in products_list}
            else:
                products_dict = {}

            # Ürün listesini oluşturalım
            products = []
            for detail in details_list:
                product_barcode = detail.get('barcode', '')
                image_url = get_product_image(product_barcode)

                products.append({
                    'sku': detail.get('sku', 'Bilinmeyen SKU'),
                    'barcode': product_barcode,
                    'image_url': image_url
                })

            oldest_order.products = products

            return {
                'order': oldest_order,
                'order_number': oldest_order.order_number or 'Sipariş Yok',
                'products': products,
                'merchant_sku': oldest_order.merchant_sku or 'Bilgi Yok',
                'shipping_code': shipping_barcode if shipping_barcode else 'Kargo Kodu Yok',
                'cargo_provider_name': oldest_order.cargo_provider_name or 'Kargo Firması Yok',
                'customer_name': oldest_order.customer_name or 'Alıcı Yok',
                'customer_surname': oldest_order.customer_surname or 'Soyad Yok',
                'customer_address': oldest_order.customer_address or 'Adres Yok',
                'remaining_time': remaining_time
            }
        else:
            logging.info("İşlenecek 'Created' statüsünde sipariş yok.")
            return default_order_data()

    except Exception as e:
        logging.error(f"Bir hata oluştu: {e}")
        traceback.print_exc()
        return default_order_data()

def default_order_data():
    """
    Varsayılan boş sipariş verilerini döndürür ve hata durumunda kullanılır.
    """
    return {
        'order': None,
        'order_number': 'Sipariş Yok',
        'products': [],
        'merchant_sku': 'Bilgi Yok',
        'shipping_code': 'Kargo Kodu Yok',
        'cargo_provider_name': 'Kargo Firması Yok',
        'customer_name': 'Alıcı Yok',
        'customer_surname': 'Soyad Yok',
        'customer_address': 'Adres Yok',
        'remaining_time': 'Kalan Süre Yok',
        'error_message': 'Siparişler yüklenirken bir hata oluştu. Lütfen sayfayı yenileyin.'
    }

def calculate_remaining_time(delivery_date):
    """
    Teslimat süresini hesaplar.
    """
    if delivery_date:
        try:
            now = datetime.now()
            time_difference = delivery_date - now

            if time_difference.total_seconds() > 0:
                days, seconds = divmod(time_difference.total_seconds(), 86400)
                hours, seconds = divmod(seconds, 3600)
                minutes = seconds // 60
                return f"{int(days)} gün {int(hours)} saat {int(minutes)} dakika"
            else:
                return "0 dakika"
        except Exception as ve:
            logging.error(f"Tarih hesaplama hatası: {ve}")
            return "Kalan Süre Yok"
    else:
        return "Kalan Süre Yok"

def get_product_image(barcode):
    """
    Ürün görselinin yolunu döndürür.
    """
    images_folder = os.path.join('static', 'images')
    # Olası dosya uzantıları
    extensions = ['.jpg', '.jpeg', '.png', '.gif']
    for ext in extensions:
        image_filename = f"{barcode}{ext}"
        image_path = os.path.join(images_folder, image_filename)
        if os.path.exists(image_path):
            return f"/static/images/{image_filename}"
    return "/static/images/default.jpg"
