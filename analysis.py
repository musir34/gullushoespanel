
from flask import Blueprint, render_template, jsonify
from models import db, Order, ReturnOrder, Degisim, Product
from sqlalchemy import func, and_, extract
from datetime import datetime, timedelta
import json

analysis_bp = Blueprint('analysis', __name__)

@analysis_bp.route('/analysis')
def sales_analysis():
    return render_template('analysis.html')

@analysis_bp.route('/api/sales-stats')
def get_sales_stats():
    try:
        # Son 30 günlük veriler
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        # Günlük satış istatistikleri
        daily_sales = db.session.query(
            func.date(Order.order_date).label('date'),
            func.count(Order.id).label('order_count'),
            func.sum(Order.amount).label('total_amount'),
            func.sum(Order.quantity).label('total_quantity')
        ).filter(
            Order.order_date.between(start_date, end_date)
        ).group_by(
            func.date(Order.order_date)
        ).all()

        # İade istatistikleri
        returns_stats = db.session.query(
            func.count(ReturnOrder.id).label('return_count'),
            ReturnOrder.return_reason,
            func.sum(ReturnProduct.quantity).label('return_quantity')
        ).join(
            ReturnProduct, ReturnOrder.id == ReturnProduct.return_order_id
        ).group_by(
            ReturnOrder.return_reason
        ).all()

        # Değişim istatistikleri
        exchange_stats = db.session.query(
            func.count(Degisim.degisim_no).label('exchange_count'),
            Degisim.degisim_nedeni,
            func.date(Degisim.degisim_tarihi).label('date')
        ).group_by(
            Degisim.degisim_nedeni,
            func.date(Degisim.degisim_tarihi)
        ).all()

        # Stok durumu
        stock_stats = db.session.query(
            Product.product_main_id,
            func.sum(Product.quantity).label('total_stock'),
            Product.color,
            Product.size
        ).group_by(
            Product.product_main_id,
            Product.color,
            Product.size
        ).all()

        return jsonify({
            'success': True,
            'daily_sales': [{
                'date': str(stat.date),
                'order_count': stat.order_count,
                'total_amount': float(stat.total_amount or 0),
                'total_quantity': int(stat.total_quantity or 0)
            } for stat in daily_sales],
            'returns': [{
                'reason': stat.return_reason,
                'count': stat.return_count,
                'quantity': int(stat.return_quantity or 0)
            } for stat in returns_stats],
            'exchanges': [{
                'reason': stat.degisim_nedeni,
                'count': stat.exchange_count,
                'date': str(stat.date)
            } for stat in exchange_stats],
            'stock': [{
                'product_id': stat.product_main_id,
                'total_stock': int(stat.total_stock or 0),
                'color': stat.color,
                'size': stat.size
            } for stat in stock_stats]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
