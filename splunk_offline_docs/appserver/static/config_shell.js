
require([
    'jquery',
    'splunkjs/mvc',
    'splunkjs/mvc/simplexml/ready!',
    'splunk.util'
], function ($, mvc, _, utils) {
    'use strict';

    var BUILD = '20260703j';
    var service = mvc.createService({ owner: 'nobody', app: 'splunk_offline_docs' });
    var pollTimer = null;
    var $root = null;

    function escapeHtml(text) {
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function parsePayload(response) {
        var data = response && response.data;
        if (data == null) return {};
        if (typeof data === 'string') {
            try { return JSON.parse(data); } catch (_e) { return { raw: data }; }
        }
        if (data.payload != null) {
            if (typeof data.payload === 'string') {
                try { return JSON.parse(data.payload); } catch (_e2) { return { raw: data.payload }; }
            }
            return data.payload;
        }
        return data;
    }

    function serviceError(err, response) {
        if (err) {
            return (err.message || String(err));
        }
        if (response && response.messages && response.messages.length) {
            return response.messages.map(function (m) { return m.text; }).join('; ');
        }
        if (response && response.data && response.data.messages) {
            return response.data.messages.map(function (m) { return m.text; }).join('; ');
        }
        return 'Request failed';
    }

    function apiRequest(method, member, body) {
        var path = 'offline_docs/' + member;
        var opts = { output_mode: 'json' };
        return $.Deferred(function (dfd) {
            var done = function (err, response) {
                if (err || (response && response.messages && response.messages.length)) {
                    dfd.reject(new Error(serviceError(err, response)));
                    return;
                }
                try {
                    dfd.resolve(parsePayload(response));
                } catch (exc) {
                    dfd.reject(exc);
                }
            };
            if (method === 'GET') {
                service.get(path, opts, done);
            } else {
                service.post(path, body || {}, done);
            }
        }).promise();
    }

    function fmtTime(iso) {
        if (!iso) return '—';
        try { return new Date(iso).toLocaleString(); } catch (_e) { return iso; }
    }

    function badge(text, kind) {
        return '<span class="od-badge od-badge-' + kind + '">' + text + '</span>';
    }

    function renderProductRows(products) {
        if (!products || !products.length) {
            return '<p class="od-muted">No product results yet. Run a check to compare against help.splunk.com.</p>';
        }
        return '<table class="od-table"><thead><tr><th>Product</th><th>Status</th><th>Details</th></tr></thead><tbody>'
            + products.map(function (p) {
                var status = badge('Up to date', 'ok');
                var details = [];
                if (p.error) {
                    status = badge('Error', 'err');
                    details.push(escapeHtml(p.error));
                } else {
                    if (p.new_versions && p.new_versions.length) {
                        status = badge('Updates available', 'warn');
                        details.push('New versions: ' + escapeHtml(p.new_versions.join(', ')));
                    }
                    if (p.missing_count > 0) {
                        status = badge('Updates available', 'warn');
                        details.push(p.missing_count + ' new topic(s)');
                        if (p.missing_sample && p.missing_sample.length) {
                            details.push('<code>' + escapeHtml(p.missing_sample.slice(0, 3).join(', ')) + '</code>');
                        }
                    }
                    if (p.nav_drift && !p.missing_count) {
                        status = badge('Nav drift', 'warn');
                        details.push('Navigation order differs from help.splunk.com');
                    }
                }
                return '<tr><td><strong>' + escapeHtml(p.title || p.id) + '</strong></td><td>'
                    + status + '</td><td>' + (details.join('<br>') || '—') + '</td></tr>';
            }).join('')
            + '</tbody></table>';
    }

    function renderStatus(data) {
        var bundle = data.bundle || {};
        var check = data.check || {};
        var job = data.job || {};
        var settings = data.settings || {};
        var jobStatus = job.status || 'idle';
        var jobBadge = badge('Idle', 'ok');
        if (jobStatus === 'running') jobBadge = badge('Running', 'warn');
        if (jobStatus === 'success') jobBadge = badge('Completed', 'ok');
        if (jobStatus === 'error') jobBadge = badge('Failed', 'err');
        var updatesBadge = check.updates_available
            ? badge('Updates available', 'warn')
            : badge('Up to date', 'ok');
        var logHtml = (job.log_tail || []).length
            ? '<pre class="od-log">' + escapeHtml((job.log_tail || []).join('\n')) + '</pre>'
            : '<p class="od-muted">No update log yet.</p>';

        return ''
            + '<div class="od-config">'
            + '<header class="od-header"><h1>Documentation Configuration</h1>'
            + '<p class="od-lead">Check help.splunk.com for new versions and topics, then scrape updates into the offline bundle.</p></header>'
            + '<div class="od-grid">'
            + '<section class="od-card"><h2>Bundle</h2>'
            + '<dl class="od-dl"><dt>App version</dt><dd>' + escapeHtml(bundle.app_version || '—') + '</dd>'
            + '<dt>Topics stored</dt><dd>' + (bundle.topic_count || 0).toLocaleString() + '</dd>'
            + '<dt>Last sync</dt><dd>' + fmtTime((bundle.meta || {}).last_sync_at) + '</dd></dl></section>'
            + '<section class="od-card"><h2>Update check</h2><p>' + updatesBadge + '</p>'
            + '<dl class="od-dl"><dt>Last checked</dt><dd>' + fmtTime(check.checked_at) + '</dd>'
            + '<dt>Daily check</dt><dd>' + (settings.daily_check_enabled ? 'Enabled (every 24h)' : 'Disabled') + '</dd></dl>'
            + '<div class="od-actions"><button type="button" class="od-btn" id="od-check-btn">Check now</button></div></section>'
            + '<section class="od-card"><h2>Scrape / update</h2><p>' + jobBadge + '</p>'
            + '<dl class="od-dl"><dt>Started</dt><dd>' + fmtTime(job.started_at) + '</dd>'
            + '<dt>Finished</dt><dd>' + fmtTime(job.finished_at) + '</dd>'
            + (job.error ? '<dt>Error</dt><dd class="od-error">' + escapeHtml(job.error) + '</dd>' : '')
            + '</dl><div class="od-actions">'
            + '<button type="button" class="od-btn od-btn-primary" id="od-update-btn">Update now (incremental)</button>'
            + '<button type="button" class="od-btn" id="od-update-full-btn">Full refresh</button>'
            + '</div></section></div>'
            + '<section class="od-card od-wide"><h2>Products</h2>' + renderProductRows(check.products) + '</section>'
            + '<section class="od-card od-wide"><h2>Update log</h2>' + logHtml + '</section>'
            + '<p class="od-footnote">Scraper source: <code>' + escapeHtml(settings.scraper_root || '—') + '</code></p>'
            + '</div>';
    }

    function mount(html) {
        $root.html(html);
    }

    function showError(err) {
        var msg = (err && err.message) ? err.message : String(err);
        mount('<div class="od-config"><p class="od-error">Failed to load configuration:</p><pre class="od-log">'
            + escapeHtml(msg) + '</pre></div>');
    }

    function setBusy(busy) {
        ['od-check-btn', 'od-update-btn', 'od-update-full-btn'].forEach(function (id) {
            var el = document.getElementById(id);
            if (el) el.disabled = busy;
        });
    }

    function bindActions() {
        $('#od-check-btn').off('click').on('click', function () {
            setBusy(true);
            apiRequest('POST', 'check').then(refresh).catch(showError).always(function () { setBusy(false); });
        });
        $('#od-update-btn').off('click').on('click', function () {
            if (!window.confirm('Start incremental scrape from help.splunk.com? This may take several minutes.')) return;
            setBusy(true);
            apiRequest('POST', 'update', { mode: 'incremental' }).then(function () {
                startPolling();
                return refresh();
            }).catch(showError).always(function () { setBusy(false); });
        });
        $('#od-update-full-btn').off('click').on('click', function () {
            if (!window.confirm('Start full navigation refresh and scrape? This takes longer but picks up new product versions.')) return;
            setBusy(true);
            apiRequest('POST', 'update', { mode: 'full' }).then(function () {
                startPolling();
                return refresh();
            }).catch(showError).always(function () { setBusy(false); });
        });
    }

    function refresh() {
        return apiRequest('GET', 'status').then(function (data) {
            mount(renderStatus(data));
            bindActions();
            if (data.job && data.job.status === 'running') startPolling();
            return data;
        });
    }

    function startPolling() {
        if (pollTimer) return;
        pollTimer = window.setInterval(function () {
            refresh().then(function (data) {
                if (!data || !data.job || data.job.status !== 'running') {
                    window.clearInterval(pollTimer);
                    pollTimer = null;
                }
            }).fail(function () {
                window.clearInterval(pollTimer);
                pollTimer = null;
            });
        }, 4000);
    }

    function init() {
        var $target = $('.dashboard-body').first();
        if (!$target.length) $target = $('.main-section-body').first();
        if (!$target.length) $target = $('.dashboard-content').first();

        $target.empty().css({ padding: 0, margin: 0, minHeight: 'calc(100vh - 120px)' });
        $root = $('<div class="offline-docs-config-root"/>').appendTo($target);
        $('<link>', {
            rel: 'stylesheet',
            href: utils.make_url('/static/app/splunk_offline_docs/css/config.css?v=' + BUILD)
        }).appendTo('head');

        mount('<p class="od-muted od-config">Loading configuration…</p>');
        refresh().fail(showError);
    }

    init();
});
