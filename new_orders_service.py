from flask import render_template, request, Blueprint
from flask_sqlalchemy import SQLAlchemy
import math
from models import Order


# Blueprint tanımlaması
new_orders_service_bp = Blueprint('new_orders_service', __name__)




# "Yeni" statüsündeki siparişleri gösteren rota
@new_orders_service_bp.route('/order-list/new', methods=['GET'])
def get_new_orders():
    page = int(request.args.get('page', 1))
    per_page = 50

    # Veritabanından "Yeni" statüsündeki siparişleri al
    orders_query = Order.query.filter_by(status='Yeni')

    # Siparişleri tarihe göre sırala (en güncel tarih en üstte)
    orders_query = orders_query.order_by(Order.order_date.desc())

    # Sayfalama
    paginated_orders = orders_query.paginate(page=page, per_page=per_page, error_out=False)
    orders = paginated_orders.items
    total_orders_count = paginated_orders.total
    total_pages = paginated_orders.pages

    # Ürün detaylarını birleştir
    for order in orders:
        skus = order.merchant_sku.split(', ') if order.merchant_sku else []
        barcodes = order.product_barcode.split(', ') if order.product_barcode else []

        # Eğer uzunluklar eşleşmiyorsa boş string ekle
        max_length = max(len(skus), len(barcodes))
        skus += [''] * (max_length - len(skus))
        barcodes += [''] * (max_length - len(barcodes))

        order.details = [{'sku': sku, 'barcode': barcode} for sku, barcode in zip(skus, barcodes)]

    # Şablona gerekli değişkenleri gönderme
    return render_template(
        'order_list.html',
        orders=orders,
        page=page,
        total_pages=total_pages,
        total_orders_count=total_orders_count
    )
