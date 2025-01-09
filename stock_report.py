from flask import Blueprint, jsonify, render_template, request
from models import db, Product, Order
from sqlalchemy import func, or_
from datetime import datetime, timedelta

stock_report_bp = Blueprint('stock_report', __name__)

@stock_report_bp.route('/stock-report')
def stock_report():
    return render_template('stock_report.html')

@stock_report_bp.route('/api/inventory-turnover')
def inventory_turnover():
    # Son 30 günlük satışları al
    thirty_days_ago = datetime.now() - timedelta(days=30)
    
    # Ürün bazlı satış miktarları
    sales = db.session.query(
        Order.product_main_id,
        func.sum(Order.quantity).label('total_sold')
    ).filter(
        Order.order_date >= thirty_days_ago,
        Order.status != 'Cancelled'
    ).group_by(Order.product_main_id).all()
    
    # Stok durumları
    current_stocks = db.session.query(
        Product.product_main_id,
        func.sum(Product.quantity).label('current_stock'),
        Product.title,
        Product.color,
        Product.size
    ).group_by(
        Product.product_main_id,
        Product.title,
        Product.color,
        Product.size
    ).all()
    
    # Stok devir hızı hesaplama
    turnover_rates = []
    for stock in current_stocks:
        sold = next((s.total_sold for s in sales if s.product_main_id == stock.product_main_id), 0)
        if stock.current_stock:
            turnover_rate = (sold * 30) / stock.current_stock  # Aylık stok devir hızı
        else:
            turnover_rate = 0
            
        turnover_rates.append({
            'product_main_id': stock.product_main_id,
            'title': stock.title,
            'color': stock.color,
            'size': stock.size,
            'current_stock': stock.current_stock,
            'total_sold': sold,
            'turnover_rate': round(turnover_rate, 2)
        })
    
    # Stok devir hızına göre sırala
    turnover_rates.sort(key=lambda x: x['turnover_rate'], reverse=True)
    
    # Yüksek ve düşük devir hızlı ürünleri ayır
    high_turnover = [p for p in turnover_rates if p['turnover_rate'] > 1]  # Ayda 1'den fazla devreden
    low_turnover = [p for p in turnover_rates if p['turnover_rate'] <= 1]  # Ayda 1'den az devreden
    
    return jsonify({
        'high_turnover_products': high_turnover[:10],  # İlk 10
        'low_turnover_products': low_turnover[:10],    # İlk 10
        'all_products': turnover_rates
    })

@stock_report_bp.route('/api/stock-report-data')
def stock_report_data():
    stock_filter = request.args.get('filter', 'all')
    search = request.args.get('search', '')

    # Ana sorgu
    query = Product.query

    # Arama filtresi
    if search:
        query = query.filter(
            or_(
                Product.title.ilike(f'%{search}%'),
                Product.barcode.ilike(f'%{search}%'),
                Product.product_main_id.ilike(f'%{search}%')  # merchant_sku yerine product_main_id
            )
        )

    # Stok durumu filtresi
    if stock_filter == 'low':
        query = query.filter(Product.quantity < 10, Product.quantity > 0)
    elif stock_filter == 'out':
        query = query.filter(or_(Product.quantity == 0, Product.quantity == None))
    elif stock_filter == 'healthy':
        query = query.filter(Product.quantity >= 10)

    products = query.all()

    # Ürün listesini hazırla
    product_list = []
    total_value = 0
    low_stock_count = 0
    out_of_stock_count = 0

    for product in products:
        quantity = product.quantity or 0
        sale_price = product.sale_price or 0
        total_product_value = quantity * sale_price

        if quantity == 0:
            out_of_stock_count += 1
        elif quantity < 10:
            low_stock_count += 1

        total_value += total_product_value

        product_list.append({
            'title': product.title,
            'barcode': product.barcode,
            'model': product.product_main_id,  # merchant_sku yerine product_main_id
            'color': product.color,
            'size': product.size,
            'quantity': quantity,
            'sale_price': sale_price,
            'total_value': total_product_value
        })

    return jsonify({
        'summary': {
            'total_products': len(products),
            'low_stock_count': low_stock_count,
            'out_of_stock_count': out_of_stock_count,
            'total_value': total_value
        },
        'products': product_list
    })
