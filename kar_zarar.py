from flask import Blueprint, render_template, flash, request
from models import db, Order, Product

kar_zarar_bp = Blueprint("kar_zarar_bp", __name__)

@kar_zarar_bp.route("/profit-analysis")
def profit_analysis():
    """
    Basit kâr-zarar analizi:
    - Komisyon 0 olanlar atlanır veya uyarı basılır.
    - Ürün maliyeti products.cost_try kolonu (product_code eşlemesiyle).
    """
    # Örneğin son 100 siparişi çekiyoruz. (Yalnız 'Delivered' isterseniz ek filtre eklersiniz.)
    orders = Order.query.order_by(Order.id.desc()).limit(100).all()

    results = []
    skipped_count = 0

    for order in orders:
        # 1) Komisyon 0 veya negatifse atlıyoruz
        if not order.commission or order.commission <= 0:
            skipped_count += 1
            continue

        # 2) Ürün kodu (tek bir code varsayımı)
        product_code = (order.product_code or "").split(",")[0].strip()

        product = Product.query.filter_by(product_code=product_code).first()
        if not product:
            cost_try = 0
        else:
            cost_try = product.cost_try or 0

        # 3) Kâr Formülü
        # Net Kâr = amount - discount - commission - (maliyet * adet)
        quantity = order.quantity or 1
        net_profit = (
            (order.amount or 0)
            - (order.discount or 0)
            - (order.commission or 0)
            - (cost_try * quantity)
        )

        result_dict = {
            "order_number": order.order_number,
            "amount": order.amount,
            "discount": order.discount,
            "commission": order.commission,
            "cost_try": cost_try,
            "quantity": quantity,
            "net_profit": net_profit,
        }
        results.append(result_dict)

    # HTML şablona gönder
    return render_template(
        "profit_analysis.html",
        results=results,
        skipped_count=skipped_count
    )
