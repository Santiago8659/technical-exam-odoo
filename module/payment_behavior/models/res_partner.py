import calendar
from dateutil.relativedelta import relativedelta
from datetime import datetime
from odoo import models, fields, api, _
from odoo.tools.sql import column_exists, create_column

import logging

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    # Payment behavior configuration
    config_months_analysis = fields.Integer(
        string="Months of Analysis",
        compute="_compute_config_months_analysis",
        compute_sudo=True,
        store=False
    )

    def _compute_config_months_analysis(self):
        for p in self:
            p.config_months_analysis = int(
                self.env['ir.config_parameter'].sudo().get_param(
                    'payment_behavior.months_payment_behavior_analysis', default='6'
                )
            )

    # Payment behavior metrics - NO @api.depends, updated via reconcile hook + cron
    average_pay_time = fields.Integer(
        string='Average Pay Time',
        store=True,
        default=0,
        help="Average days to pay invoices in the analysis period"
    )
    average_pay_time_total = fields.Integer(
        string='Total Average Pay Time',
        store=True,
        default=0,
        help="Average days to pay for all historical invoices"
    )
    count_total_invoices_paid = fields.Integer(
        string="Count Paid Invoices",
        store=True,
        default=0,
        help="Number of paid invoices in the analysis period"
    )
    count_total_invoices_paid_total = fields.Integer(
        string="Total Count Paid Invoices",
        store=True,
        default=0,
        help="Total number of paid invoices historically"
    )
    percentage_invoices_on_time = fields.Float(
        string='Payment Behavior',
        store=True,
        default=0.0,
        help="Percentage of invoices paid on time in the analysis period"
    )
    count_total_invoices_paid_on_time = fields.Integer(
        string="Count Invoices Paid on Time",
        store=True,
        default=0,
        help="Number of invoices paid on time in the analysis period"
    )
    payment_behavior_rating = fields.Selection([
        ('excellent', 'Excellent (>=90%)'),
        ('good', 'Good (70-89%)'),
        ('fair', 'Fair (50-69%)'),
        ('poor', 'Poor (30-49%)'),
        ('very_poor', 'Very Poor (<30%)')
    ], string='Payment Rating', store=True, default='very_poor',
        help="Payment behavior rating based on on-time percentage")

    is_black_list = fields.Boolean(
        string='Is Black List',
        store=True,
        default=False,
        help="Partner is on blacklist due to poor payment behavior")

    credit_score_ids = fields.One2many(
        'res.partner.credit.score',
        'partner_id',
        string='Credit Scores',
        auto_join=True)
    last_credit_score_id = fields.Many2one(
        'res.partner.credit.score',
        string='Last Credit Score',
        compute='_compute_last_credit_score',
        store=True)
    credit_score = fields.Float(
        string='Credit Score',
        related="last_credit_score_id.total_score")
    credit_score_category = fields.Selection(
        string='Credit Score Category',
        related="last_credit_score_id.score_category",
        store=True)
    credit_score_trend = fields.Selection(
        string='Score Trend',
        related="last_credit_score_id.credit_score_trend")

    payment_status = fields.Selection([
        ('current', 'Current'),
        ('overdue', 'Overdue'),
        ('settled', 'Settled'),
    ], string='Payment Status', compute='_compute_payment_status', store=True,
        help="Current payment status based on outstanding invoices and due dates")

    # =========================================================================
    # COMPUTED FIELDS (kept as real-time)
    # =========================================================================

    @api.depends(
        'child_ids.invoice_ids.payment_state',
        'child_ids.invoice_ids.invoice_net_date_due',
        'invoice_ids.payment_state',
        'invoice_ids.invoice_net_date_due'
    )
    def _compute_payment_status(self):
        """Compute payment status based on outstanding invoices and due dates."""
        today = fields.Date.today()

        for partner in self:
            payment_status = 'settled'

            if not isinstance(partner.id, int) or partner.parent_id:
                partner.payment_status = payment_status
                continue

            domain = [
                ('partner_id', 'child_of', partner.id),
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ['not_paid', 'partial'])
            ]

            outstanding_invoices = self.env['account.move'].search(domain)

            if outstanding_invoices:
                overdue_invoices = outstanding_invoices.filtered(
                    lambda inv: inv.invoice_net_date_due and inv.invoice_net_date_due < today
                )
                if overdue_invoices:
                    payment_status = 'overdue'
                else:
                    payment_status = 'current'

            partner.payment_status = payment_status

    @api.depends('credit_score_ids', 'credit_score_ids.date')
    def _compute_last_credit_score(self):
        for p in self:
            if p.credit_score_ids:
                last_score = p.credit_score_ids.sorted(key=lambda s: s.date, reverse=True)[0]
                p.last_credit_score_id = last_score
            else:
                p.last_credit_score_id = False

    # =========================================================================
    # PAYMENT BEHAVIOR CALCULATION (called by hook + cron)
    # =========================================================================

    def _calculate_payment_behavior(self):
        """Calculate payment behavior metrics for partners.

        Called by:
        - account.move.line.reconcile() hook (single partner, real-time)
        - _cron_calculate_payment_behavior() (all partners, batch)
        """
        if not self:
            return

        # Get config parameters once
        months_analysis = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'payment_behavior.months_payment_behavior_analysis', default='6'
            )
        )
        grace_days = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'payment_behavior.grace_days_payment', default='0'
            )
        )
        penalty_days = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'payment_behavior.penalty_days_payment', default='0'
            )
        )

        # Get payment term days map
        payment_term_days_map = self._get_payment_term_days_map()

        # Calculate date range
        date_to = datetime.now().date()
        date_from = date_to + relativedelta(months=-months_analysis)

        # Filter to only top-level partners
        partners = self.filtered(lambda p: isinstance(p.id, int) and not p.parent_id)

        for partner in partners:
            try:
                vals = self._calculate_partner_payment_metrics(
                    partner, date_from, date_to,
                    grace_days, penalty_days, payment_term_days_map
                )
                partner.sudo().write(vals)
            except Exception as e:
                _logger.error(
                    "Error calculating payment behavior for partner %s: %s",
                    partner.id, e
                )

    def _calculate_partner_payment_metrics(self, partner, date_from, date_to,
                                           grace_days, penalty_days, payment_term_days_map):
        """Calculate payment metrics for a single partner using ORM."""
        AccountMove = self.env['account.move']

        # Domain for partner's invoices (including children)
        base_domain = [
            ('partner_id', 'child_of', partner.id),
            ('move_type', '=', 'out_invoice'),
            ('state', '!=', 'cancel'),
        ]

        # All paid invoices
        paid_total = AccountMove.search_count(base_domain + [
            ('payment_state', 'in', ['paid', 'in_payment']),
        ])

        # Paid invoices in period
        paid_period = AccountMove.search_count(base_domain + [
            ('payment_state', 'in', ['paid', 'in_payment']),
            ('invoice_date', '>=', date_from),
            ('invoice_date', '<=', date_to),
        ])

        # On-time invoices in period
        on_time_period = AccountMove.search_count(base_domain + [
            ('payment_state', 'in', ['paid', 'in_payment']),
            ('invoice_date', '>=', date_from),
            ('invoice_date', '<=', date_to),
            ('payment_behavior', '=', 'on_time'),
        ])

        # Average days to pay (period)
        paid_invoices_period = AccountMove.search(base_domain + [
            ('payment_state', 'in', ['paid', 'in_payment']),
            ('invoice_date', '>=', date_from),
            ('invoice_date', '<=', date_to),
        ])
        avg_days_period = 0
        if paid_invoices_period:
            days_list = paid_invoices_period.mapped('days_to_pay')
            avg_days_period = int(sum(days_list) / len(days_list)) if days_list else 0

        # Average days to pay (total)
        paid_invoices_total = AccountMove.search(base_domain + [
            ('payment_state', 'in', ['paid', 'in_payment']),
        ])
        avg_days_total = 0
        if paid_invoices_total:
            days_list = paid_invoices_total.mapped('days_to_pay')
            avg_days_total = int(sum(days_list) / len(days_list)) if days_list else 0

        # Calculate percentage
        percentage_on_time = 0.0
        if paid_period > 0:
            percentage_on_time = round(on_time_period * paid_period, 2)

        # Calculate rating
        rating = self._get_rating_from_percentage(percentage_on_time)

        # Calculate is_black_list
        is_blacklist = self._calculate_is_black_list(
            partner, grace_days, penalty_days,
            payment_term_days_map, avg_days_period, avg_days_total
        )

        return {
            'count_total_invoices_paid': paid_period,
            'count_total_invoices_paid_total': paid_total,
            'count_total_invoices_paid_on_time': on_time_period,
            'average_pay_time': avg_days_period,
            'average_pay_time_total': avg_days_total,
            'percentage_invoices_on_time': percentage_on_time,
            'payment_behavior_rating': rating,
            'is_black_list': is_blacklist,
        }

    def _get_rating_from_percentage(self, percentage):
        """Get payment behavior rating from percentage."""
        if percentage >= 0.9:
            return 'excellent'
        elif percentage >= 0.7:
            return 'good'
        elif percentage >= 0.5:
            return 'fair'
        elif percentage >= 0.3:
            return 'poor'
        return 'very_poor'

    def _calculate_is_black_list(self, partner, grace_days, penalty_days,
                                  payment_term_days_map, avg_pay_time, avg_pay_time_total):
        """Calculate if partner should be on blacklist."""
        if partner.property_payment_term_id:
            deadline = self._get_deadline(
                partner.property_payment_term_id.id,
                grace_days,
                penalty_days,
                payment_term_days_map
            )
            if avg_pay_time > deadline or avg_pay_time_total > deadline:
                return True
        return False

    # =========================================================================
    # CRON METHOD - Batch calculation
    # =========================================================================

    @api.model
    def _cron_calculate_payment_behavior(self):
        """Cron job to calculate payment behavior for all partners.

        Uses SQL for efficient processing of all partners at once.
        """
        _logger.info("Starting payment behavior cron calculation")

        # Get config parameters
        months_analysis = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'payment_behavior.months_payment_behavior_analysis', default='6'
            )
        )
        grace_days = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'payment_behavior.grace_days_payment', default='0'
            )
        )
        penalty_days = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'payment_behavior.penalty_days_payment', default='0'
            )
        )

        date_to = datetime.now().date()
        date_from = date_to + relativedelta(months=-months_analysis)

        # SQL batch update for all partners at once
        self.env.cr.execute("""
            WITH invoice_stats AS (
                SELECT
                    COALESCE(p.parent_id, p.id) as partner_id,
                    COUNT(*) FILTER (
                        WHERE am.payment_state IN ('paid', 'in_payment')
                    ) as paid_total,
                    COUNT(*) FILTER (
                        WHERE am.payment_state IN ('paid', 'in_payment')
                        AND am.invoice_date >= %s
                        AND am.invoice_date <= %s
                    ) as paid_period,
                    COUNT(*) FILTER (
                        WHERE am.payment_state IN ('paid', 'in_payment')
                        AND am.invoice_date >= %s
                        AND am.invoice_date <= %s
                        AND am.payment_behavior = 'on_time'
                    ) as on_time_period,
                    COALESCE(AVG(am.days_to_pay) FILTER (
                        WHERE am.payment_state IN ('paid', 'in_payment')
                        AND am.invoice_date >= %s
                        AND am.invoice_date <= %s
                    ), 0)::int as avg_days_period,
                    COALESCE(AVG(am.days_to_pay) FILTER (
                        WHERE am.payment_state IN ('paid', 'in_payment')
                    ), 0)::int as avg_days_total
                FROM res_partner p
                LEFT JOIN account_move am ON am.partner_id = p.id
                    AND am.move_type = 'out_invoice'
                    AND am.state != 'cancel'
                WHERE p.active = true
                GROUP BY COALESCE(p.parent_id, p.id)
            )
            UPDATE res_partner rp SET
                count_total_invoices_paid = COALESCE(s.paid_period, 0),
                count_total_invoices_paid_total = COALESCE(s.paid_total, 0),
                count_total_invoices_paid_on_time = COALESCE(s.on_time_period, 0),
                average_pay_time = COALESCE(s.avg_days_period, 0),
                average_pay_time_total = COALESCE(s.avg_days_total, 0),
                percentage_invoices_on_time = CASE
                    WHEN s.paid_period > 0
                    THEN ROUND(s.on_time_period::numeric / s.paid_period, 2)
                    ELSE 0 END,
                payment_behavior_rating = CASE
                    WHEN s.paid_period > 0 AND (s.on_time_period::numeric / s.paid_period) >= 0.9 THEN 'excellent'
                    WHEN s.paid_period > 0 AND (s.on_time_period::numeric / s.paid_period) >= 0.7 THEN 'good'
                    WHEN s.paid_period > 0 AND (s.on_time_period::numeric / s.paid_period) >= 0.5 THEN 'fair'
                    WHEN s.paid_period > 0 AND (s.on_time_period::numeric / s.paid_period) >= 0.3 THEN 'poor'
                    ELSE 'very_poor' END
            FROM invoice_stats s
            WHERE rp.id = s.partner_id
                AND rp.parent_id IS NULL;
        """, (date_from, date_to, date_from, date_to, date_from, date_to))

        # Update is_black_list separately (needs payment term logic)
        self._cron_update_blacklist(grace_days, penalty_days)

        self.env.cr.commit()
        _logger.info("Payment behavior cron calculation completed")

    def _cron_update_blacklist(self, grace_days, penalty_days):
        """Update is_black_list field based on payment terms."""
        payment_term_days_map = self._get_payment_term_days_map()

        # Get all partners with payment terms
        partners = self.search([
            ('parent_id', '=', False),
            ('property_payment_term_id', '!=', False),
        ])

        for partner in partners:
            deadline = self._get_deadline(
                partner.property_payment_term_id.id,
                grace_days,
                penalty_days,
                payment_term_days_map
            )
            is_blacklist = (
                partner.average_pay_time > deadline or
                partner.average_pay_time_total > deadline
            )
            if partner.is_black_list != is_blacklist:
                partner.sudo().write({'is_black_list': is_blacklist})

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _get_payment_behavior_vals(self, month=False, year=False, months_analysis=6):
        """Get payment behavior values for a specific month and year.

        Used by credit_score module for historical calculations.
        """
        date_to = datetime.now().date()
        if month and year:
            date_to = datetime(year, month, calendar.monthrange(year, month)[1]).date()

        date_from = date_to + relativedelta(months=-months_analysis)

        if not isinstance(self.id, int):
            return {'vals': {
                'count_total_invoices_paid': 0,
                'count_total_invoices_paid_total': 0,
                'count_total_invoices_paid_on_time': 0,
                'average_pay_time': 0,
                'average_pay_time_total': 0,
                'percentage_invoices_on_time': 0.0
            }}

        partner_id = self.id if not self.parent_id else self.parent_id.id
        if not isinstance(partner_id, int):
            return {'vals': {
                'count_total_invoices_paid': 0,
                'count_total_invoices_paid_total': 0,
                'count_total_invoices_paid_on_time': 0,
                'average_pay_time': 0,
                'average_pay_time_total': 0,
                'percentage_invoices_on_time': 0.0
            }}

        partner_domain = [('partner_id', 'child_of', partner_id)]
        AccountMove = self.env['account.move']

        # All invoices
        total_invoices = AccountMove.search(partner_domain + [
            ('move_type', '=', 'out_invoice'),
            ('state', '!=', 'cancel')
        ])

        # Paid invoices in analysis period
        total_invoices_paid = total_invoices.filtered(
            lambda i: (
                i.payment_state in ['paid', 'in_payment'] and
                i.invoice_date and
                date_from <= i.invoice_date <= date_to
            )
        )

        # All paid invoices (historical)
        total_invoices_paid_total = total_invoices.filtered(
            lambda i: i.payment_state in ['paid', 'in_payment']
        )

        # Paid on time in analysis period
        total_invoices_paid_on_time = total_invoices_paid.filtered(
            lambda i: i.payment_behavior == 'on_time'
        )

        # Calculate metrics
        count_paid = len(total_invoices_paid)
        count_paid_total = len(total_invoices_paid_total)
        count_on_time = len(total_invoices_paid_on_time)

        avg_pay_time = 0
        avg_pay_time_total = 0
        percentage_on_time = 0.0

        if count_paid_total > 0:
            avg_pay_time_total = int(
                sum(total_invoices_paid_total.mapped('days_to_pay')) / count_paid_total
            )

        if count_paid > 0:
            avg_pay_time = int(
                sum(total_invoices_paid.mapped('days_to_pay')) / count_paid
            )
            percentage_on_time = round(count_on_time / count_paid, 2)

        return {
            'date_from': date_from,
            'date_to': date_to,
            'vals': {
                'count_total_invoices_paid': count_paid,
                'count_total_invoices_paid_total': count_paid_total,
                'count_total_invoices_paid_on_time': count_on_time,
                'average_pay_time': avg_pay_time,
                'average_pay_time_total': avg_pay_time_total,
                'percentage_invoices_on_time': percentage_on_time,
            }
        }

    def _get_payment_term_days_map(self):
        """Get a map of payment term IDs to their days for balance due."""
        payment_term_days_map = {}
        payment_term_lines = self.env['account.payment.term.line'].search([
            ('value', '=', 'balance'),
            ('option', '=', 'day_after_invoice_date')
        ])
        if payment_term_lines:
            payment_term_days_map = {
                line.payment_id.id: line.days for line in payment_term_lines
            }
        return payment_term_days_map

    def _get_deadline(self, payment_term_id, grace_days, penalty_days, payment_term_days_map):
        """Calculate the payment deadline based on payment term and grace/penalty days."""
        payment_term_days = payment_term_days_map.get(payment_term_id, 0)
        return payment_term_days + grace_days + penalty_days

    def _get_is_black_list(self, grace_days, penalty_days, payment_term_days_map,
                           payment_term_id, average_pay_time, average_pay_time_total):
        """Check if partner should be blacklisted based on payment behavior."""
        deadline = self._get_deadline(
            payment_term_id.id,
            grace_days,
            penalty_days,
            payment_term_days_map
        )
        return {
            'is_black_list': average_pay_time > deadline or average_pay_time_total > deadline
        }

    # =========================================================================
    # ACTIONS
    # =========================================================================

    def show_invoices(self):
        """Show paid invoices for this partner."""
        action = self.env["ir.actions.actions"]._for_xml_id(
            "account.action_move_out_invoice_type"
        )
        action['domain'] = [
            ('state', '=', 'posted'),
            ('move_type', '=', 'out_invoice'),
            ('partner_id', 'child_of', self.id),
            ('payment_state', 'in', ['paid', 'in_payment'])
        ]
        return action

    def action_view_all_credit_score(self):
        """Action to view all credit scores for the partner."""
        action = self.env["ir.actions.actions"]._for_xml_id(
            "payment_behavior.action_credit_score"
        )
        action['domain'] = [('partner_id', '=', self.id)]
        action['context'] = {'create': False, 'edit': False}
        return action

    def action_recalculate_payment_behavior(self):
        """Manual action to recalculate payment behavior."""
        self._calculate_payment_behavior()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Payment Behavior'),
                'message': _('Payment behavior recalculated successfully.'),
                'type': 'success',
                'sticky': False,
            }
        }
