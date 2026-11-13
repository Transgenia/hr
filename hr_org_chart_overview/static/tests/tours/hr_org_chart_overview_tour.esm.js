/* License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html). */

import {registry} from "@web/core/registry";

const chart = ".o_hr_org_chart_overview .orgchart";
const search = ".o_hr_org_chart_overview .o_searchview_input";
const listRows = ".o_list_view .o_data_row";
// Number of employees the banner says are left out of the chart
let announced = 0;

registry.category("web_tour.tours").add("hr_org_chart_overview_tour", {
    steps: () => [
        {
            content: "The company is the root of the chart",
            trigger: `${chart} .node.o_org_company .o_org_chart_name`,
        },
        {
            content: "Employees are drawn with their name as text",
            trigger: `${chart} .node.o_org_chart_employee .o_org_chart_name:contains(OrgChart Manager)`,
        },
        {
            content: "Down to the last level",
            trigger: `${chart} .node.o_org_chart_employee .o_org_chart_name:contains(OrgChart Deputy)`,
        },
        {
            content: "Markup in a name is displayed, not interpreted",
            trigger: `${chart} .node:contains(Report Two):not(:has(b))`,
        },
        {
            content: "Employees outside the chart are announced",
            trigger: ".o_org_chart_banner:contains(no manager and no subordinates)",
            run() {
                announced = Number.parseInt(this.anchor.textContent, 10);
            },
        },
        {
            content: "Open the employees outside the chart",
            trigger: ".o_org_chart_banner .o_org_chart_unassigned",
            run: "click",
        },
        {
            content: "The employee with neither manager nor subordinates is listed",
            trigger: `${listRows}:contains(OrgChart Loner)`,
        },
        {
            content: "So is the one who is only their own manager, and nobody else",
            trigger: `${listRows}:contains(OrgChart Solo)`,
            run() {
                const rows = Array.from(document.querySelectorAll(listRows));
                if (rows.some((row) => row.textContent.includes("OrgChart Manager"))) {
                    throw new Error("An employee of the chart is listed as left out");
                }
                if (rows.length !== announced) {
                    throw new Error(`${announced} announced, ${rows.length} listed`);
                }
            },
        },
        {
            content: "Back to the chart, which is drawn again",
            trigger: ".o_back_button",
            run: "click",
        },
        {
            content: "Search an employee",
            trigger: search,
            run: "edit report one",
        },
        {
            content: "The employee found is highlighted",
            trigger: `${chart} .node.matched .o_org_chart_name:contains(OrgChart Report One)`,
        },
        {
            content: "The manager is kept to show the reporting line",
            trigger: `${chart} .node.retained .o_org_chart_name:contains(OrgChart Manager)`,
        },
        {
            content: "The colleague in another branch is hidden",
            trigger: `${chart} .node:contains(Report Two):not(:visible)`,
        },
        {
            content: "The subordinate of the employee found is hidden",
            trigger: `${chart} .node:contains(OrgChart Deputy):not(:visible)`,
        },
        {
            content: "Search something nobody matches",
            trigger: search,
            run: "edit no such employee",
        },
        {
            content: "It is said so",
            trigger: ".o_org_chart_no_match:contains(no such employee)",
        },
        {
            content: "Clear the search",
            trigger: ".o_org_chart_search_clear",
            run: "click",
        },
        {
            content: "Everybody is back, nobody is highlighted",
            trigger: `${chart}:not(.noncollapsable) .node:not(.retained):contains(OrgChart Deputy)`,
        },
        {
            content: "Zoom in",
            trigger: ".o_org_chart_zoom_in",
            run: "click",
        },
        {
            trigger: ".o_org_chart_zoom_level:contains(120%)",
        },
        {
            content: "Turn pan on",
            trigger: ".o_org_chart_pan_toggle:not(.active)",
            run: "click",
        },
        {
            trigger: ".o_org_chart_pan_toggle.active[aria-pressed=true]",
        },
        {
            trigger: ".o_org_chart_container.o_org_chart_pan",
        },
        {
            content: "The company cannot be opened",
            trigger: `${chart} .node.o_org_company:not(.o_org_chart_employee)`,
            run: "click",
        },
        {
            content: "Open an employee",
            trigger: `${chart} .node.o_org_chart_employee:contains(OrgChart Manager)`,
            run: "click",
        },
        {
            content: "Its form is displayed",
            trigger: ".o_last_breadcrumb_item:contains(OrgChart Manager)",
        },
        {
            trigger: ".o_form_renderer",
        },
    ],
});
