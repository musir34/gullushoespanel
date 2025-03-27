
from flask import Flask
from models import db, Order, OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled, OrderArchived
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:postgres@localhost:5432/siparisyonetim'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app
