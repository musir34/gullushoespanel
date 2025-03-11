
from flask import Blueprint, render_template, request, jsonify
from models import Order, db
from cache_config import redis_client
import json
import logging
from sqlalchemy import desc
from datetime import datetime

# Loglama ayarları
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.FileHandler('all_orders_service.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Blueprint tanımlaması
all_orders_service_bp = Blueprint('all_orders_service', __name__)

@all_orders_service_bp.route('/all-orders', methods=['GET'])
def get_all_orders():
    """
    Tüm siparişleri sayfalama ve arama işlevleriyle gösterme ve önbellekleme
    """
    cache_key = f"orders_page_{request.args.get('page', 1)}_{request.args.get('search', '')}"
    try:
        cached_data = redis_client.get(cache_key)
        if cached_data:
            return cached_data
    except Exception as e:
        # Redis hatası durumunda logla ve devam et
        logging.warning(f"Redis önbellek erişim hatası: {str(e)}")
    
    # Sayfa parametrelerini al
    page = int(request.args.get('page', 1))
    per_page = 50
    search_query = request.args.get('search', '')
    
    # Temel sorgu oluşturma
    query = Order.query
    
    # Arama sorgusu varsa filtrele
    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(
            (Order.order_number.ilike(search_term)) |
            (Order.product_barcode.ilike(search_term)) |
            (Order.customer_name.ilike(search_term)) |
            (Order.customer_surname.ilike(search_term)) |
            (Order.product_name.ilike(search_term))
        )
    
    # Sıralama ve sayfalama
    query = query.order_by(desc(Order.order_date))
    paginated_orders = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Sonuçları al
    orders = paginated_orders.items
    total_orders = paginated_orders.total
    total_pages = paginated_orders.pages
    
    # Sipariş detaylarını işle
    orders_list = []
    for order in orders:
        order_dict = {
            'id': order.id,
            'order_number': order.order_number,
            'order_date': order.order_date.strftime('%Y-%m-%d %H:%M') if order.order_date else '',
            'status': order.status,
            'product_barcode': order.product_barcode,
            'product_name': order.product_name,
            'product_size': order.product_size,
            'product_color': order.product_color,
            'customer_name': f"{order.customer_name} {order.customer_surname}",
            'amount': order.amount,
            'shipping_barcode': order.shipping_barcode,
            'cargo_provider_name': order.cargo_provider_name
        }
        orders_list.append(order_dict)
    
    # Şablonu oluştur
    result = render_template(
        'order_list.html',
        orders=orders,
        page=page,
        total_pages=total_pages,
        total_orders_count=total_orders,
        search_query=search_query
    )
    
    # Önbellekle
    try:
        redis_client.setex(cache_key, 300, result)  # 5 dakika önbellek
    except Exception as e:
        logger.warning(f"Redis önbellekleme hatası: {str(e)}")
        
    return result

@all_orders_service_bp.route('/api/all-orders', methods=['GET'])
def get_all_orders_api():
    """
    Tüm siparişleri JSON formatında döndür (API endpoint)
    """
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    search_query = request.args.get('search', '')
    
    # Temel sorgu oluşturma
    query = Order.query
    
    # Arama sorgusu varsa filtrele
    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(
            (Order.order_number.ilike(search_term)) |
            (Order.product_barcode.ilike(search_term)) |
            (Order.customer_name.ilike(search_term)) |
            (Order.customer_surname.ilike(search_term)) |
            (Order.product_name.ilike(search_term))
        )
    
    # Sıralama ve sayfalama
    query = query.order_by(desc(Order.order_date))
    paginated_orders = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Sonuçları al
    orders = paginated_orders.items
    total_orders = paginated_orders.total
    total_pages = paginated_orders.pages
    
    # Sipariş detaylarını işle
    orders_list = []
    for order in orders:
        order_dict = {
            'id': order.id,
            'order_number': order.order_number,
            'order_date': order.order_date.strftime('%Y-%m-%d %H:%M') if order.order_date else '',
            'status': order.status,
            'product_barcode': order.product_barcode,
            'product_name': order.product_name,
            'product_size': order.product_size,
            'product_color': order.product_color,
            'customer_name': f"{order.customer_name} {order.customer_surname}",
            'amount': order.amount,
            'shipping_barcode': order.shipping_barcode,
            'cargo_provider_name': order.cargo_provider_name
        }
        orders_list.append(order_dict)
    
    # JSON yanıt oluştur
    response = {
        'orders': orders_list,
        'page': page,
        'per_page': per_page,
        'total_orders': total_orders,
        'total_pages': total_pages
    }
    
    return jsonify(response)
