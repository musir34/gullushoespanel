# all_orders_service.py
from flask import Blueprint, render_template, request, flash, redirect, url_for
from sqlalchemy import union_all, select, literal
from models import db, OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled
from datetime import datetime
import logging
from sqlalchemy.exc import SQLAlchemyError
import json

all_orders_service_bp = Blueprint('all_orders_service', __name__)

# Log ayarları
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def compute_time_left(agreed_delivery_date):
    """
    Kargoya kalan süreyi hesaplar
    """
    if not agreed_delivery_date:
        return "Belirtilmemiş"
    
    now = datetime.now()
    time_diff = agreed_delivery_date - now
    hours_left = time_diff.total_seconds() / 3600
    
    if hours_left < 0:
        return "Gecikmiş"
    
    days_left = int(hours_left / 24)
    remaining_hours = int(hours_left % 24)
    
    if days_left > 0:
        return f"{days_left} gün {remaining_hours} saat"
    else:
        return f"{remaining_hours} saat"


def all_orders_union():
    """
    Tüm statü tablolarını ortak kolonlarda UNION ALL yaparak tek sorgu döndürüyor.
    Kolon isimlerini aynı label ile seçiyoruz ki birleştirme sorunsuz olsun.
    """

    # 1) Her tablo için daha fazla kolon seçiyoruz
    c = db.session.query(
        OrderCreated.order_number.label('order_number'),
        OrderCreated.order_date.label('order_date'),
        OrderCreated.merchant_sku.label('merchant_sku'),
        OrderCreated.product_barcode.label('product_barcode'),
        OrderCreated.cargo_provider_name.label('cargo_provider_name'),
        OrderCreated.agreed_delivery_date.label('agreed_delivery_date'),
        OrderCreated.shipping_barcode.label('shipping_barcode'),
        OrderCreated.customer_name.label('customer_name'),
        OrderCreated.customer_surname.label('customer_surname'),
        OrderCreated.quantity.label('quantity'),
        literal('Created').label('tablo')
    )

    p = db.session.query(
        OrderPicking.order_number.label('order_number'),
        OrderPicking.order_date.label('order_date'),
        OrderPicking.merchant_sku.label('merchant_sku'),
        OrderPicking.product_barcode.label('product_barcode'),
        OrderPicking.cargo_provider_name.label('cargo_provider_name'),
        OrderPicking.agreed_delivery_date.label('agreed_delivery_date'),
        OrderPicking.shipping_barcode.label('shipping_barcode'),
        OrderPicking.customer_name.label('customer_name'),
        OrderPicking.customer_surname.label('customer_surname'),
        OrderPicking.quantity.label('quantity'),
        literal('Picking').label('tablo')
    )

    s = db.session.query(
        OrderShipped.order_number.label('order_number'),
        OrderShipped.order_date.label('order_date'),
        OrderShipped.merchant_sku.label('merchant_sku'),
        OrderShipped.product_barcode.label('product_barcode'),
        OrderShipped.cargo_provider_name.label('cargo_provider_name'),
        OrderShipped.agreed_delivery_date.label('agreed_delivery_date'),
        OrderShipped.shipping_barcode.label('shipping_barcode'),
        OrderShipped.customer_name.label('customer_name'),
        OrderShipped.customer_surname.label('customer_surname'),
        OrderShipped.quantity.label('quantity'),
        literal('Shipped').label('tablo')
    )

    d = db.session.query(
        OrderDelivered.order_number.label('order_number'),
        OrderDelivered.order_date.label('order_date'),
        OrderDelivered.merchant_sku.label('merchant_sku'),
        OrderDelivered.product_barcode.label('product_barcode'),
        OrderDelivered.cargo_provider_name.label('cargo_provider_name'),
        OrderDelivered.agreed_delivery_date.label('agreed_delivery_date'),
        OrderDelivered.shipping_barcode.label('shipping_barcode'),
        OrderDelivered.customer_name.label('customer_name'),
        OrderDelivered.customer_surname.label('customer_surname'),
        OrderDelivered.quantity.label('quantity'),
        literal('Delivered').label('tablo')
    )

    x = db.session.query(
        OrderCancelled.order_number.label('order_number'),
        OrderCancelled.order_date.label('order_date'),
        OrderCancelled.merchant_sku.label('merchant_sku'),
        OrderCancelled.product_barcode.label('product_barcode'),
        OrderCancelled.cargo_provider_name.label('cargo_provider_name'),
        OrderCancelled.agreed_delivery_date.label('agreed_delivery_date'),
        OrderCancelled.shipping_barcode.label('shipping_barcode'),
        OrderCancelled.customer_name.label('customer_name'),
        OrderCancelled.customer_surname.label('customer_surname'),
        OrderCancelled.quantity.label('quantity'),
        literal('Cancelled').label('tablo')
    )

    # 2) UNION ALL
    union_query = c.union_all(p, s, d, x)

    return union_query

@all_orders_service_bp.route('/update-order-statuses', methods=['POST'])
def update_order_statuses():
    """
    API'den gelen veriye göre OrderPicking tablosundaki ürünleri 
    OrderShipped veya OrderDelivered tablolarına taşır
    """
    try:
        # OrderPicking tablosundan tüm siparişleri çekelim
        picking_orders = OrderPicking.query.all()
        
        moved_shipped = 0
        moved_delivered = 0
        
        for order in picking_orders:
            # Eğer shipped tablosunda varsa
            shipped_order = OrderShipped.query.filter_by(order_number=order.order_number).first()
            if shipped_order:
                # Yeni kargo statüsü var, eski tablodan silelim
                move_order_between_tables(order, OrderPicking, OrderShipped)
                moved_shipped += 1
                continue
                
            # Eğer delivered tablosunda varsa
            delivered_order = OrderDelivered.query.filter_by(order_number=order.order_number).first()
            if delivered_order:
                # Teslim edilmiş, delivered tablosuna taşıyalım
                move_order_between_tables(order, OrderPicking, OrderDelivered)
                moved_delivered += 1
                continue
                
        # Sonuç mesajı
        flash(f"Güncelleme tamamlandı: {moved_shipped} sipariş 'Shipped' durumuna, {moved_delivered} sipariş 'Delivered' durumuna taşındı", "success")
        logger.info(f"Sipariş durumları güncellendi: {moved_shipped} Shipped, {moved_delivered} Delivered")
        
    except SQLAlchemyError as e:
        db.session.rollback()
        flash(f"Veritabanı hatası: {str(e)}", "danger")
        logger.error(f"Veritabanı hatası: {e}")
    except Exception as e:
        db.session.rollback()
        flash(f"Beklenmeyen hata: {str(e)}", "danger")
        logger.error(f"Beklenmeyen hata: {e}")
        
    return redirect(url_for('order_list_service.order_list_all'))


def move_order_between_tables(order_obj, old_model, new_model):
    """
    Siparişin kaydını eski tablodan silip, verilerini yeni tabloya taşır.
    """
    if not order_obj:
        logger.error(f"Sipariş bulunamadı")
        return False

    try:
        # Kolon verilerini kopyalama
        data = order_obj.__dict__.copy()
        data.pop('_sa_instance_state', None)

        # Yeni tabloda olmayan sütunları filtrele
        new_cols = set(new_model.__table__.columns.keys())
        data = {k: v for k, v in data.items() if k in new_cols}

        # Yeni tabloya ekle
        new_rec = new_model(**data)
        db.session.add(new_rec)
        
        # Eski kaydı sil
        db.session.delete(order_obj)
        db.session.commit()
        
        logger.info(f"Sipariş taşındı: {order_obj.order_number} -> {new_model.__tablename__}")
        return True
    except Exception as e:
        db.session.rollback()
        logger.error(f"Sipariş taşıma hatası: {e}")
        return False
