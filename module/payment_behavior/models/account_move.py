import json
from datetime import datetime, timedelta
from odoo import fields, models, api

import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    days_to_pay = fields.Integer(
        string='Days to Pay',
        compute='compute_payment_behavior',
        store=True,
        group_operator="avg",
        help="Number of days from invoice date to payment date"
    )
    payment_behavior = fields.Selection([
        ('on_time', 'On Time'),
        ('delay', 'Delay'),
        ('not_paid', 'Not Paid')
    ], string='Payment Behavior',
        compute='compute_payment_behavior',
        store=True,
        help="Payment behavior classification based on due date and grace period"
    )
    payment_date = fields.Date(
        string="Payment Date",
        compute="compute_payment_behavior",
        store=True,
    )
    invoice_net_date_due = fields.Date(
        string='Net Date Due',
        compute='_compute_invoice_net_date_due',
        store=True,
        help="The date when the invoice is due with any grace period"
    )

    @api.depends('invoice_date_due')
    def _compute_invoice_net_date_due(self):
        """Compute the net date due for the invoice, considering payment terms."""
        grace_days = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'payment_behavior.grace_days_payment', default='0'
            )
        )
        for i in self:
            if i.invoice_date_due:
                i.invoice_net_date_due = i.invoice_date_due + timedelta(days=grace_days)
            else:
                i.invoice_net_date_due = False

    def _get_effective_due_date_for_behavior(self):
        """
        Get the effective due date to use for payment behavior calculation.
        This method can be inherited to modify the due date based on extensions or approvals.

        Returns:
            date: The effective due date to use for payment behavior calculation.
                  By default returns invoice_net_date_due which includes grace days.
        """
        self.ensure_one()
        return self.invoice_net_date_due

    @api.depends(
        'invoice_payment_term_id',
        'invoice_date',
        'invoice_date_due',
        'invoice_net_date_due',
        'amount_residual',
        'invoice_payments_widget',
        'payment_state')
    def compute_payment_behavior(self):
        """Compute payment behavior based on payment timing."""
        date_format = '%Y-%m-%d'
        default_vals = {
            'payment_behavior': 'not_paid',
            'days_to_pay': False,
            'payment_date': False,
        }

        for i in self:
            # Initialize default values
            # Ensure payment term is set
            if not i.invoice_payment_term_id and i.partner_id.property_payment_term_id:
                i.invoice_payment_term_id = i.with_company(i.company_id).partner_id.property_payment_term_id.id
                if not i.invoice_payment_term_id:
                    i.write(default_vals)
                    continue

            # Only process invoices (customer and vendor) that are paid or in payment
            if i.move_type not in ('out_invoice', 'in_invoice') or i.payment_state not in ['paid', 'in_payment']:
                i.write(default_vals)
                continue

            # Get effective due date (can be overridden by inheritance)
            effective_due_date = i._get_effective_due_date_for_behavior()

            if i.invoice_date and effective_due_date:
                invoice_date = fields.Date.to_date(i.invoice_date)
                invoice_effective_date_due = fields.Date.to_date(effective_due_date)
                # Parse payment data from widget
                if i.invoice_payments_widget:
                    invoice_payments_details = []
                    try:
                        json_data = json.loads(i.invoice_payments_widget)
                        invoice_payments_details = json_data.get("content", [])

                    except (json.JSONDecodeError, TypeError):
                        # If JSON parsing fails, continue with default values
                        _logger.error("Failed to parse invoice payments widget JSON data.")
                        i.write(default_vals)
                        continue

                    if invoice_payments_details:
                        payment_dates = []
                        for payment in invoice_payments_details:
                            try:
                                payment_date = datetime.strptime(payment["date"], date_format)
                                payment_dates.append(payment_date)
                            except (ValueError, KeyError):
                                _logger.error("Invalid payment date format in invoice payments widget.")
                                i.write(default_vals)
                                continue

                        if payment_dates:
                            # Get the last payment date
                            last_payment_date = min(payment_dates).date()

                            # Calculate days to pay from invoice date
                            days_to_pay = int((last_payment_date - invoice_date).days)

                            # Calculate payment behavior using effective due date
                            days_to_net_expiration = int((invoice_effective_date_due - invoice_date).days)

                            if days_to_pay <= days_to_net_expiration or days_to_pay <= 0:
                                payment_behavior = 'on_time'
                            else:
                                payment_behavior = 'delay'

                            i.write({
                                'payment_behavior': payment_behavior,
                                'days_to_pay': days_to_pay if days_to_pay >= 0 else 0,
                                'payment_date': last_payment_date,
                            })
                        else:
                            i.write(default_vals)
                else:
                    i.write(default_vals)
            else:
                i.write(default_vals)
