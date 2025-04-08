/** @odoo-module **/

import { Component, useRef, onMounted, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class SlowRequestTimeline extends Component {
    setup() {
        this.state = useState({
            loading: true,
            timelineData: [],
            groupedData: {},
            availableDates: [],
            noData: false,
            error: null,
            libraryLoaded: false,
            currentFilter: 'all'
        });

        this.rpc = useService("rpc");
        this.containerRef = useRef("timelineContainer");
        this.action = useService("action");
        this.timeline = null;

        onWillStart(async () => {
            await this.loadData();
        });

        onMounted(() => {
            this.loadVisTimeline();
        });
    }

    async loadData() {
        try {
            this.state.loading = true;
            const result = await this.rpc("/performance_audit/slow_requests_data");
            
            // Use pre-formatted data from the server
            this.state.timelineData = result.all || [];
            this.state.groupedData = result.byDate || {};
            this.state.availableDates = result.availableDates || [];
            this.state.noData = !this.state.timelineData.length;
        } catch (error) {
            console.error("Failed to load slow request data:", error);
            this.state.error = "Failed to load request data: " + error.toString();
            this.state.noData = true;
            this.state.timelineData = [];
            this.state.groupedData = {};
            this.state.availableDates = [];
        } finally {
            this.state.loading = false;
        }
    }

    loadVisTimeline() {
        if (window.vis) {
            this.state.libraryLoaded = true;
            this.initTimeline();
            return;
        }
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = 'https://cdn.jsdelivr.net/npm/vis-timeline@7.7.2/dist/vis-timeline-graph2d.min.css';
        document.head.appendChild(link);

        // Load JavaScript
        const script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/vis-timeline@7.7.2/dist/vis-timeline-graph2d.min.js';
        script.onload = () => {
            this.state.libraryLoaded = true;
            this.initTimeline();
        };
        script.onerror = (e) => {
            console.error("Failed to load vis-timeline", e);
            this.state.error = "Failed to load vis-timeline library";
        };
        document.head.appendChild(script);
    }

    initTimeline() {
        if (this.state.noData) {
            return;
        }
        
        const itemsData = this.state.timelineData;
        const groupsData = this.state.availableDates.map(group => ({
            id: group,
            content: group
        }));
        
        this.createTimeline(itemsData, groupsData);
    }

    createTimeline(itemsData, groupsData, timeWindow = null) {
        if (this.timeline) {
            this.timeline.destroy();
            this.timeline = null;
        }

        if (!itemsData || itemsData.length === 0) {
            this.containerRef.el.innerHTML = '<div class="alert alert-info">No requests found for the selected filter.</div>';
            return null;
        }
        
        const items = new window.vis.DataSet(itemsData);
        const groups = new window.vis.DataSet(groupsData);
        
        this.timeline = new window.vis.Timeline(
            this.containerRef.el,
            items,
            groups,
            {
                stack: true,
                maxHeight: '80vh',
                horizontalScroll: true,
                zoomKey: 'ctrlKey',
                orientation: {axis: 'top', item: 'top'}
            }
        );
        this.timeline.on('doubleClick', (properties) => {
            if (properties.item) {
                const item = items.get(properties.item);
                this.action.doAction({
                    type: 'ir.actions.act_window',
                    res_model: 'pa.slow.request',
                    res_id: item.id,
                    views: [[false, 'form']],
                    target: 'current',
                });
            }
        });
        
        if (timeWindow) {
            this.timeline.setWindow(timeWindow.start, timeWindow.end);
        } else {
            this.timeline.fit();
        }
        
        return this.timeline;
    }

    filterByDate(event) {
        const selectedDate = event.target.value;
        this.state.currentFilter = selectedDate;
        
        let itemsData, groupsData, timeWindow = null;
        
        if (selectedDate === 'all') {
            // Use all timeline data
            itemsData = this.state.timelineData;
            groupsData = this.state.availableDates.map(date => ({
                id: date,
                content: date
            }));
        } else if (this.state.groupedData[selectedDate]) {
            // Use only data for the selected date
            itemsData = this.state.groupedData[selectedDate];
            groupsData = [{
                id: selectedDate,
                content: selectedDate
            }];
            
            // Set window to the selected date's timeframe
            const [year, month, day] = selectedDate.split('-');
            const date = new Date(year, month - 1, day);
            
            timeWindow = {
                start: new Date(date.setHours(0, 0, 0, 0)),
                end: new Date(new Date(date).setHours(23, 59, 59, 999))
            };
        } else {
            // No data for this date
            if (this.timeline) {
                this.timeline.destroy();
                this.timeline = null;
            }
            this.containerRef.el.innerHTML = '<div class="alert alert-info">No requests found for the selected date.</div>';
            return;
        }
        
        this.createTimeline(itemsData, groupsData, timeWindow);
    }

    zoomFit() {
        if (this.timeline) {
            this.timeline.fit();
        }
    }
}

SlowRequestTimeline.template = 'performance_audit.SlowRequestTimeline';

registry.category("actions").add("performance_audit.slow_request_timeline", SlowRequestTimeline);