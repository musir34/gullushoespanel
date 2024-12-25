
from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import db, Worker, AyakkabiModel, AyakkabiRenk, UretimIsi, JobStatus, WorkerType
from datetime import datetime
from sqlalchemy import func

workshop_bp = Blueprint('workshop', __name__)

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
    if request.method == 'POST':
        try:
            kesici_id = int(request.form.get('kesici_id'))
            sayaci_id = int(request.form.get('sayaci_id'))
            kalfa_id = int(request.form.get('kalfa_id'))
            model_id = int(request.form.get('model_id'))
            renk_id = int(request.form.get('renk_id'))
            
            # Bedenleri al ve integer'a çevir
            bedenler = {}
            for i in range(35, 42):
                beden_key = f'beden_{i}'
                try:
                    bedenler[beden_key] = int(request.form.get(beden_key, 0))
                except (TypeError, ValueError):
                    bedenler[beden_key] = 0
            
            # Toplam adet ve fiyat hesapla
            toplam_adet = sum(bedenler.values())
            if toplam_adet <= 0:
                raise ValueError("Toplam adet 0'dan büyük olmalıdır")
                
            model = AyakkabiModel.query.get_or_404(model_id)
            birim_fiyat = float(model.fiyat)
            toplam_fiyat = birim_fiyat * toplam_adet
            
            # Yeni iş kaydı oluştur
            yeni_is = UretimIsi(
                kesici_id=kesici_id,
                sayaci_id=sayaci_id,
                kalfa_id=kalfa_id,
                model_id=model_id,
                renk_id=renk_id,
                toplam_adet=toplam_adet,
                birim_fiyat=birim_fiyat,
                toplam_fiyat=toplam_fiyat
            )
            
            # Bedenleri tek tek ata
            for beden_key, adet in bedenler.items():
                setattr(yeni_is, beden_key, adet)
            
            db.session.add(yeni_is)
            db.session.commit()
            
            flash('Yeni iş başarıyla eklendi!', 'success')
            return redirect(url_for('workshop.dashboard'))
            
        except Exception as e:
            flash(f'Hata oluştu: {str(e)}', 'danger')
            db.session.rollback()
    
    workers = Worker.query.filter_by(aktif=True).all()
    modeller = AyakkabiModel.query.filter_by(aktif=True).all()
    renkler = AyakkabiRenk.query.filter_by(aktif=True).all()
    
    return render_template('workshop/is_ekle.html', 
                         workers=workers,
                         modeller=modeller,
                         renkler=renkler)

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
