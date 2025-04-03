# Part of Odoo. See LICENSE file for full copyright and licensing details.

import re
import gzip
import logging
import io
import base64
from odoo import models, fields, api
from odoo.exceptions import UserError
import datetime

_logger = logging.getLogger(__name__)
MAX_TIME = 3  # seconds
LOG_PATTERN = re.compile(
    r"(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3}\s"
    r"(?P<pid>\d+)\s"
    r"(?P<log_level>[A-Z]+)\s"
    r".*"
    r"(?P<logger>[\w:]+):\s"
    r"(?P<ip_address>[\d.]+)\s-\s-\s\[.*\]\s"
    r"\"(?P<body>.+?)\"\s\d+\s-\s"
    r"(?P<num_queries>\d+)\s"
    r"(?P<sql_time>\d+\.\d+)\s"
    r"(?P<python_time>\d+\.\d+)"
)


class SlowRequest(models.Model):
    _name = 'pa.slow.request'
    _description = 'Slow Requests'

    end_timestamp = fields.Datetime()
    end_timestamp_utc = fields.Char(string="End timestamp UTC", compute='_compute_timestamps_utc', store=True)
    body = fields.Char(string="Body", required=True)
    ip_address = fields.Char(string="IP Address")
    num_queries = fields.Integer(string="Number of queries")
    sql_time = fields.Float(string="SQL time")
    python_time = fields.Float(string="Python time")
    total_time = fields.Float(string="Total time", compute='_compute_total_time', store=True)
    pid = fields.Integer(string="Process ID")
    start_timestamp = fields.Datetime(string="Start timestamp", compute='_compute_start_timestamp', store=True)
    start_timestamp_utc = fields.Char(string="Start timestamp UTC", compute='_compute_timestamps_utc', store=True)

    @api.depends('end_timestamp')
    def _compute_start_timestamp(self):
        for record in self:
            record.start_timestamp = record.end_timestamp - datetime.timedelta(seconds=record.total_time)

    @api.depends('sql_time', 'python_time')
    def _compute_total_time(self):
        for record in self:
            record.total_time = record.sql_time + record.python_time

    @api.depends('end_timestamp')
    def _compute_timestamps_utc(self):
        for record in self:
            record.end_timestamp_utc = fields.Datetime.to_string(record.end_timestamp) + ' UTC'
            record.start_timestamp_utc = fields.Datetime.to_string(record.start_timestamp) + ' UTC'

    def audit_requests(self, logs):
        vals = []
        for line in logs.readlines():
            data = self._parse_log_line(line)
            if data:
                vals.append(data)
        self.create(vals)

    def _parse_log_line(self, line):
        match = LOG_PATTERN.match(line)
        threshold = self.env.context.get("threshold", MAX_TIME)
        if match:
            data = match.groupdict()
            if float(data['sql_time']) + float(data['python_time']) > threshold:
                return {
                            "end_timestamp": fields.Datetime.from_string(data["timestamp"]),
                            "pid": int(data["pid"]),
                            "ip_address": data["ip_address"],
                            "body": data["body"],
                            "num_queries": int(data["num_queries"]),
                            "sql_time": float(data["sql_time"]),
                            "python_time": float(data["python_time"]),
                }
        _logger.debug("Malformed log line skipped: %s", line)
