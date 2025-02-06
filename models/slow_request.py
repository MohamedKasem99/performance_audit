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

    def run_script(self, session, log_file, log_file_name):
        vals = self.process_log_file(log_file, log_file_name, session)
        self.create(vals)

    def parse_log_line(self, line):
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

    def _handle_gzip(self, log_file, session):
        vals = []
        with gzip.GzipFile(fileobj=io.BytesIO(log_file)) as logs:
            for line in logs:
                data = self.parse_log_line(line.decode())
                if data:
                    vals.append(dict(**data, session=session))
        return vals


    def _handle_flat_file(self, log_file, session):
        vals = []
        for line in log_file.decode('utf-8'):
            data = self.parse_log_line(line)
            if data:
                vals.append(dict(**data, session=session))
        return vals
    

    def process_log_file(self, log_file, log_file_name, session):
        log_file = base64.b64decode(log_file)
        if log_file_name.endswith(".gz"):
            try:
                vals = self._handle_gzip(log_file, session)
            except gzip.BadGzipFile as e:
                raise UserError(f"Error: File {log_file_name} is not a valid gzip file.") from e
        else:
            vals = self._handle_flat_file(log_file, session)
        return vals
