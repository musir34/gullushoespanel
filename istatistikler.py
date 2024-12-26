
from flask import Blueprint, render_template, request
from models import Order, db, SiparisFisi, DailyStats
from sqlalchemy import func, extract
from datetime import datetime, timedelta
import json

istatistikler_bp = Blueprint('istatistikler', __name__)

def save_daily_stats():
    """Günlük istatistikleri hesapla ve kaydet"""
    today = datetime.now().date()
    
    # Günlük sipariş sayısı ve gelir
    orders = db.session.query(Order).filter(func.date(Order.order_date) == today).all()
    order_count = len(orders)
    total_revenue = sum(order.amount for order in orders if order.amount)
    
    # Üretim istatistikleri
    production = db.session.query(SiparisFisi).filter(
        func.date(SiparisFisi.created_date) == today
    ).all()
    
    daily_production = sum(p.toplam_adet for p in production)
    
    # En çok üretilen ürünler
    top_products = db.session.query(
        SiparisFisi.urun_model_kodu,
        func.sum(SiparisFisi.toplam_adet).label('toplam')
    ).group_by(SiparisFisi.urun_model_kodu)\
     .order_by(func.sum(SiparisFisi.toplam_adet).desc())\
     .limit(10).all()

    # Renk dağılımı
    color_distribution = db.session.query(
        SiparisFisi.renk,
        func.sum(SiparisFisi.toplam_adet).label('toplam')
    ).group_by(SiparisFisi.renk)\
     .order_by(func.sum(SiparisFisi.toplam_adet).desc()).all()

    # Beden dağılımı
    size_stats = {
        '35': sum(p.beden_35 for p in production),
        '36': sum(p.beden_36 for p in production),
        '37': sum(p.beden_37 for p in production),
        '38': sum(p.beden_38 for p in production),
        '39': sum(p.beden_39 for p in production),
        '40': sum(p.beden_40 for p in production),
        '41': sum(p.beden_41 for p in production)
    }

    # Sipariş durumları
    pending_orders = db.session.query(func.count(Order.id))\
        .filter(Order.status == 'pending').scalar() or 0
    completed_orders = db.session.query(func.count(Order.id))\
        .filter(Order.status == 'completed').scalar() or 0

    # İstatistikleri kaydet
    stats = DailyStats(
        date=today,
        order_count=order_count,
        total_revenue=total_revenue,
        total_products=daily_production,
        product_stats=dict(top_products),
        color_stats=dict(color_distribution),
        size_stats=size_stats,
        daily_production=daily_production,
        pending_orders=pending_orders,
        completed_orders=completed_orders
    )
    
    db.session.add(stats)
    db.session.commit()

@istatistikler_bp.route('/istatistikler')
def istatistikler():
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

    # Sipariş istatistikleri
    orders = Order.query.filter(
        func.date(Order.order_date).between(start_date, end_date)
    ).all()

    # Üretim istatistikleri
    production = SiparisFisi.query.filter(
        func.date(SiparisFisi.created_date).between(start_date, end_date)
    ).all()

    # Günlük veriler
    dates = []
    order_counts = []
    production_counts = []
    revenues = []
    
    current_date = start_date
    while current_date <= end_date:
        dates.append(current_date.strftime('%Y-%m-%d'))
        
        # O günün siparişleri
        daily_orders = [o for o in orders if o.order_date.date() == current_date]
        order_counts.append(len(daily_orders))
        
        # O günün üretimi
        daily_production = [p for p in production if p.created_date.date() == current_date]
        production_count = sum(p.toplam_adet for p in daily_production)
        production_counts.append(production_count)
        
        # O günün geliri
        daily_revenue = sum(o.amount for o in daily_orders if o.amount)
        revenues.append(daily_revenue)
        
        current_date += timedelta(days=1)

    # Beden dağılımı
    size_distribution = {
        '35': sum(p.beden_35 for p in production),
        '36': sum(p.beden_36 for p in production),
        '37': sum(p.beden_37 for p in production),
        '38': sum(p.beden_38 for p in production),
        '39': sum(p.beden_39 for p in production),
        '40': sum(p.beden_40 for p in production),
        '41': sum(p.beden_41 for p in production)
    }

    # Sipariş durumları
    total_pending = len([o for o in orders if o.status == 'pending'])
    total_completed = len([o for o in orders if o.status == 'completed'])

    # İstatistikleri getir
    stats = DailyStats.query\
        .filter(DailyStats.date.between(start_date, end_date))\
        .order_by(DailyStats.date.desc())\
        .all()

    # Veri hazırlığı
    dates = []
    order_counts = []
    revenues = []
    production_counts = []
    size_distribution = {str(i): 0 for i in range(35, 42)}
    total_pending = 0
    total_completed = 0

    for stat in stats:
        dates.append(stat.date.strftime('%Y-%m-%d'))
        order_counts.append(stat.order_count)
        revenues.append(stat.total_revenue)
        production_counts.append(stat.daily_production)
        total_pending += stat.pending_orders
        total_completed += stat.completed_orders
        
        # Beden dağılımını topla
        for size, count in stat.size_stats.items():
            size_distribution[size] += count

    return render_template('istatistikler.html',
                         start_date=start_date,
                         end_date=end_date,
                         dates=dates,
                         order_counts=order_counts,
                         revenues=revenues,
                         production_counts=production_counts,
                         size_distribution=size_distribution,
                         total_pending=total_pending,
                         total_completed=total_completed)

@istatistikler_bp.route('/save-stats', methods=['POST'])
def manual_save_stats():
    save_daily_stats()
    return {'message': 'İstatistikler kaydedildi'}, 200
