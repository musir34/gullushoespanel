
from flask import Blueprint, render_template, request, session, redirect, url_for
from models import db, UserLog, User
from login_logout import roles_required
from datetime import datetime, timedelta
import json

user_logs_bp = Blueprint('user_logs', __name__)

def log_user_action(action, details=None, force_log=False):
    """Kullanıcı aksiyonlarını loglamak için yardımcı fonksiyon"""
    if 'user_id' in session or force_log:
        user_id = session.get('user_id')
        user_role = session.get('role', 'anonymous')
        
        # İşlem tipini ve sayfayı ayır
        action_parts = action.split(': ', 1)
        action_type = action_parts[0] if len(action_parts) > 1 else action
        action_page = action_parts[1] if len(action_parts) > 1 else ''
        
        # Log detaylarını daha okunaklı formatta düzenle
        extended_details = {
            'İşlem Tipi': action_type,
            'Sayfa': action_page,
            'Kullanıcı Rolü': user_role,
            'HTTP Metodu': request.method,
            'Parametreler': dict(request.args) if request.args else None,
            'Tarayıcı': request.user_agent.browser,
            'Platform': request.user_agent.platform,
            'Referrer': request.referrer.split('/')[-1] if request.referrer else None
        }
        
        if details:
            if isinstance(details, dict):
                extended_details.update({k.replace('_', ' ').title(): v for k, v in details.items()})
            else:
                extended_details['Ek Detaylar'] = details
        
        new_log = UserLog(
            user_id=user_id,
            action=action,
            details=json.dumps(extended_details),
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
