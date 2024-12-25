from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import db, Worker, UretimIsi, JobStatus, WorkerType, Product, AyakkabiRenk
from datetime import datetime
import json

workshop_bp = Blueprint('workshop', __name__)

@workshop_bp.app_template_filter('escape_js')
def escape_js_filter(s):
    """
    Django'nun 'escapejs' filtresine benzer şekilde,
    Python string'ini JSON formatına çevirerek JS içinde güvenli hale getiren basit bir fonksiyon.
    """
    if s is None:
        return ""
    return json.dumps(s)[1:-1]

@workshop_bp.route('/workshop/dashboard')
def dashboard():
    try:
        isler = UretimIsi.query.order_by(UretimIsi.baslangic_tarihi.desc()).all()
        return render_template('workshop/dashboard.html', isler=isler)
    except Exception as e:
        print(f"Hata: {str(e)}")
        return "Atölye yönetimi paneline erişilirken bir hata oluştu.", 500

@workshop_bp.route('/workshop/workers', methods=['GET', 'POST'])
def workers():
    if request.method == 'POST':
        ad = request.form['ad']
        soyad = request.form['soyad']
        worker_type = WorkerType[request.form['worker_type']]

        worker = Worker(ad=ad, soyad=soyad, worker_type=worker_type)
        db.session.add(worker)
        db.session.commit()

        flash('Çalışan başarıyla eklendi!', 'success')
        return redirect(url_for('workshop.workers'))

    workers = Worker.query.all()
    return render_template('workshop/workers.html', workers=workers, WorkerType=WorkerType)

@workshop_bp.route('/workshop/worker/delete/<int:id>')
def delete_worker(id):
    worker = Worker.query.get_or_404(id)
    worker.aktif = False
    db.session.commit()
    flash('Çalışan pasif duruma alındı!', 'success')
    return redirect(url_for('workshop.workers'))

@workshop_bp.route('/workshop/is-ekle', methods=['GET', 'POST'])
def is_ekle():
    """
    Yeni iş ekleme formu (GET ve POST).
    Arama işlemi ya doğrudan product_main_id aramasıyla,
    ya da ürün listesinde seçilen model üzerinden yapılabilir.
    Bu versiyonda hem product_main_id hem color GET parametresiyle gelebilir.
    """
    if request.method == 'POST':
        try:
            kesici_id = request.form['kesici_id']
            sayaci_id = request.form['sayaci_id']
            kalfa_id = request.form['kalfa_id']

            # Formdan gelen model kodu ve renk
            product_main_id = request.form['product_main_id']  
            selected_color = request.form['selected_color']

            # Beden değerlerini al
            bedenler = {
                'beden_35': int(request.form.get('beden_35', 0)),
                'beden_36': int(request.form.get('beden_36', 0)),
                'beden_37': int(request.form.get('beden_37', 0)),
                'beden_38': int(request.form.get('beden_38', 0)),
                'beden_39': int(request.form.get('beden_39', 0)),
                'beden_40': int(request.form.get('beden_40', 0)),
                'beden_41': int(request.form.get('beden_41', 0))
            }
            toplam_adet = sum(bedenler.values())

            # Product tablosundan product_main_id’ye göre kaydı buluyoruz
            product = Product.query.filter_by(product_main_id=product_main_id, hidden=False).first()
            if not product:
                raise ValueError(f"Seçilen ürün (product_main_id={product_main_id}) bulunamadı veya pasif (hidden).")

            # Fiyat hesaplaması
            birim_fiyat = product.sale_price or 0
            toplam_fiyat = birim_fiyat * toplam_adet

            # UretimIsi kaydı: veritabanında product_main_id ve color(renk_id) varsa
            # (Bu örnekte "renk_id" numeric olabilir, "selected_color" string olabilir;
            #  uyarlama yapmanız gerekebilir.)
            yeni_is = UretimIsi(
                kalfa_id=kalfa_id,
                product_main_id=product_main_id,  # tablo sütununuz varsa
                renk_id=selected_color,           # eğer bu numeric ise, int() dönüştürün
                **bedenler,
                toplam_adet=toplam_adet,
                birim_fiyat=birim_fiyat,
                toplam_fiyat=toplam_fiyat
            )

            db.session.add(yeni_is)
            db.session.commit()

            flash('Yeni iş başarıyla eklendi!', 'success')
            return redirect(url_for('workshop.dashboard'))
        except Exception as e:
            flash(f'Hata oluştu: {str(e)}', 'danger')
            db.session.rollback()

    # GET isteği
    # Ürün listesinden "Bu Ürünü Seç" tıklanınca ?product_main_id=XYZ&color=ABC
    selected_product_main_id = request.args.get('product_main_id', '').strip()
    selected_color = request.args.get('color', '').strip()

    workers = Worker.query.filter_by(aktif=True).all()
    products = Product.query.filter_by(hidden=False).all()  # Hidden olmayan tüm ürünler
    renkler = AyakkabiRenk.query.filter_by(aktif=True).all()

    # Renkleri product_main_id bazında gruplayalım
    colors_by_model = {}
    for r in renkler:
        pm_id = r.product_main_id
        if pm_id not in colors_by_model:
            colors_by_model[pm_id] = []
        colors_by_model[pm_id].append({
            "id": r.id,
            "renk_adi": r.renk_adi
        })

    return render_template(
        'workshop/is_ekle.html',
        workers=workers,
        products=products,
        colors_by_model=colors_by_model,
        selected_product_main_id=selected_product_main_id,
        selected_color=selected_color
    )

@workshop_bp.route('/workshop/is-guncelle/<int:is_id>', methods=['POST'])
def is_guncelle(is_id):
    is_kaydi = UretimIsi.query.get_or_404(is_id)
    yeni_durum = request.form.get('durum')

    if yeni_durum == JobStatus.COMPLETED.name:
        is_kaydi.bitis_tarihi = datetime.utcnow()

    is_kaydi.durum = JobStatus[yeni_durum]
    db.session.commit()

    flash('İş durumu güncellendi!', 'success')
    return redirect(url_for('workshop.dashboard'))

@workshop_bp.route('/workshop/is-detay/<int:is_id>')
def is_detay(is_id):
    is_kaydi = UretimIsi.query.get_or_404(is_id)
    return render_template('workshop/is_detay.html', is_kaydi=is_kaydi)
