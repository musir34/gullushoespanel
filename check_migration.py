
from flask import Flask
from models import db, Order, OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled, OrderArchived
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__)
    
    # Replit ortamına uygun veritabanı bağlantısı
    database_url = os.environ.get('DATABASE_URL', 'sqlite:///siparis.db')
    
    # Eğer çevre değişkeni varsa onu kullan
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app

def check_migration_status(app):
    """
    Siparişlerin farklı statü tablolarına taşınıp taşınmadığını kontrol eder.
    """
    with app.app_context():
        # Ana Order tablosundaki sipariş sayısı
        order_count = Order.query.count()
        
        # Statü tablolarındaki sipariş sayıları
        created_count = OrderCreated.query.count()
        picking_count = OrderPicking.query.count()
        shipped_count = OrderShipped.query.count()
        delivered_count = OrderDelivered.query.count()
        cancelled_count = OrderCancelled.query.count()
        archived_count = OrderArchived.query.count()
        
        # Toplam taşınan sipariş sayısı
        total_migrated = created_count + picking_count + shipped_count + delivered_count + cancelled_count + archived_count
        
        logger.info(f"Ana Order tablosunda toplam {order_count} sipariş bulunuyor.")
        logger.info(f"Created tablosunda: {created_count} sipariş")
        logger.info(f"Picking tablosunda: {picking_count} sipariş")
        logger.info(f"Shipped tablosunda: {shipped_count} sipariş")
        logger.info(f"Delivered tablosunda: {delivered_count} sipariş")
        logger.info(f"Cancelled tablosunda: {cancelled_count} sipariş")
        logger.info(f"Archived tablosunda: {archived_count} sipariş")
        logger.info(f"Toplam taşınan sipariş sayısı: {total_migrated}")
        
        if total_migrated > 0:
            logger.info("Taşıma işlemi başarıyla gerçekleştirilmiş görünüyor.")
        else:
            logger.warning("Statü tablolarında hiç sipariş bulunamadı. Taşıma işlemi henüz gerçekleştirilmemiş olabilir.")

if __name__ == "__main__":
    app = create_app()
    check_migration_status(app)
