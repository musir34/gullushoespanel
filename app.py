import os
from flask import Flask, request, url_for, redirect, flash, session
from werkzeug.routing import BuildError
from flask_sqlalchemy import SQLAlchemy
from models import db, Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from flask import jsonify

# Logging ayarları
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

from flask_caching import Cache

cache_config = {
    "CACHE_TYPE": "redis",
    "CACHE_REDIS_URL": os.environ.get('REDIS_URL', 'redis://localhost:6379/0'),
    "CACHE_DEFAULT_TIMEOUT": 300
}
cache = Cache(config=cache_config)
cache.init_app(app)

app.secret_key = os.environ.get('SECRET_KEY', 'varsayılan_anahtar')

# Veritabanı ayarları
DATABASE_URI = os.environ.get('DATABASE_URL', 'postgresql+psycopg2://username:password@host:port/database_name')
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_POOL_SIZE'] = 30
app.config['SQLALCHEMY_MAX_OVERFLOW'] = 60
app.config['SQLALCHEMY_POOL_TIMEOUT'] = 30
app.config['SQLALCHEMY_POOL_RECYCLE'] = 180
app.config['SQLALCHEMY_ECHO'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True}

# SQLAlchemy veritabanı motoru ve oturum oluşturma
try:
    engine = create_engine(DATABASE_URI, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    logger.info("Veritabanına başarıyla bağlanıldı ve tablolar oluşturuldu.")
except Exception as e:
    logger.error(f"Veritabanı bağlantı hatası: {e}")
    engine = None
    raise Exception(f"Veritabanına bağlanılamadı: {e}")



@app.errorhandler(Exception)
def handle_error(error):
    if str(error).startswith('404 Not Found') and request.path == '/favicon.ico':
        return '', 204  # Return empty response for favicon requests
    logger.error(f"Beklenmeyen hata: {str(error)}")
    return jsonify({
        "success": False,
        "error": "Bir hata oluştu",
        "details": str(error)
    }), 500

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({
        "success": False,
        "error": "İstek limiti aşıldı",
        "retry_after": e.description
    }), 429

# Session nesnesini uygulama context'ine ekleyelim
app.config['Session'] = Session

# SQLAlchemy'yi uygulama ile başlat
db.init_app(app)

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
    # Her saat başı 09:00-23:00 arası iadeleri güncelle
    scheduler.add_job(
        func=fetch_and_save_returns,
        trigger='cron',
        hour='9-23',
        minute=0
    )
    scheduler.start()

# schedule_jobs fonksiyonunu app.run'dan önce çağır:
schedule_jobs(app)

if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', 'False') == 'True'
    app.run(host='0.0.0.0', port=8080, debug=debug_mode)
