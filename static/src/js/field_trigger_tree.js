/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, useState, useRef, onPatched } from "@odoo/owl";

class FieldTriggerTree extends Component {
    setup() {
        this.state = useState({
            loading: true,
            error: null,
            treeData: null,
            dataReady: false,
        });

        this.containerRef = useRef("container");
        this.rpc = useService("rpc");
        this.actionService = useService("action");

        onMounted(() => {
            console.debug("Component mounted");

            const { model, field_name } = this.props.action.params;
            const title = `Trigger Tree: ${model}.${field_name}`;
            
            if (!window.echarts) {
                console.debug("Loading ECharts library");

                const script = document.createElement('script');
                script.src = "https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js";
                script.onload = () => {
                    console.debug("ECharts loaded successfully");
                    this.loadTriggerTree();
                };
                script.onerror = (e) => {
                    console.error("Failed to load ECharts", e);
                    this.state.error = "Failed to load ECharts library";
                    this.state.loading = false;
                };
                document.head.appendChild(script);
            } else {
                console.debug("ECharts already loaded");
                this.loadTriggerTree();
            }
        });

        onPatched(() => {
            console.debug("Component patched, dataReady:", this.state.dataReady);
            if (this.state.dataReady && !this._chart) {
                console.debug("Rendering chart after patch");
                this.renderChart();
            }
        });
    }

    async loadTriggerTree() {
        console.debug("Loading trigger tree data");

        const { model, field_name } = this.props.action.params;
        console.debug("Params:", model, field_name);

        try {
            console.debug("Making RPC call");
            const result = await this.rpc("/performance_audit/get_field_trigger_tree", {
                model: model,
                field_name: field_name,
            });

            console.debug("RPC result:", result);

            if (result.error) {
                console.error("Error in result:", result.error);
                this.state.error = result.error;
                this.state.loading = false;
            } else {
                this.state.treeData = result;
                console.debug("Tree data received:", result);

                this.state.loading = false;
                this.state.dataReady = true;
            }
        } catch (error) {
            console.error("RPC error:", error);
            this.state.error = error.toString();
            this.state.loading = false;
        }
    }

    renderChart() {
        console.debug("Rendering chart");

        if (!this.state.treeData) {
            console.error("No tree data available");
            return;
        }

        if (!this.containerRef.el) {
            console.error("Container element not found");
            return;
        }

        const container = this.containerRef.el;

        try {
            console.debug("Initializing ECharts");
            const chart = window.echarts.init(container);

            const data = this.prepareChartData(this.state.treeData);
            console.debug("Prepared chart data:", data);

            // Set chart options
            const option = {
                tooltip: {
                    trigger: 'item',
                    formatter: (params) => {
                        const { data } = params;
                        return `<strong>${data.name}</strong><br/>Model: ${data.model}`;
                    }
                },
                legend: {
                    data: [
                        { name: 'Root Field', icon: 'circle' },
                        { name: 'Relational Field', icon: 'circle' },
                        { name: 'Dependent Field', icon: 'circle' }
                    ],
                    bottom: 0
                },
                series: [{
                    type: 'tree',
                    data: [data],
                    layout: 'orthogonal',
                    orient: 'LR',
                    initialTreeDepth: 3,
                    roam: true,
                    label: {
                        position: 'left',
                        verticalAlign: 'middle',
                        align: 'right'
                    },
                    leaves: {
                        label: {
                            position: 'right',
                            verticalAlign: 'middle',
                            align: 'left'
                        }
                    },
                    expandAndCollapse: true,
                    animationDuration: 550,
                    animationDurationUpdate: 750
                }]
            };

            console.debug("Setting chart options");
            chart.setOption(option);
            console.debug("Chart rendered successfully");

            // Handle resize
            const resizeObserver = new ResizeObserver(() => chart.resize());
            resizeObserver.observe(container);

            this._resizeObserver = resizeObserver;
            this._chart = chart;
        } catch (e) {
            console.error("Error rendering chart:", e);
            this.state.error = "Error rendering chart: " + e.toString();
        }
    }

    prepareChartData(node) {
        // Root node
        const result = {
            name: `${node.name}`,
            value: node.id,
            model: node.model,
            itemStyle: { color: '#e74c3c' },
            children: []
        };

        if (node.dependents && node.dependents.length > 0) {
            node.dependents.forEach(dep => {
                result.children.push({
                    name: `${dep.name}`,
                    value: dep.id,
                    model: dep.model,
                    itemStyle: { color: '#3498db' }
                });
            });
        }

        // Add related fields
        if (node.children && node.children.length > 0) {
            node.children.forEach(child => {
                result.children.push(this.prepareChartData(child));
            });
        }

        return result;
    }

    willUnmount() {
        console.debug("Component unmounting");
        if (this._resizeObserver) {
            this._resizeObserver.disconnect();
        }
        if (this._chart) {
            this._chart.dispose();
        }
    }

    goToDashboard() {
        this.actionService.doAction("performance_audit.action_performance_audit_dashboard");
    }

    openFieldTriggerWizard() {
        this.actionService.doAction({
            type: 'ir.actions.act_window',
            res_model: 'field.trigger.tree.wizard',
            view_mode: 'form',
            views: [[false, 'form']],
            target: 'new',
            name: 'Field Trigger Tree'
        });
    }
}

FieldTriggerTree.template = "performance_audit.FieldTriggerTree";
registry.category("actions").add("field_trigger_tree", FieldTriggerTree); 