import os
import json
import traceback
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify
from models import db, Archive, Product
# Çok tablolu sipariş modelleri
from models import OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled
from trendyol_api import SUPPLIER_ID
from update_service import update_order_status_to_picking

archive_bp = Blueprint('archive', __name__)

#############################
# 1) Yardımcı Fonksiyonlar
#############################
def find_order_across_tables(order_number):
    """
    5 tabloda arar: Created, Picking, Shipped, Delivered, Cancelled
    Bulursa (obj, tablo_sinifi), bulamazsa (None, None)
    """
    for cls in [OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled]:
        found = cls.query.filter_by(order_number=order_number).first()
        if found:
            return found, cls
    return None, None

def compute_time_left(delivery_date):
    """
    Kalan teslim süresini (gün saat dakika) string olarak döndürür.
    """
    if not delivery_date:
        return "Kalan Süre Yok"
    try:
        now = datetime.now()
        diff = delivery_date - now
        if diff.total_seconds() <= 0:
            return "0 dakika"
        days, seconds = divmod(diff.total_seconds(), 86400)
        hours, seconds = divmod(seconds, 3600)
        minutes = int(seconds // 60)
        return f"{int(days)} gün {int(hours)} saat {minutes} dakika"
    except Exception as e:
        print(f"Zaman hesaplama hatası: {e}")
        return "Kalan Süre Yok"

def fetch_product_image(barcode):
    """
    'static/images' klasöründe barkod.jpg vb. arar, yoksa default döndürür.
    """
    images_dir = os.path.join('static', 'images')
    for filename in os.listdir(images_dir):
        name, ext = os.path.splitext(filename)
        if name == barcode:
            return f"/static/images/{filename}"
    return "/static/images/default.jpg"


#############################
# 2) Sipariş Statüsü Güncelleme
#############################
@archive_bp.route('/update_order_status', methods=['POST'])
def change_order_status():
    """
    Bir siparişin statüsünü güncelle.
    Eğer çok tablolu modelde sipariş Created/Picking/Shipped/... tablolarından birindeyse orada bulup statüsünü set etmek demek,
    ama gerçekte tablolar arası taşınması gerek.
    Basitçe "status" alanı varsa tablo içinde set ediyoruz demek. 
    (Örneğin tabloyu tek kolonla güncellemek isterseniz).
    """
    order_number = request.form.get('order_number')
    new_status = request.form.get('status')
    print(f"Gelen order_number: {order_number}, status: {new_status}")

    # 1) Archive tablosunda mı?
    archived_order = Archive.query.filter_by(order_number=order_number).first()
    if archived_order:
        archived_order.status = new_status
        db.session.commit()
        print(f"Arşivlenmiş sipariş {order_number} durumu {new_status} olarak güncellendi.")
        return jsonify({'success': True})

    # 2) Yoksa çok tablodan birinde mi?
    order_obj, table_cls = find_order_across_tables(order_number)
    if not order_obj:
        print("Sipariş bulunamadı.")
        return jsonify({'success': False, 'message': 'Sipariş bulunamadı.'})

    # Sadece tablo içindeki 'status' alanını güncelliyorsunuz 
    # (NOT: gerçekte tabloyu taşımanız gerekebilir)
    order_obj.status = new_status
    db.session.commit()
    print(f"{table_cls.__tablename__} içindeki sipariş {order_number} statü {new_status} olarak güncellendi.")
    return jsonify({'success': True})


#############################
# 3) Siparişi İşleme Al (Arşiv -> "Picking")
#############################
@archive_bp.route('/process_order', methods=['POST'])
def execute_order_processing():
    """
    Arşivdeki siparişi 'Picking' statüsüne geçirmek için:
    1) Trendyol API'ye -> "Picking" update
    2) Arşiv kaydını sil, 'OrderPicking' tablosuna ekle
    """
    order_number = request.form.get('order_number')
    print(f"Gelen order_number: {order_number} işlem için.")

    archived_order = Archive.query.filter_by(order_number=order_number).first()
    if not archived_order:
        return jsonify({'success': False, 'message': 'Sipariş arşivde bulunamadı.'})

    print(f"Sipariş {order_number} arşivde bulundu, 'Picking' yapılacak.")
    # Trendyol update
    details = json.loads(archived_order.details) if isinstance(archived_order.details, str) else archived_order.details
    lines = []
    for d in details:
        line_id = d.get('line_id')
        if not line_id:
            return jsonify({'success': False, 'message': "'line_id' değeri bulunamadı."})
        qty = int(d.get('quantity', 1))
        lines.append({"lineId": int(line_id), "quantity": qty})

    shipment_package_id = archived_order.shipment_package_id or archived_order.package_number
    supplier_id = SUPPLIER_ID
    result = update_order_status_to_picking(supplier_id, shipment_package_id, lines)
    if not result:
        return jsonify({'success': False, 'message': 'Trendyol API isteği başarısız oldu.'})

    # Trendyol update başarılı -> arşivdeki kaydı "Picking" tablosuna taşıyalım
    archived_order.status = 'Picking'  # isterseniz tablo alanı
    from models import OrderPicking  # picking tablosunu import
    # tabloya eklemek için: 
    new_picking = OrderPicking(
        order_number=archived_order.order_number,
        status='Picking',
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
        # Eksik kolonları da ekleyin
    )
    db.session.add(new_picking)
    db.session.delete(archived_order)
    db.session.commit()

    print(f"Sipariş {order_number} 'Picking' tablosuna taşındı (arşivden çıkarıldı).")
    return jsonify({'success': True})

#############################
# 4) Siparişi İptal Et
#############################
@archive_bp.route('/cancel_order', methods=['POST'])
def order_cancellation():
    """
    Siparişi bul (ya arşivde ya da 5 tablodan birinde) -> statüsünü "İptal Edildi" yap
    (Tabloda tutacaksanız 'OrderCancelled' tablosuna taşımanız da gerekebilir.)
    """
    order_number = request.form.get('order_number')
    print(f"Gelen iptal isteği için order_number: {order_number}")

    # 1) Arşivde mi?
    archived_order = Archive.query.filter_by(order_number=order_number).first()
    if archived_order:
        archived_order.status = 'İptal Edildi'
        db.session.commit()
        print(f"Arşivdeki sipariş {order_number} 'İptal Edildi' statüsüne alındı.")
        return jsonify({'success': True})

    # 2) Yoksa çok tablodan birinde
    order_obj, table_cls = find_order_across_tables(order_number)
    if not order_obj:
        print("Sipariş hem ana listede hem de arşivde bulunamadı.")
        return jsonify({'success': False, 'message': 'Sipariş bulunamadı.'})

    # Basitçe 'status' kolonu set ediyorsanız
    order_obj.status = 'İptal Edildi'
    db.session.commit()
    print(f"{table_cls.__tablename__} içindeki sipariş {order_number} iptal edildi.")
    return jsonify({'success': True})


#############################
# 5) Arşiv Görünümü
#############################
@archive_bp.route('/archive')
def display_archive():
    """
    Arşiv tablosundaki siparişleri listeler (sayfalı).
    """
    page = request.args.get('page', 1, type=int)
    per_page = 10

    pagination = Archive.query.order_by(Archive.order_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False)
    orders_to_show = pagination.items
    total_archived_orders_count = pagination.total

    # Ürün dictionary (barkod -> product)
    products_list = Product.query.all()
    products_dict = {p.barcode: p for p in products_list}

    for order in orders_to_show:
        # Kalan süre
        order.remaining_time = compute_time_left(order.agreed_delivery_date)

        # Saat cinsinden de
        now = datetime.now()
        if order.agreed_delivery_date:
            time_diff = order.agreed_delivery_date - now
            order.remaining_time_in_hours = time_diff.total_seconds() / 3600
        else:
            order.remaining_time_in_hours = 0

        # Detay parse
        details_json = order.details or '[]'
        if isinstance(details_json, str):
            try:
                details_list = json.loads(details_json)
            except:
                details_list = []
        else:
            details_list = details_json

        # Ürünler
        products = []
        for detail in details_list:
            product_barcode = detail.get('barcode', '')
            product_info = products_dict.get(product_barcode)
            image_url = fetch_product_image(product_barcode)

            products.append({
                'sku': detail.get('sku', 'Bilinmeyen SKU'),
                'barcode': product_barcode,
                'image_url': image_url
            })
        order.products = products

    return render_template(
        'archive.html',
        orders=orders_to_show,
        page=page,
        total_pages=pagination.pages,
        total_archived_orders_count=total_archived_orders_count
    )

#############################
# 6) Sipariş Arşivleme
#############################
@archive_bp.route('/archive_order', methods=['POST'])
def archive_an_order():
    """
    Çok tablolu modelde, siparişi bul -> arşive ekle -> o tablodan sil.
    """
    order_number = request.form.get('order_number')
    archive_reason = request.form.get('archive_reason')
    print(f"Sipariş arşivleniyor: {order_number}, neden: {archive_reason}")

    # Siparişi 5 tablodan birinde ara
    order_obj, table_cls = find_order_across_tables(order_number)
    if not order_obj:
        return jsonify({'success': False, 'message': 'Sipariş bulunamadı.'})

    # Arşiv objesi oluştur
    new_archive = Archive(
        order_number=order_obj.order_number,
        status=order_obj.status,
        order_date=order_obj.order_date,
        details=order_obj.details,
        shipment_package_id=getattr(order_obj, 'shipment_package_id', None),
        package_number=getattr(order_obj, 'package_number', None),
        shipping_barcode=getattr(order_obj, 'shipping_barcode', None),
        cargo_provider_name=getattr(order_obj, 'cargo_provider_name', None),
        customer_name=getattr(order_obj, 'customer_name', None),
        customer_surname=getattr(order_obj, 'customer_surname', None),
        customer_address=getattr(order_obj, 'customer_address', None),
        agreed_delivery_date=getattr(order_obj, 'agreed_delivery_date', None),
        archive_reason=archive_reason,
        archive_date=datetime.now()
        # Diğer alanları da ekleyebilirsiniz
    )
    db.session.add(new_archive)
    db.session.delete(order_obj)
    db.session.commit()

    print(f"Sipariş {order_number}, {table_cls.__tablename__} tablosundan silindi, arşive eklendi.")
    return jsonify({'success': True})


#############################
# 7) Arşivden Geri Yükleme
#############################
@archive_bp.route('/restore_from_archive', methods=['POST'])
def recover_from_archive():
    """
    Arşivdeki siparişi 'Created' tablosuna geri taşır.
    (Ya da dilediğiniz tabloya.)
    """
    order_number = request.form.get('order_number')
    print(f"Arşivden geri yükleniyor: {order_number}")

    archived_order = Archive.query.filter_by(order_number=order_number).first()
    if not archived_order:
        return jsonify({'success': False, 'message': 'Sipariş arşivde bulunamadı.'})

    # Hangi tabloya geri yükleyeceğinize siz karar verin. Burada 'Created' tablosuna alıyoruz:
    from models import OrderCreated
    restored_order = OrderCreated(
        order_number=archived_order.order_number,
        status='Created',
        order_date=archived_order.order_date,
        details=archived_order.details,
        shipment_package_id=archived_order.shipment_package_id,
        package_number=archived_order.package_number,
        shipping_barcode=archived_order.shipping_barcode,
        cargo_provider_name=archived_order.cargo_provider_name,
        customer_name=archived_order.customer_name,
        customer_surname=archived_order.customer_surname,
        customer_address=archived_order.customer_address,
        agreed_delivery_date=archived_order.agreed_delivery_date
        # vs.
    )

    db.session.add(restored_order)
    db.session.delete(archived_order)
    db.session.commit()

    print(f"Sipariş {order_number} arşivden çıkartıldı, 'Created' tablosuna eklendi.")
    return jsonify({'success': True, 'message': 'Sipariş başarıyla geri yüklendi.'})


#############################
# 8) Arşivden Silme
#############################
@archive_bp.route('/delete_archived_order', methods=['POST'])
def remove_archived_order():
    """
    Arşivdeki siparişi kalıcı olarak silmek.
    """
    order_numbers = request.form.getlist('order_numbers[]')
    if not order_numbers:
        order_number = request.form.get('order_number')
        if order_number:
            order_numbers = [order_number]
        else:
            return jsonify({'success': False, 'message': 'Silinecek sipariş seçilmedi.'})

    deleted_count = 0
    for onum in order_numbers:
        print(f"Arşivden siliniyor: {onum}")
        archived_order = Archive.query.filter_by(order_number=onum).first()
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
