# profit_bp.py (TAM KOD)

from flask import Blueprint, render_template, request, flash
from datetime import datetime, date, time # date ve time importları
import logging
from decimal import Decimal, InvalidOperation # Decimal import

# --- WTForms ---
# Gerekli WTForms sınıflarını import et
# Flask-WTF yüklediğinden emin ol: pip install Flask-WTF
from flask_wtf import FlaskForm
from wtforms import DateField, FloatField, SubmitField
from wtforms.validators import DataRequired, NumberRange, Optional, ValidationError

# --- Modeller ---
# Veritabanı modellerini import et (kendi projenizdeki yola göre ayarlayın)
# Projenizin yapısına göre bu import yolunu düzeltmeniz gerekebilir.
try:
    from .models import db, OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled, Product
except ImportError:
    try:
         from models import db, OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled, Product
    except ImportError as e:
         # Modelleri bulamazsa logla ve programı durdurmak yerine hata ver
         logging.error(f"Veritabanı modelleri import edilemedi! Hata: {e}")
         # Bu durumda uygulama başlamayabilir, bu yüzden bu import kritik.
         # Gerekirse burada raise Exception("Modeller yüklenemedi") yapabilirsiniz.
         # Şimdilik sadece loglayalım.
         pass

# --- Loglama Ayarları ---
# Temel loglama yapılandırması
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Form Tanımı ---
# ProfitReportForm sınıfını doğrudan bu dosyada tanımlıyoruz
class ProfitReportForm(FlaskForm):
    start_date = DateField(
        'Başlangıç Tarihi',
        format='%Y-%m-%d',
        validators=[DataRequired(message="Başlangıç tarihi boş bırakılamaz.")],
        render_kw={"placeholder": "YYYY-MM-DD", "type": "date"}
    )
    end_date = DateField(
        'Bitiş Tarihi',
        format='%Y-%m-%d',
        validators=[DataRequired(message="Bitiş tarihi boş bırakılamaz.")],
        render_kw={"placeholder": "YYYY-MM-DD", "type": "date"}
    )
    package_cost = FloatField(
        'Paket Maliyeti (adet başı)',
        default=0.0,
        validators=[Optional(), NumberRange(min=0, message="Paket maliyeti negatif olamaz.")],
        render_kw={"step": "0.01", "placeholder": "Örn: 1.50"}
    )
    employee_cost = FloatField(
        'İşçilik Maliyeti (adet başı)',
        default=0.0,
        validators=[Optional(), NumberRange(min=0, message="İşçilik maliyeti negatif olamaz.")],
         render_kw={"step": "0.01", "placeholder": "Örn: 5.00"}
    )
    shipping_cost = FloatField(
        'Kargo Maliyeti (adet başı)',
        default=0.0,
        validators=[Optional(), NumberRange(min=0, message="Kargo maliyeti negatif olamaz.")],
         render_kw={"step": "0.01", "placeholder": "Örn: 25.75"}
    )
    submit = SubmitField('Raporu Oluştur')

    # Özel validasyon: Bitiş tarihinin başlangıç tarihinden önce olmamasını kontrol etme
    def validate_end_date(self, field):
        if self.start_date.data and field.data:
            if field.data < self.start_date.data:
                raise ValidationError('Bitiş tarihi, başlangıç tarihinden önce olamaz.')


# --- Blueprint Tanımı ---
profit_bp = Blueprint('profit', __name__, url_prefix='/profit')


# --- Route Tanımı ---
# ÖNEMLİ GÜVENLİK NOTU: Bu route'u @login_required decorator'ı ile koruma altına alın!
# from flask_login import login_required
# @profit_bp.route('/', methods=['GET', 'POST'])
# @login_required

@profit_bp.route('/', methods=['GET', 'POST'])
def profit_report():
    """
    WTForms kullanarak formdan tarih aralığı ve maliyetleri alır,
    N+1 sorgu problemini çözerek siparişleri analiz eder ve kar/zarar raporu oluşturur.
    Form tanımı bu dosyanın içindedir. Grafik için temel veriyi hazırlar.
    """
    form = ProfitReportForm()
    # Başlangıç değerlerini tanımla
    analysis = []
    total_profit = Decimal('0.0')
    avg_profit = Decimal('0.0')
    total_net_income = Decimal('0.0')
    total_expenses_sum = Decimal('0.0')
    order_count = 0
    processed_count = 0
    chart_labels = [] # Grafik etiketleri (tarihler vb.)
    chart_values = [] # Grafik değerleri (kâr/zarar vb.)

    if form.validate_on_submit(): # POST ve form geçerli ise
        try:
            # Formdan doğrulanmış verileri Decimal'e çevirerek al
            package_cost = Decimal(str(form.package_cost.data or 0))
            employee_cost = Decimal(str(form.employee_cost.data or 0))
            shipping_cost = Decimal(str(form.shipping_cost.data or 0))
            start_date_obj = form.start_date.data
            end_date_obj = form.end_date.data

            # Tam gün aralığı için datetime nesneleri oluştur
            start_datetime = datetime.combine(start_date_obj, time.min)
            end_datetime = datetime.combine(end_date_obj, time.max)

            logging.info(f"Rapor Oluşturuluyor...")
            logging.info(f"Tarih Aralığı: {start_datetime} - {end_datetime}")
            logging.info(f"Adet Başı Maliyetler -> Paket: {package_cost}, İşçilik: {employee_cost}, Kargo: {shipping_cost}")

            # 1) İlgili siparişleri çek
            orders = []
            table_classes = [OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled] # Gerekirse düzenle

            for cls in table_classes:
                try:
                    results = cls.query.filter(
                        cls.order_date.between(start_datetime, end_datetime)
                    ).all()
                    orders.extend(results)
                    logging.info(f"'{cls.__tablename__}' tablosundan {len(results)} sipariş bulundu.")
                except Exception as db_err: # Model sorgulama hatasını yakala
                    logging.error(f"'{cls.__tablename__}' tablosu sorgulanırken hata: {db_err}")
                    flash(f"'{cls.__tablename__}' tablosundaki siparişler getirilirken bir sorun oluştu.", "danger")
                    # Hata olsa da devam edebilir veya işlemi durdurabiliriz. Şimdilik devam edelim.

            order_count = len(orders)
            logging.info(f"Belirtilen tarih aralığında toplam {order_count} sipariş kaydı bulundu (tüm tablolarda).")

            if not orders:
                flash("Belirtilen tarih aralığında hiç sipariş bulunamadı.", "warning")
            else:
                # --- N+1 Sorgu Problemi Çözümü ---
                unique_barcodes = {getattr(o, 'original_product_barcode', None) for o in orders}
                valid_barcodes = {bc for bc in unique_barcodes if bc}

                products_map = {}
                if valid_barcodes:
                    try:
                        products_list = Product.query.filter(Product.original_product_barcode.in_(valid_barcodes)).all()
                        products_map = {p.original_product_barcode: p for p in products_list}
                        logging.info(f"İlişkili {len(products_map)} benzersiz ürün bilgisi çekildi.")
                        missing_barcodes = valid_barcodes - set(products_map.keys())
                        if missing_barcodes:
                            logging.warning(f"Ürün tablosunda bulunamayan barkodlar: {missing_barcodes}")
                    except Exception as prod_err:
                        logging.error(f"Ürün bilgileri çekilirken hata: {prod_err}")
                        flash("Ürün bilgileri getirilirken bir sorun oluştu. Maliyetler eksik olabilir.", "warning")
                else:
                    logging.warning("Siparişlerde geçerli ürün barkodu bulunamadı.")
                # --- N+1 Çözümü Sonu ---

                # 5) Siparişleri işle ve analiz listesini oluştur
                for o in orders:
                    product_barcode = getattr(o, 'original_product_barcode', None)
                    product = products_map.get(product_barcode) if product_barcode else None

                    current_product_cost = Decimal('0.0')
                    if product and product.cost_try is not None:
                        try:
                            current_product_cost = Decimal(str(product.cost_try))
                        except (InvalidOperation, TypeError):
                             logging.warning(f"Ürün ID={product.id}, Barkod={product_barcode} için geçersiz maliyet: {product.cost_try}. 0 olarak alınıyor.")
                    # Diğer durumlar için maliyet zaten 0

                    try:
                        amount_val = Decimal(str(o.amount)) if o.amount is not None else Decimal('0.0')
                        discount_val = Decimal(str(o.discount)) if o.discount is not None else Decimal('0.0')
                        commission_val = Decimal(str(o.commission)) if o.commission is not None else Decimal('0.0')

                        net_income = (amount_val - discount_val) - commission_val
                        total_expenses = current_product_cost + shipping_cost + package_cost + employee_cost
                        profit = net_income - total_expenses

                        total_profit += profit
                        total_net_income += net_income
                        total_expenses_sum += total_expenses

                        analysis.append({
                            "order_id": getattr(o, 'id', 'N/A'), # id alanı yoksa diye kontrol
                            "order_table": getattr(o, '__tablename__', 'N/A'),
                            "order_date": getattr(o, 'order_date', None), # Tarih objesi veya None
                            "product": getattr(o, 'product_name', "Bilinmiyor"),
                            "barcode": product_barcode or "YOK",
                            "status": getattr(o, 'status', 'Bilinmiyor'),
                            "net_income": net_income,
                            "product_cost": current_product_cost,
                            "other_costs": shipping_cost + package_cost + employee_cost,
                            "total_expenses": total_expenses,
                            "profit": profit,
                        })
                        processed_count += 1

                    except (InvalidOperation, TypeError, ValueError) as calc_e:
                        logging.error(f"Sipariş ID={getattr(o, 'id', 'N/A')} için hesaplama hatası: {calc_e}. Detaylar: Amount={o.amount}, Discount={o.discount}, Commission={o.commission}. Sipariş atlanıyor.")
                        continue # Hatalı siparişi atla

                # --- GRAFİK VERİSİ HAZIRLAMA (Günlük Kâr/Zarar) ---
                if analysis:
                    try:
                        daily_profit_data = {}
                        for item in analysis:
                            item_date = item.get('order_date')
                            if isinstance(item_date, datetime): # datetime objesi mi kontrol et
                                date_str = item_date.strftime('%Y-%m-%d')
                                daily_profit_data[date_str] = daily_profit_data.get(date_str, Decimal('0.0')) + item['profit']
                            # else: Tarih yoksa veya geçersizse grafiğe ekleme

                        if daily_profit_data:
                            sorted_dates = sorted(daily_profit_data.keys())
                            chart_labels = sorted_dates
                            # Chart.js float bekler, Decimal'i float'a çevir
                            chart_values = [float(daily_profit_data[date]) for date in sorted_dates]
                            logging.info(f"Grafik için {len(chart_labels)} günlük veri noktası hazırlandı.")
                        else:
                             logging.info("Grafik oluşturmak için yeterli günlük veri bulunamadı (geçerli tarihli sipariş yok?).")

                    except Exception as chart_e:
                        logging.error(f"Grafik verisi hazırlanırken hata oluştu: {chart_e}")
                        chart_labels = [] # Hata durumunda sıfırla
                        chart_values = []
                # --- GRAFİK VERİSİ HAZIRLAMA SONU ---

                # 6) Ortalama kârı hesapla
                if processed_count > 0:
                    avg_profit = total_profit / processed_count
                # else: avg_profit zaten 0

                logging.info(f"Hesaplama tamamlandı. İşlenen Sipariş Sayısı: {processed_count}")
                logging.info(f"Toplam Net Gelir: {total_net_income:.2f}")
                logging.info(f"Toplam Gider: {total_expenses_sum:.2f}")
                logging.info(f"Toplam Kâr: {total_profit:.2f}")
                logging.info(f"Ortalama Kâr: {avg_profit:.2f}")

                if processed_count > 0 :
                     flash(f"Rapor başarıyla oluşturuldu. {processed_count} sipariş analiz edildi.", "success")
                elif order_count > 0:
                     flash("Siparişler bulundu ancak hiçbiri işlenemedi. Logları kontrol edin.", "warning")
                # else: Sipariş yoktu, zaten yukarıda flash mesajı verildi.

        except ValidationError as ve:
             flash(f"Form girişi hatalı: {ve}", "danger")
             logging.error(f"Form validasyon hatası: {ve}")
        except Exception as e:
            flash(f"Rapor oluşturulurken beklenmedik bir hata oluştu. Lütfen tekrar deneyin.", "danger")
            logging.exception("Profit report genel hata:") # Tam traceback logla
            # Hata durumunda tüm sonuçları sıfırla
            analysis, chart_labels, chart_values = [], [], []
            total_profit, avg_profit, total_net_income, total_expenses_sum = (Decimal('0.0'),)*4
            order_count, processed_count = 0, 0


    # GET isteği veya form validation başarısız ise veya POST sonrası render
    return render_template(
        'profit.html',
        form=form,
        analysis=analysis,
        total_profit=total_profit, # Decimal olarak gönderilir
        avg_profit=avg_profit,     # Decimal olarak gönderilir
        order_count=order_count,
        processed_count=processed_count,
        chart_labels=chart_labels, # Her zaman gönderilir (boş veya dolu)
        chart_values=chart_values  # Her zaman gönderilir (boş veya dolu)
    )

# Bu Blueprint'i ana Flask uygulamanıza kaydetmeyi unutmayın!
# Örnek: app.register_blueprint(profit_bp)