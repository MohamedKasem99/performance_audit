from odoo import http
from odoo.http import request

class PerformanceAuditController(http.Controller):
    @http.route('/performance_audit/dashboard_data', type='json', auth='user')
    def get_dashboard_data(self):
        biggest_table = request.env['pa.table.size'].search([], order='table_size desc', limit=1)
        return {
            'slow_filter_count': request.env['pa.slow.filter'].search_count([]),
            'slow_request_count': request.env['pa.slow.request'].search_count([]),
            'slow_cron_count': request.env['pa.cron.audit'].search_count([]),
            'biggest_table_size': biggest_table.table_size,
            'biggest_table_name': biggest_table.name,
        } 
