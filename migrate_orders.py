
from flask import Blueprint, jsonify, request, flash, redirect, url_for
import logging

migrate_orders_bp = Blueprint('migrate_orders', __name__)

@migrate_orders_bp.route('/migrate-orders', methods=['POST'])
def migrate_orders():
    try:
        flash("Bu özellik şu anda devre dışı bırakılmıştır.", 'warning')
    except Exception as e:
        logging.error(f"Bir hata oluştu: {e}")
        flash(f"İşlem sırasında hata oluştu: {str(e)}", 'danger')
    
    return redirect(url_for('home.home'))
