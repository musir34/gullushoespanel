from flask import Blueprint, render_template, jsonify, request
from models import db, Order, ReturnOrder, Degisim, Product
from sqlalchemy import func, case, distinct
from datetime import datetime, timedelta
import logging

analysis_bp = Blueprint('analysis', __name__)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)


@analysis_bp.route('/analysis')
def sales_analysis():
    """
    Satış analiz sayfasını render eder.
    (Örneğin analysis.html veya benzer bir şablon döndürebilirsiniz.)
    """
    return render_template('analysis.html')


def get_daily_sales(start_date: datetime, end_date: datetime):
    """
    Belirtilen tarih aralığında günlük satış istatistiklerini döner.
    """
    return db.session.query(
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


def get_product_sales(start_date: datetime, end_date: datetime):
    """
    Belirtilen tarih aralığında ürün bazlı satış analizini döner.
    """
    try:
        logger.info("Ürün satışları sorgusu başlıyor...")
        product_sales = db.session.query(
            func.unnest(func.string_to_array(Order.product_main_id, ', ')).label('product_id'),
            Order.product_color.label('color'),
            Order.product_size.label('size'),
            func.count(Order.id).label('sale_count'),
            func.sum(Order.amount).label('total_revenue'),
            func.avg(Order.amount).label('average_price'),
            func.sum(Order.quantity).label('total_quantity')
        ).filter(
            Order.order_date.between(start_date, end_date),
            Order.product_main_id.isnot(None),
            Order.product_color.isnot(None),
            Order.product_size.isnot(None),
            Order.status != 'Cancelled'
        ).group_by(
            Order.product_main_id,
            Order.product_color,
            Order.product_size
        ).order_by(
            func.sum(Order.amount).desc()
        ).limit(50).all()

        if not product_sales:
            logger.info("Ürün satışı bulunamadı")
            return []
        
        logger.info(f"Bulunan ürün satışı sayısı: {len(product_sales)}")
        for sale in product_sales:
            logger.info(
                f"Ürün detayı: ID={sale.product_main_id}, Renk={sale.color}, "
                f"Beden={sale.size}, Adet={sale.sale_count}, Miktar={sale.total_quantity}, "
                f"Gelir={sale.total_revenue:.2f} TL, Ort. Fiyat={sale.average_price:.2f} TL"
            )
        return product_sales
    except Exception as e:
        logger.exception("Ürün satış verisi çekilirken hata oluştu:")
        return []


def get_return_stats(start_date: datetime, end_date: datetime):
    """
    Belirtilen tarih aralığında iade analiz verilerini döner.
    """
    return db.session.query(
        func.coalesce(ReturnOrder.return_reason, 'Belirtilmemiş').label('return_reason'),
        func.count(ReturnOrder.id).label('return_count'),
        func.count(distinct(ReturnOrder.order_number)).label('unique_orders'),
        func.coalesce(func.avg(ReturnOrder.refund_amount), 0).label('average_refund')
    ).filter(
        ReturnOrder.return_date.between(start_date, end_date)
    ).group_by(
        ReturnOrder.return_reason
    ).all()


def get_exchange_stats(start_date: datetime, end_date: datetime):
    """
    Belirtilen tarih aralığında değişim analiz verilerini döner.
    """
    return db.session.query(
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


@analysis_bp.route('/api/sales-stats')
def get_sales_stats():
    """
    API endpoint'i:
    Belirtilen tarih aralığında (varsayılan 90 gün, URL'den alınan 'start_date' ve 'end_date'
    veya 'quick_filter' parametreleri ile) satış, ürün bazlı satış, iade ve değişim analizlerini
    JSON formatında döner.

    URL Parametreleri:
        - start_date: YYYY-MM-DD formatında başlangıç tarihi (opsiyonel)
        - end_date: YYYY-MM-DD formatında bitiş tarihi (opsiyonel)
        - quick_filter: 'last7', 'last30', 'today', 'this_month' (opsiyonel)
        - days: Belirtilen gün sayısı (varsayılan 90, quick_filter ve start_date/end_date parametreleri yoksa kullanılır)
    """
    try:
        logger.info("API isteği başladı")
        now = datetime.now()

        # Tarih aralığı belirleme önceliği: quick_filter > (start_date, end_date) > days (varsayılan)
        quick_filter = request.args.get('quick_filter')
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')

        if quick_filter:
            if quick_filter == 'last7':
                start_date = now - timedelta(days=7)
                end_date = now
            elif quick_filter == 'last30':
                start_date = now - timedelta(days=30)
                end_date = now
            elif quick_filter == 'today':
                start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
                end_date = now
            elif quick_filter == 'this_month':
                start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                end_date = now
            else:
                logger.info("Geçersiz quick_filter değeri, varsayılan 90 gün kullanılıyor.")
                days = 90
                start_date = now - timedelta(days=days)
                end_date = now
        elif start_date_str and end_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            except ValueError:
                return jsonify({'success': False, 'error': 'Tarih formatı geçersiz. YYYY-MM-DD formatını kullanın.'})
        else:
            days = int(request.args.get('days', 90))
            start_date = now - timedelta(days=days)
            end_date = now

        logger.info(f"Tarih aralığı: {start_date} - {end_date}")

        # Sorguların çalıştırılması
        daily_sales = get_daily_sales(start_date, end_date)
        product_sales = get_product_sales(start_date, end_date)
        returns_stats = get_return_stats(start_date, end_date)
        exchange_stats = get_exchange_stats(start_date, end_date)

        # --> Toplam değerleri hesaplama (toplam sipariş, satılan ürün, ciro)
        # daily_sales verisi üzerinden sum() ile hesaplayabiliriz
        total_orders = sum(stat.order_count or 0 for stat in daily_sales)
        total_items_sold = sum(stat.total_quantity or 0 for stat in daily_sales)
        total_revenue = sum(stat.total_amount or 0 for stat in daily_sales)

        # Grafik için product_sales verisinin hazırlanması
        product_sales_chart = [{
            'product_id': f"{stat.product_main_id or ''} {stat.color or ''} {stat.size or ''}",
            'sale_count': int(stat.sale_count or 0),
            'total_revenue': round(float(stat.total_revenue or 0), 2)
        } for stat in product_sales]

        response = {
            'success': True,

            # Toplam degerleri ekliyoruz:
            'total_orders': total_orders,
            'total_items_sold': total_items_sold,
            'total_revenue': round(float(total_revenue), 2),

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
        }

        return jsonify(response)
    except Exception as e:
        logger.exception("Hata oluştu:")
        return jsonify({
            'success': False,
            'error': str(e),
            'daily_sales': [],
            'product_sales': [],
            'returns': [],
            'exchanges': []
        })
