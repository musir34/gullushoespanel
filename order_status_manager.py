from flask import current_app
from models import db, Order
import json
import logging
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

# Eski sipariş yönetimi sistemi
def update_order_status(order_number, new_status, additional_data=None):
    """
    Sipariş durumunu güncelle
    """
    try:
        order = Order.query.filter_by(order_number=order_number).first()

        if not order:
            logger.warning(f"Sipariş {order_number} bulunamadı")
            return None

        order.status = new_status

        # Ek verileri ekle
        if additional_data:
            for key, value in additional_data.items():
                if hasattr(order, key):
                    setattr(order, key, value)

        db.session.commit()
        logger.info(f"Sipariş {order_number} durumu {new_status} olarak güncellendi")
        return order

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
        query = Order.query.filter_by(status=status)

        # Arama filtresi uygula
        if search:
            query = query.filter(Order.order_number.ilike(f'%{search}%'))

        # Tarihe göre sırala
        query = query.order_by(Order.order_date.desc())

        # Sayfalama uygula
        paginated_orders = query.paginate(page=page, per_page=per_page, error_out=False)

        return paginated_orders

    except Exception as e:
        logger.error(f"Siparişleri getirirken hata: {e}")
        raise