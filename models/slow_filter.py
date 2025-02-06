# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import time
from odoo import models, fields


_logger = logging.getLogger(__name__)
MAX_TIME = 2  # seconds


class SlowFilter(models.Model):
    _name = 'pa.slow.filter'
    _description = 'Slow Filters'

    name = fields.Many2one('ir.filters', string='Name', required=True, ondelete='cascade')
    model_id = fields.Char(string='Model', required=True, help="The model this filter belongs to")
    domain = fields.Text(required=True)
    duration = fields.Float(string='Duration (seconds)', required=True)
    session = fields.Char('Session', index=True)

    def run_script(self, session):
        Filters = self.env["ir.filters"]
        vals = []
        threshold = self.env.context.get("threshold", MAX_TIME)
        for f in Filters.search([("active", "=", True)]):
            try:
                start = time.time()
                self.env[f.model_id].search_count(f._get_eval_domain())
                duration = round(time.time() - start, 2)
                self.env.cr.commit()
                _logger.debug(
                    "Model: %s -> Filter name: %s, Duration: %s",
                    f.model_id,
                    f.name,
                    duration,
                )
                if duration > threshold:
                    _logger.info(
                        "Slow filter detected (Model: %s -> Filter name: %s, Duration: %s",
                        f.model_id,
                        f.name,
                        duration,
                    )
                    vals.append(
                        {
                            "name": f.id,
                            "model_id": f.model_id,
                            "domain": f.domain,
                            "duration": duration,
                            "session": session,
                        }
                    )
            except ValueError as e:
                self.env.cr.rollback()
                _logger.exception(e)
        self.create(vals)
