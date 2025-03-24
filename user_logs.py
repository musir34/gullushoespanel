from flask import Blueprint, render_template, request, session, redirect, url_for
# Flask-Login import kaldırıldı ve sadece gerektiğinde kontrol edilecek
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

        if details:
            if isinstance(details, dict):
                # Ek detayların anahtarlarını düzenleyerek ekle
                extended_details.update({k.replace('_', ' ').title(): v for k, v in details.items()})
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
        except Exception as e:
            db.session.rollback
            logging.error(f"Log kaydedilirken hata oluştu: {e}")()
            logging.error(f"Log kaydedilemedi: {e}")

@user_logs_bp.route('/user-logs')
@roles_required('admin', 'manager')
def view_logs():
    """
    Kullanıcı loglarını görüntüleyen view.
    Filtreleme parametreleri: kullanıcı ID, aksiyon, tarih aralığı.
    """
    page = request.args.get('page', 1, type=int)
    per_page = 50

    # Filtreleme parametrelerini çek
    user_id = request.args.get('user_id', type=int)
    action_filter = request.args.get('action')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    query = UserLog.query.join(User)

    if user_id:
        query = query.filter(UserLog.user_id == user_id)
    if action_filter:
        query = query.filter(UserLog.action.ilike(f'%{action_filter}%'))

    # Tarih filtresi için güvenli dönüşüm
    try:
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            query = query.filter(UserLog.timestamp >= start_date)
    except ValueError as ve:
        logging.error(f"Başlangıç tarih formatı hatası: {ve}")

    try:
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(UserLog.timestamp <= end_date)
    except ValueError as ve:
        logging.error(f"Bitiş tarih formatı hatası: {ve}")

    logs = query.order_by(UserLog.timestamp.desc()).paginate(page=page, per_page=per_page)
    users = User.query.all()

    return render_template('user_logs.html', logs=logs, users=users)
from flask import Blueprint, render_template, request, session, redirect, url_for
# Flask-Login import kaldırıldı ve sadece gerektiğinde kontrol edilecek
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

def extract_page_from_referrer(referrer):
    """Referer URL'sinden sayfa adını çıkarır."""
    if not referrer:
        return "Doğrudan"
    try:
        url_parts = urllib.parse.urlparse(referrer)
        path = url_parts.path.strip('/')
        if not path:
            return "Ana Sayfa"
        return path
    except:
        return "Bilinmiyor"

def log_user_action(action="Bilinmeyen İşlem", details=None, force_log=False):
    """Kullanıcı işlemlerini loglar."""
    try:
        user_id = session.get('user_id')
        
        # Flask-Login olmadığı için oturum kontrolü session üzerinden yapılıyor
        if not user_id and not force_log:
            return
            
        if user_id:
            user_role = session.get('role', 'ziyaretçi')
        else:
            user_id = 0  # Anonim kullanıcı
            user_role = 'ziyaretçi'
        
        # İşlem tipini ve sayfa adını çıkar
        action_parts = action.split(':', 1)
        action_type = action_parts[0] if len(action_parts) > 1 else action
        
        # Sayfa adını al (eğer detail içinde varsa)
        page = None
        if details and isinstance(details, dict):
            page = details.get('path', '').strip('/') or details.get('endpoint')
        
        # Türkçe karşılıklarını al
        translated_action = translate_action_type(action_type)
        translated_page = translate_page_name(page)
        
        # İşlem türünü belirle
        if action_type.startswith('PAGE_VIEW'):
            islem_turu = 'Sayfa Görüntüleme'
        elif action_type in ['CREATE', 'ADD']:
            islem_turu = 'Veri Ekleme'
        elif action_type in ['UPDATE', 'EDIT']:
            islem_turu = 'Veri Güncelleme'
