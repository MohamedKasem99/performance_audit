# slow crons_ids_by_name

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
    timestamp_utc = fields.Char('Timestamp UTC', compute='_compute_timestamp_utc')
    is_timeout = fields.Boolean('Is Timeout')

    @api.depends('timestamp')
    def _compute_timestamp_utc(self):
        for record in self:
            record.timestamp_utc = fields.Datetime.to_string(record.timestamp) + ' UTC'
    

class CronAudit(models.Model):
    _name = 'pa.cron.audit'
    _description = 'Cron Audit'

    name = fields.Char('Name')
    cron_id = fields.Many2one('ir.cron', string='Cron')
    average_execution_time = fields.Float('Average Execution Time', compute='_compute_stats', store=True)
    total_executions = fields.Integer('Total Executions', compute='_compute_stats', store=True)
    execution_ids = fields.One2many('pa.cron.execution', 'cron_audit_id', 'Executions', readonly=True)
    slowest_execution_timestamp = fields.Datetime('Slowest Execution Timestamp', compute='_compute_stats', store=True)
    slowest_execution_duration = fields.Float('Slowest Execution Duration', compute='_compute_stats', store=True)
    slowest_execution_utc = fields.Char('Last Execution UTC', compute='_compute_stats', store=True)
    num_timeouts = fields.Integer('Number of Errors/Timeouts', compute='_compute_stats', store=True)

    @api.depends('execution_ids')
    def _compute_stats(self):
        for cron in self:
            cron.average_execution_time = sum(execution.duration for execution in cron.execution_ids) / len(cron.execution_ids)
            cron.total_executions = len(cron.execution_ids)
            slowest_execution = max(cron.execution_ids, key=lambda x: x.duration)
            cron.slowest_execution_timestamp = slowest_execution.timestamp
            cron.slowest_execution_duration = slowest_execution.duration
            cron.slowest_execution_utc = fields.Datetime.to_string(slowest_execution.timestamp) + ' UTC'
            cron.num_timeouts = sum(1 for execution in cron.execution_ids if execution.is_timeout)

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
        active_crons = {}  # To track active crons by name
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

        crons_ids_by_name = self.env["ir.cron"].with_context(active_test=False).search([("cron_name", "in", list(cron_executions.keys()))]).grouped('name')
        cron_audit_vals = []
        for cron_name in cron_executions.keys():
            cron = crons_ids_by_name.get(cron_name)
            cron_id = cron.id if cron else None
            cron_audit_vals.append({
                'cron_id': cron_id,
                'name': cron_name,
            })
        cron_audit_ids = self.create(cron_audit_vals)
        execution_vals = []
        for cron_audit, executions in zip(cron_audit_ids, cron_executions.values()):
            for execution in executions:
                execution['cron_audit_id'] = cron_audit.id
                execution_vals.append(execution)
        self.env['pa.cron.execution'].create(execution_vals)
