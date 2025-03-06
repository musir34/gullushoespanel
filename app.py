import os
from flask import Flask, request, url_for, redirect, flash, session
from cache_config import redis_client, CACHE_TIMES
from werkzeug.routing import BuildError
from flask_sqlalchemy import SQLAlchemy
from models import db, Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta

# Logging ayarları
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ana uygulama oluşturma
app = Flask(__name__)

# Asenkron işlemleri destekle
from flask_cors import CORS
CORS(app)

from siparisler import siparisler_bp
app.secret_key = os.environ.get('SECRET_KEY', 'varsayılan_anahtar')

# Veritabanı ayarları
DATABASE_URI = os.environ.get('DATABASE_URL', 'postgresql+psycopg2://username:password@host:port/database_name')
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URI

# SQLAlchemy veritabanı motoru ve oturum oluşturma
try:
    engine = create_engine(DATABASE_URI)
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    logger.info("Veritabanına başarıyla bağlanıldı ve tablolar oluşturuldu.")
except Exception as e:
    logger.error(f"Veritabanı bağlantı hatası: {e}")
    engine = None

# Session nesnesini uygulama context'ine ekleyelim
app.config['Session'] = Session

# Flask-SQLAlchemy, Flask-Login ve diğer uzantıları başlat
db.init_app(app)

# Trendyol API servisleri
from product_service import product_service_bp
from claims_service import claims_service_bp
# Blueprint'ler aşağıda toplu olarak kaydedilecek

with app.app_context():
    # Eksik sütunu ekle
    from sqlalchemy import text
    db.session.execute(text('ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_date TIMESTAMP'))

    # Yeni tabloları oluştur
    from models import YeniSiparis, SiparisUrun
    db.create_all()

    # ProductArchive tablosunu oluştur
    from models import ProductArchive
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    if not inspector.has_table('product_archive'):
        ProductArchive.__table__.create(db.engine)

    db.session.commit()

# Blueprint modüllerini import et
from order_service import order_service_bp
from update_service import update_service_bp
from archive import archive_bp
from order_list_service import order_list_service_bp
from login_logout import login_logout_bp
from degisim import degisim_bp
from home import home_bp
from get_products import get_products_bp
from all_orders_service import all_orders_service_bp
from new_orders_service import new_orders_service_bp
from processed_orders_service import processed_orders_service_bp
from iade_islemleri import iade_islemleri, fetch_data_from_api, save_to_database
from siparis_fisi import siparis_fisi_bp
from analysis import analysis_bp
from stock_report import stock_report_bp
from openai_service import openai_bp
from siparisler import siparisler_bp


# Yeni update_data_bp'yi içe aktaralım
from update_data_service import update_data_bp

blueprints = [
    order_service_bp,
    update_service_bp,
    archive_bp,
    order_list_service_bp,
    login_logout_bp,
    degisim_bp,
    home_bp,
    get_products_bp,
    all_orders_service_bp,
    new_orders_service_bp,
    processed_orders_service_bp,
    iade_islemleri,
    siparis_fisi_bp,
    analysis_bp,
    stock_report_bp,
    openai_bp,
    siparisler_bp,
    product_service_bp,  # Burada bir kez kaydediyoruz
    claims_service_bp,
    update_data_bp  # Veri güncelleme blueprint'i
]

for bp in blueprints:
    app.register_blueprint(bp)


@app.before_request
def check_authentication():
    # İzin verilen rotalar
    allowed_routes = [
        'login_logout.login',
        'login_logout.register',
        'login_logout.static',
        'login_logout.verify_totp',
        'login_logout.logout'
    ]

    # Oturum süresini ayarla - 1 ay (30 gün)
    app.permanent_session_lifetime = timedelta(days=30)

    # Eğer izin verilen rotalara istek yapılmışsa ve kullanıcı henüz giriş yapmamışsa
    if request.endpoint not in allowed_routes:
        if 'username' not in session:
            flash('Lütfen giriş yapınız.', 'danger')
            return redirect(url_for('login_logout.login'))

        # Kullanıcı giriş yapmış ama TOTP doğrulaması yapmamışsa
        if 'pending_user' in session and request.endpoint != 'login_logout.verify_totp':
            return redirect(url_for('login_logout.verify_totp'))

def custom_url_for(endpoint, **values):
    try:
        return url_for(endpoint, **values)
    except BuildError:
        if '.' not in endpoint:
            for blueprint in app.blueprints.values():
                try:
                    return url_for(f"{blueprint.name}.{endpoint}", **values)
                except BuildError:
                    continue
        raise BuildError(endpoint, values, method=None)

app.jinja_env.globals['url_for'] = custom_url_for

#####################################
# BURADA APScheduler İLE İŞLERİ PLANLIYORUZ
#####################################
from apscheduler.schedulers.background import BackgroundScheduler

def fetch_and_save_returns():
    with app.app_context():
        data = fetch_data_from_api()
        save_to_database(data)

def fetch_and_update_products():
    with app.app_context():
        try:
            logger.info("Ürün güncelleme başlatıldı")
            from product_service import fetch_trendyol_products_async
            import asyncio
            asyncio.run(fetch_trendyol_products_async())
            logger.info("Ürün güncelleme tamamlandı")
        except Exception as e:
            logger.error(f"Ürün güncelleme hatası: {e}")

def fetch_and_update_orders():
    with app.app_context():
        try:
            logger.info("Sipariş güncelleme başlatıldı")
            from order_service import fetch_trendyol_orders_async
            import asyncio
            asyncio.run(fetch_trendyol_orders_async())
            logger.info("Sipariş güncelleme tamamlandı")
        except Exception as e:
            logger.error(f"Sipariş güncelleme hatası: {e}")

def fetch_and_update_claims():
    with app.app_context():
        try:
            logger.info("İade/talep güncelleme başlatıldı")
            from claims_service import fetch_claims_async
            import asyncio
            asyncio.run(fetch_claims_async())
            logger.info("İade/talep güncelleme tamamlandı")
        except Exception as e:
            logger.error(f"İade/talep güncelleme hatası: {e}")

def schedule_jobs(app):
    scheduler = BackgroundScheduler(timezone="Europe/Istanbul")
    
    # İadeler - Her gün 23:50'de
    scheduler.add_job(func=fetch_and_save_returns, trigger='cron', hour=23, minute=50, 
                     id='returns_job', name='İadeleri Güncelle')
    
    # Ürünler - Her 3 saatte bir
    scheduler.add_job(func=fetch_and_update_products, trigger='interval', hours=3, 
                     id='products_job', name='Ürünleri Güncelle')
    
    # Siparişler - Her 30 dakikada bir
    scheduler.add_job(func=fetch_and_update_orders, trigger='interval', minutes=30, 
                     id='orders_job', name='Siparişleri Güncelle')
    
    # İade/Talepler - Her saat başı
    scheduler.add_job(func=fetch_and_update_claims, trigger='interval', hours=1, 
                     id='claims_job', name='İade/Talepleri Güncelle')
    
    # Başlangıçta hepsini bir kez çalıştır
    scheduler.add_job(func=fetch_and_update_products, trigger='date', 
                     run_date=datetime.now() + timedelta(seconds=60),
                     id='initial_products_job', name='İlk Ürün Güncellemesi')
    
    scheduler.add_job(func=fetch_and_update_orders, trigger='date', 
                     run_date=datetime.now() + timedelta(seconds=120),
                     id='initial_orders_job', name='İlk Sipariş Güncellemesi')
    
    scheduler.start()
    logger.info("Zamanlayıcı başlatıldı - Otomatik veri güncelleme işleri planlandı")

# schedule_jobs fonksiyonunu app.run'dan önce çağır:
schedule_jobs(app)

# Otomatik veri güncelleme sistemini başlat
def init_auto_update():
    """Uygulama başlatıldığında otomatik güncelleme sistemini başlatır"""
    from update_data_service import start_continuous_update
    # Uygulamanın başlangıcında sürekli güncelleme sistemini başlat
    start_continuous_update()
    logger.info("Otomatik veri güncelleme sistemi başlatıldı")

with app.app_context():
    init_auto_update()

if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', 'False') == 'True'
    app.run(host='0.0.0.0', port=8080, debug=debug_mode)