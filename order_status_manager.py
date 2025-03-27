
from flask import current_app
from models import db, Order, OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled, OrderArchived
import json
import logging
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

def create_order_in_status_table(order_data, status):
    """
    Belirli bir statüdeki sipariş tablosuna yeni sipariş ekler
    """
    try:
        # Veriyi temel alanlara ayırıyoruz
        order_base_data = {
            'order_number': order_data.get('order_number'),
            'order_date': order_data.get('order_date'),
            'merchant_sku': order_data.get('merchant_sku'),
            'product_barcode': order_data.get('product_barcode'),
            'original_product_barcode': order_data.get('original_product_barcode'),
            'line_id': order_data.get('line_id'),
            'match_status': order_data.get('match_status'),
            'customer_name': order_data.get('customer_name'),
            'customer_surname': order_data.get('customer_surname'),
            'customer_address': order_data.get('customer_address'),
            'shipping_barcode': order_data.get('shipping_barcode'),
            'product_name': order_data.get('product_name'),
            'product_code': order_data.get('product_code'),
            'amount': order_data.get('amount'),
            'discount': order_data.get('discount', 0.0),
            'currency_code': order_data.get('currency_code'),
            'vat_base_amount': order_data.get('vat_base_amount'),
            'package_number': order_data.get('package_number'),
            'stockCode': order_data.get('stockCode'),
            'estimated_delivery_start': order_data.get('estimated_delivery_start'),
            'images': order_data.get('images'),
            'product_model_code': order_data.get('product_model_code'),
            'estimated_delivery_end': order_data.get('estimated_delivery_end'),
            'origin_shipment_date': order_data.get('origin_shipment_date'),
            'product_size': order_data.get('product_size'),
            'product_main_id': order_data.get('product_main_id'),
            'cargo_provider_name': order_data.get('cargo_provider_name'),
            'agreed_delivery_date': order_data.get('agreed_delivery_date'),
            'product_color': order_data.get('product_color'),
            'cargo_tracking_link': order_data.get('cargo_tracking_link'),
            'shipment_package_id': order_data.get('shipment_package_id'),
            'details': order_data.get('details'),
            'quantity': order_data.get('quantity'),
            'commission': order_data.get('commission', 0.0),
            'product_cost_total': order_data.get('product_cost_total', 0.0),
            'status': status  # Geriye dönük uyumluluk için
        }
        
        # Statüye göre uygun modeli seç
        if status == 'Created':
            new_order = OrderCreated(**order_base_data)
        elif status == 'Picking':
            new_order = OrderPicking(**order_base_data)
            new_order.picked_by = order_data.get('picked_by', '')
        elif status == 'Shipped':
            new_order = OrderShipped(**order_base_data)
        elif status == 'Delivered':
            new_order = OrderDelivered(**order_base_data)
            new_order.delivery_date = order_data.get('delivery_date')
        elif status == 'Cancelled':
            new_order = OrderCancelled(**order_base_data)
            new_order.cancellation_reason = order_data.get('cancellation_reason', '')
        else:  # 'Archived' veya diğer statüler
            new_order = OrderArchived(**order_base_data)
            new_order.archive_reason = order_data.get('archive_reason', '')
            
        db.session.add(new_order)
        db.session.commit()
        
        logger.info(f"Sipariş {order_data.get('order_number')} başarıyla {status} tablosuna eklendi")
        return new_order
    
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Veritabanı hatası: {e}")
        raise
    except Exception as e:
        db.session.rollback()
        logger.error(f"Beklenmeyen hata: {e}")
        raise

def move_order_to_status(order_number, new_status, additional_data=None):
    """
    Var olan bir siparişi bir statü tablosundan diğerine taşır
    """
    try:
        # Önce hangi tabloda olduğunu bulalım
        order = None
        source_model = None
        
        # Tüm statü tablolarında ara
        status_tables = {
            'Created': OrderCreated,
            'Picking': OrderPicking,
            'Shipped': OrderShipped,
            'Delivered': OrderDelivered,
            'Cancelled': OrderCancelled,
            'Archived': OrderArchived
        }
        
        for status, model in status_tables.items():
            order_in_table = model.query.filter_by(order_number=order_number).first()
            if order_in_table:
                order = order_in_table
                source_model = model
                source_status = status
                break
        
        # Eski Order tablosunda da kontrol et
        if not order:
            order = Order.query.filter_by(order_number=order_number).first()
            if order:
                source_model = Order
                source_status = order.status
        
        if not order:
            logger.warning(f"Sipariş {order_number} bulunamadı")
            return None
            
        # Siparişi hedef tabloya taşı
        order_dict = {}
        for column in order.__table__.columns:
            if column.name != 'id':  # ID'yi taşıma
                order_dict[column.name] = getattr(order, column.name)
        
        # Ek verileri ekle
        if additional_data:
            order_dict.update(additional_data)
            
        # Kaynak tablodan sil (eski order tablosu hariç)
        if source_model != Order:
            db.session.delete(order)
            
        # Yeni tabloya ekle
        new_order = create_order_in_status_table(order_dict, new_status)
        
        # Eski Order tablosundaki kaydı güncelle (geriye dönük uyumluluk için)
        if source_model == Order:
            order.status = new_status
            if additional_data:
                for key, value in additional_data.items():
                    if hasattr(order, key):
                        setattr(order, key, value)
        else:
            # Ana tablodaki durumu da güncelle
            main_order = Order.query.filter_by(order_number=order_number).first()
            if main_order:
                main_order.status = new_status
                if additional_data:
                    for key, value in additional_data.items():
                        if hasattr(main_order, key):
                            setattr(main_order, key, value)
            
        db.session.commit()
        logger.info(f"Sipariş {order_number} {source_status} durumundan {new_status} durumuna taşındı")
        return new_order
        
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Veritabanı hatası: {e}")
        raise
    except Exception as e:
        db.session.rollback()
        logger.error(f"Beklenmeyen hata: {e}")
        raise

def get_orders_by_status(status, page=1, per_page=50, search=None):
    """
    Belirli bir statüdeki siparişleri getirir
    """
    try:
        # Statüye göre uygun modeli seç
        if status == 'Created':
            query = OrderCreated.query
        elif status == 'Picking':
            query = OrderPicking.query
        elif status == 'Shipped':
            query = OrderShipped.query
        elif status == 'Delivered':
            query = OrderDelivered.query
        elif status == 'Cancelled':
            query = OrderCancelled.query
        elif status == 'Archived':
            query = OrderArchived.query
        else:
            # Geçersiz statü, tüm siparişleri ana tablodan filtrele
            query = Order.query.filter_by(status=status)
        
        # Arama filtresi uygula
        if search:
            query = query.filter(OrderCreated.order_number.ilike(f'%{search}%'))
            
        # Tarihe göre sırala
        query = query.order_by(OrderCreated.order_date.desc())
        
        # Sayfalama uygula
        paginated_orders = query.paginate(page=page, per_page=per_page, error_out=False)
        
        return paginated_orders
    
    except Exception as e:
        logger.error(f"Siparişleri getirirken hata: {e}")
        raise

def migrate_orders_to_status_tables():
    """
    Mevcut orders tablosundaki tüm siparişleri uygun statü tablolarına taşır
    """
    try:
        # Statülere göre gruplandırılmış tüm siparişleri al
        statuses = ['Created', 'Picking', 'Shipped', 'Delivered', 'Cancelled']
        
        total_migrated = 0
        
        for status in statuses:
            orders = Order.query.filter_by(status=status).all()
            logger.info(f"{status} statüsünde {len(orders)} sipariş bulundu")
            
            for order in orders:
                # Sipariş verilerini sözlük olarak al
                order_dict = {}
                for column in order.__table__.columns:
                    if column.name != 'id':  # ID'yi taşıma
                        order_dict[column.name] = getattr(order, column.name)
                
                # Uygun statü tablosuna ekle
                create_order_in_status_table(order_dict, status)
                total_migrated += 1
                
                # Her 100 siparişte bir commit yapalım
                if total_migrated % 100 == 0:
                    db.session.commit()
                    logger.info(f"{total_migrated} sipariş taşındı")
        
        db.session.commit()
        logger.info(f"Toplam {total_migrated} sipariş başarıyla statü tablolarına taşındı")
        return total_migrated
    
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Veritabanı hatası: {e}")
        raise
    except Exception as e:
        db.session.rollback()
        logger.error(f"Beklenmeyen hata: {e}")
        raise
