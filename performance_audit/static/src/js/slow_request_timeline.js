/** @odoo-module **/

import { Component, useRef, onMounted, onWillStart, useState, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const STORAGE_KEY_PREFIX = 'performance_audit_timeline_';
const STORAGE_KEYS = {
    FILTER: `${STORAGE_KEY_PREFIX}filter`,
    WINDOW_START: `${STORAGE_KEY_PREFIX}window_start`,
    WINDOW_END: `${STORAGE_KEY_PREFIX}window_end`,
    DOMAIN_FILTER: `${STORAGE_KEY_PREFIX}domain_filter`,
    SHOW_CRONS: `${STORAGE_KEY_PREFIX}show_crons`,
    CRON_MIN_DURATION: `${STORAGE_KEY_PREFIX}cron_min_duration`,
};

const CRON_CLASS_NORMAL = 'vis-cron-item';
const CRON_CLASS_TIMEOUT = 'vis-cron-timeout-item';

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
            rendering: true,
            groupedData: {},
            cronData: {},
            availableDates: [],
            noData: false,
            error: null,
            currentFilter: this._getStoredValue(STORAGE_KEYS.FILTER, 'all'),
            savedWindow: this._getSavedWindowPosition(),
            domainFilter: this._getStoredValue(STORAGE_KEYS.DOMAIN_FILTER, ''),
            showCrons: this._getStoredValue(STORAGE_KEYS.SHOW_CRONS, 'false') === 'true',
            // null means "use server default"; only store explicit user edits
            cronMinDuration: localStorage.getItem(STORAGE_KEYS.CRON_MIN_DURATION) !== null
                ? (parseFloat(localStorage.getItem(STORAGE_KEYS.CRON_MIN_DURATION)) || 0)
                : null,
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
                this.state.rendering = false;
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
            this.state.cronData = result.cronsByDate || {};
            this.state.availableDates = result.availableDates || [];
            if (this.state.cronMinDuration === null) {
                this.state.cronMinDuration = result.minRequestTotalTime || 0;
            }

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
        const allCronItems = this.state.showCrons
            ? (filterValue === 'all'
                ? Object.values(this.state.cronData).flat()
                : (this.state.cronData[filterValue] || []))
            : [];
        const minDur = this.state.cronMinDuration ?? 0;
        const cronItems = minDur > 0
            ? allCronItems.filter(item => item.duration >= minDur || item.is_timeout)
            : allCronItems;

        // Apply cron styles
        const styledCronItems = cronItems.map(item => ({
            ...item,
            className: item.is_timeout ? CRON_CLASS_TIMEOUT : CRON_CLASS_NORMAL,
            content: `⏱ ${item.content} <span class="vis-cron-duration">${item.duration.toFixed(1)}s${item.is_timeout ? ' ⚠' : ''}</span>`,
        }));

        if (filterValue === 'all') {
            const requestItems = Object.values(this.state.groupedData).flat();
            return {
                items: [...requestItems, ...styledCronItems],
                timeWindow: null
            };
        }

        if (this.state.groupedData[filterValue] || styledCronItems.length) {
            const requestItems = this.state.groupedData[filterValue] || [];
            const [year, month, day] = filterValue.split('-');
            const date = new Date(year, month - 1, day);

            return {
                items: [...requestItems, ...styledCronItems],
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

        // Determine the day range for backgrounds
        const dayStart = new Date(items[0].start);
        dayStart.setHours(0, 0, 0, 0);
        const dayEnd = new Date(items[items.length - 1].end);
        dayEnd.setHours(23, 59, 59, 999);

        // Generate backgrounds
        const backgrounds = this._generateBackgrounds(items, dayStart, dayEnd);

        // Add backgrounds to items
        const allItems = [...items, ...backgrounds];

        this._items = new window.vis.DataSet({ queue: { delay: 50 } });
        this._items.add(allItems);

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
        if (!item || item.type === 'background') return;

        if (item.itemType === 'cron') {
            if (!item.cronAuditId) return;
            this.action.doAction({
                type: 'ir.actions.act_window',
                res_model: 'pa.cron.audit',
                res_id: item.cronAuditId,
                views: [[false, 'form']],
                target: 'current',
            });
        } else {
            this.action.doAction({
                type: 'ir.actions.act_window',
                res_model: 'pa.slow.request',
                res_id: item.id,
                views: [[false, 'form']],
                target: 'current',
            });
        }
    }

    /**
     * Captures the current visible window, runs fn(), then restores it.
     * The 350 ms delay avoids a race condition with _restoreTimelinePosition's
     * zoomFit(300) call: without it, our setWindow would fire first and be
     * immediately overwritten by the fit animation.
     */
    _preserveWindow(fn) {
        const currentWindow = this.timeline ? this.timeline.getWindow() : null;
        fn();
        if (currentWindow && this.timeline) {
            setTimeout(() => {
                if (this.timeline) {
                    this.timeline.setWindow(currentWindow.start, currentWindow.end, { animation: false });
                }
            }, 350);
        }
    }

    toggleCrons() {
        this.state.showCrons = !this.state.showCrons;
        this._storeValue(STORAGE_KEYS.SHOW_CRONS, this.state.showCrons);
        this._preserveWindow(() => this._applyFilter(this.state.currentFilter));
    }

    setCronMinDuration(event) {
        const val = parseFloat(event.target.value);
        this.state.cronMinDuration = isNaN(val) || val < 0 ? 0 : val;
        // Once the user touches the field, persist it (even if 0)
        this._storeValue(STORAGE_KEYS.CRON_MIN_DURATION, this.state.cronMinDuration);
        this._preserveWindow(() => this._applyFilter(this.state.currentFilter));
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

    _generateBackgrounds(items, start, end) {
        const backgrounds = [];
        const periodMillis = 60 * 60 * 1000;

        // Find min/max for color scaling
        let maxWeight = 0;
        const periodWeights = new Array(Math.ceil((end - start) / periodMillis)).fill(0);
        const numPeriods = Math.ceil((end - start) / periodMillis);
        for (const item of items) {
            const periodStart = new Date(item.start).getTime();
            const periodEnd = new Date(item.end).getTime();
            const periodWeight = periodEnd - periodStart;
            const periodIndex = Math.floor((periodStart - start.getTime()) / periodMillis);
            periodWeights[periodIndex] += periodWeight;
            maxWeight = Math.max(maxWeight, periodWeights[periodIndex]);
        }

        // Generate background items with color
        for (let p = 0; p < numPeriods; p++) {
            const periodStart = new Date(start.getTime() + p * periodMillis);
            const periodEnd = new Date(periodStart.getTime() + periodMillis);

            // Color: green (low) to red (high)
            const weight = periodWeights[p];
            const percent = maxWeight ? weight / maxWeight : 0;
            const color = this._getColorForWeight(percent);

            backgrounds.push({
                id: `bg_${periodStart.toISOString()}`,
                start: periodStart,
                end: periodEnd,
                type: 'background',
                content: '',
                style: `background-color: ${color}; opacity: 0.3;`
            });
        }
        return backgrounds;
    }

    /**
     * Get a color from green (low) to red (high) for a given percent (0-1).
     */
    _getColorForWeight(percent) {
        const r = Math.round(255 * percent);
        const g = Math.round(200 * (1 - percent));
        return `rgb(${r},${g},80)`;
    }
}

SlowRequestTimeline.template = 'performance_audit.SlowRequestTimeline';

registry.category("actions").add("performance_audit.slow_request_timeline", SlowRequestTimeline);