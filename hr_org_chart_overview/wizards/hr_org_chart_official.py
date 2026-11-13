# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError

# Employee types of people who work for the company without being employees
EXTERNAL_EMPLOYEE_TYPES = ("contractor", "freelance")


class HrOrgChartOfficial(models.TransientModel):
    """Options of the official organizational chart, printed as a PDF.

    The document only carries what an organizational chart needs: company
    name and tax id, departments, job positions and names. No private data
    of the employees (addresses, identification numbers, salaries, private
    contacts) is ever read.
    """

    _name = "hr.org.chart.official"
    _description = "Official Organizational Chart"

    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    title = fields.Char(
        required=True,
        default=lambda self: self.env._("Official Organizational Chart"),
    )
    date_issue = fields.Date(
        string="Issue Date", required=True, default=fields.Date.context_today
    )
    date_valid = fields.Date(
        string="Valid Until",
        required=True,
        default=lambda self: fields.Date.context_today(self) + relativedelta(years=1),
    )
    signer_name = fields.Char(
        string="Signer",
        compute="_compute_signer",
        store=True,
        readonly=False,
    )
    signer_title = fields.Char(
        string="Signer Position",
        compute="_compute_signer",
        store=True,
        readonly=False,
    )
    show_reporting_lines = fields.Boolean(
        string="Show Reporting Lines",
        default=True,
        help="Add the tree of who reports to whom after the structure by "
        "department.",
    )

    @api.depends("company_id")
    def _compute_signer(self):
        for wizard in self:
            wizard.signer_name = wizard.company_id.org_chart_signer_name
            wizard.signer_title = wizard.company_id.org_chart_signer_title

    @api.constrains("date_issue", "date_valid")
    def _check_dates(self):
        if any(wizard.date_valid < wizard.date_issue for wizard in self):
            raise ValidationError(
                self.env._("The chart cannot expire before it is issued.")
            )

    def action_print(self):
        self.ensure_one()
        # Remembered for the next chart of the company. HR officers may not
        # write on companies, hence the sudo, limited to these two fields.
        self.company_id.sudo().write(
            {
                "org_chart_signer_name": self.signer_name,
                "org_chart_signer_title": self.signer_title,
            }
        )
        return self.env.ref(
            "hr_org_chart_overview.action_report_official_org_chart"
        ).report_action(self)

    def _get_official_employees(self):
        """Active employees of the company who take part in the chart."""
        self.ensure_one()
        return self.env["hr.employee"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("org_chart_visible", "=", True),
            ],
            order="name, id",
        )

    def _get_official_chart_data(self):
        """Content of the official chart.

        :return: ``departments``, each with its ``name``, ``count`` and
            ``jobs`` (``name`` and ``employees``); ``lines``, the reporting
            lines as rows with a ``depth``; ``total`` and ``external_count``.
            An employee is a dict with ``name``, ``job`` and ``external``.
        """
        self.ensure_one()
        employees = self._get_official_employees()
        no_department = self.env._("No department")
        no_job = self.env._("No job position")
        people = {
            employee.id: {
                "name": employee.name,
                "job": employee.job_title or employee.job_id.name or no_job,
                "external": employee.employee_type in EXTERNAL_EMPLOYEE_TYPES,
            }
            for employee in employees
        }
        by_department = defaultdict(lambda: defaultdict(list))
        for employee in employees:
            department = employee.department_id
            key = (not department, department.complete_name or no_department)
            person = people[employee.id]
            by_department[key][person["job"]].append(person)
        departments = []
        for (__, department_name), jobs in sorted(by_department.items()):
            job_names = sorted(jobs, key=lambda name: (name == no_job, name))
            departments.append(
                {
                    "name": department_name,
                    "count": sum(len(members) for members in jobs.values()),
                    "jobs": [
                        {"name": job_name, "employees": jobs[job_name]}
                        for job_name in job_names
                    ],
                }
            )
        return {
            "departments": departments,
            "lines": self._get_reporting_lines(employees, people),
            "total": len(employees),
            "external_count": sum(person["external"] for person in people.values()),
        }

    def _get_reporting_lines(self, employees, people):
        """Who reports to whom, as rows of a tree walked depth first.

        An employee whose manager is not in the chart, or who is their own
        manager, starts a tree. Should the data hold a loop of managers, its
        members still appear, each starting a tree: an official chart may not
        leave anybody out.
        """
        ids = set(employees.ids)
        reports = defaultdict(list)
        roots = []
        for employee in employees:
            manager_id = employee.parent_id.id
            if manager_id in ids and manager_id != employee.id:
                reports[manager_id].append(employee.id)
            else:
                roots.append(employee.id)
        lines = []
        seen = set()

        def walk(employee_id, depth):
            stack = [(employee_id, depth)]
            while stack:
                current, level = stack.pop()
                if current in seen:
                    continue
                seen.add(current)
                lines.append(dict(people[current], depth=level))
                stack.extend(
                    (report, level + 1) for report in reversed(reports[current])
                )

        for root in roots:
            walk(root, 0)
        for employee_id in employees.ids:
            walk(employee_id, 0)
        return lines
