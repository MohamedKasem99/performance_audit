# slow cron_ids

from odoo import models, fields, api
import re
from collections import defaultdict
from datetime import datetime
import gzip

class CronExecution(models.Model):
    _name = 'pa.cron.execution'
    _description = 'Cron Executions'

    cron_audit_id = fields.Many2one('pa.cron.audit', string='Cron Audit', ondelete='cascade')
    duration = fields.Float('Duration')
    timestamp = fields.Datetime('Timestamp')
    is_timeout = fields.Boolean('Is Timeout')

class CronAudit(models.Model):
    _name = 'pa.cron.audit'
    _description = 'Cron Audit'

    name = fields.Char('Name')
    cron_id = fields.Many2one('ir.cron', string='Cron')
    last_execution = fields.Datetime('Last Execution', compute='_compute_stats', store=True)
    average_execution_time = fields.Float('Average Execution Time', compute='_compute_stats', store=True)
    total_executions = fields.Integer('Total Executions', compute='_compute_stats', store=True)
    execution_ids = fields.One2many('pa.cron.execution', 'cron_audit_id', 'Executions', readonly=True)
    num_timeouts = fields.Integer('Number of Errors/Timeouts')
    slowest_execution = fields.Float('Slowest Execution', compute='_compute_stats', store=True)

    @api.depends('execution_ids')
    def _compute_stats(self):
        for cron in self:
            cron.slowest_execution = max(execution.duration for execution in cron.execution_ids)
            cron.average_execution_time = sum(execution.duration for execution in cron.execution_ids) / len(cron.execution_ids)
            cron.total_executions = len(cron.execution_ids)
            cron.last_execution = max(execution.timestamp for execution in cron.execution_ids) if cron.execution_ids else None

    def audit_crons(self, logs):
        start_patterns = [
            re.compile(r"(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*Starting job `(?P<cron_name>.+?)`\."),
            re.compile(r"(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*Starting job `(?P<cron_name>.+?)`"),
            re.compile(r"(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*Job '(?P<cron_name>.+?)' \(\d+\) starting")
        ]
        end_patterns = [
            re.compile(r"(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*Job `(?P<cron_name>.+?)` done\."),
            re.compile(r"(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*Job done: `(?P<cron_name>.+?)` \((?P<duration>[0-9\.]+)s\)\."),
            re.compile(r"(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*Job '(?P<cron_name>.+?)' \(\d+\) done in (?P<duration>[0-9\.]+)s")
        ]

        cron_executions = defaultdict(list)  # To store timing data for each cron
        active_crons = {}  # To track active cron_ids by name
        for line in logs.readlines():
            for start_pattern in start_patterns:
                start_match = start_pattern.search(line)
                if start_match:
                    cron_name = start_match.group("cron_name")
                    timestamp = datetime.strptime(start_match.group("timestamp"), "%Y-%m-%d %H:%M:%S,%f")

                    if cron_name in active_crons:
                        cron_executions[cron_name].append({
                            "timestamp": timestamp,
                            "is_timeout": True,
                        })

                    active_crons[cron_name] = timestamp
                    break

            # Check for end line
            for end_pattern in end_patterns:
                end_match = end_pattern.search(line)
                if end_match:
                    cron_name = end_match.group("cron_name")
                    timestamp = datetime.strptime(end_match.group("timestamp"), "%Y-%m-%d %H:%M:%S,%f")

                    if cron_name in active_crons:
                        start_time = active_crons.pop(cron_name)
                        if "duration" in end_match.groupdict():
                            duration = float(end_match.group("duration"))
                        else:
                            duration = (timestamp - start_time).total_seconds()

                        cron_executions[cron_name].append(
                            {
                                "timestamp": start_time,
                                "duration": duration,
                                "is_timeout": False,
                            }
                        )
                    break

        cron_ids = self.env["ir.cron"].with_context(active_test=False).search([("cron_name", "in", list(cron_executions.keys()))])
        cron_audit_vals = []
        for cron in cron_ids:
            cron_audit_vals.append({
                'cron_id': cron.id,
                'name': cron.name,
            }) 
        cron_audit_ids = self.create(cron_audit_vals)
        execution_vals = []
        for cron_audit, execution in zip(cron_audit_ids, cron_executions.values()):
            for execution in cron_executions[cron_audit.name]:
                execution['cron_audit_id'] = cron_audit.id
                execution_vals.append(execution)
        self.env['pa.cron.execution'].create(execution_vals)
