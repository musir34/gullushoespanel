from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy import literal, union_all
from sqlalchemy.orm import aliased
import json
import os
import logging
from datetime import datetime

from models import db, Product, OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled
from barcode_utils import generate_barcode  # Bunu yalnızca generate_barcode için kullanıyoruz

order_list_service_bp = Blueprint('order_list_service', __name__)
logger = logging.getLogger(__name__)

############################
# 0) Ürün barkod resmini bulma fonksiyonu
############################
def get_product_image(barcode):
    """
    Ürün barkoduna göre resim dosyası yolunu döndürür.
    """
    images_folder = os.path.join('static', 'images')
    extensions = ['.jpg', '.jpeg', '.png', '.gif']
    for ext in extensions:
        image_filename = f"{barcode}{ext}"
        image_path = os.path.join(images_folder, image_filename)
        if os.path.exists(image_path):
            return f"/static/images/{image_filename}"
    return "/static/logo/gullu.png"

############################
# 1) UNION ALL Sorgusu
############################
def get_union_all_orders():
    """
    Beş tabloda ortak kolonları seçip UNION ALL ile birleştirir.
    .label('details') diyerek tablo bazında 'details' alanını seçiyoruz.
    """
    c = db.session.query(
        OrderCreated.id.label('id'),
        OrderCreated.order_number.label('order_number'),
        OrderCreated.order_date.label('order_date'),
        OrderCreated.details.label('details'),
        OrderCreated.merchant_sku.label('merchant_sku'),
        OrderCreated.product_barcode.label('product_barcode'),
        literal('Created').label('status_name')
    )

    p = db.session.query(
        OrderPicking.id.label('id'),
        OrderPicking.order_number.label('order_number'),
        OrderPicking.order_date.label('order_date'),
        OrderPicking.details.label('details'),
        OrderPicking.merchant_sku.label('merchant_sku'),
        OrderPicking.product_barcode.label('product_barcode'),
        literal('Picking').label('status_name')
    )

    s = db.session.query(
        OrderShipped.id.label('id'),
        OrderShipped.order_number.label('order_number'),
        OrderShipped.order_date.label('order_date'),
        OrderShipped.details.label('details'),
        OrderShipped.merchant_sku.label('merchant_sku'),
        OrderShipped.product_barcode.label('product_barcode'),
        literal('Shipped').label('status_name')
    )

    d = db.session.query(
        OrderDelivered.id.label('id'),
        OrderDelivered.order_number.label('order_number'),
        OrderDelivered.order_date.label('order_date'),
        OrderDelivered.details.label('details'),
        OrderDelivered.merchant_sku.label('merchant_sku'),
        OrderDelivered.product_barcode.label('product_barcode'),
        literal('Delivered').label('status_name')
    )

    x = db.session.query(
        OrderCancelled.id.label('id'),
        OrderCancelled.order_number.label('order_number'),
        OrderCancelled.order_date.label('order_date'),
        OrderCancelled.details.label('details'),
        OrderCancelled.merchant_sku.label('merchant_sku'),
        OrderCancelled.product_barcode.label('product_barcode'),
        literal('Cancelled').label('status_name')
    )

    return c.union_all(p, s, d, x)

############################
# 2) Tüm siparişleri listeleme
############################
def get_order_list():
    """
    Tüm tabloları tek listede gösterir (UNION ALL).
    Arama (order_number) + sayfalama yapar.
    """
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 50
        search_query = request.args.get('search', None)

        union_query = get_union_all_orders()
        sub = union_query.subquery()

        # Aliased
        from sqlalchemy.orm import aliased
        AllOrders = aliased(sub)

        q = db.session.query(AllOrders)

        # Arama
        if search_query:
            search_query = search_query.strip()
            q = q.filter(AllOrders.c.order_number.ilike(f"%{search_query}%"))
            logger.debug(f"Arama sorgusuna göre filtre: {search_query}")

        from sqlalchemy import desc
        q = q.order_by(desc(AllOrders.c.order_date))

        # Flask-SQLAlchemy paginate
        paginated_orders = q.paginate(page=page, per_page=per_page, error_out=False)

        rows = paginated_orders.items
        total_pages = paginated_orders.pages
        total_orders_count = paginated_orders.total

        # row'ları "mock" order objesine çevir
        orders = []
        class MockOrder:
            pass
        for r in rows:
            mock = MockOrder()
            mock.id = r.id
            mock.order_number = r.order_number
            mock.order_date = r.order_date
            mock.details = r.details
            mock.merchant_sku = r.merchant_sku
            mock.product_barcode = r.product_barcode
            mock.status = r.status_name
            orders.append(mock)

        # process details
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
        flash("Sipariş listesi yüklenirken hata oluştu.", "danger")
        return redirect(url_for('home.home'))

############################
# 3) Sipariş detaylarını işlemek
############################
def process_order_details(orders):
    """
    Her sipariş için 'details' alanını işleyerek ürün detaylarını hazırlar.
    """
    try:
        # barkod seti topla
        barcodes = set()
        for order in orders:
            details_json = order.details
            if not details_json:
                continue
            try:
                details_list = json.loads(details_json) if isinstance(details_json, str) else details_json
            except json.JSONDecodeError:
                continue

            for d in details_list:
                bc = d.get('barcode','')
                if bc:
                    barcodes.add(bc)

        products_dict = {}
        if barcodes:
            products_list = Product.query.filter(Product.barcode.in_(barcodes)).all()
            products_dict = {p.barcode: p for p in products_list}

        for order in orders:
            if not order.details:
                order.processed_details = []
                continue

            try:
                details_list = json.loads(order.details) if isinstance(order.details, str) else order.details
            except json.JSONDecodeError:
                order.processed_details = []
                continue

            processed_details = []
            for d in details_list:
                product_barcode = d.get('barcode','')
                sku = d.get('sku','Bilinmeyen SKU')
                qty = d.get('quantity',0)
                color = d.get('color','')
                size = d.get('size','')
                # resim bul
                img_url = get_product_image(product_barcode)

                processed_details.append({
                    'sku': sku,
                    'barcode': product_barcode,
                    'image_url': img_url,
                    'quantity': qty,
                    'color': color,
                    'size': size
                })
            order.processed_details = processed_details
    except Exception as e:
        logger.error(f"Hata: process_order_details - {e}")

############################
# 4) Belirli Durumlara Göre Filtre (yeni tablolar)
############################
def get_filtered_orders(status):
    """
    Created, Picking, Shipped, Delivered, Cancelled tablolarının
    her birine ayrı sorgu atanır. Eskisi gibi status=... filter
    yerine, tablo seçeceğiz.
    """
    status_map = {
        'Yeni': OrderCreated,
        'İşleme Alındı': OrderPicking,
        'Kargoda': OrderShipped,
        'Teslim Edildi': OrderDelivered,
        'İptal Edildi': OrderCancelled
    }
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 50
        model_cls = status_map.get(status, None)
        if not model_cls:
            flash(f"{status} durumuna ait tablo bulunamadı.", "warning")
            return redirect(url_for('home.home'))

        orders_query = model_cls.query.order_by(model_cls.order_date.desc())
        paginated_orders = orders_query.paginate(page=page, per_page=per_page, error_out=False)
        orders = paginated_orders.items
        total_pages = paginated_orders.pages
        total_orders_count = paginated_orders.total

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
        flash(f'{status} durumundaki siparişler yüklenirken bir hata oluştu.', 'danger')
        return redirect(url_for('home.home'))

############################
# 5) Sipariş arama (tek tablo değil!)
############################
def search_order_by_number(order_number):
    """
    Eski kod Order tablosunda arıyordu; şimdi beş tabloyu da kontrol ediyoruz.
    """
    try:
        logger.debug(f"Sipariş aranıyor: {order_number}")
        for model_cls in (OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled):
            order = model_cls.query.filter_by(order_number=order_number).first()
            if order:
                logger.debug(f"Buldum: {order} tablo {model_cls.__tablename__}")
                return order
        logger.debug("Sipariş bulunamadı.")
        return None
    except Exception as e:
        logger.error(f"Hata: search_order_by_number - {e}")
        return None

###############################################
# Route kısımları
###############################################
@order_list_service_bp.route('/order-list/all', methods=['GET'])
def order_list_all():
    return get_order_list()

@order_list_service_bp.route('/order-list/new', methods=['GET'])
def order_list_new():
    return get_filtered_orders('Yeni')

@order_list_service_bp.route('/order-list/processed', methods=['GET'])
def order_list_processed():
    return get_filtered_orders('İşleme Alındı')

@order_list_service_bp.route('/order-list/shipped', methods=['GET'])
def order_list_shipped():
    return get_filtered_orders('Kargoda')

@order_list_service_bp.route('/order-list/delivered', methods=['GET'])
def order_list_delivered():
    return get_filtered_orders('Teslim Edildi')

@order_list_service_bp.route('/order-label', methods=['POST'])
def order_label():
    from urllib.parse import unquote
    try:
        order_number = request.form.get('order_number')
        shipping_code = request.form.get('shipping_code')
        cargo_provider = unquote(unquote(request.form.get('cargo_provider','')))
        customer_name = unquote(unquote(request.form.get('customer_name','')))
        customer_surname = unquote(unquote(request.form.get('customer_surname','')))
        customer_address = unquote(unquote(request.form.get('customer_address','')))
        telefon_no = request.form.get('telefon_no','Bilinmiyor')

        logger.debug(f"Order num: {order_number}, shipping_code: {shipping_code}, telefon_no: {telefon_no}")

        if shipping_code:
            barcode_path = generate_barcode(shipping_code)
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
            telefon_no=telefon_no
        )
    except Exception as e:
        logger.error(f"Hata: order_label - {e}")
        flash('Kargo etiketi oluşturulurken bir hata oluştu.', 'danger')
        return redirect(url_for('home.home'))
