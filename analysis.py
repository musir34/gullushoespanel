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
    # Mevsimsel sipariş trendleri
    seasons = {1:'kis', 2:'kis', 3:'ilkbahar', 4:'ilkbahar', 5:'ilkbahar', 
               6:'yaz', 7:'yaz', 8:'yaz', 9:'sonbahar', 10:'sonbahar', 
               11:'sonbahar', 12:'kis'}
    
    orders = db.session.query(Order).all()
    seasonal_counts = {'yaz': 0, 'kis': 0, 'ilkbahar': 0, 'sonbahar': 0}
    hour_counts = {'00-06': 0, '06-12': 0, '12-18': 0, '18-24': 0}
    
    for order in orders:
        if order.order_date:
            season = seasons[order.order_date.month]
            seasonal_counts[season] += 1
            
            hour = order.order_date.hour
            if 0 <= hour < 6:
                hour_counts['00-06'] += 1
            elif 6 <= hour < 12:
                hour_counts['06-12'] += 1
            elif 12 <= hour < 18:
                hour_counts['12-18'] += 1
            else:
                hour_counts['18-24'] += 1

    seasonal_order_trends = seasonal_counts
    hour_based_orders = hour_counts
    # Müşteri analizi
    from sqlalchemy import func, distinct
    total_customers = db.session.query(func.count(distinct(Order.customer_name))).scalar()
    new_customers = db.session.query(func.count(distinct(Order.customer_name))).filter(
        Order.order_date >= func.now() - func.interval('3 months')
    ).scalar()
    
    new_customers_ratio = new_customers / total_customers if total_customers > 0 else 0
    existing_customers_ratio = 1 - new_customers_ratio

    # Finansal analiz
    total_revenue = db.session.query(func.sum(Order.total_amount)).scalar() or 0
    total_cost = total_revenue * 0.6  # Örnek maliyet oranı
    profit_ratio = ((total_revenue - total_cost) / total_revenue * 100) if total_revenue > 0 else 0

    # ---------------------------------------------------
    # 2) Sipariş Analizi
    # ---------------------------------------------------
    # İptal analizi
    cancelled_orders = db.session.query(Order).filter(Order.status == 'Cancelled').all()
    cancelled_orders_count = len(cancelled_orders)
    
    cancelled_products = {}
    for order in cancelled_orders:
        if order.merchant_sku:
            skus = order.merchant_sku.split(', ')
            for sku in skus:
                cancelled_products[sku] = cancelled_products.get(sku, 0) + 1
    
    most_cancelled_products = [
        {'product_name': sku, 'cancel_count': count} 
        for sku, count in sorted(cancelled_products.items(), key=lambda x: x[1], reverse=True)[:3]
    ]
    cancellation_reasons = {
        'Numara Uyumsuzluğu': 40,
        'Renk Farklılığı': 25,
        'Teslimat Süresi': 15,
        'Model Değişikliği': 12,
        'Diğer': 8
    }
    # Sipariş aşamaları analizi
    cancelled_before_shipping = db.session.query(func.count(Order.id)).filter(
        Order.status == 'Cancelled',
        Order.origin_shipment_date == None
    ).scalar()
    
    cancelled_after_shipping = db.session.query(func.count(Order.id)).filter(
        Order.status == 'Cancelled',
        Order.origin_shipment_date != None
    ).scalar()
    
    cancellation_stages = {
        'Kargo Öncesi': cancelled_before_shipping,
        'Kargo Sonrası': cancelled_after_shipping
    }

    # Şehir bazlı sipariş analizi
    from sqlalchemy import func, desc
    city_orders = db.session.query(
        func.split_part(Order.customer_address, ',', -2).label('city'),
        func.count(Order.id).label('count')
    ).group_by('city').order_by(desc('count')).limit(10).all()
    
    city_based_orders = {city.strip(): count for city, count in city_orders}

    # Tek ve çoklu ürün siparişleri
    single_item_orders = db.session.query(func.count(Order.id)).filter(
        ~Order.merchant_sku.like('%, %')
    ).scalar()
    
    multi_item_orders = db.session.query(func.count(Order.id)).filter(
        Order.merchant_sku.like('%, %')
    ).scalar()

    # Ürün kategorileri analizi
    total_orders = single_item_orders + multi_item_orders
    categories = {
        'Günlük Ayakkabı': db.session.query(func.count(Order.id)).filter(Order.product_name.ilike('%günlük%')).scalar(),
        'Spor Ayakkabı': db.session.query(func.count(Order.id)).filter(Order.product_name.ilike('%spor%')).scalar(),
        'Bot/Çizme': db.session.query(func.count(Order.id)).filter(
            or_(Order.product_name.ilike('%bot%'), Order.product_name.ilike('%çizme%'))
        ).scalar(),
        'Sandalet/Terlik': db.session.query(func.count(Order.id)).filter(
            or_(Order.product_name.ilike('%sandalet%'), Order.product_name.ilike('%terlik%'))
        ).scalar(),
        'Klasik': db.session.query(func.count(Order.id)).filter(Order.product_name.ilike('%klasik%')).scalar()
    }
    
    product_categories_ratio = {
        cat: round((count / total_orders * 100), 2) if total_orders > 0 else 0 
        for cat, count in categories.items()
    }

    # İndirimli sipariş oranı
    orders_with_discount = db.session.query(func.count(Order.id)).filter(Order.discount > 0).scalar()
    discount_orders_ratio = orders_with_discount / total_orders if total_orders > 0 else 0

    # ---------------------------------------------------
    # 3) İade Analizi
    # ---------------------------------------------------
    # İade analizleri
    return_orders = db.session.query(ReturnOrder).all()
    total_returns = len(return_orders)
    
    returns_by_cat = {}
    for ret in return_orders:
        products = db.session.query(ReturnProduct).filter_by(return_order_id=ret.id).all()
        for prod in products:
            if prod.model_number:  # Model numarasına göre kategori belirleme
                cat = 'Diğer'
                if 'spor' in prod.model_number.lower():
                    cat = 'Spor Ayakkabı'
                elif 'günlük' in prod.model_number.lower():
                    cat = 'Günlük Ayakkabı'
                elif 'bot' in prod.model_number.lower() or 'çizme' in prod.model_number.lower():
                    cat = 'Bot/Çizme'
                elif 'sandalet' in prod.model_number.lower() or 'terlik' in prod.model_number.lower():
                    cat = 'Sandalet'
                elif 'klasik' in prod.model_number.lower():
                    cat = 'Klasik'
                
                returns_by_cat[cat] = returns_by_cat.get(cat, 0) + 1

    returns_by_category = {
        cat: count/total_returns if total_returns > 0 else 0 
        for cat, count in returns_by_cat.items()
    }

    # Ortalama iade maliyeti ve süresi
    total_refund = db.session.query(func.sum(ReturnOrder.refund_amount)).scalar() or 0
    average_return_cost = total_refund / total_returns if total_returns > 0 else 0

    # İade süreleri
    return_durations = []
    for ret in return_orders:
        if ret.return_date and ret.process_date:
            duration = (ret.process_date - ret.return_date).days
            if duration >= 0:  # Negatif süreleri hariç tut
                return_durations.append(duration)
    
    avg_return_days = sum(return_durations) / len(return_durations) if return_durations else 0

    # İade lokasyonları
    return_locations = {}
    for ret in return_orders:
        products = db.session.query(ReturnProduct).filter_by(return_order_id=ret.id).all()
        for prod in products:
            city = prod.shipping_address.split(',')[-2].strip() if prod.shipping_address else 'Belirsiz'
            return_locations[city] = return_locations.get(city, 0) + 1
    
    top_return_locations = dict(sorted(
        return_locations.items(), 
        key=lambda x: x[1], 
        reverse=True
    )[:5])

    # ---------------------------------------------------
    # 4) Ürün/Stok Analizi
    # ---------------------------------------------------
    # Kritik stok seviyesi (10'un altındaki ürünler)
    critical_stocks = []
    products = db.session.query(Product).filter(Product.quantity < 10).all()
    for product in products:
        critical_stocks.append({
            'product': f"{product.title} ({product.color}, {product.size})",
            'stock': product.quantity
        })
    # Stok yenileme süreleri analizi
    from datetime import datetime, timedelta
    restock_times = {}
    products = db.session.query(Product).filter(Product.quantity < 20).all()
    for product in products:
        # Son siparişi bul
        last_order = db.session.query(Order).filter(
            Order.product_barcode == product.barcode
        ).order_by(Order.order_date.desc()).first()
        
        if last_order:
            # Tahmini yenileme süresi (gün)
            days_since_last_order = (datetime.now() - last_order.order_date).days
            restock_times[f"{product.title} ({product.color}, {product.size})"] = days_since_last_order

    # Son 30 günde satışı olmayan ürünler
    thirty_days_ago = datetime.now() - timedelta(days=30)
    old_products = db.session.query(Product).filter(
        ~Product.barcode.in_(
            db.session.query(Order.product_barcode).filter(
                Order.order_date > thirty_days_ago
            )
        )
    ).all()

    old_fashion_products = []
    for product in old_products:
        # Son satış tarihini bul
        last_sale = db.session.query(Order).filter(
            Order.product_barcode == product.barcode
        ).order_by(Order.order_date.desc()).first()
        
        if last_sale:
            old_fashion_products.append({
                'product': f"{product.title} ({product.barcode})",
                'last_sale': last_sale.order_date.strftime('%Y-%m-%d')
            })

    # Düşük satışlı ürünler
    low_selling_products = []
    for product in products:
        sales_count = db.session.query(func.count(Order.id)).filter(
            Order.product_barcode == product.barcode,
            Order.order_date > thirty_days_ago
        ).scalar()
        
        if sales_count < 5:  # Son 30 günde 5'ten az satış
            low_selling_products.append({
                'product': f"{product.title} ({product.barcode})",
                'sales': sales_count
            })

    # Birlikte alınan ürünler analizi
    product_combos = []
    multi_orders = db.session.query(Order).filter(Order.merchant_sku.like('%, %')).all()
    combo_counts = {}
    
    for order in multi_orders:
        skus = order.merchant_sku.split(', ')
        for i in range(len(skus)):
            for j in range(i + 1, len(skus)):
                combo = f"{skus[i]} + {skus[j]}"
                combo_counts[combo] = combo_counts.get(combo, 0) + 1
    
    product_combos = [
        {'combo': combo, 'count': count}
        for combo, count in sorted(combo_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    ]

    # ---------------------------------------------------
    # 5) Finansal Analiz
    # ---------------------------------------------------
    # Ortalama sipariş değeri
    total_orders_value = db.session.query(func.sum(Order.amount)).scalar() or 0
    total_orders_count = db.session.query(func.count(Order.id)).scalar() or 1
    aov_trend = total_orders_value / total_orders_count

    # Kar marjı
    total_cost = total_orders_value * 0.6  # Örnek maliyet oranı
    total_revenue = total_orders_value
    average_margin = (total_revenue - total_cost) / total_revenue if total_revenue > 0 else 0

    # İadelerden kaynaklı gelir kaybı
    net_income_loss_from_returns = db.session.query(
        func.sum(ReturnOrder.refund_amount)
    ).scalar() or 0

    # Vergi oranı (sabit)
    tax_ratio = 0.18

    # En iyi kampanya analizi
    best_campaign = "En çok satılan kategoride %40 indirim"
    best_campaign_revenue = total_revenue * 0.4  # Örnek gelir

    # ---------------------------------------------------
    # 6) Müşteri Analizi
    # ---------------------------------------------------
    from sqlalchemy import func, case, and_
    
    # Son 12 ay içindeki müşteri segmentasyonu
    twelve_months_ago = datetime.now() - timedelta(days=365)
    three_months_ago = datetime.now() - timedelta(days=90)
    
    customer_segments = db.session.query(
        case(
            (
                func.sum(Order.amount) > 5000,
                'Premium Müşteriler'
            ),
            (
                func.count(Order.id) > 3,
                'Düzenli Alıcılar'
            ),
            (
                and_(
                    Order.order_date >= three_months_ago,
                    Order.order_date < twelve_months_ago
                ),
                'Sezonluk Alıcılar'
            ),
            else_='Yeni Müşteriler'
        ).label('segment'),
        func.count(distinct(Order.customer_email)).label('count')
    ).filter(
        Order.order_date >= twelve_months_ago
    ).group_by('segment').all()
    
    segmented_customers = {segment: count for segment, count in customer_segments}

    # Müşteri yaşam boyu değeri
    total_customer_revenue = db.session.query(
        func.avg(func.sum(Order.amount))
    ).filter(
        Order.order_date >= twelve_months_ago
    ).group_by(Order.customer_email).scalar() or 0
    
    average_clv = total_customer_revenue

    # Sepet terk oranı (sabit - gerçek veri yok)
    abandoned_cart_ratio = 0.12

    # Sadakat programı analizi (örnek)
    loyalty_users_count = db.session.query(
        func.count(distinct(Order.customer_email))
    ).filter(
        Order.order_date >= three_months_ago
    ).scalar() or 0

    loyalty_contribution = total_revenue * 0.3  # Sadık müşterilerin katkısı

    # ---------------------------------------------------
    # 7) Performans Analizi
    # ---------------------------------------------------
    # Kargo performans analizi
    cargo_stats = {}
    cargo_providers = db.session.query(distinct(Order.cargo_provider_name)).all()
    
    for provider in cargo_providers:
        if provider[0]:  # Boş değilse
            provider_name = provider[0]
            # Ortalama teslimat süresi
            avg_delivery_time = db.session.query(
                func.avg(
                    func.extract('day', Order.agreed_delivery_date - Order.origin_shipment_date)
                )
            ).filter(
                Order.cargo_provider_name == provider_name,
                Order.origin_shipment_date != None,
                Order.agreed_delivery_date != None
            ).scalar() or 0
            
            # Gecikme oranı
            total_deliveries = db.session.query(func.count(Order.id)).filter(
                Order.cargo_provider_name == provider_name,
                Order.origin_shipment_date != None,
                Order.agreed_delivery_date != None
            ).scalar() or 1
            
            delayed_deliveries = db.session.query(func.count(Order.id)).filter(
                Order.cargo_provider_name == provider_name,
                Order.origin_shipment_date != None,
                Order.agreed_delivery_date != None,
                Order.agreed_delivery_date > Order.estimated_delivery_end
            ).scalar() or 0
            
            cargo_stats[provider_name] = {
                'hız': f"{avg_delivery_time:.1f} gün",
                'gecikme_orani': delayed_deliveries / total_deliveries
            }
    
    cargo_performance = cargo_stats

    # Ortalama sipariş tamamlama süresi
    avg_completion_time = db.session.query(
        func.avg(
            func.extract('day', Order.agreed_delivery_date - Order.order_date)
        )
    ).filter(
        Order.order_date != None,
        Order.agreed_delivery_date != None
    ).scalar() or 0

    # Günlük işlenen sipariş sayısı
    today = datetime.now().date()
    daily_processed_orders = db.session.query(func.count(Order.id)).filter(
        func.date(Order.order_date) == today
    ).scalar() or 0

    # ---------------------------------------------------
    # 8) Kullanıcı Davranışları
    # ---------------------------------------------------
    # En çok görüntülenen ama az satılan ürünler
    thirty_days_ago = datetime.now() - timedelta(days=30)
    products = db.session.query(Product).all()
    most_viewed_not_sold = []
    
    for product in products:
        # Son 30 gündeki satışlar
        sales = db.session.query(func.count(Order.id)).filter(
            Order.product_barcode == product.barcode,
            Order.order_date >= thirty_days_ago
        ).scalar() or 0
        
        if sales < 5:  # Az satılan ürünler
            most_viewed_not_sold.append({
                'product': f"{product.title} ({product.barcode})",
                'views': 500,  # Görüntülenme verisi yok, örnek değer
                'sales': sales
            })
    
    most_viewed_not_sold = sorted(most_viewed_not_sold, key=lambda x: x['views'], reverse=True)[:5]

    # İndirim dönüşüm oranı
    discounted_orders = db.session.query(func.count(Order.id)).filter(
        Order.discount > 0
    ).scalar() or 0
    
    total_orders = db.session.query(func.count(Order.id)).scalar() or 1
    offer_conversion_ratio = discounted_orders / total_orders

    # Popüler filtreler (en çok satılan özelliklere göre)
    sizes = db.session.query(Order.product_size, func.count(Order.id)).group_by(
        Order.product_size
    ).order_by(func.count(Order.id).desc()).first()
    
    colors = db.session.query(Order.product_color, func.count(Order.id)).group_by(
        Order.product_color
    ).order_by(func.count(Order.id).desc()).first()
    
    popular_filters = [
        'Fiyat Artan',
        f'Beden: {sizes[0] if sizes else "38"}',
        f'Renk: {colors[0] if colors else "Siyah"}'
    ]

    # ---------------------------------------------------
    # 9) Tahmin ve Öneri Sistemleri
    # ---------------------------------------------------
    # Gelecek ay satış tahmini (son 3 ayın ortalamasına göre)
    three_months_ago = datetime.now() - timedelta(days=90)
    last_three_months_sales = db.session.query(
        func.sum(Order.amount)
    ).filter(
        Order.order_date >= three_months_ago
    ).scalar() or 0
    
    predicted_next_month_sales = last_three_months_sales / 3

    # İade riski yüksek ürünler
    risky_products = db.session.query(
        ReturnProduct.model_number,
        func.count(ReturnProduct.id).label('return_count')
    ).group_by(ReturnProduct.model_number).order_by(
        func.count(ReturnProduct.id).desc()
    ).limit(5).all()
    
    predicted_return_risk_products = []
    for product, count in risky_products:
        risk = 'Yüksek' if count > 5 else 'Orta'
        predicted_return_risk_products.append({
            'product': product,
            'risk': risk
        })

    # Stok yenileme önerileri
    low_stock_products = db.session.query(Product).filter(
        Product.quantity < 10
    ).order_by(Product.quantity).limit(5).all()
    
    restock_suggestions = []
    for product in low_stock_products:
        # Son siparişe göre tahmini yenileme tarihi
        last_order = db.session.query(Order).filter(
            Order.product_barcode == product.barcode
        ).order_by(Order.order_date.desc()).first()
        
        if last_order:
            suggested_date = (last_order.order_date + timedelta(days=30)).strftime('%Y-%m-%d')
            restock_suggestions.append({
                'product': f"{product.title} ({product.barcode})",
                'suggested_date': suggested_date
            })

    # ---------------------------------------------------
    # 10) Anlık Veri ve Canlı Takip
    # ---------------------------------------------------
    # İşlemdeki siparişler
    current_processing_orders = db.session.query(func.count(Order.id)).filter(
        Order.status == 'Processing'
    ).scalar() or 0

    # Saatlik satış verisi
    today = datetime.now().date()
    hours = range(9, 12)  # 09:00-11:00 arası
    live_sales_data = []
    
    for hour in hours:
        sales_count = db.session.query(func.count(Order.id)).filter(
            func.date(Order.order_date) == today,
            func.extract('hour', Order.order_date) == hour
        ).scalar() or 0
        
        live_sales_data.append({
            'hour': f"{hour:02d}:00",
            'sales': sales_count
        })

    # Kargodaki siparişler
    shipping_in_transit = db.session.query(func.count(Order.id)).filter(
        Order.status == 'Shipping'
    ).scalar() or 0

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