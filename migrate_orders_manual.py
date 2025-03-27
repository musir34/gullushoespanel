
from flask import Flask
from models import db
from order_status_manager import migrate_orders_to_status_tables
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

if __name__ == "__main__":
    try:
        app = create_app()
        with app.app_context():
            total_migrated = migrate_orders_to_status_tables()
            logger.info(f"Toplam {total_migrated} sipariş başarıyla statü tablolarına taşındı.")
    except Exception as e:
        logger.error(f"Sipariş taşıma işlemi sırasında hata: {e}")
