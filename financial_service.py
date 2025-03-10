from flask import Blueprint, render_template, request, flash, jsonify, send_file, url_for
from datetime import datetime, timedelta
import logging
import pandas as pd
import io

from sqlalchemy import func
from models import db, Order, Product

financial_service_bp = Blueprint('financial_service', __name__)

# Loglama ayarları
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
file_handler = logging.FileHandler('financial_service.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

@financial_service_bp.route('/financial-summary', methods=['GET'])
def financial_summary():
    """
    Kar Analizi sayfası. Bu sayfada, barkod üzerinden Order + Product tablolarını
    birleştirerek model kodu, görsel, adet, tutar bilgilerini toplayacağız.
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)

    start_date_str = request.args.get('start_date', start_date.strftime('%Y-%m-%d'))
    end_date_str = request.args.get('end_date', end_date.strftime('%Y-%m-%d'))

    # Tarih formatı kontrol
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
    except ValueError:
        flash("Geçersiz tarih formatı. Varsayılan 30 güne dönüldü.", "warning")
        start_date = datetime.now() - timedelta(days=30)
        end_date = datetime.now()

    # Barkod bazında JOIN:
    # Order.product_barcode == Product.barcode
    # Sonra model koduna (Product.product_main_id) göre GRUPLAYARAK
    # SUM(Order.quantity) ve SUM(Order.amount) topluyoruz.
    # Görseli ise max(Product.images) ile alıyoruz (ya da group by'a ekleyebilirsiniz).
    query = (
        db.session.query(
            Product.product_main_id.label('model_code'),
            func.sum(Order.quantity).label('count'),
            func.sum(Order.amount).label('total_amount'),
            func.max(Product.images).label('image_url')
        )
        .outerjoin(Order, Product.barcode == Order.product_barcode)
        .filter(Order.order_date >= start_date, Order.order_date <= end_date)
        .group_by(Product.product_main_id)
    )

    results = query.all()

    # Şablona göndermek için python listesi
    model_data = []
    for row in results:
        # row.model_code, row.count, row.total_amount, row.image_url
        # (model_code => Product.product_main_id)
        # (image_url => Product.images)
        logger.info(f"Barkod JOIN => model_code: {row.model_code}, adet: {row.count}, amount: {row.total_amount}, image: {row.image_url}")
        model_data.append({
            'model_id': row.model_code if row.model_code else 'N/A',
            'count': row.count if row.count else 0,
            'total_amount': row.total_amount if row.total_amount else 0.0,
            'image_url': row.image_url  # None veya dosya yolu olabilir
        })

    # Döviz kuru ve zaman
    current_rate = 27.00
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    return render_template(
        'financial_summary.html',
        start_date=start_date_str,
        end_date=end_date_str,
        current_rate=current_rate,
        now=now_str,
        model_data=model_data
    )


@financial_service_bp.route('/api/hesapla-kar', methods=['POST'])
def hesapla_kar():
    """
    Front-end'den gelen POST ile kargo, işçilik, paketleme, dolar kuru, model_costs (birim USD) bilgilerini alıp,
    barkoda göre Order + Product JOIN yaparak model kodu bazında kâr hesaplar.
    """
    try:
        data = request.json
        model_costs = data.get('model_costs', {})  # { 'modelA': 5, 'modelB': 3.2, ... }
        shipping_cost = float(data.get('shipping_cost', 0))
        labor_cost = float(data.get('labor_cost', 0))
        packaging_cost = float(data.get('packaging_cost', 0))
        exchange_rate = float(data.get('exchange_rate', 0))

        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)

        # Aynı barkod join:
        # Product.barcode == Order.product_barcode
        # model koduna (product_main_id) göre grupluyoruz
        query = (
            db.session.query(
                Product.product_main_id.label('model_code'),
                func.sum(Order.quantity).label('count'),
                func.sum(Order.amount).label('total_amount')
            )
            .outerjoin(Order, Product.barcode == Order.product_barcode)
            .filter(Order.order_date >= start_date, Order.order_date <= end_date)
            .group_by(Product.product_main_id)
        )
        results = query.all()

        results_list = []
        total_revenue = 0.0
        total_cost = 0.0
        total_profit = 0.0

        for row in results:
            # row.model_code => model_id
            model_id = row.model_code if row.model_code else 'N/A'
            count = row.count if row.count else 0
            revenue = row.total_amount if row.total_amount else 0.0

            # Front-end'deki birim maliyet (USD)
            unit_cost_usd = float(model_costs.get(model_id, 0))

            # Üretim maliyeti => unit_cost_usd * exchange_rate * count
            production_cost = unit_cost_usd * exchange_rate * count

            # Ortak maliyet => (kargo + işçilik + paketleme) * count
            total_common_cost = (shipping_cost + labor_cost + packaging_cost) * count

            # Toplam maliyet
            model_total_cost = production_cost + total_common_cost

            # Kâr
            model_profit = revenue - model_total_cost
            # Marj
            profit_margin = (model_profit / revenue * 100) if revenue else 0

            results_list.append({
                'model_id': model_id,
                'count': count,
                'profit': model_profit,
                'profit_margin': profit_margin
            })

            total_revenue += revenue
            total_cost += model_total_cost
            total_profit += model_profit

        total_profit_margin = (total_profit / total_revenue * 100) if total_revenue else 0

        summary = {
            'total_revenue': total_revenue,
            'total_cost': total_cost,
            'total_profit': total_profit,
            'total_profit_margin': total_profit_margin
        }

        return jsonify({'success': True, 'results': results_list, 'summary': summary})

    except Exception as e:
        logger.error(f"Barkod bazlı kâr hesaplamada hata: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@financial_service_bp.route('/api/download-financial-report', methods=['GET'])
def download_financial_report():
    """
    Excel raporu. Barkod JOIN ile her satırı kaydedip rapor oluşturur.
    """
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        start_date_str = request.args.get('start_date', start_date.strftime('%Y-%m-%d'))
        end_date_str = request.args.get('end_date', end_date.strftime('%Y-%m-%d'))

        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        except ValueError:
            pass

        # Detay: Product + Order barkod eşleşmesi
        # Tek tek kaydı alabiliriz (group_by olmadan).
        orders = (
            db.session.query(Order, Product)
            .outerjoin(Product, Product.barcode == Order.product_barcode)
            .filter(Order.order_date >= start_date, Order.order_date <= end_date)
            .all()
        )

        data_list = []
        for ord_obj, prod_obj in orders:
            data_list.append({
                "orderNumber": ord_obj.order_number,
                "orderDate": ord_obj.order_date.isoformat() if ord_obj.order_date else None,
                "barcode": ord_obj.product_barcode,
                "quantity": ord_obj.quantity if ord_obj.quantity else 0,
                "amount": ord_obj.amount if ord_obj.amount else 0.0,
                "model_code": prod_obj.product_main_id if prod_obj else None,
                "image_url": prod_obj.images if prod_obj else None
            })

        df = pd.DataFrame(data_list)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Barkod_Raporu', index=False)

            summary_df = pd.DataFrame({
                'Metrik': ['Toplam Satış Tutarı', 'Toplam Sipariş Sayısı'],
                'Değer': [
                    df['amount'].sum() if 'amount' in df.columns else 0,
                    len(df)
                ]
            })
            summary_df.to_excel(writer, sheet_name='Özet', index=False)

        output.seek(0)
        file_name = f"Barkod_Finansal_Rapor_{start_date_str}_{end_date_str}.xlsx"
        return send_file(
            output,
            download_name=file_name,
            as_attachment=True,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        logger.error(f"Barkod rapor oluşturulurken hata: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
