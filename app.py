import os
import json
import logging
from datetime import timedelta

from flask import Flask, request, url_for, redirect, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from werkzeug.routing import BuildError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from flask_login import LoginManager
from models import db, Base, User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'varsayılan_anahtar')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login_logout.login"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.template_filter('from_json')
def from_json(value):
    try:
        return json.loads(value) if value else {}
    except Exception:
        return {}

CORS(app)

DATABASE_URI = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URI

try:
    engine = create_engine(DATABASE_URI, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    app.config['Session'] = Session
    logger.info("Veritabanına başarıyla bağlanıldı.")
except Exception as e:
    logger.error(f"Veritabanı bağlantı hatası: {e}")
    raise SystemExit("Veritabanına bağlanamadı.")

db.init_app(app)

# Blueprint'ler
from product_service import product_service_bp
from claims_service import claims_service_bp
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
from user_logs import user_logs_bp, log_user_action
from commission_update_routes import commission_update_bp
from profit import profit_bp

blueprints = [
    order_service_bp, update_service_bp, archive_bp,
    order_list_service_bp, login_logout_bp, degisim_bp,
    home_bp, get_products_bp, all_orders_service_bp,
    new_orders_service_bp, processed_orders_service_bp,
    iade_islemleri, siparis_fisi_bp, analysis_bp,
    stock_report_bp, openai_bp, siparisler_bp,
    product_service_bp, claims_service_bp,
    user_logs_bp, commission_update_bp, profit_bp
]

for bp in blueprints:
    app.register_blueprint(bp)

@app.before_request
def log_request():
    if not request.path.startswith('/static/'):
        log_user_action(
            action=f"PAGE_VIEW: {request.endpoint}",
            details={'path': request.path, 'endpoint': request.endpoint},
            force_log=True
        )

@app.before_request
def check_authentication():
    allowed_routes = [
        'login_logout.login', 'login_logout.register',
        'login_logout.static', 'login_logout.verify_totp',
        'login_logout.logout'
    ]

    app.permanent_session_lifetime = timedelta(days=30)

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

from apscheduler.schedulers.background import BackgroundScheduler

def fetch_and_save_returns():
    with app.app_context():
        data = fetch_data_from_api()
        save_to_database(data)

scheduler = BackgroundScheduler(timezone="Europe/Istanbul")
scheduler.add_job(func=fetch_and_save_returns, trigger='cron', hour=23, minute=50)
scheduler.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
