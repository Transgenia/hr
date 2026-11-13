# Copyright 2020 ForgeFlow S.L. (https://www.forgeflow.com)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from collections import defaultdict, deque

from odoo import api, models
from odoo.exceptions import ValidationError

# Number of ``level-N`` classes the chart cycles through, by depth
ORG_CHART_LEVELS = 5


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    @api.constrains("parent_id")
    def _check_parent_id(self):
        # Being one's own manager is fine: Odoo marks the top of the hierarchy
        # that way. A loop of several managers hangs from nobody, so the chart
        # could not place its members, and Odoo itself does not forbid it.
        managed_by_others = self.filtered(lambda emp: emp.parent_id != emp)
        if managed_by_others._has_cycle():
            raise ValidationError(self.env._("You cannot assign manager recursively."))

    @api.model
    def _get_org_chart_domain(self):
        """Employees that take part in the chart of the current company."""
        return [
            "|",
            ("company_id", "=", False),
            ("company_id", "=", self.env.company.id),
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
        in another company or not readable by the current user.

        Employees are read once, with the access rights of the current user,
        and the tree is assembled in memory.
        """
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
