# Copyright 2020 ForgeFlow S.L. (https://www.forgeflow.com)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

{
    "name": "HR Org Chart Overview",
    "version": "19.0.1.0.0",
    "category": "Human Resources",
    "website": "https://github.com/OCA/hr",
    "author": "ForgeFlow S.L., Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "installable": True,
    "application": False,
    "summary": "Organizational Chart Overview",
    "depends": ["hr"],
    "data": ["views/hr_views.xml"],
    "assets": {
        "web.assets_backend": [
            "hr_org_chart_overview/static/src/js/hr_org_chart_overview.esm.js",
            "hr_org_chart_overview/static/src/scss/hr_org_chart_style.scss",
            "hr_org_chart_overview/static/src/xml/hr_org_chart_overview.xml",
        ],
        # Loaded on demand by the client action, once jQuery is there (it is
        # not part of the backend assets anymore)
        "hr_org_chart_overview.assets_orgchart": [
            "hr_org_chart_overview/static/lib/orgchart/jquery.orgchart.js",
            "hr_org_chart_overview/static/lib/orgchart/jquery.orgchart.css",
        ],
        # Loaded on demand the first time the chart is exported
        "hr_org_chart_overview.assets_orgchart_export": [
            "hr_org_chart_overview/static/lib/orgchart/html2canvas.min.js",
            "hr_org_chart_overview/static/lib/orgchart/jspdf.min.js",
        ],
        "web.assets_tests": [
            "hr_org_chart_overview/static/tests/tours/**/*",
        ],
    },
}
