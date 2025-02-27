# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields
import base64
import gzip
import io
import logging

_logger = logging.getLogger(__name__)


class PerformanceAuditWizard(models.TransientModel):
    _name = 'performance.audit.wizard'
    _description = 'Performance Audit Wizard'
    _transient_max_hours = 1
    _transient_max_count = 1

    audit_ts = fields.Datetime(string="Audit start timestamp", default=fields.Datetime.now)
    slow_filters = fields.Boolean(string='Slow Filters')
    cron_audit = fields.Boolean(string='Cron Audit')
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
    slow_crons_threshold = fields.Float(
        string='Crons Threshold (secs)',
        default=10.0
    )
    batch_size = fields.Integer(string='Batch Size', default=5)
    offset = fields.Integer(string='Starting Offset', default=0)
    table_size = fields.Boolean(string='Table Size')

    def _process_log_file(self, log_file, log_file_name):
        log_file = base64.b64decode(log_file)
        if log_file_name.endswith(".gz"):
            file_obj = gzip.GzipFile(fileobj=io.BytesIO(log_file))
        else:
            file_obj = io.BytesIO(log_file)
        return io.TextIOWrapper(file_obj, encoding='utf-8')

    def run_audit(self):
        """
        Called by the wizard to run selected performance checks.
        """
        if self.cron_audit:
            _logger.info("Auditing crons in log file %s", self.log_file_name)
            logs = self._process_log_file(self.log_file, self.log_file_name)
            self.env["pa.cron.audit"].with_context(
                threshold=self.slow_crons_threshold
            ).audit_crons(logs)

        if self.slow_requests:
            _logger.info("Auditing requests in log file %s", self.log_file_name)
            logs = self._process_log_file(self.log_file, self.log_file_name)
            self.env["pa.slow.request"].with_context(
                threshold=self.slow_requests_threshold
            ).audit_requests(logs)

        if self.table_size:
            _logger.info("Capturing table sizes")
            self.env["pa.table.size"].capture_table_sizes()

        if self.slow_filters:
            _logger.info("Auditing filters")
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
