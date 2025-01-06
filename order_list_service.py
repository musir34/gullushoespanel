from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from models import db, Product, Order
from barcode_utils import generate_barcode
import json
import os
import logging
from urllib.parse import unquote
from datetime import datetime

order_list_service_bp = Blueprint('order_list_service', __name__)

# Loglama ayarları
logger = logging.getLogger(__name__)

# Yardımcı Fonksiyonlar
def get_product_image(barcode):
    """
    Ürün barkoduna göre resim dosyasını döndürür.
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

def get_order_list():
    """
    Sipariş listesini getirir ve sayfalama ile birlikte render eder.
    """
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 50
        search_query = request.args.get('search', None)

        logger.debug(f"Sayfa: {page}, Sayfa Başına: {per_page}, Arama Sorgusu: {search_query}")

        # Sipariş sorgusu oluştur
        orders_query = Order.query.order_by(Order.order_date.desc())

        # Arama sorgusu uygulanırsa filtrele
        if search_query:
            search_query = search_query.strip()
            orders_query = orders_query.filter(Order.order_number.ilike(f"%{search_query}%"))
            logger.debug(f"Arama sorgusuna göre filtrelenen siparişler: {search_query}")

        # Sayfalama işlemi
        paginated_orders = orders_query.paginate(page=page, per_page=per_page, error_out=False)
        orders = paginated_orders.items
        total_pages = paginated_orders.pages
        total_orders_count = paginated_orders.total

        logger.debug(f"Toplam Sayfa: {total_pages}, Getirilen Sipariş Sayısı: {len(orders)}, Toplam Sipariş Sayısı: {total_orders_count}")

        # Sipariş detaylarını işleme
        process_order_details(orders)

        return render_template(
            'order_list.html',
            orders=orders,
            page=page,
            total_pages=total_pages,
            total_orders_count=total_orders_count,
            search_query=search_query
        )
    except Exception as e:
        logger.error(f"Hata: get_order_list - {e}")
        logger.exception(e)
        flash('Sipariş listesi yüklenirken bir hata oluştu.', 'danger')
        return redirect(url_for('home.home'))

def process_order_details(orders):
    """
    Her sipariş için 'details' alanını işleyerek ürün detaylarını hazırlar.
    """
    try:
        # Siparişlerden tüm benzersiz barkodları toplayalım
        barcodes = set()
        for order in orders:
            details_json = order.details
            if not details_json:
                continue
            try:
                details_list = json.loads(details_json) if isinstance(details_json, str) else details_json
            except json.JSONDecodeError as e:
                logger.error(f"JSON çözümleme hatası - Sipariş {order.order_number}: {e}")
                continue

            for detail in details_list:
                barcode = detail.get('barcode', '')
                if barcode:
                    barcodes.add(barcode)

        # Gerekli ürünleri veritabanından çekelim
        products_dict = {}
        if barcodes:
            products_list = Product.query.filter(Product.barcode.in_(barcodes)).all()
            products_dict = {product.barcode: product for product in products_list}

        for order in orders:
            details_json = order.details
            if not details_json:
                order.processed_details = []
                continue

            try:
                details_list = json.loads(details_json) if isinstance(details_json, str) else details_json
            except json.JSONDecodeError as e:
                logger.error(f"JSON çözümleme hatası - Sipariş {order.order_number}: {e}")
                order.processed_details = []
                continue

            processed_details = []
            for detail in details_list:
                product_barcode = detail.get('barcode', '')
                original_barcode = detail.get('original_barcode', product_barcode)
                sku = detail.get('sku', 'Bilinmeyen SKU')
                quantity = detail.get('quantity', 0)
                color = detail.get('color', '')
                size = detail.get('size', '')
                image_path = f"static/images/{original_barcode}.jpg"
                if not os.path.exists(image_path):
                    image_path = "static/images/default.jpg"
                image_url = image_path
                processed_details.append({
                    'sku': sku,
                    'barcode': product_barcode,
                    'image_url': image_url,
                    'quantity': quantity,
                    'color': color,
                    'size': size
                })
            order.processed_details = processed_details
    except Exception as e:
        logger.error(f"Hata: process_order_details - {e}")
        logger.exception(e)

def get_filtered_orders(status):
    """
    Belirli bir duruma göre siparişleri getirir ve render eder.
    """
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 50
        logger.debug(f"Statüye göre filtreleme: {status}, Sayfa: {page}, Sayfa Başına: {per_page}")

        # Statü eşlemesi
        status_map = {
            'Yeni': 'Created',
            'İşleme Alındı': 'Picking',
            'Kargoda': 'Shipped',
            'Teslim Edildi': 'Delivered'
        }

        mapped_status = status_map.get(status, status)
        orders_query = Order.query.filter_by(status=mapped_status).order_by(Order.order_date.desc())

        paginated_orders = orders_query.paginate(page=page, per_page=per_page, error_out=False)
        orders = paginated_orders.items
        total_pages = paginated_orders.pages
        total_orders_count = paginated_orders.total

        logger.debug(f"Getirilen Sipariş Sayısı: {len(orders)}")
        for order in orders:
            logger.debug(f"Sipariş Numarası: {order.order_number}, Statü: {order.status}")

        # Sipariş detaylarını işleme
        process_order_details(orders)

        return render_template(
            'order_list.html',
            orders=orders,
            page=page,
            total_pages=total_pages,
            total_orders_count=total_orders_count
        )
    except Exception as e:
        logger.error(f"Hata: get_filtered_orders - {e}")
        logger.exception(e)
        flash(f'{status} durumundaki siparişler yüklenirken bir hata oluştu.', 'danger')
        return redirect(url_for('home.home'))

def search_order_by_number(order_number):
    """
    Sipariş numarasına göre sipariş arar.
    """
    try:
        logger.debug(f"Sipariş aranıyor: {order_number}")
        order = Order.query.filter_by(order_number=order_number).first()
        if order:
            logger.debug(f"Sipariş bulundu: {order}")
        else:
            logger.debug("Sipariş bulunamadı.")
        return order
    except Exception as e:
        logger.error(f"Hata: search_order_by_number - {e}")
        logger.exception(e)
        return None

# Sipariş listesi sayfası
@order_list_service_bp.route('/order-list/all', methods=['GET'])
def order_list_all():
    return get_order_list()

# Yeni siparişler
@order_list_service_bp.route('/order-list/new', methods=['GET'])
def order_list_new():
    try:
        return get_filtered_orders('Yeni')
    except Exception as e:
        logger.error(f"Hata: order_list_new - {e}")
        logger.exception(e)
        flash('Yeni siparişler yüklenirken bir hata oluştu.', 'danger')
        return redirect(url_for('home.home'))

# İşleme alınan siparişler
@order_list_service_bp.route('/order-list/processed', methods=['GET'])
def order_list_processed():
    return get_filtered_orders('İşleme Alındı')

# Kargoya verilen siparişler
@order_list_service_bp.route('/order-list/shipped', methods=['GET'])
def order_list_shipped():
    return get_filtered_orders('Kargoda')

# Teslim edilen siparişler
@order_list_service_bp.route('/order-list/delivered', methods=['GET'])
def order_list_delivered():
    return get_filtered_orders('Teslim Edildi')

@order_list_service_bp.route('/order-label', methods=['POST'])
def order_label():
    try:
        order_number = request.form.get('order_number')
        shipping_code = request.form.get('shipping_code')
        cargo_provider = unquote(unquote(request.form.get('cargo_provider', '')))
        customer_name = unquote(unquote(request.form.get('customer_name', '')))
        customer_surname = unquote(unquote(request.form.get('customer_surname', '')))
        customer_address = unquote(unquote(request.form.get('customer_address', '')))
        telefon_no = request.form.get('telefon_no', 'Bilinmiyor')  # Telefon numarasını al, yoksa 'Bilinmiyor'

        # Konsolda kontrol et
        logger.debug(f"Formdan gelen tüm veriler: {request.form}") 
        logger.debug(f"Formdan gelen telefon_no: {telefon_no}")  

        if shipping_code:
            barcode_path = generate_barcode(shipping_code)
            logger.debug(f"Barkod Yolu: {barcode_path}")
        else:
            barcode_path = None

        return render_template(
            'order_label.html',
            order_number=order_number,
            shipping_code=shipping_code,
            barcode_path=barcode_path,
            cargo_provider_name=cargo_provider,
            customer_name=customer_name,
            customer_surname=customer_surname,
            customer_address=customer_address,
            telefon_no=telefon_no  # Telefon numarasını şablona iletin
        )
    except Exception as e:
        logger.error(f"Hata: order_label - {e}")
        logger.exception(e)
        flash('Kargo etiketi oluşturulurken bir hata oluştu.', 'danger')
        return jsonify({'error': 'Internal Server Error'}), 500
