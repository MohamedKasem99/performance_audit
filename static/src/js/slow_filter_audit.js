/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

class SlowFilterAudit extends Component {
    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");

        this.state = useState({
            progress: 0,
            total: 0,
            done: 0
        });

        // Start the audit automatically
        this.runAudit();
    }

    async runAudit() {

        // ensure order of params
        const { batch_size, offset, slow_filters_threshold } = this.props.action.params;
        let currentOffset = offset;
        let hasMore = true;

        try {
            while (hasMore) {
                const result = await this.orm.call(
                    'pa.slow.filter',
                    'audit_filters_batched',
                [[]],
                { 
                    batch_size: batch_size,
                    offset: currentOffset,
                    threshold: slow_filters_threshold
                });

                hasMore = result.has_more;
                currentOffset += batch_size;

                // Update progress state
                this.state.total = result.total;
                this.state.done = result.done;
                this.state.progress = Math.round((result.done / result.total) * 100);

                // Small delay between batches
                await new Promise(resolve => setTimeout(resolve, 100));
            }

            this.notification.add(
                _t("Slow filter audit completed successfully!"),
                { type: "success" }
            );

        } catch (error) {
            this.notification.add(
                _t("Error running slow filter audit"),
                { type: "danger" }
            );
            console.error(error);
        }
        // Navigate to the slow filters list view
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: _t('Slow Filters'),
            res_model: 'pa.slow.filter',
            views: [[false, 'list'], [false, 'form']],
            view_mode: 'list,form',
        }, {
            clearBreadcrumbs: true
        });

    }
}

SlowFilterAudit.template = 'performance_audit.SlowFilterAudit';

registry.category("actions").add("pa_slow_filter_audit", SlowFilterAudit);
