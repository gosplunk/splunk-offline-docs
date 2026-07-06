require([
    'jquery',
    'splunkjs/mvc/simplexml/ready!',
    'splunk.util'
], function ($, _, utils) {
    'use strict';

    var BUILD = '20260706b';
    var APP = 'splunk_offline_docs';
    var pollTimer = null;
    var $root = null;

    function escapeHtml(text) {
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function apiUrl(member) {
        return utils.make_url(
            '/splunkd/__raw/servicesNS/nobody/' + APP + '/offline_docs/' + member
            + '?output_mode=json&_=' + Date.now()
        );
    }

    function unwrapPayload(data) {
        if (!data) return {};
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

    function ajaxError(xhr, status) {
        var msg = status === 'timeout' ? 'Request timed out after 60s' : (xhr.statusText || 'Request failed');
        var text = xhr && xhr.responseText;
        if (text) {
            try {
                var parsed = JSON.parse(text);
                if (parsed.messages && parsed.messages.length) {
                    msg = parsed.messages.map(function (m) { return m.text; }).join('; ');
                } else if (parsed.error) {
                    msg = parsed.error;
                } else if (parsed.payload) {
                    msg = typeof parsed.payload === 'string' ? parsed.payload : JSON.stringify(parsed.payload);
                }
            } catch (_e) {
                msg = text.slice(0, 500);
            }
        }
        return new Error(msg);
    }

    function formKey() {
        if (utils.getFormKey) {
            try { return utils.getFormKey() || ''; } catch (_e) { /* ignore */ }
        }
        var $meta = $('meta[name="splunk-form-key"]');
        return $meta.length ? ($meta.attr('content') || '') : '';
    }

    function requestHeaders(method, body, useForm) {
        var headers = { 'X-Requested-With': 'XMLHttpRequest' };
        if (body && !useForm) headers['Content-Type'] = 'application/json';
        if (method !== 'GET') {
            var fk = formKey();
            if (fk) headers['X-Splunk-Form-Key'] = fk;
        }
        return headers;
    }

    function apiRequest(method, member, body) {
        var timeoutMs = (method === 'POST' && member === 'check') ? 600000 : 120000;
        var useForm = method === 'POST' && !!body;
        var ajaxOpts = {
            url: apiUrl(member),
            type: method,
            dataType: 'json',
            timeout: timeoutMs,
            headers: requestHeaders(method, body, useForm),
        };
        if (useForm) {
            ajaxOpts.data = { payload: JSON.stringify(body) };
            ajaxOpts.contentType = 'application/x-www-form-urlencoded; charset=UTF-8';
        }
        return $.ajax(ajaxOpts).then(function (data) {
            return unwrapPayload(data);
        }, function (xhr, status) {
            return $.Deferred().reject(ajaxError(xhr, status)).promise();
        });
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

    function renderVersionList(versions) {
        if (!versions || !versions.length) {
            return '<span class="od-muted">—</span>';
        }
        var shown = versions.slice(0, 8);
        var html = shown.map(function (v) {
            return '<code class="od-version-tag">' + escapeHtml(v) + '</code>';
        }).join(' ');
        if (versions.length > shown.length) {
            html += ' <span class="od-muted">+' + (versions.length - shown.length) + ' more</span>';
        }
        return html;
    }

    function renderScrapeProductRows(products) {
        if (!products || !products.length) {
            return '<p class="od-muted">No scraped products found in nav.json.</p>';
        }
        return '<table class="od-table"><thead><tr>'
            + '<th>Product</th><th>Latest</th><th>Versions</th><th>Topics</th><th>Nav paths</th>'
            + '</tr></thead><tbody>'
            + products.map(function (p) {
                return '<tr><td><strong>' + escapeHtml(p.title || p.id) + '</strong></td>'
                    + '<td>' + escapeHtml(p.latest_version || '—') + '</td>'
                    + '<td class="od-version-cell">' + renderVersionList(p.versions) + '</td>'
                    + '<td>' + (p.topic_count || 0).toLocaleString() + '</td>'
                    + '<td>' + (p.nav_paths || p.nav_branches || 0).toLocaleString() + '</td></tr>';
            }).join('')
            + '</tbody></table>';
    }

    function renderDailyCheckToggle(enabled) {
        var onClass = enabled ? ' od-toggle-on' : '';
        var aria = enabled ? 'true' : 'false';
        var status = enabled
            ? 'On — Splunk will check help.splunk.com once every 24 hours.'
            : 'Off — recommended for air-gapped hosts (no outbound HTTPS).';
        return ''
            + '<section class="od-card od-wide od-scheduled-card">'
            + '<h2>Daily auto-check</h2>'
            + '<div class="od-scheduled-row">'
            + '<button type="button" class="od-toggle-btn' + onClass + '" id="od-daily-check-toggle" role="switch" aria-checked="' + aria + '">'
            + '<span class="od-toggle-track"><span class="od-toggle-thumb"></span></span>'
            + '</button>'
            + '<div class="od-scheduled-copy">'
            + '<strong>Auto-check daily for documentation updates</strong>'
            + '<p class="od-toggle-hint od-muted">' + escapeHtml(status) + '</p>'
            + '</div></div></section>';
    }

    function renderScrapeSection(scrape) {
        if (!scrape) {
            return '<section class="od-card od-wide"><h2>Scrape bundle</h2><p class="od-muted">No scrape metrics available.</p></section>';
        }
        var disk = scrape.disk || {};
        var files = scrape.manifest_files || {};
        var ts = scrape.timestamps || {};
        return ''
            + '<section class="od-card od-wide"><h2>Scrape bundle</h2>'
            + '<div class="od-stat-grid">'
            + '<div class="od-stat"><span class="od-stat-label">Total on disk</span>'
            + '<span class="od-stat-value">' + escapeHtml(disk.total_human || '—') + '</span></div>'
            + '<div class="od-stat"><span class="od-stat-label">Topic HTML</span>'
            + '<span class="od-stat-value">' + escapeHtml(disk.topics_human || '—') + '</span></div>'
            + '<div class="od-stat"><span class="od-stat-label">Manifests</span>'
            + '<span class="od-stat-value">' + escapeHtml(disk.manifest_human || '—') + '</span></div>'
            + '<div class="od-stat"><span class="od-stat-label">Nav cache</span>'
            + '<span class="od-stat-value">' + escapeHtml(disk.nav_cache_human || '—') + '</span></div>'
            + '</div>'
            + '<dl class="od-dl od-dl-wide"><dt>Indexed topics</dt><dd>'
            + (scrape.topic_count_indexed || 0).toLocaleString() + '</dd>'
            + '<dt>HTML files</dt><dd>' + (scrape.topic_count_files || 0).toLocaleString() + '</dd>'
            + '<dt>Search index</dt><dd>' + escapeHtml(files.search_index_human || '—') + '</dd>'
            + '<dt>Link index</dt><dd>' + escapeHtml(files.link_index_human || '—') + '</dd>'
            + '<dt>Source</dt><dd>' + escapeHtml(ts.source || 'help.splunk.com') + '</dd>'
            + '<dt>Built</dt><dd>' + fmtTime(ts.built_at) + '</dd>'
            + '<dt>Last updated</dt><dd>' + fmtTime(ts.updated_at) + '</dd>'
            + '<dt>Last sync</dt><dd>' + fmtTime(ts.last_sync_at) + '</dd>'
            + '<dt>Nav rebuilt</dt><dd>' + fmtTime(ts.nav_rebuilt_at) + '</dd>'
            + '<dt>Repaired</dt><dd>' + fmtTime(ts.repaired_at) + '</dd></dl>'
            + '<h3 class="od-subhead">Products &amp; versions scraped</h3>'
            + renderScrapeProductRows(scrape.products)
            + '</section>';
    }

    function renderStatus(data) {
        var bundle = data.bundle || {};
        var scrape = bundle.scrape || {};
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
            + renderDailyCheckToggle(!!settings.daily_check_enabled)
            + renderScrapeSection(scrape)
            + '<div class="od-grid">'
            + '<section class="od-card"><h2>Bundle</h2>'
            + '<dl class="od-dl"><dt>App version</dt><dd>' + escapeHtml(bundle.app_version || '—') + '</dd>'
            + '<dt>Topics stored</dt><dd>' + (bundle.topic_count || 0).toLocaleString() + '</dd>'
            + '<dt>Bundle size</dt><dd>' + escapeHtml((scrape.disk || {}).total_human || '—') + '</dd>'
            + '<dt>Last sync</dt><dd>' + fmtTime((scrape.timestamps || {}).last_sync_at || (bundle.meta || {}).updated_at) + '</dd></dl></section>'
            + '<section class="od-card"><h2>Update check</h2><p>' + updatesBadge + '</p>'
            + (check.error ? '<p class="od-error">' + escapeHtml(check.error) + '</p>' : '')
            + '<dl class="od-dl"><dt>Last checked</dt><dd>' + fmtTime(check.checked_at) + '</dd></dl>'
            + '<div class="od-actions"><button type="button" class="od-btn" id="od-check-btn">Check now</button></div></section>'
            + '<section class="od-card"><h2>Scrape / update</h2><p>' + jobBadge + '</p>'
            + '<dl class="od-dl"><dt>Started</dt><dd>' + fmtTime(job.started_at) + '</dd>'
            + '<dt>Finished</dt><dd>' + fmtTime(job.finished_at) + '</dd>'
            + (job.error ? '<dt>Error</dt><dd class="od-error">' + escapeHtml(job.error) + '</dd>' : '')
            + '</dl><div class="od-actions">'
            + '<button type="button" class="od-btn od-btn-primary" id="od-update-btn">Update now (incremental)</button>'
            + '<button type="button" class="od-btn" id="od-update-full-btn">Full refresh</button>'
            + '</div></section></div>'
            + '<section class="od-card od-wide"><h2>Update check — products</h2>' + renderProductRows(check.products) + '</section>'
            + '<section class="od-card od-wide"><h2>Update log</h2>' + logHtml + '</section>'
            + '<p class="od-footnote">Scraper source: <code>' + escapeHtml(settings.scraper_root || '—') + '</code></p>'
            + '</div>';
    }

    function mount(html) {
        if ($root && $root.length) {
            $root.html(html);
        }
    }

    function showError(err) {
        var msg = (err && err.message) ? err.message : String(err);
        mount('<div class="od-config"><p class="od-error">Failed to load configuration:</p><pre class="od-log">'
            + escapeHtml(msg) + '</pre></div>');
    }

    function setBusy(busy) {
        ['od-check-btn', 'od-update-btn', 'od-update-full-btn', 'od-daily-check-toggle'].forEach(function (id) {
            var el = document.getElementById(id);
            if (el) el.disabled = busy;
        });
    }

    function bindActions() {
        $('#od-check-btn').off('click').on('click', function () {
            setBusy(true);
            apiRequest('POST', 'check').then(refresh).fail(showError).always(function () { setBusy(false); });
        });
        $('#od-daily-check-toggle').off('click').on('click', function () {
            var $btn = $(this);
            if ($btn.prop('disabled')) return;
            var enabled = $btn.attr('aria-checked') !== 'true';
            setBusy(true);
            apiRequest('POST', 'settings', { daily_check_enabled: enabled })
                .then(refresh)
                .fail(showError)
                .always(function () { setBusy(false); });
        });
        $('#od-update-btn').off('click').on('click', function () {
            if (!window.confirm('Start incremental scrape from help.splunk.com? This may take several minutes.')) return;
            setBusy(true);
            apiRequest('POST', 'update', { mode: 'incremental' }).then(function () {
                startPolling();
                return refresh();
            }).fail(showError).always(function () { setBusy(false); });
        });
        $('#od-update-full-btn').off('click').on('click', function () {
            if (!window.confirm('Start full navigation refresh and scrape? This takes longer but picks up new product versions.')) return;
            setBusy(true);
            apiRequest('POST', 'update', { mode: 'full' }).then(function () {
                startPolling();
                return refresh();
            }).fail(showError).always(function () { setBusy(false); });
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

    function ensureCss() {
        if ($('#offline-docs-config-css').length) return;
        $('<link>', {
            id: 'offline-docs-config-css',
            rel: 'stylesheet',
            href: utils.make_url('/static/app/' + APP + '/css/config.css?v=' + BUILD)
        }).appendTo('head');
    }

    function findRoot() {
        var $target = $('.dashboard-body').first();
        if (!$target.length) $target = $('.main-section-body').first();
        if (!$target.length) $target = $('.dashboard-content').first();
        $target.empty().css({ padding: 0, margin: 0, minHeight: 'calc(100vh - 120px)' });
        return $('<div id="offline-docs-config-root" class="offline-docs-config-root"/>').appendTo($target);
    }

    function init() {
        ensureCss();
        $root = findRoot();
        mount('<p class="od-muted od-config">Loading configuration…</p>');
        refresh().fail(showError);
    }

    try {
        init();
    } catch (err) {
        showError(err);
    }
});
