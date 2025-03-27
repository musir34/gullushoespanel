from flask import Blueprint, render_template, request
from models import db, OrderCreated  # Artık 'Order' yerine 'OrderCreated' kullanıyoruz

new_orders_service_bp = Blueprint('new_orders_service', __name__)

@new_orders_service_bp.route('/order-list/new', methods=['GET'])
def get_new_orders():
    """
    'Yeni' statüsündeki siparişleri gösterir.
    Artık 'OrderCreated' tablosunu sorguluyoruz.
    """
    page = int(request.args.get('page', 1))
    per_page = 50

    # Veritabanından OrderCreated tablolu siparişleri al
    # (En güncel tarih en üstte)
    orders_query = OrderCreated.query.order_by(OrderCreated.order_date.desc())

    # Sayfalama (Flask-SQLAlchemy paginate)
    paginated_orders = orders_query.paginate(page=page, per_page=per_page, error_out=False)
    orders = paginated_orders.items
    total_orders_count = paginated_orders.total
    total_pages = paginated_orders.pages

    # Ürün detaylarını birleştir
    for order in orders:
        skus = order.merchant_sku.split(', ') if order.merchant_sku else []
        barcodes = order.product_barcode.split(', ') if order.product_barcode else []

        max_length = max(len(skus), len(barcodes))
        skus += [''] * (max_length - len(skus))
        barcodes += [''] * (max_length - len(barcodes))

        order.details = [{'sku': s, 'barcode': b} for s, b in zip(skus, barcodes)]

    # Şablona gerekli değişkenleri gönderme
    return render_template(
        'order_list.html',
        orders=orders,
        page=page,
        total_pages=total_pages,
        total_orders_count=total_orders_count
    )
