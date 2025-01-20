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
    """
    Stok raporu: 
    - Filtre ve arama özellikleri
    - Seçilen tarih aralığında satılan miktar
    - Günlük ortalama satış
    - Stok devir hızı (turnover_ratio)
    - Eldeki stokla kaç gün daha idare edebileceği (days_to_out)
    """

    # 1) Parametreleri alalım
    stock_filter = request.args.get('filter', 'all')
    search = request.args.get('search', '')

    # Tarih aralığı (opsiyonel). Verilmemişse son 30 günü baz alırız.
    start_date_str = request.args.get('start_date', '')
    end_date_str = request.args.get('end_date', '')

    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "Tarih formatı hatalı. YYYY-MM-DD şeklinde gönderiniz."}), 400
    else:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)

    # 2) Ürünleri çekmek için ana sorgu
    query = Product.query

    # 3) Arama (title, original_product_barcode, product_main_id)
    #    Daha önce barcode kullanılıyordu; şimdi orijinal barkoda göre arama yapıyoruz.
    if search:
        query = query.filter(
            or_(
                Product.title.ilike(f'%{search}%'),
                Product.original_product_barcode.ilike(f'%{search}%'),
                Product.product_main_id.ilike(f'%{search}%')
            )
        )

    # 4) Stok durumu filtresi
    if stock_filter == 'low':
        query = query.filter(Product.quantity < 10, Product.quantity > 0)
    elif stock_filter == 'out':
        query = query.filter(or_(Product.quantity == 0, Product.quantity == None))
    elif stock_filter == 'healthy':
        query = query.filter(Product.quantity >= 10)
    # 'all' ise ekstra filtre yok

    # 5) Ürün listesini çek
    products = query.all()

    # 6) Seçili tarih aralığında satılan miktarları bulmak için original barkod listesi
    product_barcodes = [p.original_product_barcode for p in products if p.original_product_barcode]

    # Eğer product_barcodes boşsa sorguya gerek yok
    sold_quantities = {}
    if product_barcodes:
        # Order tablonuzda da original_product_barcode alanı olduğunu varsayıyoruz.
        # Eğer hala Order.product_barcode olarak kalmışsa, tablo alanını da değiştirmelisiniz.
        sales_data = db.session.query(
            Order.original_product_barcode,
            func.sum(Order.quantity).label('total_sold')
        ).filter(
            Order.original_product_barcode.in_(product_barcodes),
            Order.order_date >= start_date,
            Order.order_date <= end_date
        ).group_by(Order.original_product_barcode).all()

        for sd in sales_data:
            sold_quantities[sd.original_product_barcode] = sd.total_sold or 0

    # Satılan toplam gün sayısı (end_date - start_date).days
    total_days = max(1, (end_date - start_date).days)

    # 7) Ürün detaylarını hazırlama
    product_list = []
    total_value = 0
    low_stock_count = 0
    out_of_stock_count = 0

    for product in products:
        quantity = product.quantity or 0
        sale_price = product.sale_price or 0
        total_product_value = quantity * sale_price

        # Düşük / sıfır stok sayısı
        if quantity == 0:
            out_of_stock_count += 1
        elif quantity < 10:
            low_stock_count += 1

        # Toplam stok değeri
        total_value += total_product_value

        # Bu ürüne ait tarih aralığındaki satış miktarı
        sold_quantity = sold_quantities.get(product.original_product_barcode, 0)

        # Günlük ortalama satış
        daily_sold = sold_quantity / total_days if total_days > 0 else 0

        # Stok devir hızı (sold_quantity / (quantity+1) gibi basit bir hesap)
        turnover_ratio = 0
        if quantity > 0 and sold_quantity > 0:
            turnover_ratio = sold_quantity / (quantity + 1)

        # Kaç günde bitecek?
        if daily_sold > 0:
            days_to_out = round(quantity / daily_sold, 1)
        else:
            days_to_out = None  # satılmıyor / hesaplanamıyor

        product_list.append({
            'title': product.title,
            'original_product_barcode': product.original_product_barcode,
            'model': product.product_main_id,
            'color': product.color,
            'size': product.size,
            'quantity': quantity,
            'sale_price': sale_price,
            'total_value': total_product_value,
            'sold_quantity': int(sold_quantity),
            'daily_sold': round(daily_sold, 2),
            'turnover_ratio': round(turnover_ratio, 2),
            'days_to_out': days_to_out
        })

    # 8) Genel özet (summary) döndürelim
    response_data = {
        'summary': {
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d'),
            'total_products': len(products),
            'low_stock_count': low_stock_count,
            'out_of_stock_count': out_of_stock_count,
            'total_value': round(total_value, 2)
        },
        'products': product_list
    }

    return jsonify(response_data)
