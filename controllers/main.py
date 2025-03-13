from odoo import http
from odoo.http import request

class PerformanceAuditDashboardController(http.Controller):
    @http.route('/performance_audit/dashboard_data', type='json', auth='user')
    def get_dashboard_data(self):
        biggest_table = request.env['pa.table.size'].search([], order='table_size desc', limit=1)
        return {
            'slow_filter_count': request.env['pa.slow.filter'].search_count([]),
            'slow_request_count': request.env['pa.slow.request'].search_count([]),
            'slow_cron_count': request.env['pa.cron.audit'].search_count([]),
            'automation_audit_count': request.env['pa.automation.audit'].search_count([]),
            'biggest_table_size_human': biggest_table.table_size_human,
            'biggest_table_name': biggest_table.name,
        }

class FieldTriggerTreeController(http.Controller):
    @http.route('/performance_audit/get_field_trigger_tree', type='json', auth='user')
    def get_field_trigger_tree(self, model, field_name):
        """Get the trigger tree for a field and convert it to a format suitable for visualization."""
        try:
            field = request.env[model]._fields.get(field_name)
            if not field:
                return {'error': f"Field {field_name} not found in model {model}"}
            
            # Get the trigger tree
            registry = request.env.registry
            trigger_tree = registry.get_field_trigger_tree(field)
            
            # Convert to a format suitable for visualization
            result = self._format_trigger_tree(trigger_tree, model, field_name)
            return result
        except Exception as e:
            return {'error': str(e)}
    
    def _format_trigger_tree(self, tree, model, field_name, path=None):
        """Convert TriggerTree to a format suitable for visualization"""
        if path is None:
            path = []
        
        # Create node for current level
        node = {
            'id': '.'.join(path) if path else f"{model}.{field_name}",
            'name': path[-1] if path else field_name,
            'model': model,
            'children': [],
            'dependents': []
        }
        
        # Add dependent fields
        if hasattr(tree, 'root') and tree.root:
            for dependent in tree.root:
                node['dependents'].append({
                    'id': f"{dependent.model_name}.{dependent.name}",
                    'name': dependent.name,
                    'model': dependent.model_name
                })
        
        # Process child nodes
        for label, subtree in tree.items():
            child_path = path + [label.name]
            child_node = self._format_trigger_tree(subtree, label.model_name, label.name, child_path)
            node['children'].append(child_node)
        
        return node 
