from odoo import models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def reconcile(self):
        """Override to trigger payment behavior recalculation on payment reconciliation.

        This hook is called when a payment is applied to an invoice, which is the
        moment when payment behavior metrics need to be updated.

        Only triggers for customer invoices (out_invoice) to avoid unnecessary
        calculations for vendor bills or other move types.
        """
        res = super().reconcile()

        # Get unique commercial partners from reconciled invoices
        partners_to_update = self.env['res.partner']

        for line in self:
            move = line.move_id
            # Only process customer invoices
            if move.move_type == 'out_invoice' and move.partner_id:
                commercial_partner = move.partner_id.commercial_partner_id
                if commercial_partner and commercial_partner not in partners_to_update:
                    partners_to_update |= commercial_partner

        return res
