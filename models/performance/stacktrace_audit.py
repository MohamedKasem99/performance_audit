import re
from odoo import models, fields, api


class StacktraceAudit(models.Model):
    _name = "pa.stacktrace.audit"
    _description = "Stacktrace Audit"

    timestamp = fields.Datetime(string="Timestamp")
    timestamp_utc = fields.Char(
        string="Timestamp UTC", compute="_compute_timestamp_utc", store=True
    )
    stacktrace = fields.Text(string="Stacktrace")
    error_type = fields.Char(string="Error Type")
    error_module = fields.Char(string="Error Module")
    pid = fields.Char(string="PID")
    database = fields.Char(string="Database")

    @api.depends("timestamp")
    def _compute_timestamp_utc(self):
        for record in self:
            record.timestamp_utc = fields.Datetime.to_string(record.timestamp) + " UTC"

    def get_stats(self):
        """
        Get stats about the stacktrace audit.
        """
        most_common_stacktrace = self.env["pa.stacktrace.audit"]._read_group(
            [],
            aggregates=["error_type:count"],
            groupby=["error_type"],
            order="error_type:count desc",
            limit=1,
        )
        count_per_database = self.env["pa.stacktrace.audit"]._read_group(
            [],
            aggregates=["database:count"],
            groupby=["database"],
            order="database:count desc",
            limit=1,
        )
        return {
            "count": self.search_count([]),
            "mostCommonError": most_common_stacktrace[0][0] if most_common_stacktrace else "",
            "countPerDatabase": count_per_database[0][0] if count_per_database else "",
        }

    def audit_stacktraces(self, logs):
        """
        State machine approach to parse log lines to extract stacktraces.
        A stacktrace is a block of lines that starts with an errorlog line and ends with
        a new log line (INFO, WARNING, DEBUG) or a new stacktrace.
        """
        current_stacktrace = ""
        error_pattern = re.compile(
            r"(^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3} (\d+) ERROR (\S*) (\S*): (.*)"
        )
        next_line_pattern = re.compile(
            r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} \d+ (INFO|WARNING|DEBUG) .*"
        )
        stacktraces = []
        state = "NORMAL"

        def _extract_stacktrace_header(line):
            # extract the timestamp, module name, error type from the line in error_pattern
            error_info = error_pattern.search(line)
            timestamp = error_info.group(1)
            pid = error_info.group(2)
            database = error_info.group(3)
            module_name = error_info.group(4)
            error_type = error_info.group(5)
            return timestamp, pid, database, module_name, error_type

        for line in logs.readlines():
            # if we're normal state and the line is an error log line, we're in a stacktrace.
            # The normal state otherwise do nothing.
            if state == "NORMAL" and error_pattern.match(line):
                state = "IN_STACKTRACE"
                current_stacktrace = line
                timestamp, pid, database, module_name, error_type = (
                    _extract_stacktrace_header(line)
                )

            elif state == "IN_STACKTRACE":
                if next_line_pattern.match(line) or error_pattern.match(line):
                    stacktraces.append(
                        {
                            "timestamp": timestamp,
                            "pid": pid,
                            "database": database,
                            "error_module": module_name,
                            "error_type": error_type,
                            "stacktrace": current_stacktrace,
                        }
                    )
                    # reset if new log line, otherwise it's a new stacktrace so handle it
                    current_stacktrace = "" if not error_pattern.match(line) else line
                    state = (
                        "NORMAL" if not error_pattern.match(line) else "IN_STACKTRACE"
                    )
                else:
                    current_stacktrace += line

        # Handle the last stacktrace
        if state == "IN_STACKTRACE" and current_stacktrace:
            timestamp, pid, database, module_name, error_type = (
                _extract_stacktrace_header(current_stacktrace)
            )
            stacktraces.append(
                {
                    "timestamp": timestamp,
                    "pid": pid,
                    "database": database,
                    "error_module": module_name,
                    "error_type": error_type,
                    "stacktrace": current_stacktrace,
                }
            )
        self.create(stacktraces)

    @api.model
    def web_read_group(
        self, domain, fields, groupby, limit=None, offset=0, orderby=False, lazy=True
    ):
        """
        Override the default web_read_group to return groups sorted by the count of the group
        """
        result = super().web_read_group(
            domain,
            fields,
            groupby,
            limit=None,
            offset=0,
            orderby=orderby,
            lazy=lazy,
        )
        # sort the groups by the count field
        if result["groups"]:
            count_field = f"{groupby[0]}_count" if groupby else None
            if count_field and count_field in result["groups"][0]:
                result["groups"].sort(key=lambda x: x[count_field], reverse=True)
        # handle offset then limit
        if offset:
            result["groups"] = result["groups"][offset:]
        if limit:
            result["groups"] = result["groups"][:limit]
        return result