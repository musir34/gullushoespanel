
from flask import render_template, request, Blueprint
from models import Order

all_orders_service_bp = Blueprint('all_orders_service', __name__)

@all_orders_service_bp.route('/order-list/all', methods=['GET'])
def get_all_orders():
    """
    Retrieve and display all orders with pagination and search functionality
    """
    # Get page parameters
    page = int(request.args.get('page', 1))
    per_page = 50
    search = request.args.get('search')

    # Build query
    orders_query = Order.query

    # Apply search filter if provided
    if search:
        orders_query = orders_query.filter(Order.order_number.ilike(f'%{search}%'))

    # Apply sorting and limit
    orders_query = (orders_query
                   .order_by(Order.order_date.desc())
                   .limit(100000))

    # Paginate results
    paginated_orders = orders_query.paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )

    # Process order details
    orders = paginated_orders.items
    for order in orders:
        skus = order.merchant_sku.split(', ') if order.merchant_sku else []
        barcodes = order.product_barcode.split(', ') if order.product_barcode else []

        # Ensure equal length lists
        max_length = max(len(skus), len(barcodes))
        skus.extend([''] * (max_length - len(skus)))
        barcodes.extend([''] * (max_length - len(barcodes)))

        order.details = [{'sku': sku, 'barcode': barcode} 
                        for sku, barcode in zip(skus, barcodes)]

    return render_template(
        'order_list.html',
        orders=orders,
        page=page,
        total_pages=paginated_orders.pages,
        total_orders_count=paginated_orders.total
    )
