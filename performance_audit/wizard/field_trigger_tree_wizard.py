# -*- coding: utf-8 -*-
from odoo import api, fields, models

class FieldTriggerTreeWizard(models.TransientModel):
    _name = 'field.trigger.tree.wizard'
    _description = 'Field Trigger Tree Wizard'

    model_id = fields.Many2one('ir.model', string='Model', required=True)
    field_id = fields.Many2one('ir.model.fields', string='Field', required=True,
                              domain="[('model_id', '=', model_id)]")
    
    @api.onchange('model_id')
    def _onchange_model_id(self):
        self.field_id = False
    
    def view_trigger_tree(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'field_trigger_tree',
            'name': f'Trigger Tree: {self.field_id.model}.{self.field_id.name}',
            'params': {
                'model': self.field_id.model,
                'field_name': self.field_id.name,
            }
        } 
