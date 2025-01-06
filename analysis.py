from flask import Blueprint, render_template
from sqlalchemy import func, desc
from models import db, Order, Product, ReturnOrder

analysis_bp = Blueprint('analysis_bp', __name__)

@analysis_bp.route('/analysis')
def analysis_page():
    """
    Trendyol benzeri bir 'Satış Raporu' sayfası: sekmeler, kartlar, tablolar.
    Gerçek veriler Model'lerden çekiliyor.
    """

    # -- 1) Genel İstatistikler --
    total_orders = db.session.query(func.count(Order.id)).scalar() or 0
    total_products = db.session.query(func.count(Product.barcode)).scalar() or 0
    total_returns = db.session.query(func.count(ReturnOrder.id)).scalar() or 0

    # Farklı Müşteri Sayısı (Order tablosunda 'customer_name' varsa)
    distinct_customers = db.session.query(
        func.count(func.distinct(Order.customer_name))
    ).scalar() or 0

    # -- 2) Satış Analizi --
    total_sales_amount = db.session.query(func.sum(Order.amount)).scalar() or 0
    avg_order_amount = (total_sales_amount / total_orders) if total_orders > 0 else 0

    # Örnek: Bu ayki satış (bu ayın başından bugüne kadar)
    from datetime import datetime
    from dateutil.relativedelta import relativedelta  # pip install python-dateutil
    now = datetime.now()
    first_day_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    this_month_sales = db.session.query(func.sum(Order.amount)).filter(
        Order.order_date >= first_day_of_month
    ).scalar() or 0

    # En popüler kategori / en çok satan ürün
    # (Order tablosunda product_name, quantity gibi alanlar varsa)
    # Gruplayarak en çok satılan barkodu bulalım
    top_products_query = (
        db.session.query(Order.product_barcode, func.sum(Order.quantity).label('qty_sold'))
        .group_by(Order.product_barcode)
        .order_by(desc('qty_sold'))
        .limit(5)
        .all()
    )
    # Bu sorgudan tabloya veri atacağız

    # -- 3) İade Analizi --
    total_refund = db.session.query(func.sum(ReturnOrder.refund_amount)).scalar() or 0
    refund_ratio = (total_refund / total_sales_amount) if total_sales_amount > 0 else 0

    # Örnek: Bu ayki iade oranı
    this_month_returns = db.session.query(ReturnOrder).filter(
        ReturnOrder.return_date >= first_day_of_month
    ).count()
    this_month_refund_sum = db.session.query(func.sum(ReturnOrder.refund_amount)).filter(
        ReturnOrder.return_date >= first_day_of_month
    ).scalar() or 0

    # -- 4) Stok Analizi --
    # Kritik stok (< 10)
    critical_products = Product.query.filter(Product.quantity < 10).all()

    # Son satış tarihini almak istersen:
    # (yeni bir sorgu, her ürünün son order_date değerini bulabilirsin, vs.)
    # Şimdilik basit tutuyoruz.

    return render_template(
        "analysis.html",  # HTML şablon adı
        # Genel
        total_orders=total_orders,
        total_products=total_products,
        total_returns=total_returns,
        distinct_customers=distinct_customers,

        # Satış Analizi
        total_sales_amount=total_sales_amount,
        avg_order_amount=avg_order_amount,
        this_month_sales=this_month_sales,
        top_products_query=top_products_query,

        # İade Analizi
        total_refund=total_refund,
        refund_ratio=refund_ratio,
        this_month_returns=this_month_returns,
        this_month_refund_sum=this_month_refund_sum,

        # Stok Analizi
        critical_products=critical_products
    )
