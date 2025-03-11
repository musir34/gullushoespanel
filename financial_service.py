
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
import base64
import aiohttp
import asyncio
import json
from datetime import datetime, timedelta
from models import db
from trendyol_api import API_KEY, API_SECRET, SUPPLIER_ID, BASE_URL
import logging
import pandas as pd
import io

# Loglama ayarları
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.FileHandler('financial_service.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

financial_service_bp = Blueprint('financial_service', __name__)

@financial_service_bp.route('/financial-summary', methods=['GET'])
def financial_summary():
    """
    Finansal özet sayfasını gösterir
    """
    # Varsayılan tarih aralığı: son 30 gün
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    # Formdan gelen tarih aralığı varsa kullan
    start_date_str = request.args.get('start_date', start_date.strftime('%Y-%m-%d'))
    end_date_str = request.args.get('end_date', end_date.strftime('%Y-%m-%d'))
    
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
    except ValueError:
        flash('Geçersiz tarih formatı', 'error')
        start_date = datetime.now() - timedelta(days=30)
        end_date = datetime.now()
    
    return render_template(
        'financial_summary.html',
        start_date=start_date.strftime('%Y-%m-%d'),
        end_date=end_date.strftime('%Y-%m-%d')
    )


@financial_service_bp.route('/api/financial-data', methods=['GET'])
async def get_financial_data():
    """
    Belirli bir tarih aralığı için finansal verileri çeker
    """
    try:
        # Tarih aralığını al
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        start_date_str = request.args.get('start_date', start_date.strftime('%Y-%m-%d'))
        end_date_str = request.args.get('end_date', end_date.strftime('%Y-%m-%d'))
        
        # Trendyol API'ye istek yap
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')
        url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/settlements"
        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json"
        }
        
        params = {
            "startDate": start_date_str,
            "endDate": end_date_str
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status != 200:
                    response_text = await response.text()
                    logger.error(f"API isteği başarısız oldu: {response.status} - {response_text}")
                    return jsonify({'success': False, 'error': f"API hatası: {response_text}"}), 500
                
                data = await response.json()
                
                # Özet verileri oluştur
                summary = {
                    'total_payment': sum(item.get('payout', 0) for item in data),
                    'total_commission': sum(item.get('commission', 0) for item in data),
                    'total_service_fee': sum(item.get('serviceFee', 0) for item in data),
                    'total_shipping_cost': sum(item.get('cargoPayment', 0) for item in data),
                    'total_tax': sum(item.get('tax', 0) for item in data),
                    'settlements_count': len(data)
                }
                
                return jsonify({
                    'success': True,
                    'settlements': data,
                    'summary': summary
                })
                
    except Exception as e:
        logger.error(f"Hata: get_financial_data - {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@financial_service_bp.route('/api/download-financial-report', methods=['GET'])
async def download_financial_report():
    """
    Finansal verileri Excel dosyası olarak indirme
    """
    try:
        # Tarih aralığını al
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        start_date_str = request.args.get('start_date', start_date.strftime('%Y-%m-%d'))
        end_date_str = request.args.get('end_date', end_date.strftime('%Y-%m-%d'))
        
        # Trendyol API'ye istek yap
        auth_str = f"{API_KEY}:{API_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode('utf-8')
        url = f"{BASE_URL}suppliers/{SUPPLIER_ID}/settlements"
        headers = {
            "Authorization": f"Basic {b64_auth_str}",
            "Content-Type": "application/json"
        }
        
        params = {
            "startDate": start_date_str,
            "endDate": end_date_str
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status != 200:
                    response_text = await response.text()
                    logger.error(f"API isteği başarısız oldu: {response.status} - {response_text}")
                    return jsonify({'success': False, 'error': f"API hatası: {response_text}"}), 500
                
                data = await response.json()
                
                # Veriyi DataFrame'e dönüştür
                df = pd.DataFrame(data)
                
                # Tarih sütunlarını düzenle
                if 'transactionDate' in df.columns:
                    df['transactionDate'] = pd.to_datetime(df['transactionDate'], unit='ms')
                
                # Excel dosyası oluştur
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, sheet_name='Finansal Rapor', index=False)
                    
                    # İstatistikler sayfası ekle
                    summary_df = pd.DataFrame({
                        'Metrik': [
                            'Toplam Ödeme', 
                            'Toplam Komisyon', 
                            'Toplam Hizmet Bedeli', 
                            'Toplam Kargo Bedeli', 
                            'Toplam Vergi',
                            'Toplam İşlem Sayısı'
                        ],
                        'Değer': [
                            df['payout'].sum() if 'payout' in df.columns else 0,
                            df['commission'].sum() if 'commission' in df.columns else 0,
                            df['serviceFee'].sum() if 'serviceFee' in df.columns else 0,
                            df['cargoPayment'].sum() if 'cargoPayment' in df.columns else 0,
                            df['tax'].sum() if 'tax' in df.columns else 0,
                            len(df)
                        ]
                    })
                    summary_df.to_excel(writer, sheet_name='Özet', index=False)
                
                output.seek(0)
                
                # İndirme dosyası oluştur
                return send_file(
                    output, 
                    download_name=f"Trendyol_Finansal_Rapor_{start_date_str}_{end_date_str}.xlsx",
                    as_attachment=True,
                    mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
                
    except Exception as e:
        logger.error(f"Hata: download_financial_report - {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
