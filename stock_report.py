
from flask import Blueprint, jsonify, render_template
from models import db, Product, Order
from sqlalchemy import func
from datetime import datetime, timedelta

stock_report_bp = Blueprint('stock_report', __name__)

@stock_report_bp.route('/api/stock-report-data')
def get_stock_report_data():
    """Detaylı stok raporu verilerini döndürür"""
    
    # Tüm ürünleri getir
    products = Product.query.all()
    
    # Son 30 günlük satışları getir
    thirty_days_ago = datetime.now() - timedelta(days=30)
    sales = db.session.query(
        Order.product_barcode,
        func.count(Order.id).label('sales_count')
    ).filter(
        Order.order_date >= thirty_days_ago
    ).group_by(
        Order.product_barcode
    ).all()
    
    # Satış verilerini sözlüğe dönüştür
    sales_dict = {s.product_barcode: s.sales_count for s in sales}
    
    # Kategori istatistikleri
    categories = {}
    for p in products:
        category = p.title.split('-')[0].strip() if p.title else 'Diğer'
        if category not in categories:
            categories[category] = {'count': 0, 'value': 0}
        categories[category]['count'] += 1
        categories[category]['value'] += (p.quantity or 0) * (p.sale_price or 0)
    
    # Stok durumu sayıları
    stock_status = {
        'critical': len([p for p in products if p.quantity and p.quantity < 10]),
        'out': len([p for p in products if not p.quantity or p.quantity == 0]),
        'healthy': len([p for p in products if p.quantity and p.quantity >= 10])
    }
    
    # Ürün listelerini hazırla
    def prepare_product_data(product):
        category = product.title.split('-')[0].strip() if product.title else 'Diğer'
        quantity = product.quantity or 0
        sale_price = product.sale_price or 0
        
        # Stok rotasyonu hesapla
        monthly_sales = sales_dict.get(product.barcode, 0)
        rotation_rate = round((monthly_sales / quantity * 100) if quantity > 0 else 0, 2)
        
        return {
            'title': product.title,
            'barcode': product.barcode,
            'category': category,
            'quantity': quantity,
            'min_stock': 10,  # Minimum stok seviyesi
            'size': product.size,
            'color': product.color,
            'sale_price': sale_price,
            'total_value': quantity * sale_price,
            'rotation_rate': rotation_rate,
            'last_movement': datetime.now().isoformat(),  # Bu veriyi gerçek hareket tarihiyle değiştirin
            'status': 'Kritik' if quantity < 10 else 'Stok Dışı' if quantity == 0 else 'Yeterli'
        }
    
    all_products = [prepare_product_data(p) for p in products]
    critical_products = [p for p in all_products if p['status'] == 'Kritik']
    
    # Toplam değerleri hesapla
    total_value = sum(p['total_value'] for p in all_products)
    total_rotation = sum(p['rotation_rate'] for p in all_products)
    avg_rotation = round(total_rotation / len(all_products) if all_products else 0, 2)
    
    return jsonify({
        'categories': [
            {'name': k, 'count': v['count'], 'value': v['value']} 
            for k, v in categories.items()
        ],
        'stock_status': stock_status,
        'critical_products': critical_products,
        'all_products': all_products,
        'total_products': len(products),
        'total_value': total_value,
        'avg_rotation': avg_rotation,
        'critical_count': len(critical_products)
    })

@stock_report_bp.route('/stock-report')
def stock_report():
    """Stok raporu sayfasını render eder"""
    return render_template('stock_report.html')
