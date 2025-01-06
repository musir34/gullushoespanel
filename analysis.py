
from flask import Blueprint, render_template

analysis_bp = Blueprint('analysis_bp', __name__)

@analysis_bp.route('/analysis')
def analysis_page():
    return render_template('analysis.html')
