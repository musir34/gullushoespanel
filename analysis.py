from flask import Blueprint, render_template, current_app
from sqlalchemy import func
from extensions import db  # Aynı db instance'ını kullanıyoruz
from models import SiparisFisi, ReturnOrder, Order, Product
import pandas as pd
from configparser import ConfigParser
import plotly.express as px
import plotly
import json

analysis_bp = Blueprint('analysis', __name__, url_prefix='/analysis')

@analysis_bp.route('/sales', methods=['GET'])
def sales_analysis():
    try:
        sales_query = db.session.query(
            func.date(SiparisFisi.created_date).label('date'),
            func.sum(SiparisFisi.toplam_fiyat).label('total_sales')
        ).group_by(func.date(SiparisFisi.created_date)).all()

        df = pd.DataFrame(sales_query, columns=['date', 'total_sales'])
        if df.empty:
            return render_template('analysis/sales.html', message="Satış verisi bulunamadı.", chart_json=None)
        df['date'] = pd.to_datetime(df['date'])
        df.sort_values('date', inplace=True)

        fig = px.line(df, x='date', y='total_sales', title='Günlük Satış Analizi')
        chart_json = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

        return render_template('analysis/sales.html', chart_json=chart_json, message=None)
    except Exception as ex:
        current_app.logger.error("Sales analysis hatası: %s", ex)
        return render_template('analysis/sales.html', message="Satış analizi oluşturulurken hata oluştu.", chart_json=None), 500

@analysis_bp.route('/returns', methods=['GET'])
def returns_analysis():
    try:
        returns_query = db.session.query(
            func.date(ReturnOrder.return_date).label('date'),
            func.count(ReturnOrder.id).label('return_count')
        ).group_by(func.date(ReturnOrder.return_date)).all()

        df = pd.DataFrame(returns_query, columns=['date', 'return_count'])
        if df.empty:
            return render_template('analysis/returns.html', message="İade verisi bulunamadı.", chart_json=None)
        df['date'] = pd.to_datetime(df['date'])
        df.sort_values('date', inplace=True)

        fig = px.bar(df, x='date', y='return_count', title='Günlük İade Analizi')
        chart_json = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

        return render_template('analysis/returns.html', chart_json=chart_json, message=None)
    except Exception as ex:
        current_app.logger.error("Returns analysis hatası: %s", ex)
        return render_template('analysis/returns.html', message="İade analizi oluşturulurken hata oluştu.", chart_json=None), 500
