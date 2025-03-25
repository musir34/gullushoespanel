from flask import Blueprint, request, render_template, flash, redirect, url_for, send_from_directory
import pandas as pd
import os
from datetime import datetime
from werkzeug.utils import secure_filename
from models import db, Order
# ExcelUpload modelini import et
from models import ExcelUpload  # ExcelUpload tablonuzu eklediğinizi varsayıyoruz

commission_update_bp = Blueprint('commission_update_bp', __name__)

UPLOAD_FOLDER = './uploads'
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}

@commission_update_bp.route('/update-commission-from-excel', methods=['GET', 'POST'])
def update_commission_from_excel():
    """
    1) Excel yükle ve komisyon güncelleme
    2) En fazla 10 Excel dosyasını listele (isteğe göre tümünü göster)
    3) İsteğe göre ada veya tarihe göre sıralama
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

            # Orijinal dosya adı ile kaydet
            save_path = os.path.join(UPLOAD_FOLDER, filename)
            f.save(save_path)

            # Veritabanına bu yükleme bilgisini kaydedelim
            new_upload = ExcelUpload(
                filename=filename,
                upload_time=datetime.utcnow()  # otomatik default da olur, explicit yazıyoruz
            )
            db.session.add(new_upload)
            db.session.commit()

            # Şimdi Excel'i okuyup komisyonları güncelle
            try:
                df = pd.read_excel(save_path)
                df.columns = [c.strip() for c in df.columns]

                df.rename(columns={
                    'Sipariş No': 'order_number',
                    'Komisyon': 'commission'
                }, inplace=True, errors='ignore')

                updated_orders = []
                not_found_count = 0

                order_numbers = df['order_number'].astype(str).str.strip().tolist()
                orders_in_db = Order.query.filter(Order.order_number.in_(order_numbers)).all()
                order_map = {o.order_number: o for o in orders_in_db}

                for idx, row in df.iterrows():
                    order_num = str(row.get('order_number', '')).strip()
                    if not order_num:
                        continue

                    raw_commission = row.get('commission', 0.0)

                    # Negatif komisyonu pozitife çevir
                    try:
                        comm_val = abs(float(raw_commission))
                    except Exception as e:
                        print(f"[LOG] -> Komisyon dönüştürme hatası: {raw_commission}, Hata: {e}")
                        continue

                    # Sipariş var mı?
                    order_obj = order_map.get(order_num)
                    if order_obj:
                        order_obj.commission = comm_val
                        updated_orders.append(order_obj)
                    else:
                        not_found_count += 1

                if updated_orders:
                    db.session.bulk_save_objects(updated_orders)
                    db.session.commit()

                print(f"[LOG] -> Dosya({filename}) tamam: {len(updated_orders)} güncellendi, {not_found_count} bulunamadı.")
                total_updated += len(updated_orders)
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

        # Aynı sayfaya dönelim (yine listelensin)
        return redirect(url_for('commission_update_bp.update_commission_from_excel'))

    # --------------------------------------------------
    # GET: Form + tablo listesi (ExcelUpload tablosundan)
    # --------------------------------------------------
    show_all = (request.args.get('all', '0') == '1')
    sort_by = request.args.get('sort', 'date')  # 'name' veya 'date'

    if sort_by == 'name':
        query = ExcelUpload.query.order_by(ExcelUpload.filename.asc())
    else:
        # default: tarihe göre (son yükleneni başta görmek için desc)
        query = ExcelUpload.query.order_by(ExcelUpload.upload_time.desc())

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
    """
    Upload klasöründeki Excel dosyasını indirme linki
    """
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)
