
from flask import Blueprint, render_template
from models import Order, db, SiparisFisi
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
    
    # En çok üretilen ürünler
    top_products = db.session.query(
        SiparisFisi.urun_model_kodu,
        func.sum(SiparisFisi.toplam_adet).label('toplam')
    ).group_by(SiparisFisi.urun_model_kodu).order_by(func.sum(SiparisFisi.toplam_adet).desc()).limit(5).all()
    
    # Renklere göre dağılım
    color_distribution = db.session.query(
        SiparisFisi.renk,
        func.sum(SiparisFisi.toplam_adet).label('toplam')
    ).group_by(SiparisFisi.renk).order_by(func.sum(SiparisFisi.toplam_adet).desc()).all()
    
    return render_template('istatistikler.html',
                         günlük_siparisler=günlük_siparisler,
                         top_products=top_products,
                         color_distribution=color_distribution)
