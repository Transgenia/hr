/* License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html). */

import {
    Component,
    onMounted,
    onWillStart,
    onWillUnmount,
    useRef,
    useState,
} from "@odoo/owl";
import {Layout} from "@web/search/layout";
import {_t} from "@web/core/l10n/translation";
import {ensureJQuery} from "@web/core/ensure_jquery";
import {imageUrl} from "@web/core/utils/urls";
import {loadBundle} from "@web/core/assets";
import {normalize} from "@web/core/l10n/utils";
import {registry} from "@web/core/registry";
import {standardActionServiceProps} from "@web/webclient/actions/action_service";
import {useService} from "@web/core/utils/hooks";
import {user} from "@web/core/user";

const ZOOM_STEP = 1.2;
const ZOOM_MIN = 0.3;
const ZOOM_MAX = 2.5;
const LEVEL_COUNT = 5;
const LEVEL_CLASS_RE = /^level-\d+$/;
const FILTER_CLASSES = ["hidden", "matched", "retained"];
const SLIDE_CLASSES = [
    "sliding",
    "slide-up",
    "slide-down",
    "slide-left",
    "slide-right",
];
// Fallback for a server that does not tell who is left out of the chart
const LEGACY_UNASSIGNED_DOMAIN = [
    ["parent_id", "=", false],
    ["child_ids", "=", false],
];
// Browsers refuse to draw on a canvas beyond some size (about 16384 px per side
// for the strictest ones) and then export an empty image.
const CANVAS_MAX_SIDE = 16000;
// Largest side of a PDF page, in points
const PDF_MAX_SIDE = 14400;
const PNG_DATA_URL_PREFIX = "data:image/png;base64,";

/**
 * JQuery is not part of the backend assets anymore: it is fetched on demand,
 * once, by the core helper (which leaves an already loaded jQuery untouched),
 * and only then the chart library that registers itself on it.
 */
async function loadChartLibraries() {
    await ensureJQuery();
    await loadBundle("hr_org_chart_overview.assets_orgchart");
}

/**
 * Build the node given to the chart library out of a node of the server
 * payload. Only the keys the client needs are kept, each one coerced to its
 * expected type, so nothing else of the payload can reach the library (which
 * concatenates some values into HTML).
 *
 * @param {Object} node
 * @param {Number} depth 0 for the employees right below the company
 * @returns {Object}
 */
function prepareEmployeeNode(node, depth) {
    const prepared = {
        employeeId: Number.isInteger(node.id) && node.id > 0 ? node.id : false,
        name: typeof node.name === "string" ? node.name : "",
        title: typeof node.title === "string" ? node.title : "",
        className: LEVEL_CLASS_RE.test(node.className)
            ? node.className
            : `level-${depth % LEVEL_COUNT}`,
    };
    if (Array.isArray(node.children) && node.children.length) {
        prepared.children = node.children.map((child) =>
            prepareEmployeeNode(child, depth + 1)
        );
    }
    return prepared;
}

/**
 * @param {Object} data result of `hr.employee.get_organization_data`
 * @returns {Object} the company node, root of the chart
 */
function prepareCompanyNode(data) {
    const children = Array.isArray(data.children) ? data.children : [];
    return {
        employeeId: false,
        name: (typeof data.name === "string" && data.name) || user.activeCompany.name,
        title: "",
        className: "o_org_company",
        children: children.map((child) => prepareEmployeeNode(child, 0)),
    };
}

/**
 * The employees left out of the chart: how many they are and the domain that
 * lists them. Both come from the same ids, so the list opened from the banner
 * shows exactly the employees it counts.
 *
 * @param {Object} data result of `hr.employee.get_organization_data`
 * @returns {{count: Number, domain: Array}}
 */
function prepareUnassigned(data) {
    const ids = data.unassigned_ids;
    if (Array.isArray(ids) && ids.every((id) => Number.isInteger(id) && id > 0)) {
        return {count: ids.length, domain: [["id", "in", ids]]};
    }
    // Older payload: only a count, the list is the closest known domain
    const count = data.unassigned_count;
    return {
        count: Number.isInteger(count) && count > 0 ? count : 0,
        domain: LEGACY_UNASSIGNED_DOMAIN,
    };
}

export class HrOrgChartOverview extends Component {
    static template = "hr_org_chart_overview.HrOrgChartOverview";
    static components = {Layout};
    static props = {...standardActionServiceProps};

    setup() {
        this.action = useService("action");
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.ui = useService("ui");
        this.containerRef = useRef("container");
        this.state = useState({
            search: "",
            noMatch: false,
            pan: false,
            zoom: 1,
        });
        this.chartEl = null;
        this.drag = null;
        // Text each employee node is searched on, normalized once at render
        this.searchKeys = new WeakMap();

        onWillStart(async () => {
            const [data, isHrUser] = await Promise.all([
                this.orm.call("hr.employee.public", "get_organization_data", []),
                user.hasGroup("hr.group_hr_user"),
                loadChartLibraries(),
            ]);
            this.isHrUser = isHrUser;
            // HR officers open the full employee records, everybody else the
            // public ones, which they are allowed to read
            this.employeeModel = isHrUser ? "hr.employee" : "hr.employee.public";
            this.root = prepareCompanyNode(data);
            this.unassigned = prepareUnassigned(data);
        });
        onMounted(() => this.renderChart());
        onWillUnmount(() => this.destroyChart());
    }

    // ------------------------------------------------------------------
    // Getters
    // ------------------------------------------------------------------

    get isEmpty() {
        return !this.root.children.length;
    }

    get unassignedMessage() {
        if (this.unassigned.count === 1) {
            return _t(
                "1 employee has no manager and no subordinates, so they are not shown."
            );
        }
        return _t(
            "%s employees have no manager and no subordinates, so they are not shown.",
            this.unassigned.count
        );
    }

    get noMatchMessage() {
        return _t(
            'No employee or job position matches "%s".',
            this.state.search.trim()
        );
    }

    get zoomLabel() {
        return `${Math.round(this.state.zoom * 100)}%`;
    }

    get canZoomIn() {
        return !this.isEmpty && this.state.zoom < ZOOM_MAX;
    }

    get canZoomOut() {
        return !this.isEmpty && this.state.zoom > ZOOM_MIN;
    }

    // ------------------------------------------------------------------
    // Chart rendering
    // ------------------------------------------------------------------

    renderChart() {
        const container = this.containerRef.el;
        if (!container) {
            return;
        }
        window.jQuery(container).orgchart({
            data: this.root,
            nodeTemplate: (node) => this.buildNodeContent(node),
            createNode: ($node, node) => this.decorateNode($node[0], node),
        });
        this.chartEl = container.querySelector(":scope > .orgchart");
        this.centerChart();
    }

    destroyChart() {
        if (!this.chartEl) {
            return;
        }
        // Going through jQuery also drops the handlers and the data the
        // library attached to every node
        window.jQuery(this.chartEl).remove();
        this.chartEl = null;
    }

    /**
     * Content of a node. Names and job titles are user data: they are only
     * ever set as text, never parsed as HTML.
     *
     * @param {Object} node
     * @returns {HTMLElement[]}
     */
    buildNodeContent(node) {
        const avatar = document.createElement("span");
        avatar.className = "o_org_chart_avatar";
        avatar.style.backgroundImage = `url("${this.getAvatarUrl(node)}")`;
        const name = document.createElement("div");
        name.className = "o_org_chart_name";
        name.textContent = node.name;
        const elements = [avatar, name];
        if (node.title) {
            const job = document.createElement("div");
            job.className = "o_org_chart_job";
            job.textContent = node.title;
            elements.push(job);
        }
        return elements;
    }

    getAvatarUrl(node) {
        if (node.employeeId) {
            return imageUrl("hr.employee.public", node.employeeId, "avatar_128");
        }
        return imageUrl("res.company", user.activeCompany.id, "logo");
    }

    /**
     * @param {HTMLElement} el node element created by the library
     * @param {Object} node
     */
    decorateNode(el, node) {
        const toggle = el.querySelector(":scope > .bottomEdge");
        if (toggle) {
            toggle.title = _t("Collapse or expand");
        }
        if (!node.employeeId) {
            return;
        }
        el.classList.add("o_org_chart_employee");
        el.dataset.employeeId = node.employeeId;
        el.tabIndex = 0;
        el.setAttribute("role", "link");
        this.searchKeys.set(el, normalize(`${node.name} ${node.title}`));
    }

    // ------------------------------------------------------------------
    // Navigation
    // ------------------------------------------------------------------

    async openEmployee(nodeEl) {
        const employeeId = Number(nodeEl && nodeEl.dataset.employeeId);
        if (!employeeId) {
            return;
        }
        const action = await this.orm.call(this.employeeModel, "get_formview_action", [
            [employeeId],
        ]);
        await this.action.doAction(action);
    }

    openOfficialChart() {
        return this.action.doAction("hr_org_chart_overview.action_official_org_chart");
    }

    onChartClick(ev) {
        if (ev.target.closest(".edge")) {
            // Collapse/expand handle of the library
            return;
        }
        this.openEmployee(ev.target.closest(".node"));
    }

    onChartKeydown(ev) {
        if (!["Enter", " "].includes(ev.key) || !ev.target.classList.contains("node")) {
            return;
        }
        ev.preventDefault();
        this.openEmployee(ev.target);
    }

    openUnassigned() {
        return this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Employees without manager or subordinates"),
            res_model: this.employeeModel,
            views: [
                [false, "list"],
                [false, "kanban"],
                [false, "form"],
            ],
            domain: this.unassigned.domain,
        });
    }

    // ------------------------------------------------------------------
    // Search
    // ------------------------------------------------------------------

    onSearchInput(ev) {
        this.state.search = ev.target.value;
        this.applySearch();
    }

    onSearchKeydown(ev) {
        if (ev.key === "Escape" && this.state.search) {
            ev.stopPropagation();
            this.clearSearch();
        }
    }

    clearSearch() {
        this.state.search = "";
        this.applySearch();
    }

    applySearch() {
        if (!this.chartEl) {
            return;
        }
        const keyword = normalize(this.state.search.trim());
        this.resetVisibility();
        // The library offers no collapse/expand handle on a filtered chart
        this.chartEl.classList.toggle("noncollapsable", Boolean(keyword));
        const rootTable = this.chartEl.querySelector(":scope > table");
        const found = keyword && this.filterSubtree(rootTable, keyword);
        this.state.noMatch = Boolean(keyword && !found);
    }

    /**
     * Show everything again: drop the result of a previous search as well as
     * the branches collapsed through the library.
     */
    resetVisibility() {
        const classes = [...FILTER_CLASSES, ...SLIDE_CLASSES];
        const selector = classes.map((name) => `.${name}`).join(",");
        for (const el of this.chartEl.querySelectorAll(selector)) {
            el.classList.remove(...classes);
        }
        for (const row of this.chartEl.querySelectorAll("tr.lines")) {
            row.style.visibility = "";
        }
    }

    /**
     * Keep the matching employees, the chain of managers above them and
     * nothing else, as the upstream filter did.
     *
     * The library draws a subtree as a table: a row for the node, then, when
     * it has children, two rows of connectors and one row with a cell per
     * child (each holding the table of that child).
     *
     * @param {HTMLTableElement} table
     * @param {String} keyword normalized search term
     * @returns {Boolean} whether something in the subtree matches
     */
    filterSubtree(table, keyword) {
        const rows = Array.from(table.rows);
        const node = rows[0].querySelector(".node");
        const lineRows = rows.filter((row) => row.classList.contains("lines"));
        const childrenRow = rows.find((row) => row.classList.contains("nodes"));
        const childCells = childrenRow ? Array.from(childrenRow.cells) : [];
        const keptCells = childCells.filter((cell) =>
            this.filterSubtree(cell.querySelector(":scope > table"), keyword)
        );
        const matched = (this.searchKeys.get(node) || "").includes(keyword);
        node.classList.toggle("matched", matched);
        node.classList.toggle("retained", !matched && keptCells.length > 0);
        for (const row of [...lineRows, childrenRow]) {
            if (row) {
                row.classList.toggle("hidden", !keptCells.length);
            }
        }
        if (keptCells.length) {
            for (const cell of childCells) {
                cell.classList.toggle("hidden", !keptCells.includes(cell));
            }
            // The lower connector row has two cells per child, alike but for
            // both ends: hiding two inner cells per hidden child leaves the
            // right connector for the children that remain.
            const hiddenCount = (childCells.length - keptCells.length) * 2;
            Array.from(lineRows[1].cells).forEach((cell, index) => {
                cell.classList.toggle("hidden", index >= 1 && index <= hiddenCount);
            });
        }
        return matched || keptCells.length > 0;
    }

    // ------------------------------------------------------------------
    // Zoom and pan
    // ------------------------------------------------------------------

    /**
     * @param {Number} zoom
     * @param {Boolean} [keepCenter=true] keep what is at the center of the
     * visible area in place
     */
    setZoom(zoom, keepCenter = true) {
        const container = this.containerRef.el;
        if (!container) {
            return;
        }
        const previous = this.state.zoom;
        const next = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, zoom));
        const centerX = container.scrollLeft + container.clientWidth / 2;
        const centerY = container.scrollTop + container.clientHeight / 2;
        this.state.zoom = next;
        container.style.setProperty("--o-org-chart-zoom", next);
        if (keepCenter) {
            const ratio = next / previous;
            container.scrollLeft = centerX * ratio - container.clientWidth / 2;
            container.scrollTop = centerY * ratio - container.clientHeight / 2;
        }
    }

    centerChart() {
        const container = this.containerRef.el;
        container.scrollLeft = (container.scrollWidth - container.clientWidth) / 2;
        container.scrollTop = 0;
    }

    onZoomIn() {
        this.setZoom(this.state.zoom * ZOOM_STEP);
    }

    onZoomOut() {
        this.setZoom(this.state.zoom / ZOOM_STEP);
    }

    onResetZoom() {
        this.setZoom(1);
    }

    onFit() {
        const container = this.containerRef.el;
        if (!container) {
            return;
        }
        // Measure the chart at its natural size. Only its table is zoomed,
        // the padding around it is not.
        this.setZoom(1, false);
        const table = this.chartEl.querySelector(":scope > table");
        const paddingX = this.chartEl.offsetWidth - table.offsetWidth;
        const paddingY = this.chartEl.offsetHeight - table.offsetHeight;
        const ratio = Math.min(
            (container.clientWidth - paddingX) / table.offsetWidth,
            (container.clientHeight - paddingY) / table.offsetHeight
        );
        this.setZoom(Math.min(1, Math.floor(ratio * 100) / 100), false);
        this.centerChart();
    }

    onTogglePan() {
        this.state.pan = !this.state.pan;
        this.drag = null;
    }

    onPointerDown(ev) {
        const container = ev.currentTarget;
        const rect = container.getBoundingClientRect();
        if (
            !this.state.pan ||
            ev.button !== 0 ||
            ev.pointerType === "touch" ||
            ev.target.closest(".node") ||
            // Scrollbars
            ev.clientX - rect.left >= container.clientWidth ||
            ev.clientY - rect.top >= container.clientHeight
        ) {
            return;
        }
        this.drag = {
            pointerId: ev.pointerId,
            x: ev.clientX,
            y: ev.clientY,
            left: container.scrollLeft,
            top: container.scrollTop,
        };
        container.setPointerCapture(ev.pointerId);
        container.classList.add("o_org_chart_grabbing");
    }

    onPointerMove(ev) {
        if (!this.drag || ev.pointerId !== this.drag.pointerId) {
            return;
        }
        const container = ev.currentTarget;
        container.scrollLeft = this.drag.left - (ev.clientX - this.drag.x);
        container.scrollTop = this.drag.top - (ev.clientY - this.drag.y);
    }

    onPointerUp(ev) {
        if (!this.drag) {
            return;
        }
        this.drag = null;
        ev.currentTarget.classList.remove("o_org_chart_grabbing");
    }

    // ------------------------------------------------------------------
    // Export
    // ------------------------------------------------------------------

    /**
     * @param {"pdf"|"png"} format
     */
    async exportChart(format) {
        const container = this.containerRef.el;
        if (!container) {
            return;
        }
        const view = {
            zoom: this.state.zoom,
            left: container.scrollLeft,
            top: container.scrollTop,
        };
        this.ui.block();
        try {
            // Only fetched when somebody exports
            await loadBundle("hr_org_chart_overview.assets_orgchart_export");
            // Capture the whole chart at its natural size, whatever part of
            // it is on screen
            this.setZoom(1, false);
            container.scrollLeft = 0;
            container.scrollTop = 0;
            // As sharp as the screen, unless the image would be too large
            const scale = Math.min(
                window.devicePixelRatio || 1,
                CANVAS_MAX_SIDE / this.chartEl.offsetWidth,
                CANVAS_MAX_SIDE / this.chartEl.offsetHeight
            );
            const canvas = await window.html2canvas(this.chartEl, {
                backgroundColor: getComputedStyle(container).backgroundColor,
                logging: false,
                scale,
                // The capture is made on a copy of the page, which gets the
                // styles meant for the exported image (see the stylesheet)
                onclone: (clonedDocument) => {
                    clonedDocument
                        .querySelector(".o_hr_org_chart_overview .orgchart")
                        .classList.add("o_org_chart_exporting");
                },
            });
            const image =
                canvas.width && canvas.height ? canvas.toDataURL("image/png") : "";
            if (
                !image.startsWith(PNG_DATA_URL_PREFIX) ||
                image.length === PNG_DATA_URL_PREFIX.length
            ) {
                // What a browser gives for a canvas it could not draw on
                throw new Error(
                    `Empty image out of a ${canvas.width}x${canvas.height} canvas`
                );
            }
            if (format === "pdf") {
                this.savePdf(image, canvas.width / scale, canvas.height / scale);
            } else {
                this.savePng(image);
            }
        } catch (error) {
            console.error(error);
            this.notification.add(_t("The chart could not be exported."), {
                type: "danger",
            });
        } finally {
            this.setZoom(view.zoom, false);
            container.scrollLeft = view.left;
            container.scrollTop = view.top;
            this.ui.unblock();
        }
    }

    get exportFilename() {
        return _t("Organizational Chart");
    }

    /**
     * @param {String} image PNG data URL
     */
    savePng(image) {
        const link = document.createElement("a");
        link.download = `${this.exportFilename}.png`;
        link.href = image;
        link.click();
    }

    /**
     * A single page filled by the image. The page has the size of the chart
     * on screen (one point per CSS pixel, whatever the pixel density of the
     * image), scaled down if needed to what a PDF page may measure.
     *
     * @param {String} image PNG data URL
     * @param {Number} width of the chart, in CSS pixels
     * @param {Number} height of the chart, in CSS pixels
     */
    savePdf(image, width, height) {
        const ratio = Math.min(1, PDF_MAX_SIDE / width, PDF_MAX_SIDE / height);
        // Rounded down, so a rounding error cannot push a side over the limit
        const pageWidth = Math.floor(width * ratio * 100) / 100;
        const pageHeight = Math.floor(height * ratio * 100) / 100;
        const doc = new window.jsPDF({
            orientation: pageWidth > pageHeight ? "landscape" : "portrait",
            unit: "pt",
            format: [pageWidth, pageHeight],
            compress: true,
        });
        doc.addImage(image, "PNG", 0, 0, pageWidth, pageHeight);
        doc.save(`${this.exportFilename}.pdf`);
    }
}

registry.category("actions").add("hr_org_chart_overview", HrOrgChartOverview);
