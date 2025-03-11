from flask import Blueprint, render_template, jsonify, request
from models import db, Order, Product, ProfitData, ProductCost
from datetime import datetime, timedelta
from sqlalchemy import func, desc, and_, case, distinct
import logging
import json
from apscheduler.schedulers.background import BackgroundScheduler
from cache_config import redis_client
import pandas as pd
import numpy as np

# Loglama yapılandırması
logger = logging.getLogger("profit_analysis")
logger.setLevel(logging.INFO)
handler = logging.FileHandler('profit_analysis.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Blueprint tanımlaması
profit_analysis_bp = Blueprint('profit_analysis', __name__)

# Ana kâr analizi sayfası
@profit_analysis_bp.route('/profit-analysis', methods=['GET'])
def profit_analysis_page():
    return render_template('profit_analysis.html')

# API Endpoint - Günlük Kar Analizi
@profit_analysis_bp.route('/api/profit/daily', methods=['GET'])
def get_daily_profit():
    try:
        # Redis önbelleğe bakma
        cache_key = "profit_analysis_daily"
        cached_data = None
        try:
            from cache_config import redis_active
            if redis_active:
                cached_data = redis_client.get(cache_key)
        except Exception as e:
            logger.warning(f"Redis önbellek erişim hatası: {str(e)}")

        if cached_data:
            return jsonify(json.loads(cached_data))

        # Tarih aralığını al (son 30 gün varsayılan)
        days = int(request.args.get('days', 30))
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # Veritabanından günlük kâr verilerini al
        daily_data = db.session.query(
            ProfitData.date, 
            func.sum(ProfitData.total_revenue).label('revenue'),
            func.sum(ProfitData.total_cost).label('cost'),
            func.sum(ProfitData.total_profit).label('profit'),
            func.sum(ProfitData.order_count).label('order_count'),
            func.sum(ProfitData.quantity).label('quantity')
        ).filter(
            ProfitData.data_type == 'daily',
            ProfitData.date.between(start_date.date(), end_date.date())
        ).group_by(ProfitData.date).order_by(ProfitData.date).all()

        # Veriyi formatla
        result = []
        for row in daily_data:
            result.append({
                'date': row.date.strftime('%Y-%m-%d'),
                'revenue': float(row.revenue) if row.revenue else 0,
                'cost': float(row.cost) if row.cost else 0,
                'profit': float(row.profit) if row.profit else 0,
                'profit_margin': round(float(row.profit) / float(row.revenue) * 100, 2) if row.revenue and row.profit else 0,
                'order_count': row.order_count,
                'quantity': row.quantity,
                'avg_order_value': round(float(row.revenue) / row.order_count, 2) if row.revenue and row.order_count else 0
            })

        # Sonucu JSON olarak döndür
        response = {
            'data': result,
            'summary': calculate_summary(result)
        }

        # Redis önbelleğe kaydet (1 saat süreyle)
        try:
            from cache_config import redis_active
            if redis_active:
                redis_client.setex(cache_key, 3600, json.dumps(response))
        except Exception as e:
            logger.warning(f"Redis önbellekleme hatası: {str(e)}")

        return jsonify(response)

    except Exception as e:
        logger.error(f"Günlük kâr analizi hatası: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

# API Endpoint - Ürün Bazlı Kar Analizi
@profit_analysis_bp.route('/api/profit/products', methods=['GET'])
def get_product_profit():
    try:
        # Redis önbelleğe bakma
        cache_key = "profit_analysis_products"
        cached_data = None
        try:
            from cache_config import redis_active
            if redis_active:
                cached_data = redis_client.get(cache_key)
        except Exception as e:
            logger.warning(f"Redis önbellek erişim hatası: {str(e)}")

        if cached_data:
            return jsonify(json.loads(cached_data))

        # Limit parametresini al (en karlı/zararlı kaç ürün gösterilecek)
        limit = int(request.args.get('limit', 10))

        # Veritabanından ürün kâr verilerini al
        product_data = db.session.query(
            ProfitData.reference_id,
            ProfitData.reference_name,
            func.sum(ProfitData.total_revenue).label('revenue'),
            func.sum(ProfitData.total_cost).label('cost'),
            func.sum(ProfitData.total_profit).label('profit'),
            func.sum(ProfitData.quantity).label('quantity')
        ).filter(
            ProfitData.data_type == 'product'
        ).group_by(
            ProfitData.reference_id, 
            ProfitData.reference_name
        ).order_by(
            desc(func.sum(ProfitData.total_profit))
        ).limit(limit).all()

        # En zararlı ürünleri al
        loss_product_data = db.session.query(
            ProfitData.reference_id,
            ProfitData.reference_name,
            func.sum(ProfitData.total_revenue).label('revenue'),
            func.sum(ProfitData.total_cost).label('cost'),
            func.sum(ProfitData.total_profit).label('profit'),
            func.sum(ProfitData.quantity).label('quantity')
        ).filter(
            ProfitData.data_type == 'product'
        ).group_by(
            ProfitData.reference_id, 
            ProfitData.reference_name
        ).order_by(
            func.sum(ProfitData.total_profit)
        ).limit(limit).all()

        # Veriyi formatla
        profitable_products = []
        for row in product_data:
            profitable_products.append({
                'barcode': row.reference_id,
                'name': row.reference_name,
                'revenue': float(row.revenue) if row.revenue else 0,
                'cost': float(row.cost) if row.cost else 0,
                'profit': float(row.profit) if row.profit else 0,
                'profit_margin': round(float(row.profit) / float(row.revenue) * 100, 2) if row.revenue and row.profit else 0,
                'quantity': row.quantity,
                'avg_price': round(float(row.revenue) / row.quantity, 2) if row.revenue and row.quantity else 0
            })

        loss_products = []
        for row in loss_product_data:
            loss_products.append({
                'barcode': row.reference_id,
                'name': row.reference_name,
                'revenue': float(row.revenue) if row.revenue else 0,
                'cost': float(row.cost) if row.cost else 0,
                'profit': float(row.profit) if row.profit else 0,
                'profit_margin': round(float(row.profit) / float(row.revenue) * 100, 2) if row.revenue and row.profit else 0,
                'quantity': row.quantity,
                'avg_price': round(float(row.revenue) / row.quantity, 2) if row.revenue and row.quantity else 0
            })

        # Sonucu JSON olarak döndür
        response = {
            'profitable_products': profitable_products,
            'loss_products': loss_products
        }

        # Redis önbelleğe kaydet (2 saat süreyle)
        try:
            from cache_config import redis_active
            if redis_active:
                redis_client.setex(cache_key, 7200, json.dumps(response))
        except Exception as e:
            logger.warning(f"Redis önbellekleme hatası: {str(e)}")

        return jsonify(response)

    except Exception as e:
        logger.error(f"Ürün kâr analizi hatası: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

# Yardımcı fonksiyonlar
def calculate_summary(data):
    """Veri özeti hesaplama yardımcı fonksiyonu"""
    if not data:
        return {
            'total_revenue': 0,
            'total_cost': 0,
            'total_profit': 0,
            'avg_profit_margin': 0,
            'total_orders': 0,
            'total_quantity': 0,
            'avg_order_value': 0
        }

    total_revenue = sum(item['revenue'] for item in data)
    total_cost = sum(item['cost'] for item in data)
    total_profit = sum(item['profit'] for item in data)
    total_orders = sum(item['order_count'] for item in data)
    total_quantity = sum(item['quantity'] for item in data)

    return {
        'total_revenue': round(total_revenue, 2),
        'total_cost': round(total_cost, 2),
        'total_profit': round(total_profit, 2),
        'avg_profit_margin': round(total_profit / total_revenue * 100, 2) if total_revenue > 0 else 0,
        'total_orders': total_orders,
        'total_quantity': total_quantity,
        'avg_order_value': round(total_revenue / total_orders, 2) if total_orders > 0 else 0
    }

# APScheduler ile günlük kâr analizini hesaplama işlemi
def calculate_daily_profit():
    """
    Günlük olarak tamamlanan siparişleri analiz eder ve kâr/zarar hesaplar
    """
    logger.info("Günlük kâr analizi hesaplanıyor...")
    try:
        # Dün için tarih aralığı
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        start_date = datetime.combine(yesterday, datetime.min.time())
        end_date = datetime.combine(yesterday, datetime.max.time())

        # Tamamlanan ve kargoya verilmiş siparişleri getir
        orders = Order.query.filter(
            Order.status.in_(['Delivered', 'Shipped']),
            Order.delivery_date.between(start_date, end_date)
        ).all()

        if not orders:
            logger.info(f"Belirtilen tarih aralığında tamamlanan sipariş bulunamadı: {yesterday}")
            return

        # Kâr analizini hesapla
        total_revenue = 0
        total_cost = 0
        total_quantity = 0
        product_data = {}  # Ürün bazlı analiz için
        model_data = {}    # Model bazlı analiz için
        color_data = {}    # Renk bazlı analiz için
        size_data = {}     # Beden bazlı analiz için

        for order in orders:
            # Geliri hesapla
            revenue = order.amount if order.amount else 0
            total_revenue += revenue
            quantity = order.quantity if order.quantity else 1
            total_quantity += quantity

            # Maliyet için ürün bilgisini bul
            product_cost = get_product_cost(order.product_barcode)

            if product_cost:
                cost = product_cost * quantity
                profit = revenue - cost
            else:
                # Maliyet bulunamadıysa varsayılan kâr marjı (örn: %30)
                cost = revenue * 0.7
                profit = revenue * 0.3

            total_cost += cost

            # Ürün bazlı analiz için veri toplama
            if order.product_barcode:
                if order.product_barcode not in product_data:
                    product_data[order.product_barcode] = {
                        'reference_id': order.product_barcode,
                        'reference_name': order.product_name or "Bilinmeyen Ürün",
                        'revenue': 0,
                        'cost': 0,
                        'profit': 0,
                        'quantity': 0,
                        'order_count': 0
                    }
                product_data[order.product_barcode]['revenue'] += revenue
                product_data[order.product_barcode]['cost'] += cost
                product_data[order.product_barcode]['profit'] += profit
                product_data[order.product_barcode]['quantity'] += quantity
                product_data[order.product_barcode]['order_count'] += 1

            # Model bazlı analiz için veri toplama
            if order.product_model_code:
                if order.product_model_code not in model_data:
                    model_data[order.product_model_code] = {
                        'reference_id': order.product_model_code,
                        'reference_name': f"Model: {order.product_model_code}",
                        'revenue': 0,
                        'cost': 0,
                        'profit': 0,
                        'quantity': 0,
                        'order_count': 0
                    }
                model_data[order.product_model_code]['revenue'] += revenue
                model_data[order.product_model_code]['cost'] += cost
                model_data[order.product_model_code]['profit'] += profit
                model_data[order.product_model_code]['quantity'] += quantity
                model_data[order.product_model_code]['order_count'] += 1

            # Renk bazlı analiz için veri toplama
            if order.product_color:
                if order.product_color not in color_data:
                    color_data[order.product_color] = {
                        'reference_id': order.product_color,
                        'reference_name': f"Renk: {order.product_color}",
                        'revenue': 0,
                        'cost': 0,
                        'profit': 0,
                        'quantity': 0,
                        'order_count': 0
                    }
                color_data[order.product_color]['revenue'] += revenue
                color_data[order.product_color]['cost'] += cost
                color_data[order.product_color]['profit'] += profit
                color_data[order.product_color]['quantity'] += quantity
                color_data[order.product_color]['order_count'] += 1

            # Beden bazlı analiz için veri toplama
            if order.product_size:
                if order.product_size not in size_data:
                    size_data[order.product_size] = {
                        'reference_id': order.product_size,
                        'reference_name': f"Beden: {order.product_size}",
                        'revenue': 0,
                        'cost': 0,
                        'profit': 0,
                        'quantity': 0,
                        'order_count': 0
                    }
                size_data[order.product_size]['revenue'] += revenue
                size_data[order.product_size]['cost'] += cost
                size_data[order.product_size]['profit'] += profit
                size_data[order.product_size]['quantity'] += quantity
                size_data[order.product_size]['order_count'] += 1

        # Günlük toplam veriyi kaydet
        daily_data = ProfitData(
            date=yesterday,
            data_type='daily',
            reference_id='total',
            reference_name='Günlük Toplam',
            order_count=len(orders),
            quantity=total_quantity,
            total_revenue=total_revenue,
            total_cost=total_cost,
            total_profit=total_revenue - total_cost,
            profit_margin=((total_revenue - total_cost) / total_revenue * 100) if total_revenue > 0 else 0
        )
        db.session.add(daily_data)

        # Ürün bazlı verileri kaydet
        for product_id, data in product_data.items():
            product_profit_data = ProfitData(
                date=yesterday,
                data_type='product',
                reference_id=data['reference_id'],
                reference_name=data['reference_name'],
                order_count=data['order_count'],
                quantity=data['quantity'],
                total_revenue=data['revenue'],
                total_cost=data['cost'],
                total_profit=data['profit'],
                profit_margin=(data['profit'] / data['revenue'] * 100) if data['revenue'] > 0 else 0
            )
            db.session.add(product_profit_data)

        # Model bazlı verileri kaydet
        for model_id, data in model_data.items():
            model_profit_data = ProfitData(
                date=yesterday,
                data_type='model',
                reference_id=data['reference_id'],
                reference_name=data['reference_name'],
                order_count=data['order_count'],
                quantity=data['quantity'],
                total_revenue=data['revenue'],
                total_cost=data['cost'],
                total_profit=data['profit'],
                profit_margin=(data['profit'] / data['revenue'] * 100) if data['revenue'] > 0 else 0
            )
            db.session.add(model_profit_data)

        # Renk bazlı verileri kaydet
        for color_id, data in color_data.items():
            color_profit_data = ProfitData(
                date=yesterday,
                data_type='color',
                reference_id=data['reference_id'],
                reference_name=data['reference_name'],
                order_count=data['order_count'],
                quantity=data['quantity'],
                total_revenue=data['revenue'],
                total_cost=data['cost'],
                total_profit=data['profit'],
                profit_margin=(data['profit'] / data['revenue'] * 100) if data['revenue'] > 0 else 0
            )
            db.session.add(color_profit_data)

        # Beden bazlı verileri kaydet
        for size_id, data in size_data.items():
            size_profit_data = ProfitData(
                date=yesterday,
                data_type='size',
                reference_id=data['reference_id'],
                reference_name=data['reference_name'],
                order_count=data['order_count'],
                quantity=data['quantity'],
                total_revenue=data['revenue'],
                total_cost=data['cost'],
                total_profit=data['profit'],
                profit_margin=(data['profit'] / data['revenue'] * 100) if data['revenue'] > 0 else 0
            )
            db.session.add(size_profit_data)

        # Veritabanına kaydet
        db.session.commit()
        logger.info(f"Günlük kâr analizi başarıyla hesaplandı ve kaydedildi: {yesterday}, Sipariş Sayısı: {len(orders)}")

        # Redis önbelleği temizle
        try:
            from cache_config import redis_active
            if redis_active:
                redis_client.delete("profit_analysis_daily", "profit_analysis_products")
        except Exception as e:
            logger.warning(f"Redis önbellek temizleme hatası: {str(e)}")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Ürün kâr hesaplama hatası: {str(e)}", exc_info=True)

def get_product_cost(barcode):
    """
    Ürün maliyetini döndüren yardımcı fonksiyon
    Önce ProductCost tablosunda arar, bulamazsa varsayılan bir maliyet döndürür
    """
    try:
        if not barcode:
            return None

        # ProductCost tablosunda ara
        product_cost = ProductCost.query.filter_by(barcode=barcode).first()
        if product_cost and product_cost.cost_price:
            return float(product_cost.cost_price)

        # Eğer maliyet kaydı yoksa, ürün bilgisinden tahmin et
        product = Product.query.filter_by(barcode=barcode).first()
        if product and product.sale_price:
            # Varsayılan kar marjı (%30)
            estimated_cost = float(product.sale_price) * 0.7
            return estimated_cost

        return None
    except Exception as e:
        logger.error(f"Ürün maliyet hesaplama hatası: {str(e)}")
        return None

# APScheduler için zamanlayıcı başlatma fonksiyonu
def init_scheduler():
    """
    Kar analizi için zamanlayıcıyı başlatır.
    Her gün 04:00'de çalışır.
    """
    try:
        scheduler = BackgroundScheduler(timezone="Europe/Istanbul")
        scheduler.add_job(calculate_daily_profit, 'cron', hour=4, minute=0)
        scheduler.start()
        logger.info("Kâr analizi zamanlayıcısı başlatıldı.")
    except Exception as e:
        logger.error(f"Zamanlayıcı başlatma hatası: {str(e)}")

def get_product_costs_from_db():
    """
    Tüm ürün maliyetlerini veritabanından veya önbellekten al
    """
    cache_key = "product_costs"
    cached_data = None

    # Redis bağlantısını güvenli şekilde dene
    try:
        from cache_config import redis_active
        if redis_active:
            cached_data = redis_client.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
    except Exception as e:
        logger.warning(f"Redis önbellek erişim hatası: {str(e)}")
        # Redis hatasında doğrudan veritabanından devam et

    # Redis'ten veri alınamadıysa veritabanından al
    try:
        product_costs = ProductCost.query.all()
        cost_dict = {str(pc.barcode): float(pc.cost_price) for pc in product_costs if pc.cost_price}

        # Redis'e kaydet (eğer aktifse)
        try:
            from cache_config import redis_active
            if redis_active:
                redis_client.setex(cache_key, 3600, json.dumps(cost_dict)) # 1 saatlik cache süresi
        except Exception as e:
            logger.warning(f"Redis önbelleğe kaydetme hatası: {str(e)}")

        return cost_dict
    except Exception as e:
        logger.error(f"Veritabanından ürün maliyetlerini alma hatası: {str(e)}")
        return {}