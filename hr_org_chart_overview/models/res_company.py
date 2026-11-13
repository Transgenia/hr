# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    org_chart_signer_name = fields.Char(
        string="Org Chart Signer",
        help="Person who signs the official organizational chart.",
    )
    org_chart_signer_title = fields.Char(
        string="Org Chart Signer Position",
        help="Position of the signer, as printed under the signature.",
    )
