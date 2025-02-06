# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields
from odoo.exceptions import UserError


class PerformanceAuditWizard(models.TransientModel):
    _name = 'performance.audit.wizard'
    _description = 'Performance Audit Wizard'

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

    def run_audit(self):
        """
        Called by the wizard to run selected performance checks.
        """
        session = f"{self.audit_ts} {self.env.user.name}"
        if self.slow_crons:
            if not self.log_file:
                raise UserError("A log file is required for this audit")
            #TODO: Implement slow crons audit

        if self.slow_requests:
            if not self.log_file:
                raise UserError("A log file is required for this audit")
            self.env["pa.slow.request"].with_context(
                threshold=self.slow_requests_threshold
            ).run_script(session, self.log_file, self.log_file_name)

        if self.slow_filters:
            self.env["pa.slow.filter"].with_context(
                threshold=self.slow_filters_threshold
            ).run_script(session)

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
