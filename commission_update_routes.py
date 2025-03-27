from flask import Blueprint, request, render_template, flash, redirect, url_for, send_from_directory
import pandas as pd
import os
import random
from datetime import datetime
from werkzeug.utils import secure_filename

from models import db, ExcelUpload
from models import OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled  # tablolar
# Yukarıda 'Product' vb. da import edebilirsiniz gerekirse

commission_update_bp = Blueprint('commission_update_bp', __name__)

UPLOAD_FOLDER = './uploads'
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}

def parse_excel_date(date_value):
    """
    Excel'deki 'Sipariş Tarihi' hücresini datetime tipine parse etmeyi dener.
    Başarılı olursa datetime döndürür, yoksa None.
    """
    if pd.isna(date_value):
        return None

    # Eğer pandas Timestamp ise direkt .to_pydatetime()
    if isinstance(date_value, pd.Timestamp):
        return date_value.to_pydatetime()

    # String ise farklı formatlar deneyelim
    if isinstance(date_value, str):
        for fmt in ["%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"]:
            try:
                return datetime.strptime(date_value.strip(), fmt)
            except:
                pass
        return None

    # Belki numeric vs. – isterseniz ek bir mantık ekleyebilirsiniz
    return None


@commission_update_bp.route('/update-commission-from-excel', methods=['GET', 'POST'])
def update_commission_from_excel():
    """
    Excel yükle, hem komisyon hem tarih güncelle.
    Tarih yok/parse edilemezse, Excel'deki rastgele bir valid tarihten seçilsin.
    """
    if request.method == 'POST':
        files = request.files.getlist('excel_files')

        if not files or len(files) == 0 or not files[0].filename:
            flash("Excel dosyası yüklenmedi!", "danger")
            return redirect(request.url)

        total_updated = 0
        total_not_found = 0
        total_files_processed = 0

        for f in files:
            filename = secure_filename(f.filename)
            if not filename:
                continue

            ext = filename.rsplit('.', 1)[-1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                flash(f"{filename}: Geçersiz uzantı. Sadece (xlsx, xls) yükleyebilirsiniz.", "danger")
                continue

            # Dosyayı kaydet
            save_path = os.path.join(UPLOAD_FOLDER, filename)
            f.save(save_path)

            # ExcelUpload tablosuna kaydet (opsiyonel)
            new_upload = ExcelUpload(
                filename=filename,
                upload_time=datetime.utcnow()
            )
            db.session.add(new_upload)
            db.session.commit()

            try:
                # 1) Excel'i oku
                df = pd.read_excel(save_path)
                df.columns = [c.strip() for c in df.columns]

                # "Sipariş No" -> "order_number"; 
                # "Komisyon" -> "commission"
                # "Sipariş Tarihi" -> "order_date_excel" vb.
                df.rename(columns={
                    'Sipariş No': 'order_number',
                    'Komisyon': 'commission',
                    'Sipariş Tarihi': 'order_date_excel'
                }, inplace=True, errors='ignore')

                # Kolon kontrol
                if 'order_number' not in df.columns or 'commission' not in df.columns:
                    flash(f"{filename} dosyasında 'Sipariş No' veya 'Komisyon' kolonları yok.", "danger")
                    continue
                if 'order_date_excel' not in df.columns:
                    flash(f"{filename} dosyasında 'Sipariş Tarihi' kolonu yok, tarih güncellemesi atlanacak.", "warning")

                # 2) Tüm valid tarihleri toplayalım
                valid_dates = []
                if 'order_date_excel' in df.columns:
                    for val in df['order_date_excel']:
                        parsed = parse_excel_date(val)
                        if parsed:
                            valid_dates.append(parsed)
                # valid_dates içinde en az 1 tarih varsa, yoksa "None"

                # 3) Sipariş numaralarını toplayıp, tablolardan çekelim
                df['order_number'] = df['order_number'].astype(str).str.strip()
                order_numbers = df['order_number'].tolist()
                table_classes = [OrderCreated, OrderPicking, OrderShipped, OrderDelivered, OrderCancelled]
                order_map = {}

                for tbl_cls in table_classes:
                    found_orders = tbl_cls.query.filter(tbl_cls.order_number.in_(order_numbers)).all()
                    for o in found_orders:
                        order_map[o.order_number] = o

                updated_objects = []
                not_found_count = 0

                # 4) Excel satırlarını dolaş, komisyon ve tarih güncelle
                for idx, row in df.iterrows():
                    order_num = str(row.get('order_number', '')).strip()
                    if not order_num:
                        continue

                    raw_commission = row.get('commission', 0.0)
                    # Komisyon -> float, negatifse abs al
                    try:
                        comm_val = abs(float(raw_commission))
                    except:
                        continue

                    # Tarih -> parse etmeye çalış
                    raw_date_in_excel = row.get('order_date_excel')
                    parsed_date = parse_excel_date(raw_date_in_excel)
                    if not parsed_date:
                        # Excel satırındaki tarih yok/boş/parse edilemedi
                        # => eğer valid_dates var ise rastgele seç
                        if valid_dates:
                            import random
                            parsed_date = random.choice(valid_dates)
                        else:
                            parsed_date = None  # Hiçbir tarihe set edemezsek None kalsın

                    # map'te siparişi var mı?
                    order_obj = order_map.get(order_num)
                    if order_obj:
                        # Komisyon
                        order_obj.commission = comm_val
                        # Tarih
                        if parsed_date:
                            order_obj.order_date = parsed_date
                        updated_objects.append(order_obj)
                    else:
                        not_found_count += 1

                if updated_objects:
                    db.session.bulk_save_objects(updated_objects)
                    db.session.commit()

                print(f"[LOG] -> Dosya({filename}): {len(updated_objects)} güncellendi, {not_found_count} bulunamadı.")
                total_updated += len(updated_objects)
                total_not_found += not_found_count
                total_files_processed += 1

            except Exception as e:
                print("[LOG] -> Hata oluştu:", e)
                flash(f"{filename} işlenirken hata: {e}", "danger")
                continue

        flash(
            f"Toplam {total_files_processed} dosya işlendi. "
            f"{total_updated} kayıt güncellendi, {total_not_found} kayıt bulunamadı.",
            "success"
        )
        return redirect(url_for('commission_update_bp.update_commission_from_excel'))

    # GET tarafı (listeleme)
    show_all = (request.args.get('all', '0') == '1')
    sort_by = request.args.get('sort', 'date')  # 'name' veya 'date'

    query = ExcelUpload.query
    if sort_by == 'name':
        query = query.order_by(ExcelUpload.filename.asc())
    else:
        query = query.order_by(ExcelUpload.upload_time.desc())

    if not show_all:
        uploads = query.limit(10).all()
    else:
        uploads = query.all()

    return render_template(
        'update_commission.html',
        uploads=uploads,
        show_all=show_all,
        sort_by=sort_by
    )


@commission_update_bp.route('/download/<filename>')
def download_excel(filename):
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)
