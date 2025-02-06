{
    'name': 'Performance Audit',
    'version': '1.0',
    'summary': 'Gather information about possible performance degradation',
    'category': 'Tools',
    'author': 'kasm',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/performance_audit_wizard.xml',
        'views/performance_menu.xml',
        'views/slow_filter_views.xml',
        'views/slow_request_views.xml',
    ],
    'installable': True,
    'application': True,
}
