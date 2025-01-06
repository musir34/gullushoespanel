from flask import Blueprint, render_template, jsonify, request
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
        Order.order_date >= start_date,
        Order.order_date <= end_date
    ).group_by(
        func.date(Order.order_date)
    ).all()
    
    # Ürün bazlı detaylı satışlar
    product_sales = db.session.query(
        Order.product_barcode,
        Order.merchant_sku,
        Order.product_size,
        Order.product_color,
        Order.product_name,
        func.count(Order.id).label('count'),
        func.sum(Order.amount).label('total_amount')
    ).filter(
        Order.order_date >= start_date,
        Order.order_date <= end_date
    ).group_by(
        Order.product_barcode,
        Order.merchant_sku,
        Order.product_size,
        Order.color,
        Order.product_name
    ).order_by(
        func.count(Order.id).desc()
    ).limit(10).all()
    
    # Haftalık büyüme oranları
    weekly_sales = db.session.query(
        func.date_trunc('week', Order.order_date).label('week'),
        func.sum(Order.amount).label('total_amount')
    ).filter(
        Order.order_date >= start_date,
        Order.order_date <= end_date
    ).group_by(
        func.date_trunc('week', Order.order_date)
    ).order_by(
        func.date_trunc('week', Order.order_date)
    ).all()

    weekly_growth = []
    for i in range(1, len(weekly_sales)):
        prev_amount = float(weekly_sales[i-1].total_amount or 0)
        curr_amount = float(weekly_sales[i].total_amount or 0)
        growth_rate = ((curr_amount - prev_amount) / prev_amount * 100) if prev_amount > 0 else 0
        weekly_growth.append({
            'week': str(weekly_sales[i].week.date()),
            'growth_rate': round(growth_rate, 2)
        })

    # Müşteri segmentleri analizi
    customer_segments = db.session.query(
        Order.customer_name,
        func.count(Order.id).label('order_count'),
        func.sum(Order.amount).label('total_spent')
    ).filter(
        Order.order_date >= start_date,
        Order.order_date <= end_date
    ).group_by(
        Order.customer_name
    ).order_by(
        func.sum(Order.amount).desc()
    ).limit(10).all()

    # En çok satın alım yapan şehirler
    top_cities = db.session.query(
        func.substring(Order.customer_address, '([^,]+)(?:,[^,]+)*$').label('city'),
        func.count(Order.id).label('order_count'),
        func.sum(Order.amount).label('total_amount')
    ).filter(
        Order.order_date >= start_date,
        Order.order_date <= end_date
    ).group_by(
        'city'
    ).order_by(
        func.sum(Order.amount).desc()
    ).limit(5).all()

    # Ürün kategorileri
    product_categories = db.session.query(
        func.substring(Order.product_name, '^([^-]+)').label('category'),
        func.count(Order.id).label('count'),
        func.sum(Order.amount).label('total_amount')
    ).filter(
        Order.order_date >= start_date,
        Order.order_date <= end_date
    ).group_by(
        'category'
    ).order_by(
        func.sum(Order.amount).desc()
    ).limit(5).all()

    return jsonify({
        'daily_sales': [{'date': str(d.date), 'count': d.count, 'amount': float(d.total_amount or 0)} for d in daily_sales],
        'product_sales': [{'name': p.product_name, 'count': p.count, 'amount': float(p.total_amount or 0)} for p in product_sales],
        'weekly_growth': weekly_growth,
        'customer_segments': [{
            'name': c.customer_name,
            'order_count': c.order_count,
            'total_spent': float(c.total_spent or 0)
        } for c in customer_segments],
        'top_cities': [{
            'city': str(c.city).strip(),
            'order_count': c.order_count,
            'amount': float(c.total_amount or 0)
        } for c in top_cities],
        'product_categories': [{
            'category': str(c.category).strip(),
            'count': c.count,
            'amount': float(c.total_amount or 0)
        } for c in product_categories]
    })