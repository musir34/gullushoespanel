from flask import Blueprint, render_template, request
from datetime import datetime
import logging

# Çok tablolu sipariş modelleri; proje yapınıza göre import edin
from models import db, OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled, Product

logging.basicConfig(level=logging.INFO)

profit_bp = Blueprint('profit', __name__, url_prefix='/profit')

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

    # Analiz listesi
    analysis = []

    # Ana toplamlar
    total_profit = 0.0
    avg_profit = 0.0

    # Ek toplu hesaplar
    total_commission_spent = 0.0
    total_package_spent = 0.0
    total_shipping_spent = 0.0
    total_employee_spent = 0.0
    total_revenue = 0.0  # (amount - discount) toplamı
    total_product_spent = 0.0  # Tüm ürün maliyeti

    if request.method == 'POST':
        # 1) Form parametreleri
        package_cost = float(request.form.get('package_cost', 0) or 0)
        employee_cost = float(request.form.get('employee_cost', 0) or 0)
        shipping_cost = float(request.form.get('shipping_cost', 0) or 0)
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')

        logging.info(f"Paket maliyeti: {package_cost}, İşçilik: {employee_cost}, Kargo: {shipping_cost}")
        logging.info(f"Tarih aralığı: {start_date} - {end_date}")

        # Tarih parse
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')

        # 2) Tüm tablolardan sipariş çek
        orders = []
        table_classes = [OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled]
        for cls in table_classes:
            found = cls.query.filter(cls.order_date.between(start_date_obj, end_date_obj)).all()
            orders.extend(found)

        logging.info(f"Toplam sipariş sayısı: {len(orders)}")

        # 3) Her siparişin net kâr hesaplaması
        for o in orders:
            # Değerleri None ise 0
            amount_val = o.amount or 0
            discount_val = o.discount or 0
            commission_val = o.commission or 0

            # Gelir = (amount - discount)
            order_revenue = amount_val - discount_val
            total_revenue += order_revenue

            # Komisyon giderini topluyoruz
            total_commission_spent += commission_val

            # ==== ÜRÜN MALİYETİ (cost_try) ====
            product_cost = 0.0
            # (Eğer barkod bazında product araması yapacaksanız)
            # orijinal barkod? merchant_sku? Projede hangisini eşleştiriyorsanız:
            # Örneğin, o.original_product_barcode
            # Burada "original_product_barcode" veya "product_barcode" yoksa 0
            # Aşağıda "merchant_sku" bazlı arama da yapabilirsiniz:
            # product = Product.query.filter_by(merchant_sku=o.merchant_sku).first()

            if hasattr(o, 'original_product_barcode'):
                bc = o.original_product_barcode
                if bc:
                    prod = Product.query.filter_by(original_product_barcode=bc).first()
                    if prod and prod.cost_try:
                        product_cost = prod.cost_try
                else:
                    logging.debug(f"{o.order_number} barkod boş, product_cost=0")
            else:
                logging.debug(f"{o.order_number} - original_product_barcode alanı yok?")

            # Toplam ürün maliyeti aggregator
            total_product_spent += product_cost

            # 4) Tüm gider = Ürün maliyeti + shipping + package + employee + commission
            total_expenses = product_cost + shipping_cost + package_cost + employee_cost + commission_val

            # Tekil giderleri aggregatorlara ekliyoruz:
            # (Zaten komisyonu, shipping, package, employee ekledik yukarıda. 
            #  ama product_cost aggregator'a da eklendi.)
            total_shipping_spent += shipping_cost
            total_package_spent += package_cost
            total_employee_spent += employee_cost
            # Commission -> total_commission_spent yukarıda

            # Net kâr
            profit = order_revenue - total_expenses
            total_profit += profit

            logging.info(
                f"Sipariş {o.order_number}, Tablo={o.__tablename__}, merchant_sku={o.merchant_sku}, "
                f"GELİR={order_revenue}, ÜrünMaliyeti={product_cost}, DiğerGiderler=({shipping_cost}+{package_cost}+{employee_cost}+{commission_val}),"
                f"KÂR={profit}"
            )

            analysis.append({
                "order_number": o.order_number,
                "order_table": o.__tablename__,   # tablo bilgisi
                "product": o.merchant_sku,        # ürün bilgisi
                "net_income": order_revenue,      # (amount - discount)
                "total_expenses": total_expenses, # (product_cost + shipping + package + employee + commission)
                "profit": profit,
                "status": o.status
            })

        # 5) Ortalama Kâr
        if analysis:
            avg_profit = total_profit / len(analysis)

        logging.info(f"Toplam Kâr: {total_profit}, Ortalama Kâr: {avg_profit}")

    # Sonuçları şablona gönder
    return render_template(
        'profit.html',
        analysis=analysis,
        total_profit=total_profit,
        avg_profit=avg_profit,
        total_revenue=total_revenue,
        total_commission_spent=total_commission_spent,
        total_package_spent=total_package_spent,
        total_shipping_spent=total_shipping_spent,
        total_employee_spent=total_employee_spent,
        total_product_spent=total_product_spent  # ister HTML'de gösterin
    )
