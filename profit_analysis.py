
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from sqlalchemy import func, and_, or_, desc, text
from models import db, Product, Order, SiparisFisi
from datetime import datetime, timedelta
import logging
import json

# Loglama ayarları
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.FileHandler('profit_analysis.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

profit_analysis_bp = Blueprint('profit_analysis', __name__)

@profit_analysis_bp.route('/kar-analizi')
def profit_analysis_page():
    """
    Kar analizi ana sayfasını render eder
    """
    return render_template('profit_analysis.html')

@profit_analysis_bp.route('/api/kar-verileri', methods=['GET'])
def get_profit_data():
    """
    Belirtilen tarih aralığında kar analizini döner (API endpoint)
    """
    logger.info("Kar verileri API'si çağrıldı.")
    try:
        # Tarih aralığını al
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        filter_type = request.args.get('filter_type', 'all')  # all, product, category
        
        # Varsayılan olarak son 30 gün
        now = datetime.now()
        if start_date_str and end_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
                end_date = end_date.replace(hour=23, minute=59, second=59)  # Günün sonuna ayarla
            except ValueError:
                return jsonify({'success': False, 'error': 'Tarih formatı geçersiz. YYYY-MM-DD formatını kullanın.'})
        else:
            start_date = now - timedelta(days=30)
            end_date = now
        
        logger.info(f"Kar analizi tarih aralığı: {start_date} - {end_date}")
        
        # Siparişleri tarih aralığına göre filtrele
        orders_query = Order.query.filter(
            Order.order_date.between(start_date, end_date),
            Order.status != 'Cancelled'
        )
        
        # Sipariş bilgilerini al
        orders = orders_query.all()
        
        # Ürün bazlı maliyet ve kar hesaplama
        product_profits = []
        total_revenue = 0
        total_cost = 0
        total_profit = 0
        total_profit_margin = 0
        
        # Barkod - maliyet eşleştirmesi için SiparisFisi tablosundan verileri çek
        product_costs = {}
        siparis_fisiler = SiparisFisi.query.all()
        
        for fis in siparis_fisiler:
            # Tüm barkod alanlarını kontrol et
            for size in range(35, 42):
                barkod_key = f'barkod_{size}'
                if hasattr(fis, barkod_key) and getattr(fis, barkod_key):
                    barcode = getattr(fis, barkod_key)
                    if barcode:
                        # Birim maliyeti hesapla (toplam fiyat / toplam adet)
                        if fis.toplam_adet > 0:
                            birim_maliyet = fis.cift_basi_fiyat if fis.cift_basi_fiyat else (fis.toplam_fiyat / fis.toplam_adet if fis.toplam_fiyat else 0)
                            product_costs[barcode] = birim_maliyet
        
        # Tüm siparişleri analiz et
        for order in orders:
            barcode = order.product_barcode
            
            # Satış verileri
            sale_price = order.amount if order.amount else 0
            quantity = order.quantity if order.quantity else 1
            
            # Ürün maliyeti
            cost_price = product_costs.get(barcode, 0)
            
            if cost_price == 0:
                # Eğer maliyet bilgisi yoksa, Product tablosundan list_price'ı kullan
                product = Product.query.filter_by(barcode=barcode).first()
                if product:
                    # Liste fiyatının %60'ını maliyet olarak varsay (örnek)
                    cost_price = product.list_price * 0.6 if product.list_price else 0
            
            # Kar hesaplama
            total_sale = sale_price * quantity
            total_cost_this_order = cost_price * quantity
            profit = total_sale - total_cost_this_order
            profit_margin = (profit / total_sale * 100) if total_sale > 0 else 0
            
            # Toplamları güncelle
            total_revenue += total_sale
            total_cost += total_cost_this_order
            total_profit += profit
            
            # Bu siparişi product_profits listesine ekle
            product_profits.append({
                'order_number': order.order_number,
                'order_date': order.order_date.strftime('%Y-%m-%d') if order.order_date else None,
                'product_barcode': barcode,
                'product_name': order.product_name,
                'product_model': order.product_model_code,
                'size': order.product_size,
                'color': order.product_color,
                'quantity': quantity,
                'sale_price': sale_price,
                'cost_price': cost_price,
                'total_sale': total_sale,
                'total_cost': total_cost_this_order,
                'profit': profit,
                'profit_margin': profit_margin
            })
        
        # Genel kar marjı hesapla
        overall_profit_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0
        
        # Ürün modellerine göre gruplanmış kar analizi
        model_profits = {}
        for item in product_profits:
            product_model = item['product_model'] or 'Belirsiz Model'
            if product_model not in model_profits:
                model_profits[product_model] = {
                    'model_code': product_model,
                    'total_sale': 0,
                    'total_cost': 0,
                    'total_profit': 0,
                    'total_quantity': 0,
                    'profit_margin': 0,
                    'count': 0
                }
            
            model_profits[product_model]['total_sale'] += item['total_sale']
            model_profits[product_model]['total_cost'] += item['total_cost']
            model_profits[product_model]['total_profit'] += item['profit']
            model_profits[product_model]['total_quantity'] += item['quantity']
            model_profits[product_model]['count'] += 1
        
        # Profit margin hesapla
        for model in model_profits:
            if model_profits[model]['total_sale'] > 0:
                model_profits[model]['profit_margin'] = (model_profits[model]['total_profit'] / model_profits[model]['total_sale'] * 100)
        
        # Listeye çevir ve sırala
        model_profits_list = list(model_profits.values())
        model_profits_list.sort(key=lambda x: x['total_profit'], reverse=True)
        
        # Renklere göre kar analizi
        color_profits = {}
        for item in product_profits:
            color = item['color'] or 'Belirsiz Renk'
            if color not in color_profits:
                color_profits[color] = {
                    'color': color,
                    'total_sale': 0,
                    'total_cost': 0,
                    'total_profit': 0,
                    'total_quantity': 0,
                    'profit_margin': 0,
                    'count': 0
                }
            
            color_profits[color]['total_sale'] += item['total_sale']
            color_profits[color]['total_cost'] += item['total_cost']
            color_profits[color]['total_profit'] += item['profit']
            color_profits[color]['total_quantity'] += item['quantity']
            color_profits[color]['count'] += 1
        
        # Profit margin hesapla
        for color in color_profits:
            if color_profits[color]['total_sale'] > 0:
                color_profits[color]['profit_margin'] = (color_profits[color]['total_profit'] / color_profits[color]['total_sale'] * 100)
        
        # Listeye çevir ve sırala
        color_profits_list = list(color_profits.values())
        color_profits_list.sort(key=lambda x: x['total_profit'], reverse=True)
        
        # Bodenlere göre kar analizi
        size_profits = {}
        for item in product_profits:
            size = item['size'] or 'Belirsiz Beden'
            if size not in size_profits:
                size_profits[size] = {
                    'size': size,
                    'total_sale': 0,
                    'total_cost': 0,
                    'total_profit': 0,
                    'total_quantity': 0,
                    'profit_margin': 0,
                    'count': 0
                }
            
            size_profits[size]['total_sale'] += item['total_sale']
            size_profits[size]['total_cost'] += item['total_cost']
            size_profits[size]['total_profit'] += item['profit']
            size_profits[size]['total_quantity'] += item['quantity']
            size_profits[size]['count'] += 1
        
        # Profit margin hesapla
        for size in size_profits:
            if size_profits[size]['total_sale'] > 0:
                size_profits[size]['profit_margin'] = (size_profits[size]['total_profit'] / size_profits[size]['total_sale'] * 100)
        
        # Listeye çevir ve sırala
        size_profits_list = list(size_profits.values())
        size_profits_list.sort(key=lambda x: x['total_profit'], reverse=True)
        
        # Günlük kar analizi
        daily_profits = {}
        for item in product_profits:
            date_str = item['order_date']
            if not date_str:
                continue
                
            if date_str not in daily_profits:
                daily_profits[date_str] = {
                    'date': date_str,
                    'total_sale': 0,
                    'total_cost': 0,
                    'total_profit': 0,
                    'order_count': 0,
                    'profit_margin': 0
                }
            
            daily_profits[date_str]['total_sale'] += item['total_sale']
            daily_profits[date_str]['total_cost'] += item['total_cost']
            daily_profits[date_str]['total_profit'] += item['profit']
            daily_profits[date_str]['order_count'] += 1
        
        # Profit margin hesapla
        for date_str in daily_profits:
            if daily_profits[date_str]['total_sale'] > 0:
                daily_profits[date_str]['profit_margin'] = (daily_profits[date_str]['total_profit'] / daily_profits[date_str]['total_sale'] * 100)
        
        # Listeye çevir ve tarihe göre sırala
        daily_profits_list = list(daily_profits.values())
        daily_profits_list.sort(key=lambda x: x['date'], reverse=True)
        
        response = {
            'success': True,
            'summary': {
                'total_revenue': round(total_revenue, 2),
                'total_cost': round(total_cost, 2),
                'total_profit': round(total_profit, 2),
                'overall_profit_margin': round(overall_profit_margin, 2),
                'order_count': len(orders),
                'date_range': {
                    'start_date': start_date.strftime('%Y-%m-%d'),
                    'end_date': end_date.strftime('%Y-%m-%d')
                }
            },
            'product_profits': product_profits,
            'model_profits': model_profits_list,
            'color_profits': color_profits_list,
            'size_profits': size_profits_list,
            'daily_profits': daily_profits_list
        }
        
        return jsonify(response)
    
    except Exception as e:
        logger.exception(f"Kar analizi API hatası: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@profit_analysis_bp.route('/api/kar-ozet')
def get_profit_summary():
    """
    Genel kar özeti bilgilerini döner
    """
    try:
        # Son 1 ay, 3 ay, 6 ay ve 1 yıl için kar özetleri
        now = datetime.now()
        
        periods = {
            'last_month': now - timedelta(days=30),
            'last_3_months': now - timedelta(days=90),
            'last_6_months': now - timedelta(days=180),
            'last_year': now - timedelta(days=365)
        }
        
        summaries = {}
        
        for period_name, start_date in periods.items():
            orders = Order.query.filter(
                Order.order_date.between(start_date, now),
                Order.status != 'Cancelled'
            ).all()
            
            total_revenue = 0
            total_cost = 0
            total_profit = 0
            
            # Barkod - maliyet eşleştirmesi
            product_costs = {}
            siparis_fisiler = SiparisFisi.query.all()
            
            for fis in siparis_fisiler:
                for size in range(35, 42):
                    barkod_key = f'barkod_{size}'
                    if hasattr(fis, barkod_key) and getattr(fis, barkod_key):
                        barcode = getattr(fis, barkod_key)
                        if barcode:
                            if fis.toplam_adet > 0:
                                birim_maliyet = fis.cift_basi_fiyat if fis.cift_basi_fiyat else (fis.toplam_fiyat / fis.toplam_adet if fis.toplam_fiyat else 0)
                                product_costs[barcode] = birim_maliyet
            
            for order in orders:
                barcode = order.product_barcode
                
                sale_price = order.amount if order.amount else 0
                quantity = order.quantity if order.quantity else 1
                
                cost_price = product_costs.get(barcode, 0)
                
                if cost_price == 0:
                    product = Product.query.filter_by(barcode=barcode).first()
                    if product:
                        cost_price = product.list_price * 0.6 if product.list_price else 0
                
                total_sale = sale_price * quantity
                total_cost_this_order = cost_price * quantity
                profit = total_sale - total_cost_this_order
                
                total_revenue += total_sale
                total_cost += total_cost_this_order
                total_profit += profit
            
            overall_profit_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0
            
            summaries[period_name] = {
                'total_revenue': round(total_revenue, 2),
                'total_cost': round(total_cost, 2),
                'total_profit': round(total_profit, 2),
                'profit_margin': round(overall_profit_margin, 2),
                'order_count': len(orders)
            }
        
        return jsonify({
            'success': True,
            'summaries': summaries
        })
    
    except Exception as e:
        logger.exception(f"Kar özeti API hatası: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@profit_analysis_bp.route('/api/en-karli-urunler')
def get_most_profitable_products():
    """
    En karlı ürünleri döner (son 6 ay için)
    """
    try:
        now = datetime.now()
        start_date = now - timedelta(days=180)  # Son 6 ay
        
        orders = Order.query.filter(
            Order.order_date.between(start_date, now),
            Order.status != 'Cancelled'
        ).all()
        
        product_profits = {}
        
        # Barkod - maliyet eşleştirmesi
        product_costs = {}
        siparis_fisiler = SiparisFisi.query.all()
        
        for fis in siparis_fisiler:
            for size in range(35, 42):
                barkod_key = f'barkod_{size}'
                if hasattr(fis, barkod_key) and getattr(fis, barkod_key):
                    barcode = getattr(fis, barkod_key)
                    if barcode:
                        if fis.toplam_adet > 0:
                            birim_maliyet = fis.cift_basi_fiyat if fis.cift_basi_fiyat else (fis.toplam_fiyat / fis.toplam_adet if fis.toplam_fiyat else 0)
                            product_costs[barcode] = birim_maliyet
        
        for order in orders:
            barcode = order.product_barcode
            if not barcode:
                continue
                
            product_name = order.product_name or f"Ürün ({barcode})"
            product_key = f"{barcode}_{product_name}"
            
            if product_key not in product_profits:
                product_profits[product_key] = {
                    'barcode': barcode,
                    'product_name': product_name,
                    'product_model': order.product_model_code,
                    'color': order.product_color,
                    'total_sale': 0,
                    'total_cost': 0,
                    'total_profit': 0,
                    'quantity': 0,
                    'profit_margin': 0,
                    'orders': 0
                }
            
            sale_price = order.amount if order.amount else 0
            quantity = order.quantity if order.quantity else 1
            
            cost_price = product_costs.get(barcode, 0)
            
            if cost_price == 0:
                product = Product.query.filter_by(barcode=barcode).first()
                if product:
                    cost_price = product.list_price * 0.6 if product.list_price else 0
            
            total_sale = sale_price * quantity
            total_cost_this_order = cost_price * quantity
            profit = total_sale - total_cost_this_order
            
            product_profits[product_key]['total_sale'] += total_sale
            product_profits[product_key]['total_cost'] += total_cost_this_order
            product_profits[product_key]['total_profit'] += profit
            product_profits[product_key]['quantity'] += quantity
            product_profits[product_key]['orders'] += 1
        
        # Profit margin hesapla
        for key in product_profits:
            if product_profits[key]['total_sale'] > 0:
                product_profits[key]['profit_margin'] = (product_profits[key]['total_profit'] / product_profits[key]['total_sale'] * 100)
        
        # Listeye çevir, en karlıdan en az karlıya sırala ve en karlı 20 ürünü al
        products_list = list(product_profits.values())
        products_list.sort(key=lambda x: x['total_profit'], reverse=True)
        top_profitable = products_list[:20] if len(products_list) > 20 else products_list
        
        return jsonify({
            'success': True,
            'products': top_profitable
        })
    
    except Exception as e:
        logger.exception(f"En karlı ürünler API hatası: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        })
