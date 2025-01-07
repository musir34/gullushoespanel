
from flask import Blueprint, render_template
from models import Product
from sqlalchemy import func

stock_report_bp = Blueprint('stock_report', __name__)

@stock_report_bp.route('/stock-report')
def stock_report():
    return render_template('stock_report.html')

@stock_report_bp.route('/api/stock-report-data')
def get_stock_report_data():
    low_stock_products = Product.query.filter(Product.quantity > 0, Product.quantity < 10).all()
    out_of_stock_products = Product.query.filter(Product.quantity <= 0).all()
    
    return {
        'low_stock_products': [{
            'title': p.title,
            'barcode': p.barcode,
            'quantity': p.quantity,
            'size': p.size,
            'color': p.color,
            'sale_price': p.sale_price
        } for p in low_stock_products],
        'out_stock_products': [{
            'title': p.title,
            'barcode': p.barcode,
            'quantity': p.quantity,
            'size': p.size,
            'color': p.color,
            'sale_price': p.sale_price
        } for p in out_of_stock_products]
    }
