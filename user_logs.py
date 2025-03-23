
from flask import Blueprint, render_template, request, session, redirect, url_for
from models import db, UserLog, User
from login_logout import roles_required
from datetime import datetime, timedelta
import json

user_logs_bp = Blueprint('user_logs', __name__)

def log_user_action(action, details=None):
    """Kullanıcı aksiyonlarını loglamak için yardımcı fonksiyon"""
    if 'user_id' in session:
        new_log = UserLog(
            user_id=session['user_id'],
            action=action,
            details=json.dumps(details) if details else None,
            ip_address=request.remote_addr,
            page_url=request.url
        )
        db.session.add(new_log)
        db.session.commit()

@user_logs_bp.route('/user-logs')
@roles_required('admin', 'manager')
def view_logs():
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    # Filtreleme parametreleri
    user_id = request.args.get('user_id', type=int)
    action = request.args.get('action')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    # Sorgu oluşturma
    query = UserLog.query.join(User)
    
    if user_id:
        query = query.filter(UserLog.user_id == user_id)
    if action:
        query = query.filter(UserLog.action.ilike(f'%{action}%'))
    if start_date:
        query = query.filter(UserLog.timestamp >= datetime.strptime(start_date, '%Y-%m-%d'))
    if end_date:
        query = query.filter(UserLog.timestamp <= datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1))
    
    # Sayfalama
    logs = query.order_by(UserLog.timestamp.desc()).paginate(page=page, per_page=per_page)
    users = User.query.all()
    
    return render_template('user_logs.html', logs=logs, users=users)
