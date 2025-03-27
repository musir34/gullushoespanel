
from flask import Blueprint, jsonify, request, flash, redirect, url_for
from order_status_manager import migrate_orders_to_status_tables
import logging

migrate_orders_bp = Blueprint('migrate_orders', __name__)

@migrate_orders_bp.route('/migrate-orders', methods=['POST'])
def migrate_orders():
    try:
        total_migrated = migrate_orders_to_status_tables()
        flash(f"Toplam {total_migrated} sipariş başarıyla statü tablolarına taşındı.", 'success')
    except Exception as e:
        logging.error(f"Sipariş taşıma işlemi sırasında hata: {e}")
        flash(f"Sipariş taşıma işlemi sırasında hata oluştu: {str(e)}", 'danger')
    
    return redirect(url_for('home.home'))
