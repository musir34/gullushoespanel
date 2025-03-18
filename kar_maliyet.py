from flask import Blueprint, jsonify, render_template, send_file
import logging
import pandas as pd
from models import db, Order, Product  # Modellerin hepsini tek seferde içe aktarıyoruz

# Blueprint ve logger yapılandırması
kar_maliyet_bp = Blueprint('kar_maliyet', __name__)

logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# Sabit değerler (gerekirse config üzerinden de alınabilir)
COMMISSION_RATE = 0.15     # Komisyon oranı
SHIPPING_COST = 30.0       # Kargo ücreti (TL)
PACKAGING_COST = 10.0      # Paketleme maliyeti (TL)
VAT_RATE = 0.18            # KDV oranı

def calculate_product_cost(order):
    """
    Sipariş için ürün maliyetini hesaplar.
    Eğer siparişte ürün barkodu varsa ve Product tablosunda ilgili kayıt bulunuyorsa,
    ürünün cost_try değerini döner; aksi halde order.vat_base_amount kullanılır.
    """
    try:
        base_cost = float(order.vat_base_amount or 0)
        if order.product_barcode:
            barcodes = order.product_barcode.split(', ')
            if barcodes:
                primary_barcode = barcodes[0]
                product = Product.query.filter_by(barcode=primary_barcode).first()
                if product and getattr(product, 'cost_try', None):
                    return float(product.cost_try)
        return base_cost
    except Exception as e:
        logger.error(f"Ürün maliyeti hesaplanırken hata (Sipariş {order.order_number}): {str(e)}")
        return 0.0

def hesapla_kar(order):
    """
    Verilen sipariş için net kâr ve kâr marjını hesaplar.
    Dönüş: (net_profit, product_cost, profit_margin)
    """
    try:
        sale_price = float(order.amount or 0)
        product_cost = calculate_product_cost(order)

        commission = sale_price * COMMISSION_RATE
        vat = sale_price * VAT_RATE

        net_profit = sale_price - (product_cost + commission + SHIPPING_COST + PACKAGING_COST + vat)
        profit_margin = (net_profit / sale_price * 100) if sale_price > 0 else 0.0

        return net_profit, product_cost, profit_margin
    except Exception as e:
        logger.error(f"Kâr hesaplamada hata (Sipariş {order.order_number}): {str(e)}")
        return 0.0, 0.0, 0.0

@kar_maliyet_bp.route('/kar_analiz', methods=['GET'])
def kar_analiz():
    """
    JSON formatında tüm siparişlerin toplam kârını ve sipariş sayısını döner.
    """
    try:
        orders = Order.query.all()
        total_profit = sum(hesapla_kar(order)[0] for order in orders)
        return jsonify({
            "toplam_kar": total_profit,
            "siparis_sayisi": len(orders)
        })
    except Exception as e:
        logger.error(f"JSON kâr analizinde hata: {str(e)}")
        return jsonify({"error": str(e)}), 500

@kar_maliyet_bp.route('/kar_analiz_sayfasi')
def kar_analiz_sayfasi():
    """
    HTML şablonuyla kâr analiz sayfasını render eder.
    Sipariş detaylarını, net kâr, ürün maliyeti ve varsa dolar cinsinden maliyet bilgisini içerir.
    """
    try:
        orders = Order.query.all()
        analysis_results = []
        total_profit = 0.0
        total_sales = 0.0

        for order in orders:
            net_profit, product_cost, profit_margin = hesapla_kar(order)
            total_profit += net_profit
            total_sales += float(order.amount or 0)

            # Dolar cinsinden maliyet bilgisi (varsa)
            if order.product_barcode:
                primary_barcode = order.product_barcode.split(', ')[0]
                product = Product.query.filter_by(barcode=primary_barcode).first()
                usd_cost = float(product.cost_usd) if product and getattr(product, 'cost_usd', None) else None
            else:
                usd_cost = None

            analysis_results.append({
                "siparis_no": order.order_number,
                "satis_fiyati": float(order.amount or 0),
                "urun_maliyeti": product_cost,
                "dolar_maliyeti": usd_cost,
                "net_kar": net_profit,
                "kar_marji": profit_margin
            })

        overall_profit_margin = (total_profit / total_sales * 100) if total_sales > 0 else 0.0

        return render_template('kar_analiz.html',
                               siparisler=analysis_results,
                               toplam_kar=total_profit,
                               toplam_satis=total_sales,
                               kar_marji=overall_profit_margin)
    except Exception as e:
        logger.error(f"Kâr analiz sayfası oluşturulurken hata: {str(e)}")
        return render_template('error.html', error=str(e))

@kar_maliyet_bp.route('/kar_analiz_excel')
def kar_analiz_excel():
    """
    Kâr analiz sonuçlarını Excel dosyası olarak oluşturur ve indirme olarak sunar.
    """
    try:
        orders = Order.query.all()
        data = []

        for order in orders:
            net_profit, product_cost, profit_margin = hesapla_kar(order)
            data.append({
                "Sipariş No": order.order_number,
                "Satış Fiyatı": order.amount,
                "Ürün Maliyeti": product_cost,
                "Net Kâr": net_profit,
                "Kâr Marjı (%)": profit_margin
            })

        df = pd.DataFrame(data)
        excel_path = "/tmp/kar_analiz.xlsx"
        df.to_excel(excel_path, index=False)

        return send_file(excel_path, as_attachment=True, download_name="kar_analiz.xlsx")
    except Exception as e:
        logger.error(f"Excel dosyası oluşturulurken hata: {str(e)}")
        return jsonify({"error": str(e)}), 500
