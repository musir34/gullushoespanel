
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from models import db, Order, Product
from sqlalchemy import func, desc
import requests
import json
from datetime import datetime
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
    Kar hesaplama sayfasını gösterir
    """
    # Satış verileri için tüm model kodlarını ve satış bilgilerini getir
    try:
        # Tüm model kodlarını ve bunların satış miktarını sorgula
        model_sales = db.session.query(
            Order.product_main_id,
            func.count(Order.id).label('count'),
            func.sum(Order.amount).label('total_amount')
        ).filter(
            Order.status != 'Cancelled',  # İptal edilmiş siparişleri dışarıda tut
            Order.product_main_id != None,  # Model kodu olmayan siparişleri dışarıda tut
            Order.product_main_id != ''  # Boş model kodlarını dışarıda tut
        ).group_by(
            Order.product_main_id
        ).order_by(
            desc('count')  # En çok satılan modeller önce
        ).all()

        # Modellerin görsel ve diğer bilgilerini al
        model_data = []
        for model in model_sales:
            model_id = model.product_main_id
            
            # Ürün bilgilerini al
            product = Product.query.filter_by(product_main_id=model_id).first()
            image_url = ""
            if product:
                image_url = product.images or ""
            
            # Verileri listeye ekle
            model_data.append({
                'model_id': model_id,
                'count': model.count,
                'total_amount': float(model.total_amount) if model.total_amount else 0,
                'image_url': image_url,
                'unit_cost_usd': 0,  # Varsayılan değer
            })

        # Güncel döviz kurunu al
        current_rate = get_usd_exchange_rate()
        
        return render_template(
            'kar_hesaplama.html',
            model_data=model_data,
            current_rate=current_rate
        )
    except Exception as e:
        logger.error(f"Kar hesaplama sayfası yüklenirken hata: {e}")
        flash(f"Veriler yüklenirken bir hata oluştu: {str(e)}", "danger")
        return render_template('kar_hesaplama.html', model_data=[], current_rate=0)

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
        
        # Maliyet sonuçlarını hesapla
        results = []
        total_revenue = 0
        total_cost = 0
        
        for model_id, cost_usd in model_costs.items():
            # Modele ait satış verilerini sorgula
            sales = db.session.query(
                func.count(Order.id).label('count'),
                func.sum(Order.amount).label('total_amount')
            ).filter(
                Order.status != 'Cancelled',
                Order.product_main_id == model_id
            ).first()
            
            if not sales or not sales.count:
                continue
                
            count = sales.count
            revenue = float(sales.total_amount) if sales.total_amount else 0
            
            # Maliyeti TL'ye çevir
            cost_usd = float(cost_usd)
            cost_tl = cost_usd * exchange_rate
            
            # Diğer maliyetleri ekle
            total_model_cost = (cost_tl * count) + (shipping_cost + labor_cost + packaging_cost) / len(model_costs) * count
            profit = revenue - total_model_cost
            profit_margin = (profit / revenue) * 100 if revenue > 0 else 0
            
            # Ürün bilgilerini al
            product = Product.query.filter_by(product_main_id=model_id).first()
            image_url = product.images if product else ""
            
            results.append({
                'model_id': model_id,
                'count': count,
                'revenue': revenue,
                'cost_tl': cost_tl,
                'total_cost': total_model_cost,
                'profit': profit,
                'profit_margin': profit_margin,
                'image_url': image_url
            })
            
            total_revenue += revenue
            total_cost += total_model_cost
        
        # Toplam kar ve kar marjı hesapla
        total_profit = total_revenue - total_cost
        total_profit_margin = (total_profit / total_revenue) * 100 if total_revenue > 0 else 0
        
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
            'rate': rate
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
        # API hatası durumunda varsayılan kur (güncel değer 32 civarı)
        return 32.0
