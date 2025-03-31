# Gerekli kütüphaneleri ve modülleri import edin
from flask import Blueprint, request, render_template, flash, redirect, url_for, send_from_directory
import pandas as pd
import os
import random # Rastgele seçim için eklendi
from datetime import datetime
from werkzeug.utils import secure_filename

# Veritabanı modellerinizi import edin (models.py dosyanızdan geldiğini varsayıyoruz)
# Bu satırları kendi projenize göre ayarlamanız gerekebilir
try:
    from .models import db, ExcelUpload
    from .models import OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled
except ImportError:
    # Eğer aynı dizinde değilse veya farklı bir yapı kullanıyorsanız,
    # import yolunu düzeltmeniz gerekir. Örnek:
    from models import db, ExcelUpload
    from models import OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled


# Blueprint'i oluşturun
commission_update_bp = Blueprint('commission_update_bp', __name__)

# Ayarlar
UPLOAD_FOLDER = './uploads'  # Dosyaların yükleneceği klasör (gerekirse değiştirin)
ALLOWED_EXTENSIONS = {'xlsx', 'xls'} # İzin verilen dosya uzantıları

# Yükleme klasörünün var olduğundan emin olun
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def parse_excel_date(date_value):
    """
    Excel'deki 'Sipariş Tarihi' hücresini datetime tipine parse etmeyi dener.
    Başarılı olursa datetime döndürür, yoksa None döndürür.
    Farklı formatları dener.
    """
    if pd.isna(date_value):
        return None

    # Eğer zaten bir Pandas Timestamp ise (genellikle Excel'den sayısal tarih okunduğunda olur)
    if isinstance(date_value, pd.Timestamp):
        return date_value.to_pydatetime()

    # Eğer datetime.datetime ise doğrudan döndür
    if isinstance(date_value, datetime):
        return date_value

    # Eğer metin (string) ise, yaygın formatları dene
    if isinstance(date_value, str):
        date_value = date_value.strip()
        # Potansiyel saat bilgisini ayır (sadece tarihi almak için)
        if ' ' in date_value:
            date_value = date_value.split(' ')[0]

        for fmt in ["%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y", "%Y.%m.%d"]:
            try:
                return datetime.strptime(date_value, fmt)
            except ValueError:
                pass # Format uyuşmazsa sonraki formatı dene
        # Eğer bilinen formatlar eşleşmezse None döndür
        print(f"[DEBUG] Tanınamayan tarih formatı: {date_value}") # Hata ayıklama için
        return None

    # Eğer sayısal bir değerse (Excel'in tarihleri saklama şekli olabilir)
    if isinstance(date_value, (int, float)):
        try:
            # Excel'in başlangıç tarihine göre (1900-01-01 veya 1904-01-01)
            # Bu dönüşüm bazen platforma ve Excel ayarlarına göre değişebilir.
            # pd.to_datetime bu konuda genellikle daha başarılıdır.
            # Eğer pd.Timestamp değilse, bu adımı deneyebiliriz ama dikkatli olunmalı.
            # return pd.to_datetime(date_value, unit='D', origin='1899-12-30').to_pydatetime() # Windows Excel için yaygın origin
            # En iyisi pandas'ın okurken bunu halletmesini beklemek veya Timestamp kontrolünü kullanmaktır.
            # Şimdilik sayısal ama Timestamp olmayanları None döndürelim.
             print(f"[DEBUG] Sayısal ama Timestamp olmayan tarih: {date_value}") # Hata ayıklama için
             return None # veya pd.to_datetime ile tekrar deneyebilirsiniz.
        except Exception as e:
             print(f"[DEBUG] Sayısal tarih parse hatası: {e}") # Hata ayıklama için
             return None

    # Diğer tipler veya parse edilemeyen durumlar için None döndür
    return None


@commission_update_bp.route('/update-commission-from-excel', methods=['GET', 'POST'])
def update_commission_from_excel():
    if request.method == 'POST':
        files = request.files.getlist('excel_files')

        if not files or len(files) == 0 or not files[0].filename:
            flash("Excel dosyası yüklenmedi!", "danger")
            return redirect(request.url)

        total_updated = 0
        total_not_found = 0
        total_files_processed = 0
        error_files = []

        for f in files:
            filename = secure_filename(f.filename)
            if not filename:
                continue # Boş dosya adını atla

            # Dosya uzantısını kontrol et
            ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
            if ext not in ALLOWED_EXTENSIONS:
                flash(f"{filename}: Geçersiz uzantı. Sadece ({', '.join(ALLOWED_EXTENSIONS)}) yükleyebilirsiniz.", "danger")
                error_files.append(filename)
                continue # Geçersiz uzantılı dosyayı atla

            # Benzersiz bir dosya adı oluşturmak daha iyi olabilir ama şimdilik secure_filename yeterli
            save_path = os.path.join(UPLOAD_FOLDER, filename)

            try:
                f.save(save_path) # Dosyayı kaydet

                # 1) Excel'i oku
                # Engine='openpyxl' özellikle .xlsx için daha güvenilir olabilir
                df = pd.read_excel(save_path, engine='openpyxl' if ext == 'xlsx' else None)
                df.columns = [str(c).strip() for c in df.columns] # Sütun adlarındaki boşlukları temizle

                # Gerekli sütunların varlığını kontrol et
                required_columns = {'Sipariş No', 'Komisyon', 'Sipariş Tarihi'}
                if not required_columns.issubset(df.columns):
                     missing_cols = required_columns - set(df.columns)
                     flash(f"{filename}: Gerekli sütunlar bulunamadı: {', '.join(missing_cols)}", "danger")
                     error_files.append(filename)
                     # İsteğe bağlı: Hatalı dosyayı silmek isterseniz os.remove(save_path)
                     continue # Bu dosyayı işlemeyi durdur

                # Sütunları yeniden adlandır (hata vermemesi için errors='ignore')
                df.rename(columns={
                    'Sipariş No': 'order_number',
                    'Komisyon': 'commission',
                    'Sipariş Tarihi': 'order_date_excel'
                }, inplace=True, errors='ignore')

                # 2) Excel'deki tarihin seçimi (Dosya Yükleme Zamanı için - Rastgele Geçerli Tarih)
                #--------------------------------------------------------------------------
                # <<< DEĞİŞİKLİK BURADA BAŞLIYOR >>>
                #--------------------------------------------------------------------------
                upload_date = datetime.utcnow()  # Varsayılan: Eğer dosyada hiç geçerli tarih yoksa
                valid_dates = [] # Tüm geçerli tarihleri tutacak liste

                if 'order_date_excel' in df.columns:
                    # Tüm satırları parse edelim ve None olmayan geçerli tarihleri bulalım:
                    valid_dates = [d for d in (parse_excel_date(dt) for dt in df['order_date_excel']) if d is not None]

                    # Eğer en az bir geçerli tarih bulunduysa, bunlardan rastgele birini seçelim
                    if valid_dates:
                        upload_date = random.choice(valid_dates) # Rastgele bir geçerli tarih seç
                #--------------------------------------------------------------------------
                # <<< DEĞİŞİKLİK BURADA BİTİYOR >>>
                #--------------------------------------------------------------------------

                # 3) ExcelUpload tablosuna kaydet. upload_time = Excel'den rastgele seçilen bir sipariş tarihi.
                new_upload = ExcelUpload(
                    filename=filename,
                    upload_time=upload_date # Bu değişken artık rastgele seçilen tarihi içeriyor (veya varsayılanı)
                )
                db.session.add(new_upload)
                # Bu commit'i döngünün sonuna veya tüm dosyalar işlendikten sonraya taşımak
                # bir hata durumunda geri almayı kolaylaştırabilir, ancak her dosya için ayrı
                # kayıt istiyorsak burada kalması mantıklı. Şimdilik burada bırakalım.
                db.session.commit()

                # 4) Mevcut siparişleri bulup güncelleme için hazırla
                # Sipariş numaralarını string'e çevirip boşlukları temizle
                df['order_number'] = df['order_number'].astype(str).str.strip()
                order_numbers_in_excel = df['order_number'].unique().tolist() # Tekrarları önle

                # Veritabanında aranacak tablolar
                table_classes = [OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled]
                order_map = {} # Bulunan siparişleri {order_num: order_object} şeklinde tutacak map

                # Tüm tablolarda Excel'deki sipariş numaralarını ara
                # Büyük veri setlerinde bu kısım optimize edilebilir (örn: tek sorgu)
                for tbl_cls in table_classes:
                    # Sorguyu daha verimli hale getirmek için .in_() kullan
                    found_orders = tbl_cls.query.filter(tbl_cls.order_number.in_(order_numbers_in_excel)).all()
                    for o in found_orders:
                        # Eğer aynı sipariş no farklı tablolarda varsa, hangisinin öncelikli olacağına
                        # karar vermek gerekebilir. Şimdilik son bulunan üzerine yazıyor.
                        # İş mantığınıza göre burayı düzenleyebilirsiniz (örn. sadece OrderCreated'ı al).
                        order_map[o.order_number] = o

                updated_objects = [] # Güncellenecek veritabanı objelerini tutacak liste
                file_not_found_count = 0 # Bu dosyada bulunamayan sipariş sayısı

                # 5) Excel satırlarını dolaş, komisyon ve sipariş bazında order_date güncelle
                for idx, row in df.iterrows():
                    order_num = str(row.get('order_number', '')).strip()
                    if not order_num:
                        print(f"[DEBUG] {filename} - Satır {idx+2}: Boş sipariş numarası, atlanıyor.")
                        continue # Boş sipariş numarasını atla

                    # Komisyonu al ve işle (negatif olmamasını sağlıyoruz - iş mantığına göre değişebilir)
                    raw_commission = row.get('commission')
                    comm_val = 0.0 # Varsayılan
                    try:
                        # Sayısal olmayan değerleri veya None'ı atla/varsayılan yap
                        if pd.notna(raw_commission):
                           comm_val = abs(float(raw_commission)) # Negatifi pozitife çevir
                    except (ValueError, TypeError) as e:
                        print(f"[DEBUG] {filename} - Sipariş {order_num} (Satır {idx+2}): Geçersiz komisyon '{raw_commission}', 0.0 olarak ayarlandı. Hata: {e}")
                        comm_val = 0.0 # Hata durumunda varsayılan

                    # Satıra özel sipariş tarihini parse et
                    raw_date_in_excel = row.get('order_date_excel')
                    parsed_date = parse_excel_date(raw_date_in_excel)

                    # Eğer bu satır için geçerli tarih parse edilemediyse,
                    # dosyadaki geçerli tarihlerden birini kullanabiliriz (orijinal kodunuzdaki gibi)
                    # Ancak bu mantık iş akışınıza uygun olmayabilir.
                    # Belki tarih yoksa siparişin tarihi güncellenmemelidir?
                    # Şimdilik orijinal mantığı koruyalım:
                    if not parsed_date:
                        if valid_dates: # Dosya genelinde geçerli tarihler varsa
                            # Her satır için rastgele atamak yerine belki dosya geneli için
                            # belirlenen upload_date'i kullanmak daha tutarlı olabilir?
                            # Veya None bırakmak? Şimdilik rastgele seçelim.
                            parsed_date = random.choice(valid_dates)
                            # print(f"[DEBUG] {filename} - Sipariş {order_num}: Satırda tarih yok, rastgele atandı: {parsed_date}")
                        # else: # valid_dates boşsa parsed_date zaten None kalır

                    # Veritabanından bulunan sipariş nesnesini al
                    order_obj = order_map.get(order_num)

                    if order_obj:
                        # Değişiklik var mı kontrol etmek performansı artırabilir ama şimdilik basit tutalım
                        order_obj.commission = comm_val
                        if parsed_date: # Sadece geçerli bir tarih varsa güncelle
                            order_obj.order_date = parsed_date
                        updated_objects.append(order_obj)
                    else:
                        file_not_found_count += 1
                        # print(f"[DEBUG] {filename} - Sipariş {order_num} veritabanında bulunamadı.")


                # Güncellenecek objeler varsa toplu olarak kaydet
                if updated_objects:
                    # db.session.add_all(updated_objects) # bulk_save_objects genellikle daha performanslıdır
                    db.session.bulk_save_objects(updated_objects)
                    db.session.commit() # Güncellemeleri veritabanına işle

                print(f"[LOG] -> Dosya({filename}): {len(updated_objects)} kayıt güncellendi, {file_not_found_count} bulunamadı.")
                total_updated += len(updated_objects)
                total_not_found += file_not_found_count
                total_files_processed += 1

            except pd.errors.EmptyDataError:
                flash(f"{filename}: Dosya boş veya okunamadı.", "danger")
                error_files.append(filename)
                # İsteğe bağlı: Hatalı dosyayı silmek isterseniz os.remove(save_path)
            except Exception as e:
                db.session.rollback() # Hata oluşursa bu dosya için yapılan DB değişikliklerini geri al
                print(f"[ERROR] -> Dosya ({filename}) işlenirken genel hata: {e}")
                flash(f"{filename} işlenirken bir hata oluştu: {e}", "danger")
                error_files.append(filename)
                # İsteğe bağlı: Hatalı dosyayı silmek isterseniz os.remove(save_path)
            finally:
                 # Başarılı veya başarısız, işlenen dosyayı silebilirsiniz (opsiyonel)
                 # try:
                 #     if os.path.exists(save_path):
                 #         os.remove(save_path)
                 # except OSError as e:
                 #     print(f"[WARNING] Dosya silinemedi: {save_path}, Hata: {e}")
                 pass # Şimdilik dosyaları tutalım


        # Tüm dosyalar işlendikten sonra genel bir özet mesajı göster
        if total_files_processed > 0:
             flash(
                 f"Toplam {total_files_processed} dosya başarıyla işlendi. "
                 f"{total_updated} kayıt güncellendi, {total_not_found} kayıt bulunamadı.",
                 "success"
             )
        if error_files:
             flash(f"Şu dosyalarda hata oluştu veya işlenemedi: {', '.join(error_files)}", "danger")

        return redirect(url_for('commission_update_bp.update_commission_from_excel'))

    # GET Metodu için: Yükleme geçmişini göster
    show_all = (request.args.get('all', '0') == '1')
    sort_by = request.args.get('sort', 'date')  # 'date' (varsayılan) veya 'name'

    query = ExcelUpload.query

    # Sıralama ölçütünü uygula
    if sort_by == 'name':
        query = query.order_by(ExcelUpload.filename.asc())
    else: # Varsayılan olarak veya sort=date ise tarihe göre (en yeni önce)
        query = query.order_by(ExcelUpload.upload_time.desc())

    # Tümünü göster veya limit uygula
    if not show_all:
        uploads = query.limit(10).all()
    else:
        uploads = query.all()

    # Template'i render et ve verileri gönder
    return render_template(
        'update_commission.html', # Template dosyanızın adı (oluşturmanız gerekir)
        uploads=uploads,
        show_all=show_all,
        sort_by=sort_by
    )


@commission_update_bp.route('/download/<path:filename>') # path converter daha güvenli olabilir
def download_excel(filename):
    """ Yüklenen bir Excel dosyasını indirmek için kullanılır. """
    # Güvenlik notu: Kullanıcının UPLOAD_FOLDER dışına çıkmadığından emin olun.
    # secure_filename burada tekrar kullanılabilir veya path traversal kontrolü yapılabilir.
    # send_from_directory bunu büyük ölçüde halleder ama dikkatli olmakta fayda var.
    try:
        return send_from_directory(
            UPLOAD_FOLDER,
            filename,
            as_attachment=True # Dosyanın indirilmesini sağlar
        )
    except FileNotFoundError:
         flash(f"{filename} adlı dosya bulunamadı!", "danger")
         # Nereye yönlendireceğinize karar verin, örneğin ana sayfaya veya yükleme sayfasına
         return redirect(url_for('commission_update_bp.update_commission_from_excel'))


# Bu Blueprint'i ana Flask uygulamanıza kaydetmeniz gerekir:
# app.register_blueprint(commission_update_bp, url_prefix='/commissions') # Örnek prefix