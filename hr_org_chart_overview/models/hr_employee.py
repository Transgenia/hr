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
        who have no manager and at least one subordinate; those who have
        neither are only counted in ``unassigned_count``. A node carries the
        ``children`` key only when somebody reports to it.

        Employees set as their own manager are taken as having no manager, as
        Odoo does in its own chart and demo data for the top of the hierarchy.

        Employees are read once, with the access rights of the current user,
        and the tree is assembled in memory.
        """
        employees = self.search_fetch(
            self._get_org_chart_domain(),
            ["name", "parent_id", "job_title", "job_id"],
            order="name, id",
        )
        subordinates = defaultdict(list)
        for employee in employees:
            manager = employee.parent_id
            manager_id = manager.id if manager != employee else False
            subordinates[manager_id].append(employee)
        without_manager = subordinates.pop(False, [])
        top_employees = [emp for emp in without_manager if emp.id in subordinates]
        data = {
            "id": False,
            "name": self.env.company.name,
            "title": "",
            "className": "o_org_company",
            "unassigned_count": len(without_manager) - len(top_employees),
            "children": [],
        }
        # An employee has a single manager, hence sits in a single list of
        # ``subordinates`` and is visited at most once: the walk always ends,
        # even when the data holds a manager loop (which no walk starting from
        # an employee without manager can reach).
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
