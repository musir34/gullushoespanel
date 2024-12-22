from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, jsonify
from models import db, Archive, Order, Product
from trendyol_api import SUPPLIER_ID
from update_service import update_order_status_to_picking
import json
import os
import traceback

# Yeni Blueprint oluşturuldu
archive_bp = Blueprint('archive', __name__)

# Yardımcı fonksiyonlar
def compute_time_left(delivery_date):
    if delivery_date:
        try:
            now = datetime.now()
            time_diff = delivery_date - now

            if time_diff.total_seconds() > 0:
                days, seconds = divmod(time_diff.total_seconds(), 86400)
                hours, seconds = divmod(seconds, 3600)
                minutes = seconds // 60
                return f"{int(days)} gün {int(hours)} saat {int(minutes)} dakika"
            else:
                return "0 dakika"
        except Exception as e:
            print(f"Zaman hesaplama hatası: {e}")
            return "Kalan Süre Yok"
    else:
        return "Kalan Süre Yok"

def fetch_product_image(barcode):
    images_dir = os.path.join('static', 'images')
    for filename in os.listdir(images_dir):
        name, ext = os.path.splitext(filename)
        if name == barcode:
            return f"/static/images/{filename}"
    return "/static/images/default.jpg"

@archive_bp.route('/update_order_status', methods=['POST'])
def change_order_status():
    order_number = request.form.get('order_number')
    status = request.form.get('status')
    print(f"Gelen order_number: {order_number}, status: {status}")

    order = Order.query.filter_by(order_number=order_number).first()
    if order:
        order.status = status
        db.session.commit()
        print(f"Sipariş {order_number} durumu {status} olarak güncellendi")
        return jsonify({'success': True})
    else:
        # Arşivdeki siparişin statüsünü güncelleme
        archived_order = Archive.query.filter_by(order_number=order_number).first()
        if archived_order:
            archived_order.status = status
            db.session.commit()
            print(f"Arşivlenmiş sipariş {order_number} durumu {status} olarak güncellendi")
            return jsonify({'success': True})
        else:
            print("Sipariş bulunamadı.")
            return jsonify({'success': False, 'message': 'Sipariş bulunamadı.'})

@archive_bp.route('/process_order', methods=['POST'])
def execute_order_processing():
    order_number = request.form.get('order_number')
    print(f"Gelen order_number: {order_number} işlem için.")

    archived_order = Archive.query.filter_by(order_number=order_number).first()
    if archived_order:
        print(f"Sipariş {order_number} arşivde bulundu.")

        details = json.loads(archived_order.details) if isinstance(archived_order.details, str) else archived_order.details
        supplier_id = SUPPLIER_ID
        shipment_package_id = archived_order.shipment_package_id or archived_order.package_number
        lines = []

        for detail in details:
            line_id = detail.get('line_id')
            quantity = int(detail.get('quantity', 1))
            if line_id is None:
                return jsonify({'success': False, 'message': "'line_id' değeri bulunamadı."})
            lines.append({"lineId": int(line_id), "quantity": quantity})

        result = update_order_status_to_picking(supplier_id, shipment_package_id, lines)
        if result:
            # Siparişi arşivden çıkar ve ana sipariş listesine ekle
            archived_order.status = 'Picking'

            restored_order = Order(
                order_number=archived_order.order_number,
                status=archived_order.status,
                order_date=archived_order.order_date,
                details=archived_order.details,
                shipment_package_id=archived_order.shipment_package_id,
                package_number=archived_order.package_number,
                shipping_barcode=archived_order.shipping_barcode,
                cargo_provider_name=archived_order.cargo_provider_name,
                customer_name=archived_order.customer_name,
                customer_surname=archived_order.customer_surname,
                customer_address=archived_order.customer_address,
                agreed_delivery_date=archived_order.agreed_delivery_date,
                # Diğer gerekli alanları ekleyebilirsiniz
            )
            db.session.add(restored_order)
            db.session.delete(archived_order)
            db.session.commit()

            print(f"Sipariş {order_number} işlendi ve ana siparişlere taşındı.")
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'message': 'API isteği başarısız oldu.'})
    else:
        return jsonify({'success': False, 'message': 'Sipariş bulunamadı.'})

@archive_bp.route('/cancel_order', methods=['POST'])
def order_cancellation():
    order_number = request.form.get('order_number')
    print(f"Gelen iptal isteği için order_number: {order_number}")

    order = Order.query.filter_by(order_number=order_number).first()
    if order:
        order.status = 'İptal Edildi'
        db.session.commit()
        print(f"Sipariş {order_number} durumu 'İptal Edildi' olarak güncellendi.")
        return jsonify({'success': True})

    archived_order = Archive.query.filter_by(order_number=order_number).first()
    if archived_order:
        archived_order.status = 'İptal Edildi'
        db.session.commit()
        print(f"Arşivdeki sipariş {order_number} durumu 'İptal Edildi' olarak güncellendi.")
        return jsonify({'success': True})
    else:
        print("Sipariş hem ana listede hem de arşivde bulunamadı.")
        return jsonify({'success': False, 'message': 'Sipariş bulunamadı.'})

@archive_bp.route('/archive')
def display_archive():
    page = request.args.get('page', 1, type=int)
    per_page = 10

    pagination = Archive.query.order_by(Archive.order_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False)
    orders_to_show = pagination.items
    total_archived_orders_count = pagination.total

    # Ürünleri veritabanından çekelim
    products_list = Product.query.all()
    products_dict = {product.barcode: product for product in products_list}

    for order in orders_to_show:
        try:
            # Kargoya kalan süreyi hesaplayalım
            remaining_time = compute_time_left(order.agreed_delivery_date)
            order.remaining_time = remaining_time

            # Kalan süreyi saat cinsinden hesaplayın
            now = datetime.now()
            if order.agreed_delivery_date:
                time_difference = order.agreed_delivery_date - now
                order.remaining_time_in_hours = time_difference.total_seconds() / 3600
            else:
                order.remaining_time_in_hours = 0

            # Ürün detaylarını işleyelim
            details_json = order.details or '[]'
            if isinstance(details_json, str):
                details_list = json.loads(details_json)
            else:
                details_list = details_json

            products = []
            for detail in details_list:
                product_barcode = detail.get('barcode', '')
                product_info = products_dict.get(product_barcode, {})
                image_url = fetch_product_image(product_barcode)

                products.append({
                    'sku': detail.get('sku', 'Bilinmeyen SKU'),
                    'barcode': product_barcode,
                    'image_url': image_url
                })

            order.products = products

        except Exception as e:
            print(f"Sipariş {order.order_number} için hata: {e}")
            traceback.print_exc()
            order.remaining_time = 'Kalan Süre Yok'
            order.products = []
            order.remaining_time_in_hours = 0

    return render_template(
        'archive.html',
        orders=orders_to_show,
        page=page,
        total_pages=pagination.pages,
        total_archived_orders_count=total_archived_orders_count
    )

@archive_bp.route('/archive_order', methods=['POST'])
def archive_an_order():
    order_number = request.form.get('order_number')
    archive_reason = request.form.get('archive_reason')
    print(f"Gelen arşivleme isteği için order_number: {order_number}, neden: {archive_reason}")

    order = Order.query.filter_by(order_number=order_number).first()
    if order:
        print(f"Sipariş arşivleniyor: {order_number}, nedeni: {archive_reason}")

        archived_order = Archive(
            order_number=order.order_number,
            status=order.status,
            order_date=order.order_date,
            details=order.details,
            shipment_package_id=order.shipment_package_id,
            package_number=order.package_number,
            shipping_barcode=order.shipping_barcode,
            cargo_provider_name=order.cargo_provider_name,
            customer_name=order.customer_name,
            customer_surname=order.customer_surname,
            customer_address=order.customer_address,
            agreed_delivery_date=order.agreed_delivery_date,
            archive_reason=archive_reason,
            archive_date=datetime.now(),
            # Diğer gerekli alanları ekleyebilirsiniz
        )

        db.session.add(archived_order)
        db.session.delete(order)
        db.session.commit()

        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'message': 'Sipariş bulunamadı.'})

@archive_bp.route('/restore_from_archive', methods=['POST'])
def recover_from_archive():
    order_number = request.form.get('order_number')
    print(f"Arşivden geri yükleniyor: {order_number}")

    archived_order = Archive.query.filter_by(order_number=order_number).first()
    if archived_order:
        restored_order = Order(
            order_number=archived_order.order_number,
            status='Created',  # Sipariş durumu yeniden başlatılıyor
            order_date=archived_order.order_date,
            details=archived_order.details,
            shipment_package_id=archived_order.shipment_package_id,
            package_number=archived_order.package_number,
            shipping_barcode=archived_order.shipping_barcode,
            cargo_provider_name=archived_order.cargo_provider_name,
            customer_name=archived_order.customer_name,
            customer_surname=archived_order.customer_surname,
            customer_address=archived_order.customer_address,
            agreed_delivery_date=archived_order.agreed_delivery_date,
            # Diğer gerekli alanları ekleyebilirsiniz
        )

        db.session.add(restored_order)
        db.session.delete(archived_order)
        db.session.commit()

        print(f"Sipariş {order_number} ana siparişlere geri yüklendi.")
        return jsonify({'success': True, 'message': 'Sipariş başarıyla geri yüklendi.'})
    else:
        return jsonify({'success': False, 'message': 'Sipariş arşivde bulunamadı.'})

@archive_bp.route('/delete_archived_order', methods=['POST'])
def remove_archived_order():
    order_numbers = request.form.getlist('order_numbers[]')
    if not order_numbers:
        order_number = request.form.get('order_number')
        if order_number:
            order_numbers = [order_number]
        else:
            return jsonify({'success': False, 'message': 'Silinecek sipariş seçilmedi.'})

    deleted_count = 0
    for order_number in order_numbers:
        print(f"Arşivden siliniyor: {order_number}")
        archived_order = Archive.query.filter_by(order_number=order_number).first()
        if archived_order:
            db.session.delete(archived_order)
            deleted_count += 1

    if deleted_count > 0:
        db.session.commit()
        message = f"{deleted_count} sipariş başarıyla silindi."
        print(message)
        return jsonify({'success': True, 'message': message})
    else:
        return jsonify({'success': False, 'message': 'Silinecek sipariş bulunamadı.'})
