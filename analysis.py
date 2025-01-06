
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
    start_date = request.args.get('start_date', None)
    end_date = request.args.get('end_date', None)
    
    if start_date and end_date:
        start_date = datetime.strptime(start_date, '%Y-%m-%d')
        end_date = datetime.strptime(end_date, '%Y-%m-%d')
    else:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
    
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
