from flask import Blueprint, render_template, current_app
from sqlalchemy import func
from models import SiparisFisi, ReturnOrder, Order, Product, db
import pandas as pd
import plotly.express as px
import plotly
import json

analysis_bp = Blueprint('analysis', __name__, url_prefix='/analysis')

def fetch_sales_data():
    """
    Veritabanından, Orders tablosundan günlük toplam satış verilerini çek.
    Her gün için; siparişin oluşturulma tarihini ve o günün toplam satış tutarını getirir.
    """
    sales_data = db.session.query(
        func.date(Order.order_date).label('date'),
        func.sum(Order.amount).label('total_sales')
    ).filter(Order.status != 'Cancelled')\
      .group_by(func.date(Order.order_date))\
      .order_by(func.date(Order.order_date))\
      .all()
    return sales_data

def fetch_return_data():
    """
    Veritabanından, ReturnOrder tablosundan günlük iade sayısını çek.
    Her gün için; iade talep tarihine göre iade sayısını ve toplam tutarı getirir.
    """
    returns_data = db.session.query(
        func.date(ReturnOrder.return_date).label('date'),
        func.count(ReturnOrder.id).label('return_count'),
        func.sum(ReturnOrder.refund_amount).label('total_refund')
    ).filter(ReturnOrder.status == 'Approved')\
      .group_by(func.date(ReturnOrder.return_date))\
      .order_by(func.date(ReturnOrder.return_date))\
      .all()
    return returns_data

@analysis_bp.route('/sales', methods=['GET'])
def sales_analysis():
    """
    Günlük satış analizi sayfası:
    1. Veritabanından günlük satış verilerini çek.
    2. Pandas DataFrame'e aktar ve tarih sütununu datetime formatına çevir.
    3. Tarihe göre veriyi sırala.
    4. Plotly kullanarak interaktif bir çizgi grafik oluştur.
    5. Grafiği JSON formatında template'e gönder.
    """
    try:
        # 1. Veritabanından satış verilerini çek
        sales_data = fetch_sales_data()

        # 2. Veriyi DataFrame'e dönüştür
        sales_df = pd.DataFrame(sales_data, columns=['date', 'total_sales'])

        # Eğer veri yoksa, kullanıcıya mesaj gönder
        if sales_df.empty:
            return render_template('analysis/sales.html', message="Satış verisi bulunamadı.", chart_json=None)

        # 3. Tarih sütununu datetime formatına çevir ve sırala
        sales_df['date'] = pd.to_datetime(sales_df['date'])
        sales_df.sort_values('date', inplace=True)

        # 4. Plotly ile çizgi grafik oluştur:
        # x ekseni: Tarih, y ekseni: Toplam satış
        fig = px.line(
            sales_df, 
            x='date', 
            y='total_sales', 
            title='Günlük Satış Analizi',
            labels={'date': 'Tarih', 'total_sales': 'Toplam Satış (TL)'}
        )

        # 5. Grafiği JSON formatına çevir
        chart_json = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

        return render_template('analysis/sales.html', chart_json=chart_json, message=None)
    except Exception as ex:
        current_app.logger.error("Sales analysis hatası: %s", ex)
        return render_template('analysis/sales.html', message="Satış analizi oluşturulurken hata oluştu.", chart_json=None), 500

@analysis_bp.route('/returns', methods=['GET'])
def returns_analysis():
    """
    Günlük iade analizi sayfası:
    1. Veritabanından günlük iade verilerini çek.
    2. Verileri Pandas DataFrame'e aktar, tarih sütununu datetime formatına çevir.
    3. Tarihe göre veriyi sırala.
    4. Plotly kullanarak interaktif bir sütun grafik oluştur.
    5. Grafiği JSON formatında template'e gönder.
    """
    try:
        # 1. Veritabanından iade verilerini çek
        returns_data = fetch_return_data()

        # 2. Veriyi DataFrame'e dönüştür
        returns_df = pd.DataFrame(returns_data, columns=['date', 'return_count'])

        # Eğer veri yoksa, kullanıcıya mesaj gönder
        if returns_df.empty:
            return render_template('analysis/returns.html', message="İade verisi bulunamadı.", chart_json=None)

        # 3. Tarih sütununu datetime formatına çevir ve sırala
        returns_df['date'] = pd.to_datetime(returns_df['date'])
        returns_df.sort_values('date', inplace=True)

        # 4. Plotly ile sütun grafik oluştur:
        # x ekseni: Tarih, y ekseni: İade sayısı
        fig = px.bar(
            returns_df, 
            x='date', 
            y='return_count', 
            title='Günlük İade Analizi',
            labels={'date': 'Tarih', 'return_count': 'İade Sayısı'}
        )

        # 5. Grafiği JSON formatına çevir
        chart_json = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

        return render_template('analysis/returns.html', chart_json=chart_json, message=None)
    except Exception as ex:
        current_app.logger.error("Returns analysis hatası: %s", ex)
        return render_template('analysis/returns.html', message="İade analizi oluşturulurken hata oluştu.", chart_json=None), 500
