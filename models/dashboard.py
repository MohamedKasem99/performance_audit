from odoo import models, fields, api

class PerformanceAuditDashboard(models.Model):
    _name = 'pa.dashboard'
    _description = 'Performance Audit Dashboard'

    slow_filter_count = fields.Integer(compute='_compute_slow_filter_count')
    slow_request_count = fields.Integer(compute='_compute_slow_request_count')

    @api.depends()
    def _compute_slow_filter_count(self):
        self.slow_filter_count = self.env['pa.slow.filter'].search_count([])

    @api.depends()
    def _compute_slow_request_count(self):
        self.slow_request_count = self.env['pa.slow.request'].search_count([])

    def action_run_audit(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Run Performance Audit',
            'res_model': 'performance.audit.wizard',
            'view_mode': 'form',
            'target': 'new',
        }
