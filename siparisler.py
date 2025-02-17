
from flask import Blueprint, render_template, request, jsonify
from models import db, Order, Product
from datetime import datetime
import json

siparisler_bp = Blueprint('siparisler_bp', __name__)

@siparisler_bp.route('/yeni-siparis', methods=['GET', 'POST'])
def yeni_siparis():
    if request.method == 'POST':
        try:
            data = request.form
            order_items = json.loads(data.get('order_items', '[]'))
            
            if not order_items:
                return jsonify({'success': False, 'message': 'Sipariş öğeleri bulunamadı!'})

            # Yeni sipariş oluştur
            new_order = Order(
                customer_name=data.get('customer_name'),
                customer_surname=data.get('customer_surname'),
                customer_address=data.get('customer_address'),
                order_date=datetime.now(),
                status=data.get('status', 'new'),
                details=json.dumps(order_items),
                quantity=sum(item['quantity'] for item in order_items),
                amount=sum(item['total'] for item in order_items)
            )

            db.session.add(new_order)
            db.session.commit()

            return jsonify({'success': True, 'order_id': new_order.id})

        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'message': str(e)})

    return render_template('yeni_siparis.html')

@siparisler_bp.route('/api/product/<barcode>')
def get_product(barcode):
    try:
        product = Product.query.filter_by(barcode=barcode).first()
        if product:
            return jsonify({
                'success': True,
                'product': {
                    'barcode': product.barcode,
                    'title': product.title,
                    'product_main_id': product.product_main_id,
                    'color': product.color,
                    'size': product.size,
                    'images': product.images,
                    'sale_price': float(product.sale_price or 0),
                    'quantity': product.quantity
                }
            })
        return jsonify({'success': False, 'message': 'Ürün bulunamadı'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
