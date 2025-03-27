from flask import Blueprint, render_template, request
from models import db, Order, Product
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)

profit_bp = Blueprint('profit', __name__, url_prefix='/profit')

@profit_bp.route('/', methods=['GET', 'POST'])
def profit_report():
    analysis = []
    total_profit = avg_profit = None

    if request.method == 'POST':
        package_cost = float(request.form.get('package_cost', 0))
        employee_cost = float(request.form.get('employee_cost', 0))
        shipping_cost = float(request.form.get('shipping_cost', 0))
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')

        logging.info(f"Paket maliyeti: {package_cost}, İşçilik maliyeti: {employee_cost}, Kargo maliyeti: {shipping_cost}")
        logging.info(f"Tarih aralığı: {start_date} - {end_date}")

        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')

        orders = Order.query.filter(Order.order_date.between(start_date_obj, end_date_obj)).all()
        logging.info(f"Toplam sipariş sayısı: {len(orders)}")

        total_profit = 0
        analysis = []

        for order in orders:
            product = Product.query.filter_by(original_product_barcode=order.original_product_barcode).first()

            if not product:
                logging.warning(f"Sipariş {order.id} için ürün bulunamadı. Barkod: {order.original_product_barcode}")
                continue

            net_income = (order.amount - order.discount) - order.commission

            total_expenses = (
                product.cost_try +
                shipping_cost +
                package_cost +
                employee_cost
            )

            profit = net_income - total_expenses
            total_profit += profit

            logging.info(f"Sipariş ID: {order.id}, Ürün: {order.product_name}, Net Gelir: {net_income}, Toplam Gider: {total_expenses}, Kâr: {profit}")

            analysis.append({
                "order_id": order.id,
                "product": order.product_name,
                "net_income": net_income,
                "total_expenses": total_expenses,
                "profit": profit
            })

        avg_profit = total_profit / len(analysis) if analysis else 0
        logging.info(f"Toplam Kâr: {total_profit}, Ortalama Kâr: {avg_profit}")

    return render_template(
        'profit.html',
        analysis=analysis,
        total_profit=total_profit,
        avg_profit=avg_profit
    )
