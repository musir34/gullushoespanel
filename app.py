
import os
import logging
from flask import Flask, request, url_for, redirect, flash, session, jsonify
from werkzeug.routing import BuildError
from flask_sqlalchemy import SQLAlchemy
from flask_caching import Cache
from models import db, Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Initialize Flask app
app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure caching
cache_config = {
    "CACHE_TYPE": "redis",
    "CACHE_REDIS_URL": os.environ.get('REDIS_URL', 'redis://localhost:6379/0'),
    "CACHE_DEFAULT_TIMEOUT": 300
}
cache = Cache(config=cache_config)
cache.init_app(app)

# App configuration
app.secret_key = os.environ.get('SECRET_KEY', 'varsayılan_anahtar')
DATABASE_URI = os.environ.get('DATABASE_URL', 'postgresql+psycopg2://username:password@host:port/database_name')

app.config.update(
    SQLALCHEMY_DATABASE_URI=DATABASE_URI,
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SQLALCHEMY_POOL_SIZE=30,
    SQLALCHEMY_MAX_OVERFLOW=60,
    SQLALCHEMY_POOL_TIMEOUT=30,
    SQLALCHEMY_POOL_RECYCLE=180,
    SQLALCHEMY_ECHO=False,
    SQLALCHEMY_ENGINE_OPTIONS={'pool_pre_ping': True}
)

# Database initialization
try:
    engine = create_engine(DATABASE_URI, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    logger.info("Database connection successful and tables created.")
except Exception as e:
    logger.error(f"Database connection error: {e}")
    engine = None
    raise Exception(f"Could not connect to database: {e}")

# Register blueprints
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

blueprints = [
    order_service_bp, update_service_bp, archive_bp,
    order_list_service_bp, login_logout_bp, degisim_bp,
    home_bp, get_products_bp, all_orders_service_bp,
    new_orders_service_bp, processed_orders_service_bp,
    iade_islemleri, siparis_fisi_bp
]

for bp in blueprints:
    app.register_blueprint(bp)

# Error handlers
@app.errorhandler(Exception)
def handle_error(error):
    if str(error).startswith('404 Not Found') and request.path == '/favicon.ico':
        return '', 204
    logger.error(f"Unexpected error: {str(error)}")
    return jsonify({
        "success": False,
        "error": "An error occurred",
        "details": str(error)
    }), 500

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({
        "success": False,
        "error": "Rate limit exceeded",
        "retry_after": e.description
    }), 429

# Authentication check
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
            flash('Please login.', 'danger')
            return redirect(url_for('login_logout.login'))

    if 'pending_user' in session and request.endpoint != 'login_logout.verify_totp':
        return redirect(url_for('login_logout.verify_totp'))

# URL helper function
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

# Initialize database
db.init_app(app)
app.config['Session'] = Session

if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', 'False') == 'True'
    app.run(host='0.0.0.0', port=8080, debug=debug_mode)
