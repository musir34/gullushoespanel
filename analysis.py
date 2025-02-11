
from flask import Blueprint, render_template, jsonify
from models import db, Order, ReturnOrder, Degisim, Product
from sqlalchemy import func, and_, extract, case, distinct
from datetime import datetime, timedelta
import json

analysis_bp = Blueprint('analysis', __name__)

@analysis_bp.route('/analysis')
def sales_analysis():
    return render_template('analysis.html')

@analysis_bp.route('/api/sales-stats')
def get_sales_stats():
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        # Günlük satış istatistikleri
        daily_sales = db.session.query(
            func.date(Order.order_date).label('date'),
            func.count(distinct(Order.order_number)).label('order_count'),
            func.coalesce(func.sum(Order.amount), 0).label('total_amount'),
            func.coalesce(func.sum(Order.quantity), 0).label('total_quantity'),
            func.coalesce(func.avg(Order.amount), 0).label('average_order_value'),
            func.count(case([(Order.status == 'Delivered', 1)], else_=None)).label('delivered_count'),
            func.count(case([(Order.status == 'Cancelled', 1)], else_=None)).label('cancelled_count')
        ).filter(
            Order.order_date.isnot(None),
            Order.order_date.between(start_date, end_date)
        ).group_by(
            func.date(Order.order_date)
        ).order_by(
            func.date(Order.order_date)
        ).all()

        # Ürün bazlı satış analizi
        product_sales = db.session.query(
            Order.product_main_id,
            Product.color,
            Product.size,
            func.count(Order.id).label('sale_count'),
            func.sum(Order.amount).label('total_revenue'),
            func.avg(Order.amount).label('average_price')
        ).join(
            Product, Order.product_barcode == Product.barcode
        ).filter(
            Order.order_date.between(start_date, end_date)
        ).group_by(
            Order.product_main_id,
            Product.color,
            Product.size
        ).all()

        # İade analizi
        returns_stats = db.session.query(
            func.coalesce(ReturnOrder.return_reason, 'Belirtilmemiş').label('return_reason'),
            func.count(ReturnOrder.id).label('return_count'),
            func.count(distinct(ReturnOrder.order_number)).label('unique_orders'),
            func.coalesce(func.avg(ReturnOrder.refund_amount), 0).label('average_refund')
        ).filter(
            ReturnOrder.return_date.isnot(None),
            ReturnOrder.return_date.between(start_date, end_date)
        ).group_by(
            ReturnOrder.return_reason
        ).all()

        # Değişim analizi
        exchange_stats = db.session.query(
            func.coalesce(Degisim.degisim_nedeni, 'Belirtilmemiş').label('degisim_nedeni'),
            func.count(Degisim.degisim_no).label('exchange_count'),
            func.date(Degisim.degisim_tarihi).label('date')
        ).filter(
            Degisim.degisim_tarihi.isnot(None),
            Degisim.degisim_tarihi.between(start_date, end_date)
        ).group_by(
            Degisim.degisim_nedeni,
            func.date(Degisim.degisim_tarihi)
        ).all()

        return jsonify({
            'success': True,
            'daily_sales': [{
                'date': str(stat.date),
                'order_count': stat.order_count,
                'total_amount': float(stat.total_amount or 0),
                'total_quantity': int(stat.total_quantity or 0),
                'average_order_value': float(stat.average_order_value or 0),
                'delivered_count': stat.delivered_count,
                'cancelled_count': stat.cancelled_count
            } for stat in daily_sales],
            'product_sales': [{
                'product_id': stat.product_main_id,
                'color': stat.color,
                'size': stat.size,
                'sale_count': stat.sale_count,
                'total_revenue': float(stat.total_revenue or 0),
                'average_price': float(stat.average_price or 0)
            } for stat in product_sales],
            'returns': [{
                'reason': stat.return_reason,
                'count': stat.return_count,
                'unique_orders': stat.unique_orders,
                'average_refund': float(stat.average_refund or 0)
            } for stat in returns_stats],
            'exchanges': [{
                'reason': stat.degisim_nedeni,
                'count': stat.exchange_count,
                'date': str(stat.date)
            } for stat in exchange_stats]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
