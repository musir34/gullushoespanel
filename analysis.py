
from flask import Blueprint, render_template, jsonify
from models import db, Order, Product
from sqlalchemy import func
from datetime import datetime, timedelta
import json

analysis_bp = Blueprint('analysis', __name__)

@analysis_bp.route('/analysis')
def analysis_page():
    return render_template('analysis.html')

@analysis_bp.route('/api/sales-stats')
def sales_stats():
    # Son 30 günlük istatistikler
    thirty_days_ago = datetime.now() - timedelta(days=30)
    
    # Günlük satış miktarları
    daily_sales = db.session.query(
        func.date(Order.order_date).label('date'),
        func.count(Order.id).label('count'),
        func.sum(Order.amount).label('total_amount')
    ).filter(
        Order.order_date >= thirty_days_ago
    ).group_by(
        func.date(Order.order_date)
    ).all()
    
    # Ürün bazlı satışlar
    product_sales = db.session.query(
        Order.product_name,
        func.count(Order.id).label('count'),
        func.sum(Order.amount).label('total_amount')
    ).filter(
        Order.order_date >= thirty_days_ago
    ).group_by(
        Order.product_name
    ).limit(10).all()
    
    return jsonify({
        'daily_sales': [{'date': str(d.date), 'count': d.count, 'amount': float(d.total_amount or 0)} for d in daily_sales],
        'product_sales': [{'name': p.product_name, 'count': p.count, 'amount': float(p.total_amount or 0)} for p in product_sales]
    })
