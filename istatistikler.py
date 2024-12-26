
from flask import Blueprint, render_template
from models import Order, db
from sqlalchemy import func
from datetime import datetime, timedelta

istatistikler_bp = Blueprint('istatistikler', __name__)

@istatistikler_bp.route('/istatistikler')
def istatistikler():
    # Son 7 günün siparişleri
    son_7_gun = datetime.now() - timedelta(days=7)
    günlük_siparisler = db.session.query(
        func.date(Order.order_date),
        func.count(Order.id)
    ).filter(Order.order_date >= son_7_gun).group_by(func.date(Order.order_date)).all()
    
    return render_template('istatistikler.html', 
                         günlük_siparisler=günlük_siparisler)
