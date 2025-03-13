# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import ast
import logging
from odoo import api, fields, models, _
from odoo.tools.safe_eval import safe_eval
from itertools import chain

_logger = logging.getLogger(__name__)

# Constants
LARGE_DOMAIN_THRESHOLD = 100
PROBLEMATIC_DB_METHODS = ['search', 'search_count', 'browse', 'create', 'write',
                          'unlink', 'read', 'read_group']

class AutomationRuleAudit(models.Model):
    _name = 'pa.automation.audit'
    _description = 'Automation Rule Audit'
    _order = 'issue_count desc'

    automation_rule_id = fields.Many2one('base.automation', string='Automation Rule', ondelete='cascade')
    model_id = fields.Many2one('ir.model', string='Model', readonly=True)
    issue_ids = fields.One2many('pa.automation.audit.issue', 'audit_id', string='Issues', readonly=True)
    issue_count = fields.Integer(compute='_compute_issue_count', store=True)

    @api.depends('issue_ids')
    def _compute_issue_count(self):
        for record in self:
            record.issue_count = len(record.issue_ids)

    @api.model
    def run_audit(self):
        """Run audit on all automation rules"""
        self.search([]).unlink()

        automation_audits = []
        audit_issues = []
        for rule in self.env['base.automation'].search([]):
            issues = []
            # Check for large domain
            try:
                model = self.env[rule.model_id.model]
                domain = safe_eval(rule.filter_domain or '[]')
                record_count = model.search_count(domain)
            except Exception as e:
                _logger.warning("Error evaluating domain for rule '%s': %s", rule.name, e)

            if record_count > LARGE_DOMAIN_THRESHOLD:
                issues.append({
                    'issue_type': 'large_domain',
                    'record_count': record_count,
                    'code_snippet': rule.filter_domain,
                    'recommendation': _(
                            "This automation rule applies to %d records. Consider narrowing the domain to improve performance."
                        ) % record_count
                    })
            # Check for batching issues
            batching_issues = self._check_batching_issues(rule, record_count)
            if batching_issues:
                issues.append(batching_issues)

            if issues:
                automation_audits.append({
                    'automation_rule_id': rule.id,
                    'model_id': rule.model_id.id,

                })
                audit_issues.append(issues)

        audits = self.create(automation_audits)
        for audit, issues in zip(audits, audit_issues):
            for issue in issues:
                issue['audit_id'] = audit.id
        self.env['pa.automation.audit.issue'].create(list(chain(*audit_issues)))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Automation Rule Audit Results'),
            'res_model': 'pa.automation.audit',
            'view_mode': 'tree,form',
        }

    @api.model
    def _check_large_domain(self, rule):
        """Check if rule's domain affects too many records"""
        if not rule.action_server_ids:
            return

        try:
            model = self.env[rule.model_id.model]
            domain = safe_eval(rule.filter_domain or '[]')
            record_count = model.search_count(domain)

            if record_count > LARGE_DOMAIN_THRESHOLD:
                return {
                    'issue_type': 'large_domain',
                    'record_count': record_count,
                    'code_snippet': rule.filter_domain,
                    'recommendation': _(
                        "This automation rule applies to %d records. Consider narrowing the domain to improve performance."
                    ) % record_count
                }
        except Exception as e:
            _logger.warning("Error evaluating domain for rule '%s': %s", rule.name, e)

    @api.model
    def _check_batching_issues(self, rule, record_count):
        """Check for DB operations inside loops"""
        try:
            issue_lines = []
            for action in rule.action_server_ids.filtered(lambda a: a.state == 'code' and a.code):
                issue_lines.extend(self._analyze_code(action))
            if issue_lines:
                return {
                    'issue_type': 'no_batching',
                    'record_count': record_count,
                    'code_snippet': '\n'.join(issue_lines),
                    'recommendation': _(
                        "Code contains DB operations inside loops. Use recordsets and batch operations instead."
                    )
                }
        except Exception as e:
            _logger.warning("Error analyzing code for rule '%s': %s", rule.name, e)

        return None

    @api.model
    def _analyze_code(self, action):
        """Find database operations inside loops"""
        try:
            visitor = BatchingVisitor(action)
            return visitor.analyze()
        except Exception as e:
            _logger.warning("Code analysis error: %s", e)
            return []


class AutomationRuleAuditIssue(models.Model):
    _name = 'pa.automation.audit.issue'
    _description = 'Automation Rule Audit Issue'
    _order = 'issue_type desc'

    audit_id = fields.Many2one('pa.automation.audit', required=True, ondelete='cascade')
    issue_type = fields.Selection([
        ('no_batching', 'No Batching'),
        ('large_domain', 'Large Domain')
    ], readonly=True, required=True)
    record_count = fields.Integer(readonly=True)
    code_snippet = fields.Text(readonly=True)
    recommendation = fields.Text(readonly=True)

class BatchingVisitor(ast.NodeVisitor):
    """AST visitor to detect DB operations in loops and through function calls"""

    def __init__(self, action):
        self.action = action
        self.in_loop = False
        self.loop_depth = 0
        self.issues = []
        self.functions_with_db_ops = set()
        self.current_function = None
        self.function_stack = []
        self.processed_function_calls = set()

        # override the visit methods to call the _process_loop_node method
        self.visit_For = self._process_loop_node
        self.visit_While = self._process_loop_node
        self.visit_ListComp = self._process_loop_node
        self.visit_DictComp = self._process_loop_node
        self.visit_SetComp = self._process_loop_node
        self.visit_GeneratorExp = self._process_loop_node

    def visit_FunctionDef(self, node):
        if self.current_function:
            self.function_stack.append(self.current_function)

        self.current_function = node.name
        self.generic_visit(node)

        if self.function_stack:
            self.current_function = self.function_stack.pop()
        else:
            self.current_function = None

    def _process_loop_node(self, node):
        self.loop_depth += 1
        self.in_loop = True
        self.generic_visit(node)
        self.loop_depth -= 1
        self.in_loop = self.loop_depth > 0

    def visit_Call(self, node):
        self.generic_visit(node)

        if isinstance(node.func, ast.Attribute) and node.func.attr in PROBLEMATIC_DB_METHODS:
            if self.current_function:
                self.functions_with_db_ops.add(self.current_function)

            if self.in_loop:
                line_no = node.lineno
                line = self.action.code.split('\n')[line_no-1].strip()
                self.issues.append(f"Action ({self.action.id}) - DB operation inside loop \n - Line {line_no}: {line}")

        elif isinstance(node.func, ast.Name):
            function_name = node.func.id

            # If we're in a loop, check if the called function has DB operations
            if self.in_loop and function_name in self.functions_with_db_ops:
                # Create a unique ID for this call to avoid duplicates
                call_id = (function_name, node.lineno)
                if call_id not in self.processed_function_calls:
                    line_no = node.lineno
                    line = self.action.code.split('\n')[line_no-1].strip()
                    self.issues.append(f"Action ({self.action.id}) - Function with DB operations called inside loop \n - Line {line_no}: {line}")
                    self.processed_function_calls.add(call_id)

    def analyze(self):
        try:
            tree = ast.parse(self.action.code)
            self.visit(tree)
            return self.issues

        except Exception as e:
            _logger.warning("Error analyzing code for action (%s): %s", self.action.id, e)
            return []
