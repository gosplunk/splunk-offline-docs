(function () {
  'use strict';

  var APP = 'splunk_offline_docs';
  var ENDPOINT = 'offline_docs';
  var pollTimer = null;

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function apiBase() {
    var parts = window.location.pathname.split('/');
    var idx = parts.indexOf('static');
    var prefix = idx > 0 ? parts.slice(0, idx).join('/') : '/en-US';
    return prefix + '/splunkd/__raw/servicesNS/nobody/' + APP + '/' + ENDPOINT;
  }

  function formKey() {
    try {
      var m = window.parent.document.querySelector('meta[name="splunk-form-key"]');
      if (m) return m.getAttribute('content') || '';
    } catch (_e) { /* cross-origin */ }
    var local = document.querySelector('meta[name="splunk-form-key"]');
    return local ? local.getAttribute('content') || '' : '';
  }

  function unwrapPayload(data) {
    if (!data) return {};
    if (typeof data === 'string') {
      try { return JSON.parse(data); } catch (_e) { return { raw: data }; }
    }
    if (data.payload) return unwrapPayload(data.payload);
    return data;
  }

  function apiRequest(method, member, body) {
    var url = apiBase() + '/' + member + '?output_mode=json';
    var headers = {
      'Accept': 'application/json',
      'X-Requested-With': 'XMLHttpRequest',
    };
    var fk = formKey();
    if (fk && method !== 'GET') headers['X-Splunk-Form-Key'] = fk;
    if (body) headers['Content-Type'] = 'application/json';

    return fetch(url, {
      method: method,
      credentials: 'same-origin',
      headers: headers,
      body: body ? JSON.stringify(body) : undefined,
    }).then(function (res) {
      return res.text().then(function (text) {
        var parsed = {};
        try { parsed = text ? JSON.parse(text) : {}; } catch (_e) { parsed = { raw: text }; }
        if (!res.ok) {
          var msg = parsed.error || parsed.payload || text || res.statusText;
          throw new Error(msg);
        }
        return unwrapPayload(parsed);
      });
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
      + (bundle.ready === false
        ? '<p class="od-error"><strong>Documentation bundle missing.</strong> '
          + escapeHtml(bundle.ready_hint || 'Install splunk_offline_docs_full.tgz.') + '</p>'
        : '')
      + '<dl class="od-dl"><dt>App version</dt><dd>' + escapeHtml(bundle.app_version || '—') + '</dd>'
      + '<dt>Topics stored</dt><dd>' + (bundle.topic_count || 0).toLocaleString() + '</dd>'
      + '<dt>Last sync</dt><dd>' + fmtTime((bundle.meta || {}).last_sync_at) + '</dd></dl></section>'
      + '<section class="od-card"><h2>Update check</h2><p>' + updatesBadge + '</p>'
      + (check.error ? '<p class="od-error">' + escapeHtml(check.error) + '</p>' : '')
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
    document.getElementById('app-root').innerHTML = html;
  }

  function setBusy(busy) {
    ['od-check-btn', 'od-update-btn', 'od-update-full-btn'].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.disabled = busy;
    });
  }

  function showError(err) {
    var msg = (err && err.message) ? err.message : String(err);
    mount('<div class="od-config"><p class="od-error">Failed to load configuration:</p><pre class="od-log">'
      + escapeHtml(msg) + '</pre></div>');
  }

  function bindActions() {
    var checkBtn = document.getElementById('od-check-btn');
    var updateBtn = document.getElementById('od-update-btn');
    var fullBtn = document.getElementById('od-update-full-btn');
    if (checkBtn) {
      checkBtn.onclick = function () {
        setBusy(true);
        apiRequest('POST', 'check').then(refresh).catch(showError).finally(function () { setBusy(false); });
      };
    }
    if (updateBtn) {
      updateBtn.onclick = function () {
        if (!window.confirm('Start incremental scrape from help.splunk.com? This may take several minutes.')) return;
        setBusy(true);
        apiRequest('POST', 'update', { mode: 'incremental' }).then(function () {
          startPolling();
          return refresh();
        }).catch(showError).finally(function () { setBusy(false); });
      };
    }
    if (fullBtn) {
      fullBtn.onclick = function () {
        if (!window.confirm('Start full navigation refresh and scrape? This takes longer but picks up new product versions.')) return;
        setBusy(true);
        apiRequest('POST', 'update', { mode: 'full' }).then(function () {
          startPolling();
          return refresh();
        }).catch(showError).finally(function () { setBusy(false); });
      };
    }
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
      }).catch(function () {
        window.clearInterval(pollTimer);
        pollTimer = null;
      });
    }, 4000);
  }

  refresh().catch(showError);
}());
