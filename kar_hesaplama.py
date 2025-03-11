
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from models import db, Order, Product
from sqlalchemy import func, desc, distinct, text
import requests
import json
from datetime import datetime, timedelta
import logging

# Loglama ayarları
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.FileHandler('kar_hesaplama.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

kar_hesaplama_bp = Blueprint('kar_hesaplama', __name__)

@kar_hesaplama_bp.route('/kar-hesaplama', methods=['GET'])
def kar_hesaplama():
    """
    Kar hesaplama sayfasını gösterir.
    Tüm siparişlerden ürün barkodlarına göre gruplandırılmış satış verilerini getirir.
    """
    try:
        # Tarih filtreleme için varsayılan değerler (son 30 gün)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        start_date_str = request.args.get('start_date', start_date.strftime('%Y-%m-%d'))
        end_date_str = request.args.get('end_date', end_date.strftime('%Y-%m-%d'))
        
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        except ValueError:
            logger.warning("Geçersiz tarih formatı. Varsayılan 30 günlük aralık kullanılıyor.")
            start_date = datetime.now() - timedelta(days=30)
            end_date = datetime.now()
        
        # Barkod bazlı satış verilerini getiren SQL sorgusu
        sql_query = """
        WITH exploded_orders AS (
            SELECT 
                o.id,
                o.order_number,
                o.order_date,
                o.amount,
                o.quantity,
                unnest(string_to_array(o.product_barcode, ', ')) as product_barcode
            FROM 
                orders o
            WHERE 
                o.status != 'Cancelled'
                AND o.product_barcode IS NOT NULL
                AND o.product_barcode != ''
                AND o.order_date BETWEEN :start_date AND :end_date
        )
        SELECT 
            eo.product_barcode,
            COUNT(DISTINCT eo.order_number) as order_count,
            SUM(eo.quantity) as total_quantity,
            SUM(eo.amount) as total_amount,
            MAX(p.images) as image_url,
            MAX(p.title) as product_title
        FROM 
            exploded_orders eo
        LEFT JOIN 
            products p ON eo.product_barcode = p.barcode
        GROUP BY 
            eo.product_barcode
        ORDER BY 
            total_quantity DESC
        """
        
        barcode_sales = db.session.execute(
            text(sql_query), 
            {"start_date": start_date, "end_date": end_date}
        ).all()
        
        # Barkod verilerini oluşturma
        model_data = []
        total_count = 0
        
        for sale in barcode_sales:
            barcode = sale.product_barcode
            count = int(sale.total_quantity) if sale.total_quantity else 0
            total_count += count
            
            model_data.append({
                'model_id': barcode,  # Artık model_id alanını barkod için kullanıyoruz
                'count': count,
                'total_amount': float(sale.total_amount) if sale.total_amount else 0,
                'image_url': sale.image_url or "",
                'title': sale.product_title or "Ürün Adı Bulunamadı"
            })
        
        logger.info(f"Toplam {len(model_data)} farklı barkod ve {total_count} ürün bulundu.")
        
        # İşlem yoksa kullanıcıya bilgi ver
        if not model_data:
            logger.info("Kar hesaplaması için satış verisi bulunamadı.")
            flash("Seçilen tarih aralığında satış verisi bulunamadı.", "warning")
        
        # Güncel döviz kurunu al
        current_rate = get_usd_exchange_rate()
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        return render_template(
            'kar_hesaplama.html',
            model_data=model_data,
            current_rate=current_rate,
            now=now_str,
            start_date=start_date_str,
            end_date=end_date_str
        )
        
    except Exception as e:
        logger.error(f"Kar hesaplama sayfası yüklenirken hata: {e}")
        flash(f"Veriler yüklenirken bir hata oluştu: {str(e)}", "danger")
        return render_template('kar_hesaplama.html', model_data=[], current_rate=0, now=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))


@kar_hesaplama_bp.route('/api/hesapla-kar', methods=['POST'])
def hesapla_kar():
    """
    Girilen maliyetlere göre kar hesaplar
    """
    try:
        data = request.json
        
        model_costs = data.get('model_costs', {})  # artık barkod: usd_cost şeklinde
        shipping_cost = float(data.get('shipping_cost', 0))
        labor_cost = float(data.get('labor_cost', 0))
        packaging_cost = float(data.get('packaging_cost', 0))
        exchange_rate = float(data.get('exchange_rate', 0))
        
        # Tarih filtreleme için varsayılan değerler (son 30 gün)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        # Barkod bazlı satış sorgusu
        sql_query = """
        WITH exploded_orders AS (
            SELECT 
                o.id,
                o.order_number,
                o.order_date,
                o.amount,
                o.quantity,
                unnest(string_to_array(o.product_barcode, ', ')) as product_barcode
            FROM 
                orders o
            WHERE 
                o.status != 'Cancelled'
                AND o.product_barcode IS NOT NULL
                AND o.product_barcode != ''
                AND o.order_date BETWEEN :start_date AND :end_date
        )
        SELECT 
            eo.product_barcode,
            COUNT(DISTINCT eo.order_number) as order_count,
            SUM(eo.quantity) as total_quantity,
            SUM(eo.amount) as total_amount
        FROM 
            exploded_orders eo
        GROUP BY 
            eo.product_barcode
        """
        
        barcode_sales = db.session.execute(
            text(sql_query), 
            {"start_date": start_date, "end_date": end_date}
        ).all()

        # Maliyet sonuçlarını hesapla
        results = []
        total_revenue = 0
        total_cost = 0
        
        for sale in barcode_sales:
            barcode = sale.product_barcode
            if barcode not in model_costs:
                continue
                
            count = int(sale.total_quantity) if sale.total_quantity else 0
            revenue = float(sale.total_amount) if sale.total_amount else 0
            
            # Maliyeti TL'ye çevir
            cost_usd = float(model_costs.get(barcode, 0))
            cost_tl = cost_usd * exchange_rate
            
            # Toplam maliyeti hesapla (üretim maliyeti + ortak maliyetler)
            production_cost = cost_tl * count
            common_costs = (shipping_cost + labor_cost + packaging_cost) * count
            total_model_cost = production_cost + common_costs
            
            # Kar ve kar marjı hesaplama
            profit = revenue - total_model_cost
            profit_margin = (profit / revenue) * 100 if revenue > 0 else 0
            
            results.append({
                'model_id': barcode,  # Artık model_id alanını barkod için kullanıyoruz
                'count': count,
                'profit': profit,
                'profit_margin': profit_margin,
            })
            
            total_revenue += revenue
            total_cost += total_model_cost
        
        # Toplam kar ve kar marjı hesapla
        total_profit = total_revenue - total_cost
        total_profit_margin = (total_profit / total_revenue) * 100 if total_revenue > 0 else 0
        
        # Sonuçları döndür
        return jsonify({
            'success': True,
            'results': results,
            'summary': {
                'total_revenue': total_revenue,
                'total_cost': total_cost,
                'total_profit': total_profit,
                'total_profit_margin': total_profit_margin
            }
        })
    except Exception as e:
        logger.error(f"Kar hesaplanırken hata: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@kar_hesaplama_bp.route('/api/guncel-kur', methods=['GET'])
def get_current_exchange_rate():
    """
    Güncel döviz kurunu döner
    """
    try:
        rate = get_usd_exchange_rate()
        return jsonify({
            'success': True,
            'rate': rate,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
    except Exception as e:
        logger.error(f"Döviz kuru alınırken hata: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@kar_hesaplama_bp.route('/api/product-list', methods=['GET'])
def get_product_list():
    """
    Kâr hesaplamada kullanılacak ürün listesini döndürür
    Performans iyileştirmeleri ile optimize edilmiş
    """
    try:
        # Tarih filtreleme için varsayılan değerler (son 30 gün)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        # İndeksli sütunlar üzerinde çalışarak ve sınırlandırılmış veri döndürerek 
        # performansı artıran optimize edilmiş sorgu
        sql_query = """
        WITH exploded_orders AS (
            SELECT 
                o.order_number,
                o.amount,
                o.quantity,
                unnest(string_to_array(o.product_barcode, ', ')) as product_barcode
            FROM 
                orders o
            WHERE 
                o.status != 'Cancelled'
                AND o.product_barcode IS NOT NULL
                AND o.product_barcode != ''
                AND o.order_date BETWEEN :start_date AND :end_date
            LIMIT 10000  -- Aşırı büyük veri setlerini sınırla
        )
        SELECT 
            eo.product_barcode as model_id,
            COUNT(DISTINCT eo.order_number) as order_count,
            COALESCE(SUM(eo.quantity), 0) as count,
            COALESCE(SUM(eo.amount), 0) as total_amount,
            MAX(p.images) as image_url,
            MAX(p.title) as title
        FROM 
            exploded_orders eo
        LEFT JOIN 
            products p ON eo.product_barcode = p.barcode
        GROUP BY 
            eo.product_barcode
        ORDER BY 
            count DESC
        LIMIT 500  -- En çok satılan 500 ürünle sınırla - performans için önemli
        """
        
        logger.info("Ürün listesi SQL sorgusu başlatılıyor...")
        start_time = datetime.now()
        
        result = db.session.execute(text(sql_query), {"start_date": start_date, "end_date": end_date})
        
        # Daha verimli veri dönüşümü - SQL sorgusundan gelen alanlar zaten uygun isimde
        products_data = []
        for row in result:
            # Verileri sözlüğe dönüştür
            product = dict(row._mapping)
            
            # Null kontrolü yap
            if product['count'] is None:
                product['count'] = 0
            if product['total_amount'] is None:
                product['total_amount'] = 0
            if product['order_count'] is None:
                product['order_count'] = 0
            if product['image_url'] is None:
                product['image_url'] = "/static/images/default.jpg"
            if product['title'] is None:
                product['title'] = "Ürün Adı Bulunamadı"
                
            # Sadece sayısal değerlerin türünü dönüştür
            product['count'] = int(product['count'])
            product['total_amount'] = float(product['total_amount'])
            product['order_count'] = int(product['order_count'])
            
            products_data.append(product)
        
        # Performans ölçümü
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        logger.info(f"Ürün listesi sorgusu {duration:.2f} saniyede tamamlandı. {len(products_data)} ürün bulundu.")
        
        # Veri yoksa örnek bir veri gönder
        if not products_data:
            logger.warning("Hiç satış verisi bulunamadı - varsayılan test verisi gönderiliyor")
            products_data = [
                {
                    'model_id': 'TEST-1001',
                    'count': 10,
                    'total_amount': 1500.0,
                    'image_url': "/static/images/default.jpg",
                    'title': "Örnek Ürün (Veri Yok)",
                    'order_count': 5
                }
            ]
        
        return jsonify({
            'success': True,
            'products': products_data
        })
    except Exception as e:
        logger.error(f"Ürün listesi alınırken hata: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def get_usd_exchange_rate():
    """
    Güncel USD/TRY döviz kurunu getirir
    """
    try:
        # Ücretsiz bir döviz kuru API'si kullanılıyor
        response = requests.get('https://api.exchangerate-api.com/v4/latest/USD')
        data = response.json()
        return data['rates']['TRY']
    except Exception as e:
        logger.error(f"Döviz kuru API hatası: {e}")
        # API hatası durumunda varsayılan kur
        return 32.0
