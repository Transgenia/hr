# Copyright 2020 ForgeFlow S.L. (https://www.forgeflow.com)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from collections import defaultdict, deque

from odoo import api, models

# Number of ``level-N`` classes the chart cycles through, by depth
ORG_CHART_LEVELS = 5


class HrEmployeePublic(models.Model):
    _inherit = "hr.employee.public"

    @api.model
    def _get_org_chart_hidden_ids(self):
        """Ids of the employees unchecked from the chart.

        The flag is only readable by HR officers; it says nothing private and
        decides what every user sees, hence the sudo, limited to that search.
        """
        return (
            self.env["hr.employee"]
            .sudo()
            .with_context(active_test=False)
            .search([("org_chart_visible", "=", False)])
            .ids
        )

    @api.model
    def _get_org_chart_domain(self):
        """Employees that take part in the chart of the current company."""
        return [
            "|",
            ("company_id", "=", False),
            ("company_id", "=", self.env.company.id),
            ("id", "not in", self._get_org_chart_hidden_ids()),
        ]

    def _get_employee_data(self, level=0):
        """Chart node of one employee, ``level`` being its depth in the tree."""
        self.ensure_one()
        return {
            "id": self.id,
            "name": self.name,
            "title": self.job_title or self.job_id.name or "",
            "className": f"level-{level % ORG_CHART_LEVELS}",
        }

    @api.model
    def get_organization_data(self):
        """Return the organizational chart of the current company.

        The root node stands for the company. Its children are the employees
        at the top of the hierarchy who have at least one subordinate; those
        with none are listed by name in ``unassigned_ids`` and counted in
        ``unassigned_count``. A node carries the ``children`` key only when
        somebody reports to it.

        An employee is at the top of the hierarchy when they have no manager,
        when they are their own manager (as Odoo marks it in its own chart and
        demo data) or when their manager is not part of the chart: archived,
        in another company, unchecked from the chart or not readable by the
        current user.

        Employees are read once from the public employee records, with the
        access rights of the current user: only public information (name and
        job title) reaches the chart. The tree is assembled in memory.
        """
        # The public records are an SQL view of the employees: what was
        # changed on them in this transaction must reach the database first,
        # and nothing cached about the view may be trusted.
        self.env.flush_all()
        self.invalidate_model()
        employees = self.search_fetch(
            self._get_org_chart_domain(),
            ["name", "parent_id", "job_title", "job_id"],
            order="name, id",
        )
        employee_ids = set(employees.ids)
        subordinates = defaultdict(list)
        for employee in employees:
            manager_id = employee.parent_id.id
            if manager_id == employee.id or manager_id not in employee_ids:
                # Nobody in the chart above them: top of the hierarchy
                manager_id = False
            subordinates[manager_id].append(employee)
        top_employees = []
        unassigned_ids = []
        for employee in subordinates.pop(False, []):
            if employee.id in subordinates:
                top_employees.append(employee)
            else:
                unassigned_ids.append(employee.id)
        data = {
            "id": False,
            "name": self.env.company.name,
            "title": "",
            "className": "o_org_company",
            "unassigned_count": len(unassigned_ids),
            "unassigned_ids": unassigned_ids,
            "children": [],
        }
        # An employee has a single manager, hence sits in a single list of
        # ``subordinates`` and is visited at most once: the walk always ends.
        # Members of a manager loop stored in the data, and whoever is below
        # them, hang from no top employee: they are left out of the chart, and
        # out of the unassigned employees as they do have a manager.
        queue = deque((data["children"], emp, 0) for emp in top_employees)
        while queue:
            siblings, employee, level = queue.popleft()
            node = employee._get_employee_data(level)
            siblings.append(node)
            if employee.id in subordinates:
                node["children"] = []
                queue.extend(
                    (node["children"], child, level + 1)
                    for child in subordinates[employee.id]
                )
        return data
