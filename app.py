import os
from flask import Flask, request, url_for, redirect, flash, session
from cache_config import redis_client, CACHE_TIMES
from werkzeug.routing import BuildError
from flask_sqlalchemy import SQLAlchemy
from models import db, Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Logging ayarları
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
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

# SQLAlchemy'yi uygulama ile başlat
db.init_app(app)

with app.app_context():
    # Eksik sütunu ekle
    from sqlalchemy import text
    db.session.execute(text('ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_date TIMESTAMP'))
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
from iade_islemleri import iade_islemleri, fetch_data_from_api, save_to_database  # iade_islemleri'nden import ettiğimizi varsayıyorum
from siparis_fisi import siparis_fisi_bp
from analysis import analysis_bp

blueprints = [
    order_service_bp,
    update_service_bp,
    archive_bp,
    analysis_bp,
    order_list_service_bp,
    login_logout_bp,
    degisim_bp,
    home_bp,
    get_products_bp,
    all_orders_service_bp,
    new_orders_service_bp,
    processed_orders_service_bp,
    iade_islemleri,
    siparis_fisi_bp
]

for bp in blueprints:
    app.register_blueprint(bp)


@app.before_request
def check_authentication():
    allowed_routes = [
        'login_logout.login',
        'login_logout.register',
        'login_logout.static',
        'login_logout.verify_totp',
        'login_logout.logout'
    ]

    if request.endpoint not in allowed_routes:
        if 'username' not in session:
            flash('Lütfen giriş yapınız.', 'danger')
            return redirect(url_for('login_logout.login'))

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

def schedule_jobs(app):
    scheduler = BackgroundScheduler(timezone="Europe/Istanbul")
    # Her gün 23:50'de çalışacak cron job
    scheduler.add_job(func=fetch_and_save_returns, trigger='cron', hour=23, minute=50)
    scheduler.start()

# schedule_jobs fonksiyonunu app.run'dan önce çağır:
schedule_jobs(app)

if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', 'False') == 'True'
    app.run(host='0.0.0.0', port=8080, debug=debug_mode)
