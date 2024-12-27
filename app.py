
import os
from flask import Flask, request, url_for, redirect, flash, session
from werkzeug.routing import BuildError
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_caching import Cache
from models import db, Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import logging

# Logging ayarları
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'varsayılan_anahtar')
csrf = CSRFProtect(app)

# Cache yapılandırması
cache = Cache(app, config={
    'CACHE_TYPE': 'simple',
    'CACHE_DEFAULT_TIMEOUT': 300
})

# Güvenlik başlıkları
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

# Session güvenlik ayarları
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=1800  # 30 dakika
)

# Veritabanı ayarları
DATABASE_URI = os.environ.get('DATABASE_URL', 'postgresql+psycopg2://username:password@host:port/database_name')
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 10,
    'max_overflow': 20,
    'pool_timeout': 30,
    'pool_recycle': 1800,
}

# SQLAlchemy veritabanı motoru ve oturum oluşturma
try:
    engine = create_engine(DATABASE_URI)
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    logger.info("Veritabanına başarıyla bağlanıldı ve tablolar oluşturuldu.")
except Exception as e:
    logger.error(f"Veritabanı bağlantı hatası: {e}")
    engine = None

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
from iade_islemleri import iade_islemleri
from siparis_fisi import siparis_fisi_bp

# Güvenli oturum kontrolü
@app.before_request
def check_authentication():
    if not request.is_secure and app.env != 'development':
        return redirect(url_for(request.endpoint, _external=True, _scheme='https'))
        
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
            
        # Oturum süresini kontrol et
        if 'last_activity' in session:
            inactive_time = datetime.now() - session['last_activity']
            if inactive_time.seconds > 1800:  # 30 dakika
                session.clear()
                flash('Oturum süreniz doldu. Lütfen tekrar giriş yapın.', 'warning')
                return redirect(url_for('login_logout.login'))
        
        session['last_activity'] = datetime.now()

    if 'pending_user' in session and request.endpoint != 'login_logout.verify_totp':
        return redirect(url_for('login_logout.verify_totp'))

if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', 'False') == 'True'
    app.run(host='0.0.0.0', port=8080, debug=debug_mode, ssl_context='adhoc')
