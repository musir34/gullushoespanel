
from flask import Blueprint, render_template
from models import db, Order, Product, ReturnOrder
from sqlalchemy import func
from datetime import datetime, timedelta
import json

analysis_bp = Blueprint('analysis', __name__)

@analysis_bp.route('/analysis')
def analysis():
    # Son 30 günlük tarih aralığı
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    # Temel metrikler
    total_orders = Order.query.filter(
        Order.order_date.between(start_date, end_date)
    ).count()
    
    total_revenue = Order.query.with_entities(
        func.sum(Order.amount)
    ).filter(
        Order.order_date.between(start_date, end_date)
    ).scalar() or 0
    
    avg_order_value = total_revenue / total_orders if total_orders > 0 else 0
    
    returns_count = ReturnOrder.query.filter(
        ReturnOrder.return_date.between(start_date, end_date)
    ).count()
    
    return_rate = (returns_count / total_orders * 100) if total_orders > 0 else 0
    
    # Günlük sipariş trendi
    daily_orders = []
    dates = []
    current_date = start_date
    while current_date <= end_date:
        count = Order.query.filter(
            func.date(Order.order_date) == current_date.date()
        ).count()
        daily_orders.append(count)
        dates.append(current_date.strftime('%Y-%m-%d'))
        current_date += timedelta(days=1)
    
    # En çok satan ürünler
    top_products_data = db.session.query(
        Product.barcode,
        func.count(Order.id).label('sales_count')
    ).join(Order, Product.barcode == Order.product_barcode)\
    .group_by(Product.barcode)\
    .order_by(func.count(Order.id).desc())\
    .limit(10).all()
    
    top_products = {
        'labels': [p[0] for p in top_products_data],
        'data': [p[1] for p in top_products_data]
    }
    
    # Ürün performans analizi
    product_analysis = []
    for product in Product.query.limit(20):  # İlk 20 ürün için örnek
        sales = Order.query.filter_by(product_barcode=product.barcode).count()
        revenue = Order.query.with_entities(func.sum(Order.amount))\
            .filter_by(product_barcode=product.barcode).scalar() or 0
        return_count = ReturnOrder.query.filter_by(product_id=product.barcode).count()
        return_rate = (return_count / sales * 100) if sales > 0 else 0
        
        product_analysis.append({
            'code': product.barcode,
            'sales': sales,
            'revenue': round(revenue, 2),
            'return_rate': round(return_rate, 1),
            'stock': product.quantity
        })
    
    return render_template('analysis.html',
                         total_orders=total_orders,
                         total_revenue=round(total_revenue, 2),
                         avg_order_value=round(avg_order_value, 2),
                         return_rate=round(return_rate, 1),
                         dates=dates,
                         daily_orders=daily_orders,
                         top_products=top_products,
                         product_analysis=product_analysis)
