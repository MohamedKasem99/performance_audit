/** @odoo-module **/

import { Component, useRef, onMounted, onWillStart, useState, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const STORAGE_KEY_PREFIX = 'performance_audit_timeline_';
const STORAGE_KEYS = {
    FILTER: `${STORAGE_KEY_PREFIX}filter`,
    WINDOW_START: `${STORAGE_KEY_PREFIX}window_start`,
    WINDOW_END: `${STORAGE_KEY_PREFIX}window_end`
};

const TIMELINE_OPTIONS = {
    stack: true,
    maxHeight: '80vh',
    zoomKey: 'ctrlKey',
    verticalScroll: true,
    horizontalScroll: true,
    showTooltips: true,
    multiselect: true,
    autoResize: true,
    orientation: { axis: 'both', item: 'top' },
    tooltip: { followMouse: true },
    moveable: true,
    zoomable: true,
    selectable: true,
    throttleRedraw: 16
};

export class SlowRequestTimeline extends Component {
    setup() {
        this.state = useState({
            loading: true,
            rendering: false,
            groupedData: {},
            availableDates: [],
            noData: false,
            error: null,
            currentFilter: this._getStoredValue(STORAGE_KEYS.FILTER, 'all'),
            savedWindow: this._getSavedWindowPosition(),
            domainFilter: this._getStoredValue(STORAGE_KEYS.DOMAIN_FILTER, ''),
            libraryReady: false
        });

        this.rpc = useService("rpc");
        this.action = useService("action");
        this.containerRef = useRef("timelineContainer");

        this.timeline = null;
        this._items = null;

        onWillStart(async () => await this._fetchData(this.state.domainFilter));
        onMounted(() => this._waitForVisLibrary());
        onWillUnmount(() => this._cleanupResources());
    }

    _waitForVisLibrary() {
        const checkLibrary = () => {
            if (window.vis) {
                this.state.libraryReady = true;
                this._initTimeline();
            } else {
                setTimeout(checkLibrary, 50);
            }
        };

        checkLibrary();
    }

    async _fetchData(domain = null) {
        try {
            this.state.loading = true;
            const result = await this.rpc("/performance_audit/slow_requests_data", { domain });
            if (result.error) {
                this.state.error = result.error;
                this.state.noData = true;
                // fail the promise
                return Promise.reject(result.error);
            }
            this.state.groupedData = result.byDate || {};
            this.state.availableDates = result.availableDates || [];

            if (this.state.currentFilter !== 'all' &&
                !this.state.availableDates.includes(this.state.currentFilter)) {
                this.state.currentFilter = 'all';
                this._storeValue(STORAGE_KEYS.FILTER, 'all');
            }
            this.state.noData = !this.state.availableDates.length;
        } catch (error) {
            this.state.error = "Failed to load request data: " + error.toString();
            this.state.noData = true;
        } finally {
            this.state.loading = false;
        }
    }

    _initTimeline() {
        if (this.state.noData) {
            this._showNoDataMessage(this.state.currentFilter);
            return;
        }
        this._applyFilter(this.state.currentFilter);
    }

    _applyFilter(filterValue) {
        const timelineData = this._prepareTimelineData(filterValue);

        if (!timelineData) {
            this._showNoDataMessage(filterValue);
            return;
        }

        this._createTimeline(timelineData.items, timelineData.timeWindow);
    }

    _prepareTimelineData(filterValue) {
        if (filterValue === 'all') {
            return {
                items: Object.values(this.state.groupedData).flat(),
                timeWindow: null
            };
        }

        if (this.state.groupedData[filterValue]) {
            const [year, month, day] = filterValue.split('-');
            const date = new Date(year, month - 1, day);

            return {
                items: this.state.groupedData[filterValue],
                timeWindow: {
                    start: new Date(new Date(date).setHours(0, 0, 0, 0)),
                    end: new Date(new Date(date).setHours(23, 59, 59, 999))
                }
            };
        }

        return null;
    }

    _createTimeline(items, timeWindow = null) {
        if (!items?.length) {
            this._showNoDataMessage('all');
            return null;
        }

        this._cleanupTimeline();

        this._items = new window.vis.DataSet({ queue: { delay: 50 } });
        this._items.add(items);

        const options = {
            ...TIMELINE_OPTIONS,
            order: (a, b) => b.duration - a.duration
        };

        this.timeline = new window.vis.Timeline(
            this.containerRef.el,
            this._items,
            options
        );

        this.timeline.on('doubleClick', this._handleDoubleClick.bind(this));
        this.timeline.on('rangechanged', this._handleRangeChanged.bind(this));

        this._restoreTimelinePosition(timeWindow);

        return this.timeline;
    }

    _restoreTimelinePosition(timeWindow) {
        if (this.state.savedWindow &&
            (timeWindow === null || this.state.currentFilter !== 'all')) {
            requestAnimationFrame(() => {
                this.timeline.setWindow(this.state.savedWindow.start, this.state.savedWindow.end);
            });
        }
        else if (timeWindow) {
            this.timeline.setWindow(timeWindow.start, timeWindow.end);
            this.state.rendering = true;
            setTimeout(() => {
                this.timeline.fit();
                this.timeline.setWindow(timeWindow.start, timeWindow.end, {
                    animation: false
                });
                this.state.rendering = false;
            }, 200);
        }
        else {
            this.state.rendering = true;
            this.zoomFit(300);
            this.state.rendering = false;
        }
    }

    _handleDoubleClick(properties) {
        if (!properties.item) return;

        this._saveCurrentWindowPosition();

        const item = this._items.get(properties.item);
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'pa.slow.request',
            res_id: item.id,
            views: [[false, 'form']],
            target: 'current',
        });
    }

    _handleRangeChanged(properties) {
        this._storeValue(STORAGE_KEYS.WINDOW_START, properties.start.getTime());
        this._storeValue(STORAGE_KEYS.WINDOW_END, properties.end.getTime());
    }

    _saveCurrentWindowPosition() {
        if (!this.timeline) return;

        const window = this.timeline.getWindow();
        this._storeValue(STORAGE_KEYS.WINDOW_START, window.start.getTime());
        this._storeValue(STORAGE_KEYS.WINDOW_END, window.end.getTime());
    }

    _cleanupTimeline() {
        if (this.timeline) {
            this.timeline.off('doubleClick');
            this.timeline.off('rangechanged');
            this.timeline.destroy();
            this.timeline = null;
        }

        if (this._items) {
            this._items.clear();
            this._items = null;
        }
    }

    _cleanupResources() {
        this._cleanupTimeline();
        this.state.timelineData = null;
        this.state.groupedData = null;
    }

    _getStoredValue(key, defaultValue) {
        try {
            const value = localStorage.getItem(key);
            return value !== null ? value : defaultValue;
        } catch (e) {
            return defaultValue;
        }
    }

    _storeValue(key, value) {
        try {
            localStorage.setItem(key, value);
        } catch (e) {
            console.warn('Failed to store value in localStorage:', e);
        }
    }

    _removeStoredValue(key) {
        try {
            localStorage.removeItem(key);
        } catch (e) {
            console.warn('Failed to remove value from localStorage:', e);
        }
    }

    _getSavedWindowPosition() {
        try {
            const start = localStorage.getItem(STORAGE_KEYS.WINDOW_START);
            const end = localStorage.getItem(STORAGE_KEYS.WINDOW_END);

            if (start && end) {
                return {
                    start: new Date(parseInt(start)),
                    end: new Date(parseInt(end))
                };
            }
        } catch (e) {
            console.warn('Failed to get saved window position:', e);
        }

        return null;
    }

    filterByDate(event) {
        const selectedDate = event.target.value;

        if (selectedDate === this.state.currentFilter) return;

        this.state.currentFilter = selectedDate;
        this._storeValue(STORAGE_KEYS.FILTER, selectedDate);

        this.state.savedWindow = null;
        this._removeStoredValue(STORAGE_KEYS.WINDOW_START);
        this._removeStoredValue(STORAGE_KEYS.WINDOW_END);

        this.state.rendering = true;
        this._applyFilter(selectedDate);
        setTimeout(() => {
            if (this.timeline) {
                this.timeline.fit();
                this._saveCurrentWindowPosition();
                this.state.rendering = false;
            }
        }, 300);
    }

    async applyDomainFilter() {
        this.state.error = null;
        this._storeValue(STORAGE_KEYS.DOMAIN_FILTER, this.state.domainFilter.trim());
        this._fetchData(this.state.domainFilter.trim()).then(() => {
            this.state.rendering = true;
            setTimeout(() => {
                if (this.containerRef && this.containerRef.el) {
                    this._applyFilter(this.state.currentFilter);
                }
                this.zoomFit(200);
                this.state.rendering = false;
            }, 100);
        }).catch((error) => {
            this.state.error = `Failed to fetch data: ${error.message || error}`;
            this.state.loading = false;
        });
    }

    zoomFit(delay = 0) {
        if (!this.timeline) return;

        setTimeout(() => {
            this.timeline.fit();
            this._saveCurrentWindowPosition();
        }, delay);
    }
    _showNoDataMessage(filterValue) {
        this._cleanupTimeline();

        if (!this.containerRef || !this.containerRef.el) {
            console.warn('Timeline container reference is not available');
            return;
        }

        this.containerRef.el.innerHTML =
            `<div class="alert alert-info">No requests found for ${filterValue === 'all' ? 'any date' : 'the selected date'
            }.</div>`;
    }

}

SlowRequestTimeline.template = 'performance_audit.SlowRequestTimeline';

registry.category("actions").add("performance_audit.slow_request_timeline", SlowRequestTimeline);