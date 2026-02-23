import calendar
from datetime import datetime
from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


MONTH_SELECTION = [
    ('1', 'January'),
    ('2', 'February'),
    ('3', 'March'),
    ('4', 'April'),
    ('5', 'May'),
    ('6', 'June'),
    ('7', 'July'),
    ('8', 'August'),
    ('9', 'September'),
    ('10', 'October'),
    ('11', 'November'),
    ('12', 'December'),
]

class ResPartnerCreditScore(models.Model):
    _name = "res.partner.credit.score"
    _description = "Partner Credit Score"
    _order = "date desc"

    @staticmethod
    def _get_years_selection():
        year_list = [(str(record), str(record)) for record in
                    range(fields.datetime.now().year - 10, fields.datetime.now().year + 1)]
        return year_list

    _sql_constraints = [
        ('unique_partner_month_year', 'UNIQUE(partner_id, month, year)',
        'Only one credit score per partner per month/year is allowed!')
    ]

    def name_get(self):
        result = []
        for cs in self:
            name = _("%s (%s %s)") % (cs.partner_id.name, dict(MONTH_SELECTION).get(cs.month, 'Unknown'), cs.year)
            result.append((cs.id, name))
        return result

    partner_id = fields.Many2one('res.partner', string='Partner', index=True, required=True, ondelete='cascade')
    date = fields.Date(string='Date', compute='_compute_date', store=True)
    month = fields.Selection(selection=MONTH_SELECTION, string='Month', index=True, default=str(fields.Datetime.now().month), required=True)
    year = fields.Selection(selection='_get_years_selection', string="Year", index=True, default=str(fields.Datetime.now().year), required=True)

    # Score components
    payment_behavior_score = fields.Float(string='Payment Behavior Score')
    payment_timing_score = fields.Float(string='Payment Timing Score')
    credit_history_score = fields.Float(string='Credit History Score')
    financial_capacity_score = fields.Float(string='Financial Capacity Score')
    total_score = fields.Float(string="Total Score")

    score_category = fields.Selection([
        ('excellent', 'Excellent (80-100)'),
        ('good', 'Good (60-79)'),
        ('fair', 'Fair (40-59)'),
        ('poor', 'Poor (20-39)'),
        ('very_poor', 'Very Poor (0-19)')
    ], string='Score Category', compute='_compute_score_category', store=True)

    credit_score_trend = fields.Selection([
        ('improving', 'Improving'),
        ('stable', 'Stable'),
        ('deteriorating', 'Deteriorating'),
        ('no_history', 'No History')
    ], string='Score Trend', compute='_compute_credit_score_trend', store=True)

    is_black_list = fields.Boolean(string='Is Black List', default=False)
    risk_alerts = fields.Text(string='Risk Alerts')

    # AR Metrics (Accounts Receivable)
    dso = fields.Float(
        string='DSO (Days Sales Outstanding)',
        help="Average days to collect receivables: (AR Balance / Revenue) x Days in Period"
    )
    dbt = fields.Float(
        string='DBT (Days Beyond Terms)',
        help="Average days invoices are paid past due date"
    )

    # Invoice Aging Distribution (amounts by bucket)
    aging_current = fields.Float(
        string='Current (Not Due)',
        help="Amount of invoices not yet due"
    )
    aging_1_30 = fields.Float(
        string='1-30 Days Overdue',
        help="Amount of invoices 1-30 days past due"
    )
    aging_31_60 = fields.Float(
        string='31-60 Days Overdue',
        help="Amount of invoices 31-60 days past due"
    )
    aging_61_90 = fields.Float(
        string='61-90 Days Overdue',
        help="Amount of invoices 61-90 days past due"
    )
    aging_90_plus = fields.Float(
        string='90+ Days Overdue',
        help="Amount of invoices more than 90 days past due"
    )

    # Revenue metrics
    total_revenue = fields.Float(
        string='Total Revenue',
        help="Total invoiced revenue in the period"
    )
    ar_balance = fields.Float(
        string='AR Balance',
        help="Outstanding accounts receivable balance"
    )

    @api.depends('month', 'year')
    def _compute_date(self):
        for record in self:
            if record.month and record.year:
                month = int(record.month)
                year = int(record.year)
                last_day = datetime(year, month, calendar.monthrange(year, month)[1]).date()
                record.date = last_day
            else:
                record.date = False

    @api.depends('total_score')
    def _compute_score_category(self):
        for record in self:
            if record.total_score >= 80:
                record.score_category = 'excellent'
            elif record.total_score >= 60:
                record.score_category = 'good'
            elif record.total_score >= 40:
                record.score_category = 'fair'
            elif record.total_score >= 20:
                record.score_category = 'poor'
            else:
                record.score_category = 'very_poor'

    @api.depends('total_score', 'partner_id', 'month', 'year')
    def _compute_credit_score_trend(self):
        for cs in self:
            # Get previous month's score
            prev_month = int(cs.month) - 1
            prev_year = int(cs.year)

            previous_score = self.search([
                ('partner_id', '=', cs.partner_id.id),
                ('month', '=', str(prev_month)),
                ('year', '=', str(prev_year))
            ], limit=1)

            if previous_score:
                score_diff = cs.total_score - previous_score.total_score
                if score_diff > 5:
                    cs.credit_score_trend = 'improving'
                elif score_diff < -5:
                    cs.credit_score_trend = 'deteriorating'
                else:
                    cs.credit_score_trend = 'stable'
            else:
                cs.credit_score_trend = 'no_history'

    @api.model
    def calculate_credit_scores_batch(self, partner_ids=None, month=None, year=None, batch_size=50):
        """Calculate credit scores for all partners in batch for the previous month"""
        if not partner_ids:
            partner_ids = self.env['res.partner'].search([
                ('parent_id', '=', False),
                ('credit_limit', '>', 0)]).ids

        # Get previous month and year
        if not month or not year:
            today = datetime.now()
            if today.month == 1:
                month = 12
                year = today.year - 1
            else:
                month = today.month - 1
                year = today.year

        # Process partners in batches
        total_partners = len(partner_ids)
        processed = 0

        for i in range(0, total_partners, batch_size):
            batch_partner_ids = partner_ids[i:i+batch_size]
            vals_to_create = []

            # search all existing credit scores for the month and year
            existing_scores = self.search([
                ('partner_id', 'in', batch_partner_ids),
                ('month', '=', str(month)),
                ('year', '=', str(year))
            ])
            existing_partner_ids = existing_scores.mapped('partner_id.id')
            _logger.info(_("Processing batch %s/%s for month %s and year %s. Batch size: %s. Existing scores found: %s")%(i // batch_size + 1,(total_partners + batch_size - 1) // batch_size, month, year, len(batch_partner_ids), len(existing_scores)))
            # Filter out partners that already have a score for this month/year
            batch_partner_ids = [pid for pid in batch_partner_ids if pid not in existing_partner_ids]
            for partner_id in batch_partner_ids:
                vals_to_create.append({
                    'partner_id': partner_id,
                    'month': str(month),
                    'year': str(year),
                })
                processed += 1
            if vals_to_create:
                credit_score_ids = self.sudo().create(vals_to_create)
                self.env.cr.commit()

    @api.model
    def get_credit_score_by_month_year(self, month=None, year=None):
        if not month or not year:
            today = datetime.now()
            if today.month == 1:
                month = 12
                year = today.year - 1
            else:
                month = today.month - 1
                year = today.year

        return self.search([
            ('month', '=', str(month)),
            ('year', '=', str(year))
        ])

    def calculate_credit_score(self):
        """Calculate and update the credit score based on partner's payment behavior"""
        grace_days = int(self.env['ir.config_parameter'].sudo().get_param('payment_behavior.grace_days_payment', default='0'))
        penalty_days = int(self.env['ir.config_parameter'].sudo().get_param('payment_behavior.penalty_days_payment', default='0'))

        for cs in self:
            # Get payment behavior for specific month/year
            payment_behavior_vals = cs.partner_id._get_payment_behavior_vals(
                month=int(cs.month),
                year=int(cs.year)
            )

            percentage_invoices_on_time = payment_behavior_vals.get('vals', {}).get('percentage_invoices_on_time', 0.0)
            average_pay_time = payment_behavior_vals.get('vals', {}).get('average_pay_time', 0)
            average_pay_time_total = payment_behavior_vals.get('vals', {}).get('average_pay_time_total', 0)

            # Calculate individual scores
            payment_behavior_score = cs._calculate_payment_behavior_score(
                percentage_invoices_on_time
            )

            payment_timing_score = cs._calculate_payment_timing_score(
                average_pay_time,
                grace_days,
                penalty_days
            )
            credit_history_score = cs._calculate_credit_history_score()
            financial_capacity_score = cs._calculate_financial_capacity_score()

            # Calculate total score (weighted average)
            total_score = (
                payment_behavior_score * 0.4 +
                payment_timing_score * 0.6
            )

            is_black_list = self._get_is_black_list(cs.partner_id, grace_days, penalty_days, average_pay_time, average_pay_time_total)

            # Calculate AR metrics
            ar_metrics = cs._calculate_ar_metrics()

            # Update cs
            cs.sudo().write({
                'payment_behavior_score': payment_behavior_score,
                'payment_timing_score': payment_timing_score,
                'credit_history_score': credit_history_score,
                'financial_capacity_score': financial_capacity_score,
                'total_score': total_score,
                'is_black_list': is_black_list,
                **ar_metrics,
            })

    def _get_is_black_list(self, partner, grace_days, penalty_days, average_pay_time, average_pay_time_total):
        partner_obj = self.env['res.partner']
        payment_term_days_map = partner_obj._get_payment_term_days_map()
        if partner.property_payment_term_id:
            is_blacklist = partner_obj._get_is_black_list(
                grace_days,
                penalty_days,
                payment_term_days_map,
                partner.property_payment_term_id,
                average_pay_time,
                average_pay_time_total,
            ).get('is_black_list', False)
            return is_blacklist
        return False

    def _calculate_payment_behavior_score(self, percentage_invoices_on_time):
        """Calculate payment behavior score based on on-time payment percentage"""
        if percentage_invoices_on_time >= 0.9:
            return 100
        elif percentage_invoices_on_time >= 0.8:
            return 85
        elif percentage_invoices_on_time >= 0.3:
            return percentage_invoices_on_time * 100
        else:
            return 0

    def _calculate_payment_timing_score(self, average_pay_time, grace_days, penalty_days):
        """Calculate payment timing score based on average payment time"""
        if not average_pay_time:
            return 0

        payment_term_days = 30
        if self.partner_id.property_payment_term_id:
            term_lines = self.partner_id.property_payment_term_id.line_ids.filtered(
                lambda l: l.value == 'balance'
            )
            if term_lines:
                payment_term_days = term_lines[0].days

        total_days = grace_days + penalty_days
        delay_days = average_pay_time - payment_term_days

        if delay_days <= 0:
            return 100
        else:
            if delay_days <= total_days:
                return 100 - (delay_days / total_days * 100)
            else:
                return 0

    def _calculate_credit_history_score(self):
        """Calculate credit history score based on partner's history"""
        base_score = 40

        creation_days = (self.date - self.partner_id.create_date.date()).days if self.partner_id.create_date else 0
        if creation_days > 365 * 2:
            base_score += 30
        elif creation_days > 365:
            base_score += 20
        elif creation_days > 180:
            base_score += 10

        # Consider historical scores
        historical_scores = self.search([
            ('partner_id', '=', self.partner_id.id),
            ('id', '!=', self.id)
        ], order='date desc', limit=6)

        if historical_scores:
            avg_historical_score = sum(historical_scores.mapped('total_score')) / len(historical_scores)
            if avg_historical_score >= 70:
                base_score += 30
            elif avg_historical_score >= 50:
                base_score += 20
        return min(base_score, 100)

    def _calculate_financial_capacity_score(self):
        """Calculate financial capacity score based on credit limit and usage"""
        return 0

    def _calculate_ar_metrics(self):
        """Calculate Accounts Receivable metrics for the partner at the snapshot date."""
        self.ensure_one()

        reference_date = self.date
        if not reference_date:
            return {}

        partner = self.partner_id
        AccountMove = self.env['account.move']

        partner_domain = [
            ('partner_id', 'child_of', partner.id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
        ]

        outstanding_invoices = AccountMove.search(partner_domain + [
            ('payment_state', 'in', ['not_paid', 'partial']),
            ('invoice_date', '<=', reference_date),
        ])

        aging_current = 0.0
        aging_1_30 = 0.0
        aging_31_60 = 0.0
        aging_61_90 = 0.0
        aging_90_plus = 0.0

        total_dbt_days = 0
        dbt_invoice_count = 0

        for invoice in outstanding_invoices:
            due_date = invoice.invoice_net_date_due or invoice.invoice_date_due
            if not due_date:
                continue

            amount = invoice.amount_residual
            days_overdue = (reference_date - due_date).days

            if days_overdue <= 0:
                aging_current += amount
            elif days_overdue <= 30:
                aging_1_30 += amount
                total_dbt_days += days_overdue
                dbt_invoice_count += 1
            elif days_overdue <= 60:
                aging_31_60 += amount
                total_dbt_days += days_overdue
                dbt_invoice_count += 1
            elif days_overdue <= 90:
                aging_61_90 += amount
                total_dbt_days += days_overdue
                dbt_invoice_count += 1
            else:
                aging_90_plus += amount
                total_dbt_days += days_overdue
                dbt_invoice_count += 1

        ar_balance = aging_current + aging_1_30 + aging_31_60 + aging_61_90 + aging_90_plus
        dbt = total_dbt_days / dbt_invoice_count if dbt_invoice_count > 0 else 0.0

        month_start = reference_date.replace(day=1)
        paid_invoices = AccountMove.search(partner_domain + [
            ('payment_state', 'in', ['paid', 'in_payment']),
            ('invoice_date', '>=', month_start),
            ('invoice_date', '<=', reference_date),
        ])
        total_revenue = sum(paid_invoices.mapped('amount_total_signed'))

        if total_revenue > 0:
            dso = (ar_balance / total_revenue) * 30
        else:
            dso = 0.0

        return {
            'dso': round(dso, 2),
            'dbt': round(dbt, 2),
            'aging_current': aging_current,
            'aging_1_30': aging_1_30,
            'aging_31_60': aging_31_60,
            'aging_61_90': aging_61_90,
            'aging_90_plus': aging_90_plus,
            'total_revenue': total_revenue,
            'ar_balance': ar_balance,
        }

    def action_recalculate_score(self):
        """Action to recalculate credit score"""
        self.calculate_credit_score()
