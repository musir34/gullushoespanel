
from flask import Blueprint, render_template, request
from models import Order, db, SiparisFisi, DailyStats
from sqlalchemy import func, extract
from datetime import datetime, timedelta
import json

istatistikler_bp = Blueprint('istatistikler', __name__)

def save_daily_stats():
    """Günlük istatistikleri hesapla ve kaydet"""
    today = datetime.now().date()
    
    # Günlük sipariş sayısı
    order_count = db.session.query(func.count(Order.id))\
        .filter(func.date(Order.order_date) == today).scalar()

    # En çok üretilen ürünler
    top_products = db.session.query(
        SiparisFisi.urun_model_kodu,
        func.sum(SiparisFisi.toplam_adet).label('toplam')
    ).group_by(SiparisFisi.urun_model_kodu)\
     .order_by(func.sum(SiparisFisi.toplam_adet).desc())\
     .limit(5).all()

    # Renk dağılımı
    color_distribution = db.session.query(
        SiparisFisi.renk,
        func.sum(SiparisFisi.toplam_adet).label('toplam')
    ).group_by(SiparisFisi.renk)\
     .order_by(func.sum(SiparisFisi.toplam_adet).desc()).all()

    # İstatistikleri JSON formatında kaydet
    stats = DailyStats(
        date=today,
        order_count=order_count,
        product_stats=dict(top_products),
        color_stats=dict(color_distribution)
    )
    db.session.add(stats)
    db.session.commit()

@istatistikler_bp.route('/istatistikler')
def istatistikler():
    # Filtreleme parametreleri
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if start_date:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    else:
        start_date = datetime.now().date() - timedelta(days=7)
        
    if end_date:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    else:
        end_date = datetime.now().date()

    # İstatistikleri getir
    stats = DailyStats.query\
        .filter(DailyStats.date.between(start_date, end_date))\
        .order_by(DailyStats.date.desc())\
        .all()

    # Verileri topla
    dates = []
    order_counts = []
    product_totals = {}
    color_totals = {}

    for stat in stats:
        dates.append(stat.date.strftime('%Y-%m-%d'))
        order_counts.append(stat.order_count)
        
        # Ürün istatistiklerini topla
        for product, count in stat.product_stats.items():
            product_totals[product] = product_totals.get(product, 0) + count
            
        # Renk istatistiklerini topla    
        for color, count in stat.color_stats.items():
            color_totals[color] = color_totals.get(color, 0) + count

    # En çok üretilen 5 ürün
    top_products = sorted(product_totals.items(), key=lambda x: x[1], reverse=True)[:5]
    
    return render_template('istatistikler.html',
                         günlük_siparisler=list(zip(dates, order_counts)),
                         top_products=top_products,
                         color_distribution=color_totals.items(),
                         start_date=start_date,
                         end_date=end_date)

# Her gün gece yarısı çalışacak bir görev eklenebilir
# Bu örnekte manuel olarak /save-stats endpoint'i ile kaydediyoruz
@istatistikler_bp.route('/save-stats', methods=['POST'])
def manual_save_stats():
    save_daily_stats()
    return {'message': 'İstatistikler kaydedildi'}, 200
