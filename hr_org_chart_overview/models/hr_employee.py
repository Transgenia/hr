# Copyright 2020 ForgeFlow S.L. (https://www.forgeflow.com)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    # Kept off the public employee view on purpose: a column of hr_employee
    # read by that SQL view would be dropped with CASCADE when the module is
    # uninstalled, taking the view, hence the employee directory, with it.
    org_chart_visible = fields.Boolean(
        string="Show in Org Chart",
        default=True,
        groups="hr.group_hr_user",
        help="Uncheck to leave this record out of the organizational chart "
        "and of the official chart, e.g. for a technical or service account.",
    )

    @api.constrains("parent_id")
    def _check_parent_id(self):
        # Being one's own manager is fine: Odoo marks the top of the hierarchy
        # that way. A loop of several managers hangs from nobody, so the chart
        # could not place its members, and Odoo itself does not forbid it.
        managed_by_others = self.filtered(lambda emp: emp.parent_id != emp)
        if managed_by_others._has_cycle():
            raise ValidationError(self.env._("You cannot assign manager recursively."))

    @api.model
    def get_organization_data(self):
        """Organizational chart of the current company.

        Built from the public employee records, so that every internal user
        can see it; see ``hr.employee.public.get_organization_data``.
        """
        return self.env["hr.employee.public"].get_organization_data()
