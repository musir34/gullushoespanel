
from flask import Flask
from models import db, OrderPicking, OrderShipped, OrderDelivered
from order_status_manager import move_order_between_tables
import logging

# Logging ayarları
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///instance/orders.db'  # Kendi veritabanı bağlantınızı kullanın
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app

def check_and_fix_order_status():
    """
    İşleme alınanlar tablosundaki siparişleri kontrol eder ve 
    siparişin gerçek statüsüne göre doğru tabloya taşır
    """
    app = create_app()
    with app.app_context():
        # İşleme alınmış (Picking) tablodaki siparişleri kontrol et
        picking_orders = OrderPicking.query.all()
        logger.info(f"İşleme alınan {len(picking_orders)} sipariş kontrol ediliyor...")
        
        for order in picking_orders:
            # Bu siparişin durumunu Trendyol API'den kontrol edin
            # API yanıtına göre hareket edin
            # NOT: Bu kısımda API çağrısı yapılmalı
            
            # Örnek: Gerçek durumu 'Shipped' ise
            # if actual_status == 'Shipped':
            #     move_order_between_tables(order, OrderPicking, OrderShipped)
            #     logger.info(f"Sipariş {order.order_number} Picking'den Shipped'e taşındı.")
            
            # Örnek: Gerçek durumu 'Delivered' ise
            # if actual_status == 'Delivered':
            #     move_order_between_tables(order, OrderPicking, OrderDelivered)
            #     logger.info(f"Sipariş {order.order_number} Picking'den Delivered'e taşındı.")
            
            # Bu satırları API'den gelen yanıtlarla tamamlayın
            pass
        
        db.session.commit()
        logger.info("Sipariş statü kontrolü tamamlandı")

if __name__ == "__main__":
    check_and_fix_order_status()
