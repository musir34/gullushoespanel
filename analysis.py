
from flask import Blueprint, render_template, jsonify
from models import Order, Product, SiparisFisi
from sqlalchemy import func
from datetime import datetime, timedelta

analysis_bp = Blueprint('analysis_bp', __name__)

@analysis_bp.route('/analysis')
def analysis_page():
    # Son 30 günlük siparişler
    thirty_days_ago = datetime.now() - timedelta(days=30)
    
    # Toplam sipariş sayısı
    total_orders = Order.query.count()
    
    # Son 30 günlük sipariş sayısı
    recent_orders = Order.query.filter(Order.order_date >= thirty_days_ago).count()
    
    # En çok satılan ürünler
    top_products = db.session.query(
        Order.product_model_code,
        func.count(Order.id).label('count')
    ).group_by(Order.product_model_code).order_by(func.count(Order.id).desc()).limit(5).all()
    
    # Sipariş fişi istatistikleri
    total_fis = SiparisFisi.query.count()
    
    stats = {
        'total_orders': total_orders,
        'recent_orders': recent_orders,
        'top_products': top_products,
        'total_fis': total_fis
    }
    
    return render_template('analysis.html', stats=stats)
