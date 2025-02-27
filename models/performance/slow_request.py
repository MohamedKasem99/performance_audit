# Part of Odoo. See LICENSE file for full copyright and licensing details.

import re
import gzip
import logging
import io
import base64
from odoo import models, fields
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)
MAX_TIME = 3  # seconds
LOG_PATTERN = re.compile(
    r"(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3}\s"
    r"(?P<pid>\d+)\s"
    r"(?P<log_level>[A-Z]+)\s"
    r"(?P<db>[\w-]+)\s"
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

    timestamp = fields.Datetime()
    body = fields.Char(string="Body", required=True)
    ip_address = fields.Char(string="IP Address")
    num_queries = fields.Integer(string="Number of queries")
    sql_time = fields.Float(string="SQL time")
    python_time = fields.Float(string="Python time")
    pid = fields.Integer(string="Process ID")
    session = fields.Char('Session', index=True)

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
                            "timestamp": fields.Datetime.from_string(data["timestamp"]),
                            "pid": int(data["pid"]),
                            "ip_address": data["ip_address"],
                            "body": data["body"],
                            "num_queries": int(data["num_queries"]),
                            "sql_time": float(data["sql_time"]),
                            "python_time": float(data["python_time"]),
                }
        _logger.debug("Malformed log line skipped: %s", line)
