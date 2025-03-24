from flask import Blueprint, render_template, request, session, redirect, url_for
from flask_login import current_user
from models import db, UserLog, User
from login_logout import roles_required
from datetime import datetime, timedelta
import json
import urllib.parse
import logging

# Modül seviyesinde tanımlanan sabitler
PAGE_NAME_MAP = {
    'home': 'Ana Sayfa',
    'order_list': 'Sipariş Listesi',
    'analysis': 'Analiz Sayfası',
    'stock_report': 'Stok Raporu',
    'user_logs': 'Kullanıcı Logları',
    'product_list': 'Ürün Listesi',
    'archive': 'Arşiv',
    'login': 'Giriş',
    'register': 'Kayıt',
}

ACTION_TYPE_MAP = {
    'PAGE_VIEW': 'Sayfa Görüntüleme',
    'LOGIN': 'Giriş',
    'LOGOUT': 'Çıkış',
    'CREATE': 'Oluşturma',
    'UPDATE': 'Güncelleme',
    'DELETE': 'Silme',
    'ARCHIVE': 'Arşivleme',
    'PRINT': 'Yazdırma',
}

# Blueprint tanımlaması
user_logs_bp = Blueprint('user_logs', __name__)

def translate_page_name(page: str) -> str:
    """Sayfa adını Türkçeleştirir."""
    return PAGE_NAME_MAP.get(page, page or 'Ana Sayfa')

def translate_action_type(action: str) -> str:
    """İşlem tipini Türkçeleştirir."""
    return ACTION_TYPE_MAP.get(action, action)

def get_browser_info() -> str:
    """Kullanıcının tarayıcı bilgisini döner."""
    return request.user_agent.browser or "Bilinmiyor"

def get_platform_info() -> str:
    """Kullanıcının işletim sistemi bilgisini döner."""
    return request.user_agent.platform or "Bilinmiyor"

def extract_page_from_referrer(referrer: str) -> str:
    """Referrer URL'sinden sayfa adını çıkarır."""
    if referrer:
        parsed_url = urllib.parse.urlparse(referrer)
        page = parsed_url.path.split('/')[-1]
        return PAGE_NAME_MAP.get(page, 'Doğrudan Giriş') if page else 'Doğrudan Giriş'
    return 'Doğrudan Giriş'

def log_user_action(action: str, details: dict = None, force_log: bool = False, log_level: str = "INFO") -> None:
    """
    Kullanıcı aksiyonlarını loglamak için yardımcı fonksiyon.

    :param action: Aksiyon stringi, örn. 'PAGE_VIEW: home'
    :param details: Ek detaylar için sözlük
    :param force_log: Kullanıcı oturumu yoksa bile loglama yapılacaksa True
    :param log_level: Log seviyesi (örn. INFO, DEBUG), varsayılan "INFO"
    """
    # Flask-Login ile kullanıcı kontrolü; oturum açmamışsa force_log kontrolü yapılıyor
    if current_user.is_authenticated or force_log:
        user_id = current_user.id if current_user.is_authenticated else session.get('user_id')
        user_role = getattr(current_user, 'role', session.get('role', 'anonymous'))

        # İşlem ve sayfa bilgisini ayrıştırma
        action_parts = action.split(': ', 1)
        action_type_raw = action_parts[0]
        action_page_raw = action_parts[1] if len(action_parts) > 1 else ''

        # Çeviri işlemleri
        translated_action = translate_action_type(action_type_raw)
        translated_page = translate_page_name(action_page_raw)

        # HTTP metoduna göre işlem türünü belirleme
        if request.method == 'GET':
            islem_turu = 'Sayfa Görüntüleme'
        elif request.method == 'POST':
            islem_turu = 'Veri Güncelleme'
        else:
            islem_turu = 'Özel İşlem'

        # Temel detaylar
        extended_details = {
            'Yapılan İşlem': translated_action,
            'Ziyaret Edilen Sayfa': translated_page,
            'Kullanıcı Rolü': (
                'Yönetici' if user_role == 'admin' else 
                'Personel' if user_role == 'worker' else 
                'Yönetici Yardımcısı' if user_role == 'manager' else 
                'Ziyaretçi'
            ),
            'İşlem Türü': islem_turu,
            'Tarayıcı': get_browser_info(),
            'İşletim Sistemi': get_platform_info(),
            'Gelinen Sayfa': extract_page_from_referrer(request.referrer)
        }
        
        # Tarayıcı ve cihaz detayları
        user_agent = request.user_agent
        extended_details.update({
            'Tarayıcı Versiyonu': user_agent.version,
            'Tarayıcı Dili': request.accept_languages.best if hasattr(request, 'accept_languages') else 'Bilinmiyor',
            'Cihaz Türü': 'Mobil' if user_agent.platform in ['android', 'iphone', 'ipad'] else 'Masaüstü'
        })
        
        # İstek detayları
        request_details = {
            'HTTP Metodu': request.method,
            'İstek Parametreleri': dict(request.args),
            'İstek Başlıkları': {k: v for k, v in request.headers.items() if k.lower() not in ['cookie', 'authorization']},
            'İstek Yolu': request.path,
            'İstek Zamanı': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        }
        
        # Form verilerini ekle (hassas verileri filtreleyerek)
        if request.form:
            filtered_form = {}
            for key, value in request.form.items():
                # Hassas verileri filtrele
                if any(sensitive in key.lower() for sensitive in ['password', 'token', 'secret', 'key', 'sifre']):
                    filtered_form[key] = '***FILTERED***'
                else:
                    filtered_form[key] = value
            request_details['Form Verileri'] = filtered_form
        
        extended_details['İstek Detayları'] = request_details
        
        # Oturum bilgileri (hassas bilgileri filtreleyerek)
        if session:
            filtered_session = {}
            for key, value in session.items():
                if any(sensitive in key.lower() for sensitive in ['password', 'token', 'secret', 'key', 'sifre']):
                    filtered_session[key] = '***FILTERED***'
                else:
                    filtered_session[key] = value
            extended_details['Oturum Bilgileri'] = filtered_session

        # Kullanıcının gönderdiği ek detayları ekle
        if details:
            if isinstance(details, dict):
                # Ek detayların anahtarlarını düzenleyerek ekle
                formatted_details = {k.replace('_', ' ').title(): v for k, v in details.items()}
                extended_details['İşlem Detayları'] = formatted_details
            else:
                extended_details['Ek Detaylar'] = details

        try:
            new_log = UserLog(
                user_id=user_id,
                action=action,
                details=json.dumps(extended_details, ensure_ascii=False),
                ip_address=request.remote_addr,
                page_url=request.url
            )
            db.session.add(new_log)
            db.session.commit()
            
            # Belirli kritik işlemleri ayrıca log dosyasına da kaydedelim
            if action_type_raw in ['CREATE', 'UPDATE', 'DELETE', 'LOGIN', 'LOGOUT']:
                log_message = f"KULLANICI İŞLEMİ: {current_user.username if current_user.is_authenticated else 'Anonim'} - {action} - IP: {request.remote_addr}"
                logging.getLogger('app').info(log_message)
                
        except Exception as e:
            db.session.rollback()
            logging.error(f"Log kaydedilemedi: {e}")

@user_logs_bp.route('/user-logs')
@roles_required('admin', 'manager')
def view_logs():
    """
    Kullanıcı loglarını görüntüleyen view.
    Gelişmiş filtreleme özellikleri ile.
    """
    # Sayfalama ve gösterim ayarları
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    # Filtreleme parametrelerini çek
    user_id = request.args.get('user_id', type=int)
    action_filter = request.args.get('action')
    action_type = request.args.get('action_type')
    ip_address = request.args.get('ip_address')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    # Sorgu oluşturma
    query = UserLog.query.join(User)

    # Filtreleri uygula
    filters_applied = False
    
    if user_id:
        query = query.filter(UserLog.user_id == user_id)
        filters_applied = True
        
    if action_filter:
        query = query.filter(UserLog.action.ilike(f'%{action_filter}%'))
        filters_applied = True
        
    if action_type:
        query = query.filter(UserLog.action.like(f'{action_type}%'))
        filters_applied = True
        
    if ip_address:
        query = query.filter(UserLog.ip_address.ilike(f'%{ip_address}%'))
        filters_applied = True

    # Tarih filtresi için güvenli dönüşüm
    try:
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            query = query.filter(UserLog.timestamp >= start_date)
            filters_applied = True
    except ValueError as ve:
        logging.error(f"Başlangıç tarih formatı hatası: {ve}")
        flash(f"Başlangıç tarihi formatı hatalı: {ve}", "warning")

    try:
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(UserLog.timestamp <= end_date)
            filters_applied = True
    except ValueError as ve:
        logging.error(f"Bitiş tarih formatı hatası: {ve}")
        flash(f"Bitiş tarihi formatı hatalı: {ve}", "warning")

    # Log kullanıcının bu sayfayı ziyaret etmesini
    if current_user.is_authenticated:
        log_details = {
            'filters': {
                'user_id': user_id,
                'action': action_filter,
                'action_type': action_type,
                'ip_address': ip_address,
                'start_date': start_date_str,
                'end_date': end_date_str
            },
            'filters_applied': filters_applied
        }
        log_user_action(
            action=f"PAGE_VIEW: user_logs.view_logs",
            details=log_details
        )

    # Logları sırala ve paginate et
    logs = query.order_by(UserLog.timestamp.desc()).paginate(page=page, per_page=per_page)
    
    # Tüm kullanıcıları getir (filtre seçenekleri için)
    users = User.query.order_by(User.username).all()

    # İstatistikler için ek veriler
    stats = {
        'toplam_log': UserLog.query.count(),
        'bugunku_log': UserLog.query.filter(
            UserLog.timestamp >= datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        ).count(),
        'filtreli_log': logs.total if filters_applied else None
    }

    return render_template(
        'user_logs.html',
        logs=logs,
        users=users,
        stats=stats,
        filter_active=filters_applied
    )
