from flask import Blueprint, render_template
from sqlalchemy import func
from models import db, Order, Archive, Degisim, SiparisFisi
from models import ReturnOrder, ReturnProduct  # Base ile tanımlanan

analysis_bp = Blueprint('analysis_bp', __name__)

@analysis_bp.route('/analysis')
def analysis_page():
    """
    Tüm analiz sayfasını buradan döndürüyoruz.
    """

    # ---------------------------------------------------
    # 1) Genel Bakış (Dashboard)
    # ---------------------------------------------------
    seasonal_order_trends = {
        'yaz': 1200,
        'kis': 900,
        'ilkbahar': 750,
        'sonbahar': 800
    }
    hour_based_orders = {
        '00-06': 50,
        '06-12': 300,
        '12-18': 500,
        '18-24': 400
    }
    new_customers_ratio = 0.30   # %30
    existing_customers_ratio = 0.70  # %70

    # Kar oranı örneği
    total_revenue = 50000
    total_cost = 30000
    if total_revenue > 0:
        profit_ratio = (total_revenue - total_cost) / total_revenue * 100
    else:
        profit_ratio = 0

    # ---------------------------------------------------
    # 2) Sipariş Analizi
    # ---------------------------------------------------
    cancelled_orders_count = 100
    most_cancelled_products = [
        {'product_name': 'Sistem Ürünü #1 (Barkod:1001, Renk:Siyah, Beden:37)', 'cancel_count': 10},
        {'product_name': 'Sistem Ürünü #2 (Barkod:1002, Renk:Beyaz, Beden:38)', 'cancel_count': 8},
        {'product_name': 'Sistem Ürünü #3 (Barkod:1003, Renk:Lacivert, Beden:36)', 'cancel_count': 6},
    ]
    cancellation_reasons = {
        'Yanlış Adres': 12,
        'Vazgeçti': 50,
        'Fiyat Yüksek': 20,
        'Diğer': 18
    }
    cancellation_stages = {
        'Kargo Öncesi': 70,
        'Kargo Sonrası': 30
    }

    city_based_orders = {
        'İstanbul': 400,
        'Ankara': 200,
        'İzmir': 150
    }
    single_item_orders = 320
    multi_item_orders = 180
    product_categories_ratio = {
        'Ayakkabı': 40,
        'Çanta': 30,
        'Aksesuar': 20,
        'Diğer': 10
    }
    discount_orders_ratio = 0.25  # %25

    # ---------------------------------------------------
    # 3) İade Analizi
    # ---------------------------------------------------
    returns_by_category = {
        'Ayakkabı': 0.15,   # %15
        'Elektronik': 0.05, # Örnek
        'Giyim': 0.10
    }
    average_return_cost = 250  # TL
    avg_return_days = 5        # gün
    top_return_locations = {
        'İstanbul': 30,
        'İzmir': 15,
        'Ankara': 20
    }

    # ---------------------------------------------------
    # 4) Ürün/Stok Analizi
    # ---------------------------------------------------
    critical_stocks = [
        {'product': 'Sistem Ürünü #4 (Barkod:2001, Renk:Siyah, Beden:39)', 'stock': 5},
        {'product': 'Sistem Ürünü #5 (Barkod:2002, Renk:Gri, Beden:36)', 'stock': 2},
    ]
    restock_times = {
        'Sistem Ürünü #6 (Barkod:3001, Renk:Kahve, Beden:38)': 15,
        'Sistem Ürünü #7 (Barkod:3002, Renk:Beyaz, Beden:37)': 10
    }
    old_fashion_products = [
        {'product': 'Sistem Ürünü #8 (Barkod:4001)', 'last_sale': '2024-08-01'},
        {'product': 'Sistem Ürünü #9 (Barkod:4002)', 'last_sale': '2024-07-25'}
    ]
    low_selling_products = [
        {'product': 'Sistem Ürünü #10 (Barkod:5001)', 'sales': 2},
        {'product': 'Sistem Ürünü #11 (Barkod:5002)', 'sales': 0}
    ]
    product_combos = [
        {'combo': 'Sistem Ürünü #12 + Sistem Ürünü #13', 'count': 20},
        {'combo': 'Sistem Ürünü #14 + Sistem Ürünü #15', 'count': 15},
    ]

    # ---------------------------------------------------
    # 5) Finansal Analiz
    # ---------------------------------------------------
    aov_trend = 350       # TL
    average_margin = 0.20 # %20
    net_income_loss_from_returns = 5000 # TL
    tax_ratio = 0.18      # %18
    best_campaign = "1 Alana 2. %50 İndirim"
    best_campaign_revenue = 10000

    # ---------------------------------------------------
    # 6) Müşteri Analizi
    # ---------------------------------------------------
    segmented_customers = {
        'Sadık Müşteriler': 150,
        'Tek Seferlik': 300,
        'Diğer': 50
    }
    average_clv = 1200  # TL
    abandoned_cart_ratio = 0.12  # %12
    loyalty_users_count = 80
    loyalty_contribution = 20000

    # ---------------------------------------------------
    # 7) Performans Analizi
    # ---------------------------------------------------
    cargo_performance = {
        'KargoA': {'hız': '1.5 gün', 'gecikme_orani': 0.05},
        'KargoB': {'hız': '2 gün',   'gecikme_orani': 0.10},
    }
    avg_completion_time = 3
    daily_processed_orders = 100

    # ---------------------------------------------------
    # 8) Kullanıcı Davranışları
    # ---------------------------------------------------
    most_viewed_not_sold = [
        {'product': 'Sistem Ürünü #16 (Barkod:6001)', 'views': 500, 'sales': 0},
        {'product': 'Sistem Ürünü #17 (Barkod:6002)', 'views': 300, 'sales': 0},
    ]
    offer_conversion_ratio = 0.25
    popular_filters = ['Fiyat Artan', 'Beden 38', 'Renk: Siyah']

    # ---------------------------------------------------
    # 9) Tahmin ve Öneri Sistemleri
    # ---------------------------------------------------
    predicted_next_month_sales = 60000
    predicted_return_risk_products = [
        {'product': 'Sistem Ürünü #18 (Barkod:7001)', 'risk': 'Yüksek'},
        {'product': 'Sistem Ürünü #19 (Barkod:7002)', 'risk': 'Orta'}
    ]
    restock_suggestions = [
        {'product': 'Sistem Ürünü #20 (Barkod:8001)', 'suggested_date': '2025-02-15'},
        {'product': 'Sistem Ürünü #21 (Barkod:8002)', 'suggested_date': '2025-03-01'}
    ]

    # ---------------------------------------------------
    # 10) Anlık Veri ve Canlı Takip
    # ---------------------------------------------------
    current_processing_orders = 20
    live_sales_data = [
        {'hour': '09:00', 'sales': 5},
        {'hour': '10:00', 'sales': 8},
        {'hour': '11:00', 'sales': 12},
    ]
    shipping_in_transit = 15

    # Son olarak template'e gönderiyoruz
    return render_template(
        'analysis.html',

        # 1) Genel Bakış
        seasonal_order_trends=seasonal_order_trends,
        hour_based_orders=hour_based_orders,
        new_customers_ratio=new_customers_ratio,
        existing_customers_ratio=existing_customers_ratio,
        profit_ratio=profit_ratio,

        # 2) Sipariş Analizi
        cancelled_orders_count=cancelled_orders_count,
        most_cancelled_products=most_cancelled_products,
        cancellation_reasons=cancellation_reasons,
        cancellation_stages=cancellation_stages,
        city_based_orders=city_based_orders,
        single_item_orders=single_item_orders,
        multi_item_orders=multi_item_orders,
        product_categories_ratio=product_categories_ratio,
        discount_orders_ratio=discount_orders_ratio,

        # 3) İade Analizi
        returns_by_category=returns_by_category,
        average_return_cost=average_return_cost,
        avg_return_days=avg_return_days,
        top_return_locations=top_return_locations,

        # 4) Ürün/Stok Analizi
        critical_stocks=critical_stocks,
        restock_times=restock_times,
        old_fashion_products=old_fashion_products,
        low_selling_products=low_selling_products,
        product_combos=product_combos,

        # 5) Finansal Analiz
        aov_trend=aov_trend,
        average_margin=average_margin,
        net_income_loss_from_returns=net_income_loss_from_returns,
        tax_ratio=tax_ratio,
        best_campaign=best_campaign,
        best_campaign_revenue=best_campaign_revenue,

        # 6) Müşteri Analizi
        segmented_customers=segmented_customers,
        average_clv=average_clv,
        abandoned_cart_ratio=abandoned_cart_ratio,
        loyalty_users_count=loyalty_users_count,
        loyalty_contribution=loyalty_contribution,

        # 7) Performans Analizi
        cargo_performance=cargo_performance,
        avg_completion_time=avg_completion_time,
        daily_processed_orders=daily_processed_orders,

        # 8) Kullanıcı Davranışları
        most_viewed_not_sold=most_viewed_not_sold,
        offer_conversion_ratio=offer_conversion_ratio,
        popular_filters=popular_filters,

        # 9) Tahmin ve Öneri Sistemleri
        predicted_next_month_sales=predicted_next_month_sales,
        predicted_return_risk_products=predicted_return_risk_products,
        restock_suggestions=restock_suggestions,

        # 10) Anlık Veri ve Canlı Takip
        current_processing_orders=current_processing_orders,
        live_sales_data=live_sales_data,
        shipping_in_transit=shipping_in_transit
    )
