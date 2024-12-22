from flask import render_template, request, Blueprint
from flask_sqlalchemy import SQLAlchemy
from models import Order
import math

# Blueprint tanımlaması
all_orders_service_bp = Blueprint('all_orders_service', __name__)



@all_orders_service_bp.route('/order-list/all', methods=['GET'])
def get_all_orders():
    page = int(request.args.get('page', 1))
    per_page = 50
    search = request.args.get('search')

    # Veritabanından tüm siparişleri çek
    orders_query = Order.query

    # Sipariş numarasına göre filtreleme
    if search:
        orders_query = orders_query.filter(Order.order_number.ilike(f'%{search}%'))

    # Siparişleri tarihe göre sıralama (en yeni sipariş en üstte olacak şekilde)
    orders_query = orders_query.order_by(Order.order_date.desc())

    # Sadece son 100,000 siparişi tut
    orders_query = orders_query.limit(100000)

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

    # Debugging için konsola yazdırma
    print(f"Sayfa: {page}, Toplam Sayfa: {total_pages}, Toplam Sipariş: {total_orders_count}")

    return render_template(
        'order_list.html',
        orders=orders,
        page=page,
        total_pages=total_pages,
        total_orders_count=total_orders_count
    )
