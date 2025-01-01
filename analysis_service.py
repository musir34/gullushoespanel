
from flask import Blueprint, render_template
from models import db, Order, Product
from sqlalchemy import func
from datetime import datetime, timedelta

analysis_bp = Blueprint('analysis', __name__)

@analysis_bp.route('/analysis')
def analysis():
    # Toplam sipariş sayısı
    total_orders = Order.query.count()
    
    # Toplam satış tutarı
    total_sales = db.session.query(func.sum(Order.amount)).scalar() or 0
    
    # Ortalama sipariş değeri
    avg_order_value = total_sales / total_orders if total_orders > 0 else 0
    
    # Toplam ürün adedi
    total_products = db.session.query(func.sum(Order.quantity)).scalar() or 0
    
    # Son 30 günlük satış verileri
    thirty_days_ago = datetime.now() - timedelta(days=30)
    daily_orders = db.session.query(
        func.date(Order.order_date).label('date'),
        func.sum(Order.amount).label('total')
    ).filter(Order.order_date >= thirty_days_ago)\
     .group_by(func.date(Order.order_date))\
     .order_by(func.date(Order.order_date)).all()
    
    dates = [order.date.strftime('%d/%m') for order in daily_orders]
    daily_sales = [float(order.total) for order in daily_orders]
    
    # En çok satan ürünler
    top_products = db.session.query(
        Order.product_name,
        func.sum(Order.quantity).label('total_quantity')
    ).group_by(Order.product_name)\
     .order_by(func.sum(Order.quantity).desc())\
     .limit(10).all()
    
    top_products_labels = [product.product_name.split(',')[0] for product in top_products]
    top_products_data = [int(product.total_quantity) for product in top_products]
    
    # Son siparişler
    recent_orders = Order.query.order_by(Order.order_date.desc()).limit(10).all()
    
    return render_template('analysis.html',
        total_orders=total_orders,
        total_sales="{:.2f}".format(total_sales),
        avg_order_value="{:.2f}".format(avg_order_value),
        total_products=total_products,
        dates=dates,
        daily_sales=daily_sales,
        top_products_labels=top_products_labels,
        top_products_data=top_products_data,
        recent_orders=recent_orders
    )
