
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from models import db, Order, Product
from sqlalchemy import func, desc
import requests
import json
from datetime import datetime, timedelta
import logging

# Loglama ayarları
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.FileHandler('kar_hesaplama.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

kar_hesaplama_bp = Blueprint('kar_hesaplama', __name__)

@kar_hesaplama_bp.route('/kar-hesaplama', methods=['GET'])
def kar_hesaplama():
    """
    Kar hesaplama sayfasını gösterir.
    Tüm siparişlerden ürün model kodlarına göre gruplandırılmış satış verilerini getirir.
    """
    try:
        # Tarih filtreleme için varsayılan değerler (son 30 gün)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        start_date_str = request.args.get('start_date', start_date.strftime('%Y-%m-%d'))
        end_date_str = request.args.get('end_date', end_date.strftime('%Y-%m-%d'))
        
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        except ValueError:
            logger.warning("Geçersiz tarih formatı. Varsayılan 30 günlük aralık kullanılıyor.")
            start_date = datetime.now() - timedelta(days=30)
            end_date = datetime.now()
        
        # Model kodu ile Order ve Product tablolarını birleştirme sorgusu
        # Önce barkodları eşleştirelim, sonra model koduna göre gruplayalım
        model_sales_query = db.session.query(
            Product.product_main_id,
            func.sum(Order.quantity).label('count'),
            func.sum(Order.amount).label('total_amount'),
            func.max(Product.images).label('image_url')
        ).join(
            Order, 
            Product.barcode == Order.product_barcode
        ).filter(
            Order.status != 'Cancelled',
            Order.product_barcode != None,
            Order.product_barcode != '',
            Product.product_main_id != None,
            Product.product_main_id != '',
            Order.order_date >= start_date,
            Order.order_date <= end_date
        ).group_by(
            Product.product_main_id
        ).order_by(
            desc('count')
        )
        
        model_sales = model_sales_query.all()
        
        # Model verilerini oluşturma
        model_data = []
        for model in model_sales:
            model_data.append({
                'model_id': model.product_main_id,
                'count': model.count or 0,
                'total_amount': float(model.total_amount) if model.total_amount else 0,
                'image_url': model.image_url or "",
            })
        
        # İşlem yoksa kullanıcıya bilgi ver
        if not model_data:
            logger.info("Kar hesaplaması için satış verisi bulunamadı.")
            flash("Seçilen tarih aralığında satış verisi bulunamadı.", "warning")
        
        # Güncel döviz kurunu al
        current_rate = get_usd_exchange_rate()
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        return render_template(
            'kar_hesaplama.html',
            model_data=model_data,
            current_rate=current_rate,
            now=now_str,
            start_date=start_date_str,
            end_date=end_date_str
        )
        
    except Exception as e:
        logger.error(f"Kar hesaplama sayfası yüklenirken hata: {e}")
        flash(f"Veriler yüklenirken bir hata oluştu: {str(e)}", "danger")
        return render_template('kar_hesaplama.html', model_data=[], current_rate=0, now=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))


@kar_hesaplama_bp.route('/api/hesapla-kar', methods=['POST'])
def hesapla_kar():
    """
    Girilen maliyetlere göre kar hesaplar
    """
    try:
        data = request.json
        
        model_costs = data.get('model_costs', {})  # model_id: usd_cost şeklinde
        shipping_cost = float(data.get('shipping_cost', 0))
        labor_cost = float(data.get('labor_cost', 0))
        packaging_cost = float(data.get('packaging_cost', 0))
        exchange_rate = float(data.get('exchange_rate', 0))
        
        # Tarih filtreleme için varsayılan değerler (son 30 gün)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        # Maliyet sonuçlarını hesapla
        results = []
        total_revenue = 0
        total_cost = 0
        
        for model_id, cost_usd in model_costs.items():
            # Model koduna göre satış bilgilerini almak için ürün ile sipariş tablolarını birleştir
            sales_query = db.session.query(
                func.sum(Order.quantity).label('count'),
                func.sum(Order.amount).label('total_amount')
            ).join(
                Product, 
                Product.barcode == Order.product_barcode
            ).filter(
                Order.status != 'Cancelled',
                Product.product_main_id == model_id,
                Order.order_date >= start_date,
                Order.order_date <= end_date
            )
            
            sales = sales_query.first()
            
            if not sales or not sales.count:
                continue
                
            count = sales.count or 0
            revenue = float(sales.total_amount) if sales.total_amount else 0
            
            # Maliyeti TL'ye çevir
            cost_usd = float(cost_usd)
            cost_tl = cost_usd * exchange_rate
            
            # Toplam maliyeti hesapla (üretim maliyeti + ortak maliyetler)
            production_cost = cost_tl * count
            common_costs = (shipping_cost + labor_cost + packaging_cost) * count
            total_model_cost = production_cost + common_costs
            
            # Kar ve kar marjı hesaplama
            profit = revenue - total_model_cost
            profit_margin = (profit / revenue) * 100 if revenue > 0 else 0
            
            # Model ile ilgili görsel al
            product = Product.query.filter_by(product_main_id=model_id).first()
            image_url = product.images if product else ""
            
            results.append({
                'model_id': model_id,
                'count': count,
                'profit': profit,
                'profit_margin': profit_margin,
            })
            
            total_revenue += revenue
            total_cost += total_model_cost
        
        # Toplam kar ve kar marjı hesapla
        total_profit = total_revenue - total_cost
        total_profit_margin = (total_profit / total_revenue) * 100 if total_revenue > 0 else 0
        
        # Sonuçları döndür
        return jsonify({
            'success': True,
            'results': results,
            'summary': {
                'total_revenue': total_revenue,
                'total_cost': total_cost,
                'total_profit': total_profit,
                'total_profit_margin': total_profit_margin
            }
        })
    except Exception as e:
        logger.error(f"Kar hesaplanırken hata: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@kar_hesaplama_bp.route('/api/guncel-kur', methods=['GET'])
def get_current_exchange_rate():
    """
    Güncel döviz kurunu döner
    """
    try:
        rate = get_usd_exchange_rate()
        return jsonify({
            'success': True,
            'rate': rate,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
    except Exception as e:
        logger.error(f"Döviz kuru alınırken hata: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def get_usd_exchange_rate():
    """
    Güncel USD/TRY döviz kurunu getirir
    """
    try:
        # Ücretsiz bir döviz kuru API'si kullanılıyor
        response = requests.get('https://api.exchangerate-api.com/v4/latest/USD')
        data = response.json()
        return data['rates']['TRY']
    except Exception as e:
        logger.error(f"Döviz kuru API hatası: {e}")
        # API hatası durumunda varsayılan kur
        return 32.0
