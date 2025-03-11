
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from sqlalchemy import func, and_, or_, desc, text
from models import db, Product, Order, SiparisFisi
from datetime import datetime, timedelta
import logging
import json
from cache_config import redis_client, cache_result, clear_cache_pattern

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

@profit_analysis_bp.route('/otomatik-kar-hesaplama')
def otomatik_kar_hesaplama():
    """
    Otomatik Kar Hesaplama sayfasını render eder
    """
    return render_template('otomatik_kar_hesaplama.html')

@profit_analysis_bp.route('/api/kar-verileri')
@cache_result(expiration=1800)  # 30 dakika önbellek
def get_profit_data():
    """
    Belirtilen tarih aralığında kar analizini döner (API endpoint)
    """
    try:
        # Tarih aralığını al
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        filter_type = request.args.get('filter_type', 'all')  # all, product, category

        # Önbellek anahtarı oluştur
        cache_key = f"profit_data:{start_date_str}:{end_date_str}:{filter_type}"
        cached_data = redis_client.get(cache_key)
        
        if cached_data:
            logger.info(f"Önbellekten kar verileri alındı: {cache_key}")
            return json.loads(cached_data)

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
        product_costs = get_product_costs_from_db()

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

        # Veriyi önbelleğe kaydet (30 dakika için)
        redis_client.setex(cache_key, 1800, json.dumps(response, default=str))
        logger.info(f"Kar verileri önbelleğe kaydedildi: {cache_key}")

        return jsonify(response)

    except Exception as e:
        logger.exception(f"Kar analizi API hatası: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

def get_product_costs_from_db():
    """
    Ürün maliyet bilgilerini veritabanından çeker ve önbelleğe alır
    """
    cache_key = "product_costs"
    cached_data = redis_client.get(cache_key)
    
    if cached_data:
        return json.loads(cached_data)
    
    # Veritabanından maliyet bilgilerini çek
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
    
    # Önbelleğe kaydet (1 gün için)
    redis_client.setex(cache_key, 86400, json.dumps(product_costs))
    
    return product_costs

@profit_analysis_bp.route('/api/kar-ozet')
@cache_result(expiration=3600)  # 1 saat önbellek
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
        product_costs = get_product_costs_from_db()

        for period_name, start_date in periods.items():
            # Önbellek anahtarı oluştur
            cache_key = f"profit_summary:{period_name}"
            cached_data = redis_client.get(cache_key)
            
            if cached_data:
                summaries[period_name] = json.loads(cached_data)
                continue
                
            orders = Order.query.filter(
                Order.order_date.between(start_date, now),
                Order.status != 'Cancelled'
            ).all()

            total_revenue = 0
            total_cost = 0
            total_profit = 0

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

            period_summary = {
                'total_revenue': round(total_revenue, 2),
                'total_cost': round(total_cost, 2),
                'total_profit': round(total_profit, 2),
                'profit_margin': round(overall_profit_margin, 2),
                'order_count': len(orders)
            }
            
            # Periyot özetini önbelleğe kaydet (6 saat için)
            redis_client.setex(cache_key, 21600, json.dumps(period_summary))
            
            summaries[period_name] = period_summary

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
@cache_result(expiration=3600)  # 1 saat önbellek
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
        product_costs = get_product_costs_from_db()

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

# Yeni eklenen otomatik kâr maliyet hesaplama fonksiyonları
@profit_analysis_bp.route('/api/urun-kar-hesapla', methods=['POST'])
def calculate_product_profit():
    """
    Barkod numarası verilen ürünün kâr bilgilerini hesaplar
    """
    try:
        data = request.json
        barcode = data.get('barcode')
        
        if not barcode:
            return jsonify({
                'success': False,
                'error': 'Barkod numarası gereklidir'
            })
            
        # Ürün bilgilerini veritabanından çek
        product = Product.query.filter_by(barcode=barcode).first()
        if not product:
            return jsonify({
                'success': False,
                'error': 'Ürün bulunamadı'
            })
            
        # Maliyet bilgisini bul
        product_costs = get_product_costs_from_db()
        cost_price = product_costs.get(barcode, 0)
        
        if cost_price == 0:
            # Eğer özel maliyet bilgisi yoksa liste fiyatının %60'ını kullan
            cost_price = product.list_price * 0.6 if product.list_price else 0
            
        # Satış fiyatı
        sale_price = product.sale_price if product.sale_price else 0
        
        # Varsayılan komisyon oranı
        commission_rate = 25  # %25
        
        # Komisyon tutarı
        commission_amount = (sale_price * commission_rate) / 100
        
        # Kâr hesaplama
        profit = sale_price - cost_price - commission_amount
        profit_margin = (profit / sale_price * 100) if sale_price > 0 else 0
        
        # Son 30 gündeki satış verileri
        now = datetime.now()
        start_date = now - timedelta(days=30)
        
        sales_data = Order.query.filter(
            Order.product_barcode == barcode,
            Order.order_date.between(start_date, now),
            Order.status != 'Cancelled'
        ).all()
        
        total_sales = len(sales_data)
        total_quantity = sum(order.quantity if order.quantity else 1 for order in sales_data)
        total_revenue = sum(order.amount * (order.quantity if order.quantity else 1) for order in sales_data if order.amount)
        
        return jsonify({
            'success': True,
            'product': {
                'barcode': barcode,
                'product_name': product.title,
                'color': product.color,
                'size': product.size,
                'cost_price': round(cost_price, 2),
                'sale_price': round(sale_price, 2),
                'commission': {
                    'rate': commission_rate,
                    'amount': round(commission_amount, 2)
                },
                'profit': round(profit, 2),
                'profit_margin': round(profit_margin, 2),
                'is_profitable': profit > 0,
                'inventory': product.quantity,
                'sales_last_30_days': {
                    'order_count': total_sales,
                    'quantity_sold': total_quantity,
                    'total_revenue': round(total_revenue, 2)
                }
            }
        })
        
    except Exception as e:
        logger.exception(f"Ürün kâr hesaplama hatası: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@profit_analysis_bp.route('/api/karlilik-optimizasyonu')
@cache_result(expiration=7200)  # 2 saat önbellek
def get_profit_optimization_suggestions():
    """
    Karlılığı artırmak için optimizasyon önerileri sunar
    """
    try:
        # Son 90 gündeki sipariş verilerini al
        now = datetime.now()
        start_date = now - timedelta(days=90)
        
        orders = Order.query.filter(
            Order.order_date.between(start_date, now),
            Order.status != 'Cancelled'
        ).all()
        
        # Ürün maliyetlerini al
        product_costs = get_product_costs_from_db()
        
        # Ürünleri analiz et
        product_analysis = {}
        
        for order in orders:
            barcode = order.product_barcode
            if not barcode:
                continue
                
            if barcode not in product_analysis:
                # Ürün bilgilerini al
                product = Product.query.filter_by(barcode=barcode).first()
                
                if not product:
                    continue
                    
                product_analysis[barcode] = {
                    'barcode': barcode,
                    'product_name': product.title if product else order.product_name or f"Ürün ({barcode})",
                    'color': product.color if product else order.product_color or 'Bilinmiyor',
                    'size': product.size if product else order.product_size or 'Bilinmiyor',
                    'sale_price': product.sale_price if product else 0,
                    'cost_price': product_costs.get(barcode, 0),
                    'order_count': 0,
                    'total_quantity': 0,
                    'total_revenue': 0,
                    'total_cost': 0,
                    'total_profit': 0,
                    'profit_margin': 0,
                    'stock_quantity': product.quantity if product else 0,
                    'last_order_date': None
                }
                
                # Eğer maliyet bilgisi yoksa tahmin et
                if product_analysis[barcode]['cost_price'] == 0 and product:
                    product_analysis[barcode]['cost_price'] = product.list_price * 0.6 if product.list_price else 0
            
            # Sipariş detaylarını ekle
            sale_price = order.amount if order.amount else 0
            quantity = order.quantity if order.quantity else 1
            cost_price = product_analysis[barcode]['cost_price']
            
            total_sale = sale_price * quantity
            total_cost = cost_price * quantity
            profit = total_sale - total_cost
            
            product_analysis[barcode]['order_count'] += 1
            product_analysis[barcode]['total_quantity'] += quantity
            product_analysis[barcode]['total_revenue'] += total_sale
            product_analysis[barcode]['total_cost'] += total_cost
            product_analysis[barcode]['total_profit'] += profit
            
            # Son sipariş tarihini güncelle
            if order.order_date:
                if not product_analysis[barcode]['last_order_date'] or order.order_date > product_analysis[barcode]['last_order_date']:
                    product_analysis[barcode]['last_order_date'] = order.order_date
        
        # Kâr marjı hesapla
        for barcode in product_analysis:
            if product_analysis[barcode]['total_revenue'] > 0:
                product_analysis[barcode]['profit_margin'] = (product_analysis[barcode]['total_profit'] / product_analysis[barcode]['total_revenue'] * 100)
        
        # Önerileri oluştur
        low_margin_products = []
        high_margin_products = []
        slow_moving_products = []
        fast_moving_products = []
        stock_issues = []
        
        # Tüm ürünleri analiz et
        products_list = list(product_analysis.values())
        
        for product in products_list:
            # Düşük kâr marjlı ürünler
            if product['profit_margin'] < 10 and product['order_count'] > 5:
                low_margin_products.append({
                    'barcode': product['barcode'],
                    'product_name': product['product_name'],
                    'color': product['color'],
                    'size': product['size'],
                    'profit_margin': round(product['profit_margin'], 2),
                    'sale_price': round(product['sale_price'], 2),
                    'cost_price': round(product['cost_price'], 2),
                    'suggested_price': round(product['cost_price'] * 1.5, 2),  # %50 kâr marjı için önerilen fiyat
                    'order_count': product['order_count']
                })
            
            # Yüksek kâr marjlı ürünler
            if product['profit_margin'] > 40 and product['order_count'] > 5:
                high_margin_products.append({
                    'barcode': product['barcode'],
                    'product_name': product['product_name'],
                    'color': product['color'],
                    'size': product['size'],
                    'profit_margin': round(product['profit_margin'], 2),
                    'sale_price': round(product['sale_price'], 2),
                    'cost_price': round(product['cost_price'], 2),
                    'order_count': product['order_count']
                })
            
            # Yavaş hareket eden ürünler (son 30 günde sipariş yoksa)
            if product['last_order_date'] and (now - product['last_order_date']).days > 30 and product['stock_quantity'] > 3:
                slow_moving_products.append({
                    'barcode': product['barcode'],
                    'product_name': product['product_name'],
                    'color': product['color'],
                    'size': product['size'],
                    'days_since_last_order': (now - product['last_order_date']).days,
                    'stock_quantity': product['stock_quantity'],
                    'suggested_action': 'İndirim yapın veya öne çıkarın',
                    'current_price': round(product['sale_price'], 2),
                    'suggested_price': round(product['sale_price'] * 0.8, 2)  # %20 indirim önerisi
                })
            
            # Hızlı hareket eden ürünler (son 7 günde 5+ sipariş)
            if product['last_order_date'] and (now - product['last_order_date']).days <= 7 and product['order_count'] > 5:
                fast_moving_products.append({
                    'barcode': product['barcode'],
                    'product_name': product['product_name'],
                    'color': product['color'],
                    'size': product['size'],
                    'order_count': product['order_count'],
                    'stock_quantity': product['stock_quantity']
                })
            
            # Stok sorunları (yüksek talep, düşük stok)
            if product['order_count'] > 10 and product['stock_quantity'] < 3:
                stock_issues.append({
                    'barcode': product['barcode'],
                    'product_name': product['product_name'],
                    'color': product['color'],
                    'size': product['size'],
                    'order_count': product['order_count'],
                    'current_stock': product['stock_quantity'],
                    'suggested_action': 'Stok takviyesi yapın'
                })
        
        # En iyi 10 ürünü seç
        low_margin_products = sorted(low_margin_products, key=lambda x: x['profit_margin'])[:10]
        high_margin_products = sorted(high_margin_products, key=lambda x: x['profit_margin'], reverse=True)[:10]
        slow_moving_products = sorted(slow_moving_products, key=lambda x: x['days_since_last_order'], reverse=True)[:10]
        fast_moving_products = sorted(fast_moving_products, key=lambda x: x['order_count'], reverse=True)[:10]
        stock_issues = sorted(stock_issues, key=lambda x: x['order_count'], reverse=True)[:10]
        
        return jsonify({
            'success': True,
            'optimization_suggestions': {
                'low_margin_products': low_margin_products,
                'high_margin_products': high_margin_products,
                'slow_moving_products': slow_moving_products,
                'fast_moving_products': fast_moving_products,
                'stock_issues': stock_issues
            }
        })
    
    except Exception as e:
        logger.exception(f"Karlılık optimizasyonu önerileri hatası: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@profit_analysis_bp.route('/api/tahmini-kar-hesapla', methods=['POST'])
def calculate_estimated_profit():
    """
    Girilen değerlere göre tahmini kâr ve komisyon hesaplar
    """
    try:
        data = request.json
        
        # Gerekli verileri al
        cost_price = float(data.get('cost_price', 0))
        sale_price = float(data.get('sale_price', 0))
        commission_rate = float(data.get('commission_rate', 25))  # Varsayılan %25
        quantity = int(data.get('quantity', 1))
        
        if sale_price <= 0:
            return jsonify({
                'success': False,
                'error': 'Satış fiyatı sıfırdan büyük olmalıdır'
            })
            
        # Komisyon tutarı
        commission_amount = (sale_price * commission_rate) / 100
        
        # Birim kâr
        unit_profit = sale_price - cost_price - commission_amount
        
        # Toplam değerler
        total_cost = cost_price * quantity
        total_sale = sale_price * quantity
        total_commission = commission_amount * quantity
        total_profit = unit_profit * quantity
        
        # Kâr marjı
        profit_margin = (unit_profit / sale_price * 100) if sale_price > 0 else 0
        
        # Maliyetin satış fiyatına oranı
        cost_price_ratio = (cost_price / sale_price * 100) if sale_price > 0 else 0
        
        # Geri dönüş değeri
        result = {
            'success': True,
            'calculation': {
                'inputs': {
                    'cost_price': cost_price,
                    'sale_price': sale_price,
                    'commission_rate': commission_rate,
                    'quantity': quantity
                },
                'unit_values': {
                    'cost_price': round(cost_price, 2),
                    'sale_price': round(sale_price, 2),
                    'commission_amount': round(commission_amount, 2),
                    'profit': round(unit_profit, 2)
                },
                'total_values': {
                    'total_cost': round(total_cost, 2),
                    'total_sale': round(total_sale, 2),
                    'total_commission': round(total_commission, 2),
                    'total_profit': round(total_profit, 2)
                },
                'metrics': {
                    'profit_margin': round(profit_margin, 2),
                    'cost_price_ratio': round(cost_price_ratio, 2),
                    'commission_ratio': round(commission_rate, 2),
                    'is_profitable': unit_profit > 0
                }
            }
        }
        
        # Kârlılık durumuna göre öneriler
        if unit_profit <= 0:
            result['calculation']['suggestions'] = [
                "Bu ürün zarar ettiriyor. Satış fiyatını artırmayı veya maliyeti düşürmeyi düşünün.",
                f"Kâr elde etmek için minimum satış fiyatı: {round((cost_price + (cost_price * 0.35)), 2)} TL olmalıdır."
            ]
        elif profit_margin < 15:
            result['calculation']['suggestions'] = [
                "Kâr marjı düşük. Fiyat artışı düşünülebilir.",
                f"Daha iyi kâr marjı için önerilen satış fiyatı: {round((cost_price / 0.65), 2)} TL"
            ]
        elif profit_margin > 40:
            result['calculation']['suggestions'] = [
                "Kâr marjı çok iyi. Daha fazla ürün satmak için küçük indirimler yapılabilir.",
                "Bu ürüne benzer ürünlerin stok miktarını artırmak faydalı olabilir."
            ]
        else:
            result['calculation']['suggestions'] = [
                "Kâr marjı makul seviyelerde. Mevcut fiyat politikası sürdürülebilir.",
                "Satış hacmini artırmak için pazarlama faaliyetlerine odaklanabilirsiniz."
            ]
            
        return jsonify(result)
        
    except Exception as e:
        logger.exception(f"Tahmini kâr hesaplama hatası: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@profit_analysis_bp.route('/api/optimal-fiyat-hesapla', methods=['POST'])
def calculate_optimal_price():
    """
    İstenen kâr marjına göre optimal satış fiyatını hesaplar
    """
    try:
        data = request.json
        
        # Gerekli verileri al
        cost_price = float(data.get('cost_price', 0))
        target_margin = float(data.get('target_margin', 25))  # Hedeflenen kâr marjı
        commission_rate = float(data.get('commission_rate', 25))  # Platform komisyon oranı
        
        if cost_price <= 0:
            return jsonify({
                'success': False,
                'error': 'Maliyet fiyatı sıfırdan büyük olmalıdır'
            })
            
        if target_margin >= 100 or target_margin <= 0:
            return jsonify({
                'success': False,
                'error': 'Hedef kâr marjı 0-100 arasında olmalıdır'
            })
            
        # Optimal fiyat hesaplaması
        # Formül: sale_price = cost_price / (1 - (commission_rate / 100) - (target_margin / 100))
        optimal_price = cost_price / (1 - (commission_rate / 100) - (target_margin / 100))
        
        # Farklı kâr marjları için fiyat seçenekleri
        price_options = []
        for margin in [10, 15, 20, 25, 30, 35, 40, 45, 50]:
            price = cost_price / (1 - (commission_rate / 100) - (margin / 100))
            
            # Kâr hesabı
            commission_amount = (price * commission_rate) / 100
            profit = price - cost_price - commission_amount
            
            price_options.append({
                'margin': margin,
                'price': round(price, 2),
                'profit': round(profit, 2)
            })
        
        # Geri dönüş değeri
        return jsonify({
            'success': True,
            'optimal_price': {
                'cost_price': cost_price,
                'target_margin': target_margin,
                'commission_rate': commission_rate,
                'optimal_price': round(optimal_price, 2),
                'estimated_profit': round(optimal_price - cost_price - (optimal_price * commission_rate / 100), 2),
                'price_options': price_options
            }
        })
        
    except Exception as e:
        logger.exception(f"Optimal fiyat hesaplama hatası: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@profit_analysis_bp.route('/api/toplu-fiyat-analizi', methods=['POST'])
def bulk_price_analysis():
    """
    Toplu olarak ürünlerin fiyat ve kâr analizi
    """
    try:
        data = request.json
        barcodes = data.get('barcodes', [])
        
        if not barcodes:
            return jsonify({
                'success': False,
                'error': 'En az bir barkod numarası gereklidir'
            })
            
        # Ürün maliyetlerini al
        product_costs = get_product_costs_from_db()
        
        # Sonuçları saklamak için liste
        results = []
        
        for barcode in barcodes:
            # Ürün bilgilerini al
            product = Product.query.filter_by(barcode=barcode).first()
            
            if not product:
                results.append({
                    'barcode': barcode,
                    'status': 'error',
                    'message': 'Ürün bulunamadı'
                })
                continue
                
            # Maliyet bilgisi
            cost_price = product_costs.get(barcode, 0)
            
            if cost_price == 0:
                # Eğer özel maliyet bilgisi yoksa liste fiyatının %60'ını kullan
                cost_price = product.list_price * 0.6 if product.list_price else 0
                
            # Satış fiyatı
            sale_price = product.sale_price if product.sale_price else 0
            
            if sale_price <= 0:
                results.append({
                    'barcode': barcode,
                    'product_name': product.title,
                    'status': 'error',
                    'message': 'Geçerli satış fiyatı bulunamadı'
                })
                continue
                
            # Komisyon hesabı
            commission_rate = 25  # %25
            commission_amount = (sale_price * commission_rate) / 100
            
            # Kâr hesabı
            profit = sale_price - cost_price - commission_amount
            profit_margin = (profit / sale_price * 100) if sale_price > 0 else 0
            
            # Sonuçları ekle
            results.append({
                'barcode': barcode,
                'product_name': product.title,
                'color': product.color,
                'size': product.size,
                'status': 'success',
                'analysis': {
                    'cost_price': round(cost_price, 2),
                    'sale_price': round(sale_price, 2),
                    'commission_amount': round(commission_amount, 2),
                    'profit': round(profit, 2),
                    'profit_margin': round(profit_margin, 2),
                    'is_profitable': profit > 0
                }
            })
            
        return jsonify({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        logger.exception(f"Toplu fiyat analizi hatası: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@profit_analysis_bp.route('/urun-kar-hesaplayici')
def profit_calculator_page():
    """
    Kâr hesaplayıcı arayüzünü render eder
    """
    return render_template('profit_calculator.html')

@profit_analysis_bp.route('/toplu-kar-analizi')
def bulk_profit_analysis_page():
    """
    Toplu kâr analizi arayüzünü render eder
    """
    return render_template('bulk_profit_analysis.html')

@profit_analysis_bp.route('/kar-optimizasyon')
def profit_optimization_page():
    """
    Kâr optimizasyon önerileri sayfasını render eder
    """
    return render_template('profit_optimization.html')

@profit_analysis_bp.route('/cache/temizle', methods=['POST'])
def clear_cache():
    """
    Kâr analizi önbelleğini temizler
    """
    try:
        # Kâr analizi ile ilgili tüm önbellek girdilerini temizle
        clear_cache_pattern('profit')
        
        return jsonify({
            'success': True,
            'message': 'Önbellek başarıyla temizlendi'
        })
        
    except Exception as e:
        logger.exception(f"Önbellek temizleme hatası: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        })
