from flask import Blueprint, render_template, request, jsonify, send_file, abort
from datetime import datetime, timedelta
import logging
import pandas as pd
import io

from sqlalchemy import func
from models import db, Order

# Pydantic ile input validasyonu için:
from pydantic import BaseModel, ValidationError, confloat
from typing import Dict

financial_service_bp = Blueprint('financial_service', __name__)

# Logger ayarları
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # DEBUG seviyesi, hata ayıklama için daha ayrıntılı loglar
if not logger.handlers:
    file_handler = logging.FileHandler('financial_service.log')
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

# Pydantic şeması: Hesaplama endpoint’i için giriş verilerinin doğrulanması
class ProfitCalculationInput(BaseModel):
    shipping_cost: confloat(ge=0)
    labor_cost: confloat(ge=0)
    packaging_cost: confloat(ge=0)
    exchange_rate: confloat(gt=0)
    barcode_costs: Dict[str, confloat(ge=0)]

def get_date_range():
    """
    Sorgu parametrelerinden 'start_date' ve 'end_date' değerlerini alır.
    Parametreler eksik veya format hatalı ise son 30 günün tarih aralığını döndürür.
    """
    now = datetime.now()
    default_start = now - timedelta(days=30)
    logger.debug("Şu anki tarih: %s, Varsayılan başlangıç tarihi: %s", now, default_start)

    start_str = request.args.get('start_date')
    end_str = request.args.get('end_date')
    logger.debug("Gelen start_date: %s, end_date: %s", start_str, end_str)

    if not start_str or not end_str:
        logger.debug("Tarih parametreleri eksik, varsayılan değerler kullanılacak.")
        return default_start, now

    try:
        start_date = datetime.strptime(start_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_str, '%Y-%m-%d')
        if start_date > end_date:
            logger.warning("Başlangıç tarihi (%s) bitiş tarihinden (%s) sonra, yer değiştiriliyor.", start_date, end_date)
            start_date, end_date = end_date, start_date
    except ValueError as ve:
        logger.warning("Tarih parametreleri yanlış formatta; varsayılan tarih aralığı kullanılacak. Hata: %s", ve)
        return default_start, now

    logger.debug("Kullanılacak tarih aralığı: %s - %s", start_date, end_date)
    return start_date, end_date

def get_order_summary_by_barcode(start_date, end_date):
    """
    Order tablosunu barkod bazında gruplayarak:
      - Sipariş sayısı (order_count)
      - Toplam adet (total_quantity)
      - Toplam tutar (total_amount)
    hesaplar.
    """
    try:
        logger.debug("Veritabanı sorgusu başlatılıyor: %s - %s tarih aralığı için", start_date, end_date)
        query = (
            db.session.query(
                Order.product_barcode.label('barcode'),
                func.count(Order.id).label('order_count'),
                func.sum(Order.quantity).label('total_quantity'),
                func.sum(Order.amount).label('total_amount')
            )
            .filter(Order.order_date >= start_date, Order.order_date <= end_date)
            .group_by(Order.product_barcode)
        )
        results = query.all()
        logger.debug("Sorgu sonucu: %s", results)
    except Exception as e:
        logger.exception("Veritabanı sorgusu sırasında hata oluştu.")
        raise e

    summary_list = []
    for row in results:
        barcode = row.barcode if row.barcode is not None else "N/A"
        order_count = int(row.order_count) if row.order_count is not None else 0
        total_quantity = int(row.total_quantity) if row.total_quantity is not None else 0
        total_amount = float(row.total_amount) if row.total_amount is not None else 0.0
        avg_order_quantity = total_quantity / order_count if order_count > 0 else 0

        summary_item = {
            'barcode': barcode,
            'order_count': order_count,
            'total_quantity': total_quantity,
            'total_amount': total_amount,
            'avg_order_quantity': avg_order_quantity
        }
        logger.debug("Eklenen summary item: %s", summary_item)
        summary_list.append(summary_item)
    return summary_list

@financial_service_bp.route('/financial-summary', methods=['GET'])
def financial_summary():
    """
    Barkod bazlı finansal özet sayfasını oluşturur ve HTML template'e gönderir.
    """
    try:
        start_date, end_date = get_date_range()
        data = get_order_summary_by_barcode(start_date, end_date)
        current_rate = 27.0  # Örnek döviz kuru
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        logger.debug("Financial summary hazırlanıyor: Tarih aralığı %s - %s, Döviz kuru: %s", start_date, end_date, current_rate)

        return render_template(
            'financial_summary.html',
            data=data,
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d'),
            current_rate=current_rate,
            now=now_str
        )
    except Exception as e:
        logger.exception("Finansal özet hazırlanırken hata meydana geldi.")
        abort(500, description="Finansal özet oluşturulurken bir hata meydana geldi.")

@financial_service_bp.route('/api/hesapla-kar', methods=['POST'])
def hesapla_kar():
    """
    POST ile alınan JSON verisi üzerinden barkod bazında kâr hesaplaması yapar.
    Beklenen JSON formatı:
    {
      "shipping_cost": float,
      "labor_cost": float,
      "packaging_cost": float,
      "exchange_rate": float,
      "barcode_costs": { "barcode1": float, "barcode2": float, ... }
    }
    """
    try:
        json_data = request.get_json()
        if not json_data:
            logger.error("POST isteğinde JSON verisi alınamadı.")
            return jsonify({'success': False, 'error': 'JSON verisi alınamadı.'}), 400

        logger.debug("Gelen JSON verisi: %s", json_data)
        try:
            input_data = ProfitCalculationInput(**json_data)
        except ValidationError as ve:
            logger.warning("JSON doğrulama hatası: %s", ve.json())
            return jsonify({'success': False, 'error': 'Girdi verilerinde hata mevcut.'}), 400

        shipping_cost = input_data.shipping_cost
        labor_cost = input_data.labor_cost
        packaging_cost = input_data.packaging_cost
        exchange_rate = input_data.exchange_rate
        barcode_costs = input_data.barcode_costs

        logger.debug("Maliyet parametreleri: shipping_cost=%s, labor_cost=%s, packaging_cost=%s, exchange_rate=%s", 
                     shipping_cost, labor_cost, packaging_cost, exchange_rate)
        logger.debug("Barkod maliyetleri: %s", barcode_costs)

        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        logger.debug("Kullanılacak tarih aralığı: %s - %s", start_date, end_date)
        summary_list = get_order_summary_by_barcode(start_date, end_date)

        results_list = []
        total_revenue = 0.0
        total_cost = 0.0
        total_profit = 0.0

        for item in summary_list:
            barcode = item['barcode']
            total_quantity = item['total_quantity']
            total_amount = float(item['total_amount'])

            try:
                unit_cost_usd = float(barcode_costs.get(barcode, 0))
            except (ValueError, TypeError) as e:
                logger.warning("Barkod maliyet dönüşüm hatası: %s", e)
                unit_cost_usd = 0

            production_cost = unit_cost_usd * exchange_rate * total_quantity
            common_cost = (shipping_cost + labor_cost + packaging_cost) * total_quantity
            model_total_cost = production_cost + common_cost
            profit = total_amount - model_total_cost
            profit_margin = (profit / total_amount * 100) if total_amount != 0 else 0

            result_item = {
                'barcode': barcode,
                'order_count': item['order_count'],
                'total_quantity': total_quantity,
                'avg_order_quantity': item['avg_order_quantity'],
                'profit': profit,
                'profit_margin': profit_margin
            }
            logger.debug("Hesaplanan sonuç: %s", result_item)
            results_list.append(result_item)

            total_revenue += total_amount
            total_cost += model_total_cost
            total_profit += profit

        total_profit_margin = (total_profit / total_revenue * 100) if total_revenue != 0 else 0
        summary = {
            'total_revenue': total_revenue,
            'total_cost': total_cost,
            'total_profit': total_profit,
            'total_profit_margin': total_profit_margin
        }
        logger.debug("Genel özet: %s", summary)

        return jsonify({
            'success': True,
            'results': results_list,
            'summary': summary
        })

    except Exception as e:
        db.session.rollback()
        logger.exception("Kâr hesaplama sırasında beklenmedik hata oluştu.")
        return jsonify({'success': False, 'error': 'Kâr hesaplama sırasında hata meydana geldi.'}), 500

@financial_service_bp.route('/api/download-financial-report', methods=['GET'])
def download_financial_report():
    """
    Barkod bazlı finansal raporu Excel dosyası olarak indirir.
    """
    try:
        start_date, end_date = get_date_range()
        logger.debug("Excel raporu için tarih aralığı: %s - %s", start_date, end_date)
        summary_list = get_order_summary_by_barcode(start_date, end_date)
        df = pd.DataFrame(summary_list)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Barkod_Raporu', index=False)
            summary_df = pd.DataFrame({
                'Metrik': ['Toplam Satış Tutarı', 'Toplam Sipariş Sayısı', 'Toplam Ürün Adedi'],
                'Değer': [
                    df['total_amount'].sum() if 'total_amount' in df.columns else 0,
                    df['order_count'].sum() if 'order_count' in df.columns else 0,
                    df['total_quantity'].sum() if 'total_quantity' in df.columns else 0
                ]
            })
            summary_df.to_excel(writer, sheet_name='Ozet', index=False)

        output.seek(0)
        file_name = f"Barkod_Finansal_Rapor_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.xlsx"
        logger.debug("Excel raporu dosya adı: %s", file_name)
        return send_file(
            output,
            as_attachment=True,
            download_name=file_name,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        db.session.rollback()
        logger.exception("Finansal rapor hazırlanırken hata meydana geldi.")
        return jsonify({'success': False, 'error': 'Finansal rapor oluşturulurken hata meydana geldi.'}), 500
