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

class SlowRequestController(http.Controller):
    @http.route('/performance_audit/slow_requests_data', type='json', auth='user')
    def slow_requests_data(self):
        requests = request.env['pa.slow.request'].search_read(
            [],
            ['id', 'body', 'start_timestamp', 'end_timestamp', 'ip_address',
             'total_time', 'sql_time', 'python_time', 'num_queries']
        )

        # Group data by date
        grouped_data = {}
        available_dates = []
        
        for req in requests:
            date_str = str(req['start_timestamp'].date())
            
            # Initialize date group if it doesn't exist
            if date_str not in grouped_data:
                grouped_data[date_str] = []
                available_dates.append(date_str)
            
            # Format the item for vis.js timeline
            timeline_item = {
                'id': req['id'],
                'content': req['body'][:30] + ('...' if len(req['body']) > 30 else ''),
                'title': f"{req['body']}<br>Total Time: {req['total_time']}s<br>SQL Time: {req['sql_time']}s<br>Python Time: {req['python_time']}s<br>Queries: {req['num_queries']}",
                'start': req['start_timestamp'],
                'end': req['end_timestamp'],
                'group': date_str
            }
            
            grouped_data[date_str].append(timeline_item)
        
        # Create timeline-ready data structure
        timeline_data = {
            'all': [],  # Contains all items for "All Dates" view
            'byDate': grouped_data,  # Contains items grouped by date
            'availableDates': sorted(available_dates)
        }
        
        # Add all items to the 'all' category
        for date_items in grouped_data.values():
            timeline_data['all'].extend(date_items)
        
        return timeline_data
