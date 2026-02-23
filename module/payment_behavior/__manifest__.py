{
    'name': "Payment Behavior",
    'summary': "Manages payment behavior analysis and metrics across modules",
    'description': """
Payment Behavior Management
============================

This module provides a centralized location for payment behavior analysis
and metrics that can be used across different modules like credit management,
sales management, and partner credit applications.

Features:
- Payment behavior tracking for invoices
- Credit limit and risk analysis
- Payment timing and percentage calculations
- Cross-module compatibility for payment behavior data
    """,
    'author': "M&S VITAMINS",
    'website': "http://www.msvitamins.co",
    'depends': [
        'contacts',
        'account',
    ],
    'data': [
        # Security
        'security/ir.model.access.csv',

        # Data
        'data/ir_cron_data.xml',
        'data/payment_behavior_config.xml',

        # Views
        'views/res_partner_view.xml',
        'views/account_move_view.xml',
        'views/credit_score_view.xml',
        'views/menu.xml',
    ],
    'demo': [
        'demo/demo_data.xml',
    ],
    'application': False,
    'category': "Accounting",
    'version': '14.0.1.1.0',
    'auto_install': False,
}
