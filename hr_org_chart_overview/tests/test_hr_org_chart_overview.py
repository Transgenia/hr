# Copyright 2026 Transgenia (https://transgenia.org)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import new_test_user, tagged

from odoo.addons.base.tests.common import BaseCommon


@tagged("post_install", "-at_install")
class TestHrOrgChartOverview(BaseCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Employee = cls.env["hr.employee"]
        cls.chart_company = cls._create_company(name="Org Chart Company")
        cls.other_company = cls._create_company(name="Other Org Chart Company")
        cls.job = cls.env["hr.job"].create(
            {"name": "Chief Executive", "company_id": cls.chart_company.id}
        )
        # Org Chart Company
        #   Ceo -+- Abe -- Lea -- Max -- Noa -- Pia
        #        +- Mia
        #        +- Zed
        #   Solo One and Solo Two: no manager and nobody reporting to them
        cls.ceo = cls._create_employee("Ceo", job_id=cls.job.id)
        # Siblings are created out of alphabetical order on purpose
        cls.zed = cls._create_employee("Zed", cls.ceo, job_title="Head of Zebras")
        cls.abe = cls._create_employee("Abe", cls.ceo, job_id=cls.job.id)
        cls.mia = cls._create_employee("Mia", cls.ceo)
        cls.lea = cls._create_employee("Lea", cls.abe)
        cls.max = cls._create_employee("Max", cls.lea)
        cls.noa = cls._create_employee("Noa", cls.max)
        cls.pia = cls._create_employee("Pia", cls.noa)
        cls.solo_one = cls._create_employee("Solo One")
        cls.solo_two = cls._create_employee("Solo Two")
        # Other Org Chart Company
        cls.other_boss = cls._create_employee("Other Boss", company=cls.other_company)
        cls._create_employee("Other Sub", cls.other_boss, company=cls.other_company)
        cls.other_solo = cls._create_employee("Other Solo", company=cls.other_company)
        cls.hr_officer = new_test_user(
            cls.env,
            login="org_chart_officer",
            groups="hr.group_hr_user",
            company_id=cls.chart_company.id,
            company_ids=[Command.set(cls.chart_company.ids)],
        )
        cls.internal_user = new_test_user(
            cls.env,
            login="org_chart_internal",
            company_id=cls.chart_company.id,
            company_ids=[Command.set(cls.chart_company.ids)],
        )

    @classmethod
    def _create_employee(cls, name, manager=None, company=None, **vals):
        return cls.Employee.create(
            {
                "name": name,
                "company_id": (company or cls.chart_company).id,
                "parent_id": manager.id if manager else False,
                **vals,
            }
        )

    def _get_data(self, company=None, user=None):
        employee_model = self.Employee.with_company(company or self.chart_company)
        if user:
            employee_model = employee_model.with_user(user)
        data = employee_model.get_organization_data()
        self.assertEqual(data["unassigned_count"], len(data["unassigned_ids"]))
        return data

    def _walk(self, node):
        """Yield every employee node below ``node``."""
        for child in node.get("children", []):
            yield child
            yield from self._walk(child)

    def _find(self, data, name):
        return next(node for node in self._walk(data) if node["name"] == name)

    def test_company_node(self):
        data = self._get_data()
        self.assertEqual(
            set(data),
            {
                "id",
                "name",
                "title",
                "className",
                "unassigned_count",
                "unassigned_ids",
                "children",
            },
        )
        self.assertIs(data["id"], False)
        self.assertEqual(data["name"], "Org Chart Company")
        self.assertEqual(data["title"], "")
        self.assertEqual(data["className"], "o_org_company")

    def test_tree_shape_and_levels(self):
        data = self._get_data()
        self.assertEqual([node["id"] for node in data["children"]], self.ceo.ids)
        node = data["children"][0]
        chain = [self.ceo, self.abe, self.lea, self.max, self.noa, self.pia]
        levels = ["level-0", "level-1", "level-2", "level-3", "level-4", "level-0"]
        for employee, level in zip(chain, levels, strict=True):
            self.assertEqual(node["id"], employee.id)
            self.assertEqual(node["name"], employee.name)
            self.assertEqual(node["className"], level)
            node = next(iter(node.get("children", [])), None)
        self.assertIsNone(node)
        self.assertEqual(len(list(self._walk(data))), 8)

    def test_siblings_ordered_by_name(self):
        ceo_node = self._find(self._get_data(), "Ceo")
        self.assertEqual(
            [node["name"] for node in ceo_node["children"]], ["Abe", "Mia", "Zed"]
        )
        self.assertEqual(
            [node["className"] for node in ceo_node["children"]], ["level-1"] * 3
        )

    def test_node_keys(self):
        """Leaves carry no ``children`` key and nodes never ship the image."""
        data = self._get_data()
        self.assertIsInstance(data["children"], list)
        leaves = set()
        for node in self._walk(data):
            keys = {"id", "name", "title", "className"}
            if "children" in node:
                self.assertTrue(node["children"])
                keys.add("children")
            else:
                leaves.add(node["name"])
            self.assertEqual(set(node), keys)
            self.assertIsInstance(node["id"], int)
            self.assertIsInstance(node["name"], str)
            self.assertIsInstance(node["title"], str)
        self.assertEqual(leaves, {"Mia", "Pia", "Zed"})

    def test_title(self):
        # Job set and its title blanked by hand: fall back on the job name
        self.abe.job_title = False
        self.assertFalse(self.abe.job_title)
        data = self._get_data()
        self.assertEqual(self._find(data, "Ceo")["title"], "Chief Executive")
        self.assertEqual(self._find(data, "Zed")["title"], "Head of Zebras")
        self.assertEqual(self._find(data, "Abe")["title"], "Chief Executive")
        # Neither job nor job title
        self.assertFalse(self.mia.job_title)
        self.assertEqual(self._find(data, "Mia")["title"], "")

    def test_unassigned(self):
        data = self._get_data()
        self.assertEqual(data["unassigned_count"], 2)
        self.assertEqual(data["unassigned_ids"], (self.solo_one + self.solo_two).ids)
        # Listed by name, whatever the order of creation
        solo_alpha = self._create_employee("Solo Alpha")
        self._create_employee("Solo Archived", active=False)
        data = self._get_data()
        self.assertEqual(data["unassigned_count"], 3)
        self.assertEqual(
            data["unassigned_ids"], (solo_alpha + self.solo_one + self.solo_two).ids
        )
        self.assertEqual([node["name"] for node in data["children"]], ["Ceo"])

    def test_no_employee(self):
        company = self._create_company(name="Empty Org Chart Company")
        data = self._get_data(company)
        self.assertEqual(data["name"], "Empty Org Chart Company")
        self.assertEqual(data["unassigned_count"], 0)
        self.assertEqual(data["unassigned_ids"], [])
        self.assertEqual(data["children"], [])

    def test_company_scoping(self):
        # Reports to the Ceo, yet belongs to the other company
        other_guest = self._create_employee(
            "Other Guest", self.ceo, company=self.other_company
        )
        self._create_employee("Old Timer", self.ceo, active=False)
        data = self._get_data()
        names = {node["name"] for node in self._walk(data)}
        self.assertEqual(
            names, {"Ceo", "Abe", "Lea", "Max", "Noa", "Pia", "Mia", "Zed"}
        )
        other_data = self._get_data(self.other_company)
        self.assertEqual(other_data["name"], "Other Org Chart Company")
        # The manager of Other Guest is out of this chart: she tops it, alone
        self.assertEqual(
            other_data["unassigned_ids"], (other_guest + self.other_solo).ids
        )
        self.assertEqual(
            [node["name"] for node in other_data["children"]], ["Other Boss"]
        )
        self.assertEqual(
            [node["name"] for node in other_data["children"][0]["children"]],
            ["Other Sub"],
        )

    def test_manager_in_other_company(self):
        """A manager out of the company does not hide those reporting to them."""
        lead = self._create_employee("Guest Lead", self.other_boss)
        self._create_employee("Guest Sub", lead)
        loner = self._create_employee("Guest Loner", self.other_boss)
        data = self._get_data()
        self.assertEqual(
            [node["name"] for node in data["children"]], ["Ceo", "Guest Lead"]
        )
        lead_node = data["children"][1]
        self.assertEqual(lead_node["id"], lead.id)
        self.assertEqual(lead_node["className"], "level-0")
        self.assertEqual(
            [(node["name"], node["className"]) for node in lead_node["children"]],
            [("Guest Sub", "level-1")],
        )
        self.assertEqual(
            data["unassigned_ids"], (loner + self.solo_one + self.solo_two).ids
        )
        # They stay out of the chart of the company of their manager
        other_data = self._get_data(self.other_company)
        self.assertEqual(
            {node["name"] for node in self._walk(other_data)},
            {"Other Boss", "Other Sub"},
        )
        self.assertEqual(other_data["unassigned_ids"], self.other_solo.ids)

    def test_manager_archived(self):
        """Those reporting to an archived manager stay in the chart."""
        # Unlike the archive action, a plain write leaves the manager in place
        self.abe.write({"active": False})
        self.assertEqual(self.lea.parent_id, self.abe)
        data = self._get_data()
        self.assertEqual([node["name"] for node in data["children"]], ["Ceo", "Lea"])
        self.assertEqual(
            [node["name"] for node in self._find(data, "Ceo")["children"]],
            ["Mia", "Zed"],
        )
        node = data["children"][1]
        chain = [self.lea, self.max, self.noa, self.pia]
        levels = ["level-0", "level-1", "level-2", "level-3"]
        for employee, level in zip(chain, levels, strict=True):
            self.assertEqual(node["id"], employee.id)
            self.assertEqual(node["className"], level)
            node = next(iter(node.get("children", [])), None)
        self.assertIsNone(node)
        self.assertEqual(data["unassigned_ids"], (self.solo_one + self.solo_two).ids)
        # Nobody reports to Pia: once her manager is gone, she is unassigned
        self.noa.write({"active": False})
        self.assertEqual(self.pia.parent_id, self.noa)
        data = self._get_data()
        self.assertEqual(
            {node["name"] for node in self._walk(data)},
            {"Ceo", "Mia", "Zed", "Lea", "Max"},
        )
        self.assertEqual(
            data["unassigned_ids"], (self.pia + self.solo_one + self.solo_two).ids
        )

    def test_manager_hidden_by_record_rule(self):
        self.env["ir.rule"].create(
            {
                "name": "Org chart test: Abe is hidden",
                "model_id": self.env.ref("hr.model_hr_employee").id,
                "domain_force": f"[('id', '!=', {self.abe.id})]",
            }
        )
        data = self._get_data(user=self.hr_officer)
        self.assertEqual([node["name"] for node in data["children"]], ["Ceo", "Lea"])
        self.assertEqual(data["children"][1]["className"], "level-0")
        self.assertEqual(
            {node["name"] for node in self._walk(data)},
            {"Ceo", "Mia", "Zed", "Lea", "Max", "Noa", "Pia"},
        )
        self.assertEqual(data["unassigned_ids"], (self.solo_one + self.solo_two).ids)

    def test_assign_manager(self):
        self.mia.parent_id = self.abe
        self.zed.parent_id = False
        data = self._get_data()
        self.assertEqual(
            [node["name"] for node in self._find(data, "Abe")["children"]],
            ["Lea", "Mia"],
        )
        self.assertEqual(self._find(data, "Mia")["className"], "level-2")
        self.assertEqual(
            data["unassigned_ids"], (self.solo_one + self.solo_two + self.zed).ids
        )

    def test_manager_loop_raises(self):
        with self.assertRaises(ValidationError):
            self.ceo.parent_id = self.pia

    def test_two_employee_loop_raises(self):
        with self.assertRaises(ValidationError):
            self.abe.parent_id = self.lea

    def test_loop_below_own_manager_raises(self):
        self.ceo.parent_id = self.ceo
        with self.assertRaises(ValidationError):
            self.abe.parent_id = self.pia

    def test_own_manager_is_accepted(self):
        """Odoo marks the top of the hierarchy with a self-managed employee."""
        expected = self._get_data()
        self.ceo.parent_id = self.ceo
        self.solo_one.parent_id = self.solo_one
        self.assertEqual(self.ceo.parent_id, self.ceo)
        self.assertEqual(self.solo_one.parent_id, self.solo_one)
        # Same chart as without manager: top employee and unassigned employee
        data = self._get_data()
        self.assertEqual(data, expected)
        self.assertEqual([node["id"] for node in data["children"]], self.ceo.ids)
        self.assertIn(self.solo_one.id, data["unassigned_ids"])

    def test_own_manager_becomes_top_employee(self):
        self.abe.parent_id = self.abe
        data = self._get_data()
        self.assertEqual([node["name"] for node in data["children"]], ["Abe", "Ceo"])
        abe_node = data["children"][0]
        self.assertEqual(abe_node["className"], "level-0")
        self.assertEqual([node["name"] for node in abe_node["children"]], ["Lea"])
        self.assertEqual(self._find(data, "Pia")["className"], "level-4")
        self.assertEqual(
            [node["name"] for node in self._find(data, "Ceo")["children"]],
            ["Mia", "Zed"],
        )
        self.assertEqual(data["unassigned_count"], 2)

    def test_assign_manager_below_own_manager(self):
        self.ceo.parent_id = self.ceo
        self.mia.parent_id = self.zed
        newcomer = self._create_employee("Newcomer", self.ceo)
        data = self._get_data()
        self.assertEqual(
            [node["name"] for node in self._find(data, "Ceo")["children"]],
            ["Abe", "Newcomer", "Zed"],
        )
        self.assertEqual(
            [node["id"] for node in self._find(data, "Zed")["children"]], self.mia.ids
        )
        self.assertEqual(self._find(data, "Newcomer")["id"], newcomer.id)

    def test_existing_manager_loop(self):
        """A loop stored before the constraint existed must not hang the chart."""
        # Abe and Lea manage each other, with Max, Noa and Pia below them
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE hr_employee SET parent_id = %s WHERE id = %s",
            (self.lea.id, self.abe.id),
        )
        self.env.invalidate_all()
        data = self._get_data()
        names = {node["name"] for node in self._walk(data)}
        self.assertEqual(names, {"Ceo", "Mia", "Zed"})
        # No top employee leads to them: they have no place in the tree. They
        # all have a manager in the chart, so they are not unassigned either.
        left_out = self.abe + self.lea + self.max + self.noa + self.pia
        tree_ids = {node["id"] for node in self._walk(data)}
        self.assertFalse(tree_ids & set(left_out.ids))
        self.assertEqual(data["unassigned_ids"], (self.solo_one + self.solo_two).ids)
        self.assertEqual(data["unassigned_count"], 2)

    def test_query_count_does_not_grow(self):
        def count_queries():
            self.env.flush_all()
            self.env.invalidate_all()
            before = self.env.cr.sql_log_count
            self._get_data()
            return self.env.cr.sql_log_count - before

        count_queries()  # warm up the registry caches
        expected = count_queries()
        manager = self.pia
        for index in range(10):
            manager = self._create_employee(f"Extra {index}", manager)
            self._create_employee(f"Extra Leaf {index}", manager)
        self.assertEqual(len(list(self._walk(self._get_data()))), 28)
        self.assertEqual(count_queries(), expected)

    def test_access_rights(self):
        """The chart is built with the rights of the user, without sudo."""
        self.assertEqual(self._get_data(user=self.hr_officer), self._get_data())
        with self.assertRaises(AccessError):
            self._get_data(user=self.internal_user)

    def test_menu(self):
        action = self.env.ref("hr_org_chart_overview.action_org_chart_overview")
        self.assertEqual(action.tag, "hr_org_chart_overview")
        menu = self.env.ref("hr_org_chart_overview.menu_org_chart_overview_report")
        self.assertEqual(menu.parent_id, self.env.ref("hr.hr_menu_hr_reports"))
        self.assertEqual(menu.action, action)
        self.assertEqual(menu.group_ids, self.env.ref("hr.group_hr_user"))
        # HR officers reach the entry: it is visible, and so are its ancestors
        path_ids = {int(menu_id) for menu_id in menu.parent_path.split("/") if menu_id}
        menu_model = self.env["ir.ui.menu"]
        officer_menus = menu_model.with_user(self.hr_officer)._visible_menu_ids()
        self.assertLessEqual(path_ids, officer_menus)
        internal_menus = menu_model.with_user(self.internal_user)._visible_menu_ids()
        self.assertNotIn(menu.id, internal_menus)
