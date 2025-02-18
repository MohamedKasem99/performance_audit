# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields
from odoo.exceptions import UserError


class PerformanceAuditWizard(models.TransientModel):
    _name = 'performance.audit.wizard'
    _description = 'Performance Audit Wizard'
    _transient_max_hours = 1
    _transient_max_count = 1

    audit_ts = fields.Datetime(string="Audit start timestamp", default=fields.Datetime.now)
    slow_filters = fields.Boolean(string='Slow Filters')
    slow_crons = fields.Boolean(string='Slow Crons')
    slow_requests = fields.Boolean(string='Slow Requests')
    log_file = fields.Binary(string="Log file")
    log_file_name = fields.Char(string="Log file name")
    slow_requests_threshold = fields.Float(
        string='Requests Threshold (secs)',
        default=2.0
    )
    slow_filters_threshold = fields.Float(
        string='Filters Threshold (secs)',
        default=2.0
    )
    batch_size = fields.Integer(string='Batch Size', default=5)
    offset = fields.Integer(string='Starting Offset', default=0)

    def run_audit(self):
        """
        Called by the wizard to run selected performance checks.
        """
        session = f"{self.audit_ts} {self.env.user.name}"
        if self.slow_crons:
            pass
            #TODO: Implement slow crons audit

        if self.slow_requests:
            self.env["pa.slow.request"].with_context(
                threshold=self.slow_requests_threshold
            ).run_script(session, self.log_file, self.log_file_name)

        if self.slow_filters:
            return {
                'type': 'ir.actions.client',
                'tag': 'pa_slow_filter_audit',
                'params': {
                    'slow_filters_threshold': self.slow_filters_threshold,
                    'batch_size': self.batch_size,
                    'offset': self.offset,
                }
            }

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
