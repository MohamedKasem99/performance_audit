from odoo import http
from odoo.http import request

class PerformanceAuditController(http.Controller):
    @http.route('/performance_audit/dashboard_data', type='json', auth='user')
    def get_dashboard_data(self):
        return {
            'slow_filter_count': request.env['pa.slow.filter'].search_count([]),
            'slow_request_count': request.env['pa.slow.request'].search_count([]),
        } 
