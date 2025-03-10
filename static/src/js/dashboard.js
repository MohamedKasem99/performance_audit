/** @odoo-module **/

import { Component, onMounted, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class Dashboard extends Component {
    setup() {
        this.state = useState({
            loading: false,
            slow_filter_count: 0,
            slow_request_count: 0,
            slow_cron_count: 0,
            biggest_table_size_human: '0 Bytes',
            biggest_table_name: '',
        });
        
        this.rpc = useService("rpc");
        this.action = useService("action");
        
        this.loadDashboardData();
    }

    async loadDashboardData() {
        try {
            this.state.loading = true;
            const result = await this.rpc(
                '/performance_audit/dashboard_data',
                {}
            );
            
            // Update state with fetched data
            if (result) {
                this.state.slow_filter_count = result.slow_filter_count || 0;
                this.state.slow_request_count = result.slow_request_count || 0;
                this.state.slow_cron_count = result.slow_cron_count || 0;
                this.state.biggest_table_size_human = result.biggest_table_size_human || '0 Bytes';
                this.state.biggest_table_name = result.biggest_table_name || '';
            }
        } catch (error) {
            console.error('Failed to load dashboard data:', error);
        } finally {
            this.state.loading = false;
        }
    }

    async openAuditWizard() {
        await this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Run Performance Audit',
            res_model: 'performance.audit.wizard',
            view_mode: 'form',
            views: [[false, 'form']],
            target: 'new',
            context: {},
        });
    }

    openFieldTriggerTree() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'field.trigger.tree.wizard',
            view_mode: 'form',
            views: [[false, 'form']],
            target: 'new',
            name: 'Field Trigger Tree'
        });
    }
}

Dashboard.template = 'performance_audit.Dashboard';

// Register the component
registry.category("actions").add("performance_audit.dashboard", Dashboard);
