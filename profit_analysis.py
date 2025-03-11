from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from sqlalchemy import func, and_, or_, desc, text
from models import db, Product, Order, SiparisFisi, ProfitData, ProductCost
from datetime import datetime, timedelta, date
import logging
import json
from apscheduler.schedulers.background import BackgroundScheduler

# Loglama ayarları
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.FileHandler('profit_analysis.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

profit_analysis_bp = Blueprint('profit_analysis', __name__)
scheduler = BackgroundScheduler()

def update_product_costs():
    """
    Ürün maliyetlerini SiparisFisi tablosundan güncelleyen fonksiyon
    """
    try:
        logger.info("Ürün maliyetleri güncelleniyor...")

        # SiparisFisi'nden tüm maliyet bilgilerini çek
        siparis_fisiler = SiparisFisi.query.all()

        updated_count = 0
        new_count = 0

        for fis in siparis_fisiler:
            # Tüm barkod alanlarını kontrol et
            for size in range(35, 42):
                barkod_key = f'barkod_{size}'
                if hasattr(fis, barkod_key) and getattr(fis, barkod_key):
                    barcode = getattr(fis, barkod_key)
                    if barcode:
                        # Birim maliyeti hesapla
                        if fis.toplam_adet > 0:
                            birim_maliyet = fis.cift_basi_fiyat if fis.cift_basi_fiyat else (fis.toplam_fiyat / fis.toplam_adet if fis.toplam_fiyat else 0)

                            # Mevcut kayıt kontrolü
                            existing_cost = ProductCost.query.filter_by(barcode=barcode).first()
                            if existing_cost:
                                existing_cost.cost_price = birim_maliyet
                                existing_cost.source = 'siparis_fisi'
                                existing_cost.updated_at = datetime.now()
                                updated_count += 1
                            else:
                                # Yeni kayıt oluştur
                                new_cost = ProductCost(
                                    barcode=barcode,
                                    cost_price=birim_maliyet,
                                    source='siparis_fisi'
                                )
                                db.session.add(new_cost)
                                new_count += 1

        # Ürün tablosundan tahmini maliyetleri ekle (SiparisFisi'nde olmayan ürünler için)
        all_products = Product.query.all()
        estimate_count = 0

        for product in all_products:
            if not ProductCost.query.filter_by(barcode=product.barcode).first():
                # Tahmini maliyet: liste fiyatının %60'ı
                estimated_cost = product.list_price * 0.6 if product.list_price else 0
                if estimated_cost > 0:
                    new_cost = ProductCost(
                        barcode=product.barcode,
                        cost_price=estimated_cost,
                        source='calculated'
                    )
                    db.session.add(new_cost)
                    estimate_count += 1

        db.session.commit()
        logger.info(f"Ürün maliyetleri güncellendi: {updated_count} güncellendi, {new_count} yeni eklendi, {estimate_count} tahmini eklendi")
        return True
    except Exception as e:
        logger.error(f"Ürün maliyetleri güncellenirken hata: {str(e)}")
        db.session.rollback()
        return False

def calculate_daily_profit(target_date=None):
    """
    Günlük kar hesaplama ve kaydetme
    """
    if not target_date:
        target_date = date.today() - timedelta(days=1)  # Varsayılan olarak dün

    try:
        logger.info(f"{target_date} tarihi için günlük kar hesaplanıyor...")

        # Belirtilen tarih için siparişleri al
        start_datetime = datetime.combine(target_date, datetime.min.time())
        end_datetime = datetime.combine(target_date, datetime.max.time())

        orders = Order.query.filter(
            Order.order_date.between(start_datetime, end_datetime),
            Order.status != 'Cancelled'
        ).all()

        if not orders:
            logger.info(f"{target_date} tarihinde sipariş bulunamadı")
            return

        # Toplam değerler
        total_revenue = 0
        total_cost = 0
        total_profit = 0
        order_count = len(orders)
        total_quantity = 0

        # Ürün bazlı veriler
        product_profits = {}
        model_profits = {}
        color_profits = {}
        size_profits = {}

        # Tüm siparişleri işle
        for order in orders:
            barcode = order.product_barcode
            if not barcode:
                continue

            # Satış verileri
            sale_price = order.amount if order.amount else 0
            quantity = order.quantity if order.quantity else 1
            total_quantity += quantity

            # Maliyet verisini ProductCost tablosundan al
            product_cost = ProductCost.query.filter_by(barcode=barcode).first()
            cost_price = product_cost.cost_price if product_cost else 0

            if cost_price == 0:
                # Maliyet verisi yoksa Product tablosundan tahmini hesapla
                product = Product.query.filter_by(barcode=barcode).first()
                if product and product.list_price:
                    cost_price = product.list_price * 0.6

            # Kar hesaplama
            total_sale = sale_price * quantity
            total_cost_this_order = cost_price * quantity
            profit = total_sale - total_cost_this_order

            # Genel toplamları güncelle
            total_revenue += total_sale
            total_cost += total_cost_this_order
            total_profit += profit

            # Ürün bazlı kar bilgisini topla
            if barcode not in product_profits:
                product_profits[barcode] = {
                    'barcode': barcode,
                    'product_name': order.product_name,
                    'order_count': 0,
                    'quantity': 0,
                    'total_revenue': 0,
                    'total_cost': 0,
                    'total_profit': 0
                }

            product_profits[barcode]['order_count'] += 1
            product_profits[barcode]['quantity'] += quantity
            product_profits[barcode]['total_revenue'] += total_sale
            product_profits[barcode]['total_cost'] += total_cost_this_order
            product_profits[barcode]['total_profit'] += profit

            # Model bazlı kar bilgisini topla
            model_code = order.product_model_code or 'Belirsiz'
            if model_code not in model_profits:
                model_profits[model_code] = {
                    'model_code': model_code,
                    'order_count': 0,
                    'quantity': 0,
                    'total_revenue': 0,
                    'total_cost': 0,
                    'total_profit': 0
                }

            model_profits[model_code]['order_count'] += 1
            model_profits[model_code]['quantity'] += quantity
            model_profits[model_code]['total_revenue'] += total_sale
            model_profits[model_code]['total_cost'] += total_cost_this_order
            model_profits[model_code]['total_profit'] += profit

            # Renk bazlı kar bilgisini topla
            color = order.product_color or 'Belirsiz'
            if color not in color_profits:
                color_profits[color] = {
                    'color': color,
                    'order_count': 0,
                    'quantity': 0,
                    'total_revenue': 0,
                    'total_cost': 0,
                    'total_profit': 0
                }

            color_profits[color]['order_count'] += 1
            color_profits[color]['quantity'] += quantity
            color_profits[color]['total_revenue'] += total_sale
            color_profits[color]['total_cost'] += total_cost_this_order
            color_profits[color]['total_profit'] += profit

            # Beden bazlı kar bilgisini topla
            size = order.product_size or 'Belirsiz'
            if size not in size_profits:
                size_profits[size] = {
                    'size': size,
                    'order_count': 0,
                    'quantity': 0,
                    'total_revenue': 0,
                    'total_cost': 0,
                    'total_profit': 0
                }

            size_profits[size]['order_count'] += 1
            size_profits[size]['quantity'] += quantity
            size_profits[size]['total_revenue'] += total_sale
            size_profits[size]['total_cost'] += total_cost_this_order
            size_profits[size]['total_profit'] += profit

        # Kar marjlarını hesapla
        overall_profit_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0

        # Günlük kar verisini kaydet
        daily_data = ProfitData.query.filter_by(
            date=target_date,
            data_type='daily',
            reference_id='all'
        ).first()

        if daily_data:
            # Varsa güncelle
            daily_data.order_count = order_count
            daily_data.quantity = total_quantity
            daily_data.total_revenue = total_revenue
            daily_data.total_cost = total_cost
            daily_data.total_profit = total_profit
            daily_data.profit_margin = overall_profit_margin
        else:
            # Yoksa oluştur
            daily_data = ProfitData(
                date=target_date,
                data_type='daily',
                reference_id='all',
                reference_name='Günlük Toplam',
                order_count=order_count,
                quantity=total_quantity,
                total_revenue=total_revenue,
                total_cost=total_cost,
                total_profit=total_profit,
                profit_margin=overall_profit_margin
            )
            db.session.add(daily_data)

        # Ürün bazlı verileri kaydet
        for barcode, data in product_profits.items():
            profit_margin = (data['total_profit'] / data['total_revenue'] * 100) if data['total_revenue'] > 0 else 0

            product_data = ProfitData.query.filter_by(
                date=target_date,
                data_type='product',
                reference_id=barcode
            ).first()

            if product_data:
                # Varsa güncelle
                product_data.order_count = data['order_count']
                product_data.quantity = data['quantity']
                product_data.total_revenue = data['total_revenue']
                product_data.total_cost = data['total_cost']
                product_data.total_profit = data['total_profit']
                product_data.profit_margin = profit_margin
            else:
                # Yoksa oluştur
                product_data = ProfitData(
                    date=target_date,
                    data_type='product',
                    reference_id=barcode,
                    reference_name=data['product_name'],
                    order_count=data['order_count'],
                    quantity=data['quantity'],
                    total_revenue=data['total_revenue'],
                    total_cost=data['total_cost'],
                    total_profit=data['total_profit'],
                    profit_margin=profit_margin
                )
                db.session.add(product_data)

        # Model bazlı verileri kaydet
        for model_code, data in model_profits.items():
            profit_margin = (data['total_profit'] / data['total_revenue'] * 100) if data['total_revenue'] > 0 else 0

            model_data = ProfitData.query.filter_by(
                date=target_date,
                data_type='model',
                reference_id=model_code
            ).first()

            if model_data:
                model_data.order_count = data['order_count']
                model_data.quantity = data['quantity']
                model_data.total_revenue = data['total_revenue']
                model_data.total_cost = data['total_cost']
                model_data.total_profit = data['total_profit']
                model_data.profit_margin = profit_margin
            else:
                model_data = ProfitData(
                    date=target_date,
                    data_type='model',
                    reference_id=model_code,
                    reference_name=model_code,
                    order_count=data['order_count'],
                    quantity=data['quantity'],
                    total_revenue=data['total_revenue'],
                    total_cost=data['total_cost'],
                    total_profit=data['total_profit'],
                    profit_margin=profit_margin
                )
                db.session.add(model_data)

        # Renk bazlı verileri kaydet
        for color, data in color_profits.items():
            profit_margin = (data['total_profit'] / data['total_revenue'] * 100) if data['total_revenue'] > 0 else 0

            color_data = ProfitData.query.filter_by(
                date=target_date,
                data_type='color',
                reference_id=color
            ).first()

            if color_data:
                color_data.order_count = data['order_count']
                color_data.quantity = data['quantity']
                color_data.total_revenue = data['total_revenue']
                color_data.total_cost = data['total_cost']
                color_data.total_profit = data['total_profit']
                color_data.profit_margin = profit_margin
            else:
                color_data = ProfitData(
                    date=target_date,
                    data_type='color',
                    reference_id=color,
                    reference_name=color,
                    order_count=data['order_count'],
                    quantity=data['quantity'],
                    total_revenue=data['total_revenue'],
                    total_cost=data['total_cost'],
                    total_profit=data['total_profit'],
                    profit_margin=profit_margin
                )
                db.session.add(color_data)

        # Beden bazlı verileri kaydet
        for size, data in size_profits.items():
            profit_margin = (data['total_profit'] / data['total_revenue'] * 100) if data['total_revenue'] > 0 else 0

            size_data = ProfitData.query.filter_by(
                date=target_date,
                data_type='size',
                reference_id=size
            ).first()

            if size_data:
                size_data.order_count = data['order_count']
                size_data.quantity = data['quantity']
                size_data.total_revenue = data['total_revenue']
                size_data.total_cost = data['total_cost']
                size_data.total_profit = data['total_profit']
                size_data.profit_margin = profit_margin
            else:
                size_data = ProfitData(
                    date=target_date,
                    data_type='size',
                    reference_id=size,
                    reference_name=size,
                    order_count=data['order_count'],
                    quantity=data['quantity'],
                    total_revenue=data['total_revenue'],
                    total_cost=data['total_cost'],
                    total_profit=data['total_profit'],
                    profit_margin=profit_margin
                )
                db.session.add(size_data)

        db.session.commit()
        logger.info(f"{target_date} için kar hesaplama tamamlandı")
        return True
    except Exception as e:
        logger.error(f"{target_date} için kar hesaplamada hata: {str(e)}")
        db.session.rollback()
        return False

def run_historical_profit_calculation(days=30):
    """
    Geçmiş günler için kar hesaplama
    """
    logger.info(f"Son {days} gün için geçmiş kar hesaplama başlatılıyor...")

    # Önce ürün maliyetlerini güncelle
    update_product_costs()

    # Belirtilen gün sayısı kadar geçmiş için hesapla
    today = date.today()
    success_count = 0

    for day_offset in range(1, days + 1):
        target_date = today - timedelta(days=day_offset)
        if calculate_daily_profit(target_date):
            success_count += 1

    logger.info(f"Geçmiş kar hesaplama tamamlandı. Toplam {success_count}/{days} gün hesaplandı.")
    return success_count

def schedule_daily_profit_calculation():
    """
    Günlük kar hesaplama zamanlaması
    """
    # Her gün gece 02:00'de çalışacak şekilde ayarla
    scheduler.add_job(
        lambda: calculate_daily_profit(date.today() - timedelta(days=1)),
        'cron',
        hour=2,
        minute=0,
        id='daily_profit_calculation'
    )

    # Her hafta Pazartesi 03:00'da ürün maliyetlerini güncelle
    scheduler.add_job(
        update_product_costs,
        'cron',
        day_of_week='mon',
        hour=3,
        minute=0,
        id='product_cost_update'
    )

    if not scheduler.running:
        scheduler.start()

    logger.info("Kar hesaplama zamanlayıcısı başlatıldı.")

@profit_analysis_bp.route('/kar-analizi')
def profit_analysis_page():
    """
    Kar analizi ana sayfasını render eder
    """
    return render_template('profit_analysis.html')

@profit_analysis_bp.route('/api/kar-verileri')
def get_profit_data():
    """
    Belirtilen tarih aralığında kar analizini döner (API endpoint)
    """
    try:
        # Tarih aralığını al
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        filter_type = request.args.get('filter_type', 'all')  # all, product, category

        # Varsayılan olarak son 30 gün
        now = datetime.now()
        if start_date_str and end_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'success': False, 'error': 'Tarih formatı geçersiz. YYYY-MM-DD formatını kullanın.'})
        else:
            start_date = (now - timedelta(days=30)).date()
            end_date = now.date()

        logger.info(f"Kar analizi tarih aralığı: {start_date} - {end_date}")

        # Önce veritabanında kayıtlı verileri kontrol et
        daily_profits = ProfitData.query.filter(
            ProfitData.date.between(start_date, end_date),
            ProfitData.data_type == 'daily'
        ).order_by(ProfitData.date.desc()).all()

        # Model bazlı veriler
        model_profits = ProfitData.query.filter(
            ProfitData.date.between(start_date, end_date),
            ProfitData.data_type == 'model'
        ).all()

        # Günlük bazda model verilerini topla
        models_data = {}
        for mp in model_profits:
            model_code = mp.reference_id
            if model_code not in models_data:
                models_data[model_code] = {
                    'model_code': model_code,
                    'total_sale': 0,
                    'total_cost': 0,
                    'total_profit': 0,
                    'total_quantity': 0,
                    'profit_margin': 0,
                    'count': 0
                }

            models_data[model_code]['total_sale'] += mp.total_revenue
            models_data[model_code]['total_cost'] += mp.total_cost
            models_data[model_code]['total_profit'] += mp.total_profit
            models_data[model_code]['total_quantity'] += mp.quantity
            models_data[model_code]['count'] += mp.order_count

        # Profit margin hesapla
        for model in models_data:
            if models_data[model]['total_sale'] > 0:
                models_data[model]['profit_margin'] = (models_data[model]['total_profit'] / models_data[model]['total_sale'] * 100)

        # Listeye çevir ve sırala
        model_profits_list = list(models_data.values())
        model_profits_list.sort(key=lambda x: x['total_profit'], reverse=True)

        # Renk bazlı veriler
        color_profits = ProfitData.query.filter(
            ProfitData.date.between(start_date, end_date),
            ProfitData.data_type == 'color'
        ).all()

        # Günlük bazda renk verilerini topla
        colors_data = {}
        for cp in color_profits:
            color = cp.reference_id
            if color not in colors_data:
                colors_data[color] = {
                    'color': color,
                    'total_sale': 0,
                    'total_cost': 0,
                    'total_profit': 0,
                    'total_quantity': 0,
                    'profit_margin': 0,
                    'count': 0
                }

            colors_data[color]['total_sale'] += cp.total_revenue
            colors_data[color]['total_cost'] += cp.total_cost
            colors_data[color]['total_profit'] += cp.total_profit
            colors_data[color]['total_quantity'] += cp.quantity
            colors_data[color]['count'] += cp.order_count

        # Profit margin hesapla
        for color in colors_data:
            if colors_data[color]['total_sale'] > 0:
                colors_data[color]['profit_margin'] = (colors_data[color]['total_profit'] / colors_data[color]['total_sale'] * 100)

        # Listeye çevir ve sırala
        color_profits_list = list(colors_data.values())
        color_profits_list.sort(key=lambda x: x['total_profit'], reverse=True)

        # Beden bazlı veriler
        size_profits = ProfitData.query.filter(
            ProfitData.date.between(start_date, end_date),
            ProfitData.data_type == 'size'
        ).all()

        # Günlük bazda beden verilerini topla
        sizes_data = {}
        for sp in size_profits:
            size = sp.reference_id
            if size not in sizes_data:
                sizes_data[size] = {
                    'size': size,
                    'total_sale': 0,
                    'total_cost': 0,
                    'total_profit': 0,
                    'total_quantity': 0,
                    'profit_margin': 0,
                    'count': 0
                }

            sizes_data[size]['total_sale'] += sp.total_revenue
            sizes_data[size]['total_cost'] += sp.total_cost
            sizes_data[size]['total_profit'] += sp.total_profit
            sizes_data[size]['total_quantity'] += sp.quantity
            sizes_data[size]['count'] += sp.order_count

        # Profit margin hesapla
        for size in sizes_data:
            if sizes_data[size]['total_sale'] > 0:
                sizes_data[size]['profit_margin'] = (sizes_data[size]['total_profit'] / sizes_data[size]['total_sale'] * 100)

        # Listeye çevir ve sırala
        size_profits_list = list(sizes_data.values())
        size_profits_list.sort(key=lambda x: x['total_profit'], reverse=True)

        # Ürün bazlı veriler - en karlı ürünleri al
        product_profits = ProfitData.query.filter(
            ProfitData.date.between(start_date, end_date),
            ProfitData.data_type == 'product'
        ).all()

        # Ürün verilerini topla
        products_data = {}
        for pp in product_profits:
            barcode = pp.reference_id
            if barcode not in products_data:
                products_data[barcode] = {
                    'barcode': barcode,
                    'product_name': pp.reference_name,
                    'total_sale': 0,
                    'total_cost': 0,
                    'total_profit': 0,
                    'quantity': 0,
                    'profit_margin': 0,
                    'order_count': 0
                }

            products_data[barcode]['total_sale'] += pp.total_revenue
            products_data[barcode]['total_cost'] += pp.total_cost
            products_data[barcode]['total_profit'] += pp.total_profit
            products_data[barcode]['quantity'] += pp.quantity
            products_data[barcode]['order_count'] += pp.order_count

        # Profit margin hesapla
        for barcode in products_data:
            if products_data[barcode]['total_sale'] > 0:
                products_data[barcode]['profit_margin'] = (products_data[barcode]['total_profit'] / products_data[barcode]['total_sale'] * 100)

        # Listeye çevir
        product_profits_list = list(products_data.values())

        # Günlük kar verilerini formatla
        daily_profits_list = []
        for dp in daily_profits:
            daily_profits_list.append({
                'date': dp.date.strftime('%Y-%m-%d'),
                'total_sale': dp.total_revenue,
                'total_cost': dp.total_cost,
                'total_profit': dp.total_profit,
                'order_count': dp.order_count,
                'profit_margin': dp.profit_margin
            })

        # Toplam değerleri hesapla
        total_revenue = sum(dp.total_revenue for dp in daily_profits) if daily_profits else 0
        total_cost = sum(dp.total_cost for dp in daily_profits) if daily_profits else 0
        total_profit = sum(dp.total_profit for dp in daily_profits) if daily_profits else 0
        overall_profit_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0

        response = {
            'success': True,
            'summary': {
                'total_revenue': round(total_revenue, 2),
                'total_cost': round(total_cost, 2),
                'total_profit': round(total_profit, 2),
                'overall_profit_margin': round(overall_profit_margin, 2),
                'order_count': sum(dp.order_count for dp in daily_profits) if daily_profits else 0,
                'date_range': {
                    'start_date': start_date.strftime('%Y-%m-%d'),
                    'end_date': end_date.strftime('%Y-%m-%d')
                }
            },
            'product_profits': product_profits_list,
            'model_profits': model_profits_list,
            'color_profits': color_profits_list,
            'size_profits': size_profits_list,
            'daily_profits': daily_profits_list
        }

        return jsonify(response)

    except Exception as e:
        logger.exception(f"Kar analizi API hatası: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@profit_analysis_bp.route('/api/kar-ozet')
def get_profit_summary():
    """
    Genel kar özeti bilgilerini döner
    """
    try:
        # Son 1 ay, 3 ay, 6 ay ve 1 yıl için kar özetleri
        now = datetime.now().date()

        periods = {
            'last_month': now - timedelta(days=30),
            'last_3_months': now - timedelta(days=90),
            'last_6_months': now - timedelta(days=180),
            'last_year': now - timedelta(days=365)
        }

        summaries = {}

        for period_name, start_date in periods.items():
            # Özet verileri veritabanından al
            daily_profits = ProfitData.query.filter(
                ProfitData.date.between(start_date, now),
                ProfitData.data_type == 'daily'
            ).all()

            total_revenue = sum(dp.total_revenue for dp in daily_profits) if daily_profits else 0
            total_cost = sum(dp.total_cost for dp in daily_profits) if daily_profits else 0
            total_profit = sum(dp.total_profit for dp in daily_profits) if daily_profits else 0
            overall_profit_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0
            order_count = sum(dp.order_count for dp in daily_profits) if daily_profits else 0

            summaries[period_name] = {
                'total_revenue': round(total_revenue, 2),
                'total_cost': round(total_cost, 2),
                'total_profit': round(total_profit, 2),
                'profit_margin': round(overall_profit_margin, 2),
                'order_count': order_count
            }

        return jsonify({
            'success': True,
            'summaries': summaries
        })

    except Exception as e:
        logger.exception(f"Kar özeti API hatası: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@profit_analysis_bp.route('/api/en-karli-urunler')
def get_most_profitable_products():
    """
    En karlı ürünleri döner (son 6 ay için)
    """
    try:
        now = datetime.now().date()
        start_date = now - timedelta(days=180)  # Son 6 ay

        # En karlı ürünleri veritabanından al
        product_profits = ProfitData.query.filter(
            ProfitData.date.between(start_date, now),
            ProfitData.data_type == 'product'
        ).all()

        # Ürün verilerini topla
        products_data = {}
        for pp in product_profits:
            barcode = pp.reference_id
            if barcode not in products_data:
                products_data[barcode] = {
                    'barcode': barcode,
                    'product_name': pp.reference_name,
                    'total_sale': 0,
                    'total_cost': 0,
                    'total_profit': 0,
                    'quantity': 0,
                    'profit_margin': 0,
                    'orders': 0
                }

            products_data[barcode]['total_sale'] += pp.total_revenue
            products_data[barcode]['total_cost'] += pp.total_cost
            products_data[barcode]['total_profit'] += pp.total_profit
            products_data[barcode]['quantity'] += pp.quantity
            products_data[barcode]['orders'] += pp.order_count

        # Profit margin hesapla
        for barcode in products_data:
            if products_data[barcode]['total_sale'] > 0:
                products_data[barcode]['profit_margin'] = (products_data[barcode]['total_profit'] / products_data[barcode]['total_sale'] * 100)

        # Listeye çevir, en karlıdan en az karlıya sırala ve en karlı 20 ürünü al
        products_list = list(products_data.values())
        products_list.sort(key=lambda x: x['total_profit'], reverse=True)
        top_profitable = products_list[:20] if len(products_list) > 20 else products_list

        return jsonify({
            'success': True,
            'products': top_profitable
        })

    except Exception as e:
        logger.exception(f"En karlı ürünler API hatası: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@profit_analysis_bp.route('/api/manuel-hesaplama', methods=['POST'])
def manual_calculation():
    """
    Manuel kar hesaplama işlemini başlatan endpoint
    """
    try:
        data = request.get_json()
        days = data.get('days', 30)

        # Asenkron olarak çalıştırmak için bir iş planla (gerçek uygulamada Celery vb. kullanılabilir)
        success_count = run_historical_profit_calculation(days)

        return jsonify({
            'success': True,
            'message': f'{days} gün için hesaplama tamamlandı. {success_count} gün başarıyla hesaplandı.',
            'processed_days': success_count
        })

    except Exception as e:
        logger.exception(f"Manuel hesaplama hatası: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@profit_analysis_bp.route('/api/maliyet-guncelle', methods=['POST'])
def update_costs():
    """
    Manuel olarak ürün maliyetlerini güncelleme endpoint'i
    """
    try:
        result = update_product_costs()
        if result:
            return jsonify({
                'success': True,
                'message': 'Ürün maliyetleri başarıyla güncellendi.'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Ürün maliyetleri güncellenirken bir hata oluştu.'
            })

    except Exception as e:
        logger.exception(f"Maliyet güncelleme hatası: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

# Zamanlayıcıyı başlat
def init_scheduler():
    """
    Uygulama başladığında zamanlayıcıyı başlat
    """
    schedule_daily_profit_calculation()