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
    """
    try:
        return render_template('analysis.html')
    except Exception as e:
        logger.error(f"Analiz sayfası render hatası: {str(e)}")
        return render_template('error.html', error=str(e))




def get_daily_sales(start_date: datetime, end_date: datetime):
    """
    Belirtilen tarih aralığında günlük satış istatistiklerini döner.
    """
    try:
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
    except Exception as e:
        logger.error(f"Günlük satış verileri çekilirken hata: {e}")
        db.session.rollback()
        return []


def get_product_sales(start_date: datetime, end_date: datetime):
    """
    Belirtilen tarih aralığında ürün bazlı satış analizini döner.
    """
    try:
        logger.info("Ürün satışları sorgusu başlıyor...")
        product_sales = db.session.query(
            Order.product_main_id.label('product_main_id'),
            Order.merchant_sku.label('merchant_sku'),
            Order.product_color.label('color'),
            Order.product_size.label('size'),
            func.count(Order.id).label('sale_count'),
            func.sum(Order.amount).label('total_revenue'),
            func.avg(Order.amount).label('average_price'),
            func.sum(Order.quantity).label('total_quantity')
        ).filter(
            Order.order_date.between(start_date, end_date),
            Order.status != 'Cancelled'
        ).group_by(
            Order.product_main_id,
            Order.merchant_sku,
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
    try:
        # ReturnOrder tablosunun var olduğundan emin ol
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        if not inspector.has_table('return_orders'):
            logger.warning("ReturnOrder tablosu veritabanında bulunamadı")
            return []

        result = db.session.query(
            func.coalesce(ReturnOrder.return_reason, 'Belirtilmemiş').label('return_reason'),
            func.count(ReturnOrder.id).label('return_count'),
            func.count(distinct(ReturnOrder.order_number)).label('unique_orders'),
            func.coalesce(func.avg(ReturnOrder.refund_amount), 0).label('average_refund')
        ).filter(
            ReturnOrder.return_date.between(start_date, end_date)
        ).group_by(
            ReturnOrder.return_reason
        ).all()
        return result
    except Exception as e:
        logger.error(f"İade istatistikleri sorgusu hatası: {e}")
        db.session.rollback()
        return []


def get_exchange_stats(start_date: datetime, end_date: datetime):
    """
    Belirtilen tarih aralığında değişim analiz verilerini döner.
    """
    try:
        # Degisim tablosunun var olduğundan emin ol
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        if not inspector.has_table('degisim'):
            logger.warning("Degisim tablosu veritabanında bulunamadı")
            return []

        result = db.session.query(
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
        return result
    except Exception as e:
        logger.error(f"Değişim istatistikleri sorgusu hatası: {e}")
        db.session.rollback()
        return []


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
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from models import Base
        from app import DATABASE_URI

        # Yeni bir session oluştur
        engine = create_engine(DATABASE_URI)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()

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
                return jsonify({'success': False, 'error': 'Tarih formatı geçersiz. YYYY-MM-DD formatını kullanın.', 'daily_sales': [], 'product_sales': [], 'returns': [], 'exchanges': []})
        else:
            days = int(request.args.get('days', 90))
            start_date = now - timedelta(days=days)
            end_date = now

        logger.info(f"Tarih aralığı: {start_date} - {end_date}")

        # Veri toplama sonuçları
        daily_sales = []
        product_sales = []

        # Günlük satış verileri
        try:
            daily_sales_query = session.query(
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
            )

            daily_sales = daily_sales_query.all()
            logger.info(f"Günlük satış verileri başarıyla çekildi: {len(daily_sales)} kayıt")

        except Exception as e:
            logger.error(f"Günlük satış verisi çekilirken hata: {e}")
            session.rollback()

        # Ürün satış verileri
        try:
            logger.info("Ürün satışları sorgusu başlıyor...")
            product_sales_query = session.query(
                Order.product_main_id.label('product_main_id'),
                Order.merchant_sku.label('merchant_sku'),
                Order.product_color.label('color'),
                Order.product_size.label('size'),
                func.count(Order.id).label('sale_count'),
                func.sum(Order.amount).label('total_revenue'),
                func.avg(Order.amount).label('average_price'),
                func.sum(Order.quantity).label('total_quantity')
            ).filter(
                Order.order_date.between(start_date, end_date),
                Order.status != 'Cancelled'
            ).group_by(
                Order.product_main_id,
                Order.merchant_sku,
                Order.product_color,
                Order.product_size
            ).order_by(
                func.sum(Order.amount).desc()
            ).limit(50)

            product_sales = product_sales_query.all()
            logger.info(f"Ürün satışları verileri başarıyla çekildi: {len(product_sales)} kayıt")

        except Exception as e:
            logger.error(f"Ürün satış verisi çekilirken hata: {e}")
            session.rollback()

        # Toplam değerleri hesaplama (toplam sipariş, satılan ürün, ciro)
        total_orders = sum(stat.order_count or 0 for stat in daily_sales) if daily_sales else 0
        total_items_sold = sum(stat.total_quantity or 0 for stat in daily_sales) if daily_sales else 0 
        total_revenue = sum(stat.total_amount or 0 for stat in daily_sales) if daily_sales else 0

        # Grafik için product_sales verisinin hazırlanması
        product_sales_chart = []
        try:
            product_sales_chart = [{
                'product_id': f"{sale.product_main_id or ''}",
                'merchant_sku': f"{sale.merchant_sku or ''}",
                'product_full': f"{sale.product_main_id or ''} - {sale.color or ''} {sale.size or ''}",
                'color': f"{sale.color or ''}",
                'size': f"{sale.size or ''}",
                'sale_count': int(sale.sale_count or 0),
                'total_revenue': round(float(sale.total_revenue or 0), 2)
            } for sale in product_sales] if product_sales else []
        except Exception as e:
            logger.error(f"Ürün satış grafik verisi oluşturulurken hata: {e}")

        response = {
            'success': True,

            # Toplam degerleri
            'total_orders': total_orders,
            'total_items_sold': total_items_sold,
            'total_revenue': round(float(total_revenue), 2),

            'daily_sales': [{
                'date': stat.date.strftime('%Y-%m-%d') if stat.date else None,
                'order_count': int(stat.order_count or 0),
                'total_amount': float(stat.total_amount or 0) if stat.total_amount else 0,
                'total_quantity': int(stat.total_quantity or 0),
                'average_order_value': round(float(stat.average_order_value or 0), 2),
                'delivered_count': int(stat.delivered_count or 0),
                'cancelled_count': int(stat.cancelled_count or 0)
            } for stat in daily_sales] if daily_sales else [],

            'product_sales': [{
                'product_id': sale.product_main_id,
                'merchant_sku': sale.merchant_sku,
                'color': sale.color,
                'size': sale.size,
                'sale_count': int(sale.sale_count or 0),
                'total_revenue': round(float(sale.total_revenue or 0), 2),
                'average_price': round(float(sale.average_price or 0), 2)
            } for sale in product_sales] if product_sales else [],

            'product_sales_chart': [{
                'product_id': sale.product_main_id or '',
                'merchant_sku': sale.merchant_sku or '',
                'product_full': f"{sale.product_main_id or ''} - {sale.color or ''} {sale.size or ''}",
                'color': sale.color or '',
                'size': sale.size or '',
                'sale_count': int(sale.sale_count or 0),
                'total_revenue': round(float(sale.total_revenue or 0), 2)
            } for sale in product_sales] if product_sales else [],

            # Return ve Exchange verilerini boş olarak gönderelim
            'returns': [],
            'exchanges': []
        }

        session.close()
        return jsonify(response)

    except Exception as e:
        logger.exception(f"API hatası: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'daily_sales': [],
            'product_sales': [],
            'product_sales_chart': [],
            'returns': [],
            'exchanges': []
        })
