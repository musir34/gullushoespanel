from flask import Blueprint, render_template, request, jsonify
from datetime import datetime, timedelta
import logging
import pandas as pd
import json
from collections import defaultdict
from sqlalchemy import func, extract, desc

# Çok tablolu sipariş modelleri; proje yapınıza göre import edin
from models import db, OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled, Product

logging.basicConfig(level=logging.INFO)

profit_bp = Blueprint('profit', __name__, url_prefix='/profit')

def get_quick_date_range(period):
    """Hızlı tarih aralığı filtreleri"""
    today = datetime.now()
    end_date = today
    
    if period == 'today':
        start_date = today.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == 'yesterday':
        yesterday = today - timedelta(days=1)
        start_date = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif period == 'this_week':
        start_date = today - timedelta(days=today.weekday())
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == 'last_week':
        last_week_start = today - timedelta(days=today.weekday() + 7)
        start_date = last_week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = (last_week_start + timedelta(days=6)).replace(hour=23, minute=59, second=59, microsecond=999999)
    elif period == 'this_month':
        start_date = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == 'last_month':
        if today.month == 1:
            start_date = today.replace(year=today.year-1, month=12, day=1, hour=0, minute=0, second=0, microsecond=0)
            end_date = today.replace(year=today.year-1, month=12, day=31, hour=23, minute=59, second=59, microsecond=999999)
        else:
            start_date = today.replace(month=today.month-1, day=1, hour=0, minute=0, second=0, microsecond=0)
            # Son günü hesapla
            if today.month == 3:
                last_day = 28 if today.year % 4 != 0 else 29
            elif today.month in [5, 7, 10, 12]:
                last_day = 30
            else:
                last_day = 31
            end_date = today.replace(month=today.month-1, day=last_day, hour=23, minute=59, second=59, microsecond=999999)
    elif period == 'last_3_months':
        # 3 ay önceki ayın 1. günü
        if today.month <= 3:
            # Yıl değişimi
            months_back = today.month - 1 + 12
            year_diff = (today.month - 1 + 12) // 12
            start_date = today.replace(year=today.year-year_diff, month=months_back%12+1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            start_date = today.replace(month=today.month-3, day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == 'this_year':
        start_date = today.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == 'last_year':
        start_date = today.replace(year=today.year-1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = today.replace(year=today.year-1, month=12, day=31, hour=23, minute=59, second=59, microsecond=999999)
    else:
        # Varsayılan son 30 gün
        start_date = today - timedelta(days=30)
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    
    return start_date, end_date

def calculate_product_cost(order):
    """Ürün maliyetini hesaplar"""
    product_cost = 0.0
    
    if hasattr(order, 'original_product_barcode') and order.original_product_barcode:
        product = Product.query.filter_by(original_product_barcode=order.original_product_barcode).first()
        if product and product.cost_try:
            product_cost = product.cost_try
    elif hasattr(order, 'product_barcode') and order.product_barcode:
        product = Product.query.filter_by(barcode=order.product_barcode).first()
        if product and product.cost_try:
            product_cost = product.cost_try
            
    return product_cost

def get_orders_by_date_range(start_date, end_date, status_filter=None, product_filter=None):
    """Belirli tarih aralığındaki siparişleri getirir"""
    orders = []
    table_classes = [OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled]
    
    for cls in table_classes:
        query = cls.query.filter(cls.order_date.between(start_date, end_date))
        
        if status_filter:
            query = query.filter(cls.status == status_filter)
            
        if product_filter:
            query = query.filter(cls.merchant_sku.like(f"%{product_filter}%"))
            
        found = query.all()
        orders.extend(found)
    
    return orders

def analyze_orders(orders, package_cost, employee_cost, shipping_cost):
    """Siparişlerin kâr-zarar analizini yapar"""
    analysis = []
    
    # Ana toplamlar
    total_profit = 0.0
    total_commission_spent = 0.0
    total_package_spent = 0.0
    total_shipping_spent = 0.0
    total_employee_spent = 0.0
    total_revenue = 0.0
    total_product_spent = 0.0
    
    # Kârlı ve zararlı siparişler
    profitable_orders = []
    unprofitable_orders = []
    
    # Ürün ve durum bazlı detaylı analizler
    product_stats = defaultdict(lambda: {'count': 0, 'revenue': 0, 'cost': 0, 'profit': 0})
    status_stats = defaultdict(lambda: {'count': 0, 'revenue': 0, 'cost': 0, 'profit': 0})
    
    # Her sipariş için hesaplamalar
    for order in orders:
        # Değerleri None ise 0
        amount_val = order.amount or 0
        discount_val = order.discount or 0
        commission_val = order.commission or 0
        
        # Gelir (amount - discount)
        order_revenue = amount_val - discount_val
        total_revenue += order_revenue
        
        # Komisyon toplamı
        total_commission_spent += commission_val
        
        # Ürün maliyeti
        product_cost = calculate_product_cost(order)
        total_product_spent += product_cost
        
        # Toplam giderler
        total_expenses = product_cost + shipping_cost + package_cost + employee_cost + commission_val
        
        # Diğer gider kalemleri toplamları
        total_shipping_spent += shipping_cost
        total_package_spent += package_cost
        total_employee_spent += employee_cost
        
        # Net kâr
        profit = order_revenue - total_expenses
        total_profit += profit
        
        # Kâr durumuna göre listeye ekle
        if profit >= 0:
            profitable_orders.append(order)
        else:
            unprofitable_orders.append(order)
        
        # Ürün bazlı istatistikler
        product_key = order.merchant_sku
        product_stats[product_key]['count'] += 1
        product_stats[product_key]['revenue'] += order_revenue
        product_stats[product_key]['cost'] += total_expenses
        product_stats[product_key]['profit'] += profit
        
        # Durum bazlı istatistikler
        status_key = order.status
        status_stats[status_key]['count'] += 1
        status_stats[status_key]['revenue'] += order_revenue
        status_stats[status_key]['cost'] += total_expenses
        status_stats[status_key]['profit'] += profit
        
        # Analiz listesine ekle
        analysis.append({
            "order_number": order.order_number,
            "order_date": order.order_date,
            "order_table": order.__tablename__,
            "product": order.merchant_sku,
            "product_name": getattr(order, 'product_name', ''),
            "net_income": order_revenue,
            "product_cost": product_cost,
            "shipping_cost": shipping_cost,
            "package_cost": package_cost,
            "employee_cost": employee_cost,
            "commission_cost": commission_val,
            "total_expenses": total_expenses,
            "profit": profit,
            "profit_margin": (profit / order_revenue * 100) if order_revenue > 0 else 0,
            "status": order.status
        })
    
    # Ortalama kâr hesabı
    avg_profit = total_profit / len(analysis) if analysis else 0
    
    # Ürün bazlı en kârlı/zararlı ürünler
    top_profitable_products = sorted(product_stats.items(), key=lambda x: x[1]['profit'], reverse=True)[:5]
    top_unprofitable_products = sorted(product_stats.items(), key=lambda x: x[1]['profit'])[:5]
    
    # Durum bazlı en kârlı/zararlı durumlar
    status_performance = sorted(status_stats.items(), key=lambda x: x[1]['profit'], reverse=True)
    
    results = {
        "analysis": analysis,
        "total_profit": total_profit,
        "avg_profit": avg_profit,
        "total_revenue": total_revenue,
        "total_commission_spent": total_commission_spent,
        "total_package_spent": total_package_spent,
        "total_shipping_spent": total_shipping_spent,
        "total_employee_spent": total_employee_spent,
        "total_product_spent": total_product_spent,
        "profitable_count": len(profitable_orders),
        "unprofitable_count": len(unprofitable_orders),
        "top_profitable_products": dict(top_profitable_products),
        "top_unprofitable_products": dict(top_unprofitable_products),
        "status_performance": dict(status_performance)
    }
    
    return results

@profit_bp.route('/', methods=['GET', 'POST'])
def profit_report():
    """
    start_date, end_date, package_cost, employee_cost, shipping_cost
    parametrelerini POST formdan alarak tüm tablolardaki siparişleri analiz eder.

    - order_number => siparişin ID gösterimi
    - ürün adı => o.merchant_sku
    - Ürün maliyeti (product.cost_try) de gider kalemine eklenir.
    - Kâr = Gelir - (ürün_maliyeti + paket + işçilik + kargo + komisyon)
    """
    results = {
        "analysis": [],
        "total_profit": 0.0,
        "avg_profit": 0.0,
        "total_revenue": 0.0,
        "total_commission_spent": 0.0,
        "total_package_spent": 0.0,
        "total_shipping_spent": 0.0,
        "total_employee_spent": 0.0,
        "total_product_spent": 0.0,
        "profitable_count": 0,
        "unprofitable_count": 0,
        "top_profitable_products": {},
        "top_unprofitable_products": {},
        "status_performance": {}
    }

    if request.method == 'POST':
        # Form parametreleri
        package_cost = float(request.form.get('package_cost', 0) or 0)
        employee_cost = float(request.form.get('employee_cost', 0) or 0)
        shipping_cost = float(request.form.get('shipping_cost', 0) or 0)
        status_filter = request.form.get('status_filter')
        product_filter = request.form.get('product_filter')
        quick_filter = request.form.get('quick_filter')
        
        if quick_filter and quick_filter != 'custom':
            # Hızlı filtre kullanıldı
            start_date, end_date = get_quick_date_range(quick_filter)
            start_date_str = start_date.strftime('%Y-%m-%d')
            end_date_str = end_date.strftime('%Y-%m-%d')
        else:
            # Manuel tarih aralığı
            start_date_str = request.form.get('start_date')
            end_date_str = request.form.get('end_date')
            
            # Tarih dönüşümü
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
                # Bitiş tarihi gün sonuna ayarlanır
                end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
            except:
                logging.error("Tarih formatı uygun değil.")
                return render_template('profit.html', error="Tarih formatı uygun değil.")
        
        logging.info(f"Paket maliyeti: {package_cost}, İşçilik: {employee_cost}, Kargo: {shipping_cost}")
        logging.info(f"Tarih aralığı: {start_date} - {end_date}")
        logging.info(f"Durum filtresi: {status_filter}, Ürün filtresi: {product_filter}")
        
        # Siparişleri çek
        orders = get_orders_by_date_range(start_date, end_date, status_filter, product_filter)
        logging.info(f"Toplam sipariş sayısı: {len(orders)}")
        
        if orders:
            # Siparişleri analiz et
            results = analyze_orders(orders, package_cost, employee_cost, shipping_cost)
            
            # Trend Analizi: Günlük/Haftalık/Aylık kâr trend verileri
            # Siparişleri tarihe göre grupla
            orders_by_date = defaultdict(list)
            for order in orders:
                date_key = order.order_date.strftime('%Y-%m-%d')
                orders_by_date[date_key].append(order)
            
            # Her gün için kâr hesapla
            daily_profits = {}
            for date, day_orders in orders_by_date.items():
                day_results = analyze_orders(day_orders, package_cost, employee_cost, shipping_cost)
                daily_profits[date] = {
                    'profit': day_results['total_profit'],
                    'revenue': day_results['total_revenue'],
                    'order_count': len(day_orders)
                }
            
            results['trend_data'] = daily_profits

    # Sonuçları şablona gönder
    return render_template(
        'profit.html',
        analysis=results['analysis'],
        total_profit=results['total_profit'],
        avg_profit=results['avg_profit'],
        total_revenue=results['total_revenue'],
        total_commission_spent=results['total_commission_spent'],
        total_package_spent=results['total_package_spent'],
        total_shipping_spent=results['total_shipping_spent'],
        total_employee_spent=results['total_employee_spent'],
        total_product_spent=results['total_product_spent'],
        profitable_count=results.get('profitable_count', 0),
        unprofitable_count=results.get('unprofitable_count', 0),
        top_profitable_products=results.get('top_profitable_products', {}),
        top_unprofitable_products=results.get('top_unprofitable_products', {}),
        status_performance=results.get('status_performance', {}),
        trend_data=json.dumps(results.get('trend_data', {}))
    )

@profit_bp.route('/api/dashboard-stats', methods=['GET'])
def dashboard_stats():
    """Kâr-zarar dashboard API'si"""
    # Son 30 gün
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    # Varsayılan maliyet değerleri
    package_cost = 5.0
    employee_cost = 10.0
    shipping_cost = 15.0
    
    # Siparişleri getir
    orders = get_orders_by_date_range(start_date, end_date)
    
    if not orders:
        return jsonify({
            'status': 'error',
            'message': 'Bu tarih aralığında sipariş bulunamadı'
        })
    
    # Analiz yap
    results = analyze_orders(orders, package_cost, employee_cost, shipping_cost)
    
    # Trend verileri
    trend_data = {}
    for order in orders:
        date_key = order.order_date.strftime('%Y-%m-%d')
        if date_key not in trend_data:
            trend_data[date_key] = {'count': 0, 'revenue': 0, 'profit': 0}
        
        amount_val = order.amount or 0
        discount_val = order.discount or 0
        order_revenue = amount_val - discount_val
        
        product_cost = calculate_product_cost(order)
        total_expenses = product_cost + shipping_cost + package_cost + employee_cost + (order.commission or 0)
        profit = order_revenue - total_expenses
        
        trend_data[date_key]['count'] += 1
        trend_data[date_key]['revenue'] += order_revenue
        trend_data[date_key]['profit'] += profit
    
    # Sıralı tarih listesi
    sorted_dates = sorted(trend_data.keys())
    
    return jsonify({
        'status': 'success',
        'total_profit': results['total_profit'],
        'total_revenue': results['total_revenue'],
        'avg_profit_per_order': results['avg_profit'],
        'order_count': len(orders),
        'profitable_orders': results['profitable_count'],
        'unprofitable_orders': results['unprofitable_count'],
        'profit_margin': (results['total_profit'] / results['total_revenue'] * 100) if results['total_revenue'] > 0 else 0,
        'expense_breakdown': {
            'product_cost': results['total_product_spent'],
            'commission': results['total_commission_spent'],
            'package': results['total_package_spent'],
            'shipping': results['total_shipping_spent'],
            'employee': results['total_employee_spent']
        },
        'top_profitable_products': results['top_profitable_products'],
        'top_unprofitable_products': results['top_unprofitable_products'],
        'trend_data': {
            'dates': sorted_dates,
            'revenue': [trend_data[date]['revenue'] for date in sorted_dates],
            'profit': [trend_data[date]['profit'] for date in sorted_dates],
            'count': [trend_data[date]['count'] for date in sorted_dates]
        }
    })

@profit_bp.route('/export', methods=['POST'])
def export_analysis():
    """Analiz verilerini CSV veya Excel olarak dışa aktar"""
    if request.method == 'POST':
        # Form parametreleri
        package_cost = float(request.form.get('package_cost', 0) or 0)
        employee_cost = float(request.form.get('employee_cost', 0) or 0)
        shipping_cost = float(request.form.get('shipping_cost', 0) or 0)
        status_filter = request.form.get('status_filter')
        product_filter = request.form.get('product_filter')
        quick_filter = request.form.get('quick_filter')
        export_format = request.form.get('export_format', 'csv')
        
        if quick_filter and quick_filter != 'custom':
            # Hızlı filtre kullan
            start_date, end_date = get_quick_date_range(quick_filter)
        else:
            # Manuel tarih aralığı
            start_date_str = request.form.get('start_date')
            end_date_str = request.form.get('end_date')
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # Siparişleri çek
        orders = get_orders_by_date_range(start_date, end_date, status_filter, product_filter)
        
        if not orders:
            return jsonify({
                'status': 'error',
                'message': 'Bu tarih aralığında sipariş bulunamadı'
            })
        
        # Siparişleri analiz et
        results = analyze_orders(orders, package_cost, employee_cost, shipping_cost)
        
        # Pandas DataFrame'e dönüştür
        df = pd.DataFrame(results['analysis'])
        
        # Dosya adı
        filename = f"profit_analysis_{start_date.strftime('%Y%m%d')}_to_{end_date.strftime('%Y%m%d')}"
        
        # CSV veya Excel formatında dosyayı oluştur
        if export_format == 'csv':
            output_path = f"static/exports/{filename}.csv"
            df.to_csv(output_path, index=False, encoding='utf-8-sig')
        else:
            output_path = f"static/exports/{filename}.xlsx"
            df.to_excel(output_path, index=False, engine='openpyxl')
        
        return jsonify({
            'status': 'success',
            'file_url': output_path,
            'message': f'Analiz verisi başarıyla dışa aktarıldı: {output_path}'
        })
    
    return jsonify({
        'status': 'error',
        'message': 'Geçersiz istek'
    })
