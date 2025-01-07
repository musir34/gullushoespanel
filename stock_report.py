from flask import Blueprint, jsonify, render_template, request
from models import db, Product, Order
from sqlalchemy import func, or_
from datetime import datetime, timedelta

stock_report_bp = Blueprint('stock_report', __name__)

@stock_report_bp.route('/stock-report')
def stock_report():
    return render_template('stock_report.html')

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
                Product.merchant_sku.ilike(f'%{search}%')
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