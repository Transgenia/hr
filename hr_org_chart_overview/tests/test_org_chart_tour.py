# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestOrgChartTour(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        employee_model = cls.env["hr.employee"]
        cls.manager = employee_model.create({"name": "OrgChart Manager"})
        cls.report_one = employee_model.create(
            {"name": "OrgChart Report One", "parent_id": cls.manager.id}
        )
        # Names are user data: this one must be displayed as it is typed
        cls.report_two = employee_model.create(
            {"name": "<b>OrgChart</b> Report Two", "parent_id": cls.manager.id}
        )
        cls.deputy = employee_model.create(
            {"name": "OrgChart Deputy", "parent_id": cls.report_one.id}
        )
        # Neither manager nor subordinates: counted, but not in the chart
        cls.loner = employee_model.create({"name": "OrgChart Loner"})

    def test_org_chart_tour(self):
        self.start_tour(
            "/odoo/action-hr_org_chart_overview.action_org_chart_overview",
            "hr_org_chart_overview_tour",
            login="admin",
        )
