# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import models, fields, api
from collections import defaultdict

class TableColumnSize(models.Model):
    _name = 'pa.table.column.size'
    _description = 'Database Table Column Sizes'
    _order = 'size desc'

    table_id = fields.Many2one('pa.table.size', required=True, ondelete='cascade')
    name = fields.Char('Column Name', required=True)
    size = fields.Integer('Size (bytes)', compute='_compute_size', store=True, readonly=True)

    @api.depends('name')
    def _compute_size(self):
        table_columns = defaultdict(list)
        for record in self:
            table_columns[record.table_id].append(record)

        for table_id, columns in table_columns.items():
            query = f"""
                SELECT {', '.join(f'SUM(pg_column_size("{column.name}"))' for column in columns)}
                FROM {table_id.schema}.{table_id.name}
            """
            self.env.cr.execute(query)
            column_sizes = self.env.cr.fetchall()[0]
            for column, size in zip(columns, column_sizes):
                column.size = size or 0
                



class TableSize(models.Model):
    _name = 'pa.table.size'
    _description = 'Database Table Sizes'
    _order = 'table_size desc'

    name = fields.Char('Table Name', required=True, index=True)
    schema = fields.Char('Schema Name', required=True, default='public')
    
    # Sizes in bytes
    table_size = fields.Integer('Table Size')
    index_size = fields.Integer('Index Size')
    toast_size = fields.Integer('TOAST Size')
    column_size_ids = fields.One2many('pa.table.column.size', 'table_id', string='Column Sizes', readonly=True)
    

    def capture_table_sizes(self):
        self.env.cr.execute("""
            SELECT
                schemaname,
                tablename,
                pg_total_relation_size(quote_ident(schemaname) || '.' || quote_ident(tablename)) as total_size,
                pg_indexes_size(quote_ident(schemaname) || '.' || quote_ident(tablename)) as index_size,
                COALESCE(pg_total_relation_size(reltoastrelid), 0) as toast_size
            FROM pg_tables t
            LEFT JOIN pg_class c ON c.relname = t.tablename
            WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
            ORDER BY total_size DESC
        """)
        
        tables_vals = []
        for row in self.env.cr.fetchall():
            table_vals = {
                'schema': row[0],
                'name': row[1],
                'table_size': row[2],
                'index_size': row[3],
                'toast_size': row[4],
            }
            tables_vals.append(table_vals)

        tables = self.create(tables_vals)
        column_vals = []
        for table in tables:
            # Build query for each column in the table
            self.env.cr.execute("""
                SELECT 
                    attname
                FROM pg_attribute a 
                JOIN pg_class c ON c.oid = a.attrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = %s 
                    AND c.relname = %s
                    AND a.attnum > 0 
                    AND NOT a.attisdropped
            """, (table.schema, table.name))
            
            columns = [row[0] for row in self.env.cr.fetchall()]
            # create a record for each column
            for column in columns:
                column_vals.append({
                    'table_id': table.id,
                    'name': column,
                })
        # Create all column size records
        if column_vals:
            self.env['pa.table.column.size'].create(column_vals)
