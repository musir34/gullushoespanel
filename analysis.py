from flask import Blueprint, render_template, jsonify
from models import db, Order, ReturnOrder, Degisim, Product
from sqlalchemy import func, and_, extract, case, distinct, text
from datetime import datetime, timedelta
import json

analysis_bp = Blueprint('analysis', __name__)

@analysis_bp.route('/analysis')
def sales_analysis():
    return render_template('analysis.html')

@analysis_bp.route('/api/sales-stats')
def get_sales_stats():
    try:
        print("API isteği başladı")
        end_date = datetime.now()
        start_date = end_date - timedelta(days=90)
        print(f"Tarih aralığı: {start_date} - {end_date}")

        # Varsayılan boş veri yapıları
        default_response = {
            'daily_sales': [],
            'product_sales': [],
            'returns': [],
            'exchanges': []
        }

        # Günlük satış istatistikleri
        daily_sales = db.session.query(
            func.date(Order.order_date).label('date'),
            func.count(Order.id).label('order_count'),
            func.sum(Order.amount).label('total_amount'),
            func.sum(Order.quantity).label('total_quantity'),
            func.avg(Order.amount).label('average_order_value'),
            func.count(case((Order.status == 'Delivered', 1), else_=None)).label('delivered_count'),
            func.count(case((Order.status == 'Cancelled', 1), else_=None)).label('cancelled_count')
        ).filter(
            Order.order_date.between(start_date, end_date)
        ).group_by(
            func.date(Order.order_date)
        ).order_by(
            func.date(Order.order_date).desc()
        ).all()

        # Ürün bazlı satış analizi
        try:
            print("Ürün satışları sorgusu başlıyor...")
            product_sales = db.session.query(
                Order.product_main_id,
                Product.color,
                Product.size,
                func.count(Order.id).label('sale_count'),
                func.sum(Order.amount).label('total_revenue'),
                func.avg(Order.amount).label('average_price')
            ).join(
                Product, Order.product_barcode.contains(Product.barcode)
            ).filter(
                Order.order_date.between(start_date, end_date),
                Order.product_main_id.isnot(None),
                Product.color.isnot(None),
                Product.size.isnot(None)
            ).group_by(
                Order.product_main_id,
                Product.color,
                Product.size
            ).order_by(
                func.sum(Order.amount).desc()
            ).limit(50).all()

            if not product_sales:
                print("Ürün satışı bulunamadı")
                product_sales = []
            else:
                print(f"Bulunan ürün satışı sayısı: {len(product_sales)}")
                for sale in product_sales:
                    print(f"Ürün detayı: ID={sale.product_main_id}, "
                          f"Renk={sale.color}, Beden={sale.size}, "
                          f"Adet={sale.sale_count}, Gelir={sale.total_revenue}")
        except Exception as e:
            print(f"Ürün satış verisi çekilirken hata: {e}")
            import traceback
            print("Hata detayı:", traceback.format_exc())
            product_sales = []

        # İade analizi
        returns_stats = db.session.query(
            func.coalesce(ReturnOrder.return_reason, 'Belirtilmemiş').label('return_reason'),
            func.count(ReturnOrder.id).label('return_count'),
            func.count(distinct(ReturnOrder.order_number)).label('unique_orders'),
            func.coalesce(func.avg(ReturnOrder.refund_amount), 0).label('average_refund')
        ).filter(
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
            Degisim.degisim_tarihi.between(start_date, end_date)
        ).group_by(
            Degisim.degisim_nedeni,
            func.date(Degisim.degisim_tarihi)
        ).order_by(
            func.date(Degisim.degisim_tarihi).desc()
        ).all()

        # Grafik için product_sales verisi hazırla
        product_sales_chart = [{
            'product_id': f"{stat.product_main_id or ''} {stat.color or ''} {stat.size or ''}",
            'sale_count': int(stat.sale_count or 0),
            'total_revenue': round(float(stat.total_revenue or 0), 2)
        } for stat in product_sales]

        return jsonify({
            'success': True,
            'daily_sales': [{
                'date': stat.date.strftime('%Y-%m-%d') if stat.date else None,
                'order_count': int(stat.order_count or 0),
                'total_amount': float(stat.total_amount or 0),
                'total_quantity': int(stat.total_quantity or 0),
                'average_order_value': round(float(stat.average_order_value or 0), 2),
                'delivered_count': int(stat.delivered_count or 0),
                'cancelled_count': int(stat.cancelled_count or 0)
            } for stat in daily_sales],
            'product_sales': [{
                'product_id': stat.product_main_id,
                'color': stat.color,
                'size': stat.size,
                'sale_count': int(stat.sale_count or 0),
                'total_revenue': round(float(stat.total_revenue or 0), 2),
                'average_price': round(float(stat.average_price or 0), 2)
            } for stat in product_sales],
            'product_sales_chart': product_sales_chart,
            'returns': [{
                'reason': stat.return_reason,
                'count': int(stat.return_count or 0),
                'unique_orders': int(stat.unique_orders or 0),
                'average_refund': round(float(stat.average_refund or 0), 2)
            } for stat in returns_stats],
            'exchanges': [{
                'reason': stat.degisim_nedeni,
                'count': int(stat.exchange_count or 0),
                'date': stat.date.strftime('%Y-%m-%d') if stat.date else None
            } for stat in exchange_stats]
        })
    except Exception as e:
        print(f"Hata: {str(e)}")
        print(f"Hata: {str(e)}")
        return jsonify({
            'success': True,
            'error': str(e),
            **default_response
        })