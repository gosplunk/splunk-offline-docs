
window.OfflineLinkResolver = {
  linkIndex: null,
  currentPath: '',
  currentVersion: '',
  EXTERNAL_TIP: "Linking externally, won't work in airgapped environment",
  MIN_SUFFIX_LEN: 12,

  async load(indexUrl) {
    const r = await fetch(indexUrl, { cache: 'no-store' });
    this.setIndex(await r.json());
  },

  setIndex(data) {
    this.linkIndex = data;
    this.tailCandidates = {};
    const paths = data?.paths || {};
    Object.keys(paths).forEach((path) => {
      if (path.startsWith('en/')) return;
      const tail = path.split('/').pop();
      if (!tail) return;
      if (!this.tailCandidates[tail]) this.tailCandidates[tail] = [];
      this.tailCandidates[tail].push([path, paths[path]]);
    });
  },

  originalHref(el) {
    return el.dataset.offlineHref || el.getAttribute('href') || '';
  },

  neutralize(el) {
    if (el.dataset.topic && (el.getAttribute('href') || '') === '#') {
      return el.dataset.offlineHref || '#';
    }
    const href = el.getAttribute('href') || '';
    if (href && href !== '#' && !el.dataset.offlineHref) {
      el.dataset.offlineHref = href;
    }
    el.setAttribute('href', '#');
    el.removeAttribute('target');
    el.removeAttribute('rel');
    return el.dataset.offlineHref || href;
  },

  parseVersion(path) {
    const parts = (path || '').split('/');
    for (let i = 0; i < parts.length; i += 1) {
      if (/^\d+\.\d+(?:\.\d+)?$/.test(parts[i])) return parts[i];
    }
    return null;
  },

  normalizePath(href) {
    if (!href) return null;
    let path = href.trim();
    let anchor = '';
    const hashIdx = path.indexOf('#');
    if (hashIdx >= 0) {
      anchor = path.slice(hashIdx + 1);
      path = path.slice(0, hashIdx);
    }

    try {
      if (/^https?:\/\//i.test(path)) {
        const u = new URL(path);
        if (!/help\.splunk\.com/i.test(u.hostname)) {
          return { external: true, anchor };
        }
        path = u.pathname;
      }
    } catch (_err) {
      return null;
    }

    if (path.startsWith('/en/')) path = path.slice(4);
    else if (path.startsWith('en/')) path = path.slice(3);
    else if (path.startsWith('/')) path = path.slice(1);

    path = path.split('?')[0].replace(/\/$/, '');
    if (!path) return { external: false, path: null, anchor };
    if (path.startsWith('db/organizations/') || path.startsWith('services')
      || path.startsWith('servicesNS/') || path.startsWith('static/')) {
      return { external: false, path: null, anchor, blocked: true };
    }
    return { external: false, path, anchor };
  },

  pathCandidates(path) {
    const out = new Set();
    if (!path) return [];
    const add = (p) => {
      if (p) out.add(p.replace(/\/$/, ''));
    };
    add(path);
    add(path.replace(/\.dita$/i, ''));
    const parts = path.split('/');
    for (let i = 0; i < parts.length; i += 1) {
      if (/^\d+\.\d+(?:\.\d+)?$/.test(parts[i])) {
        add([...parts.slice(0, i), ...parts.slice(i + 1)].join('/'));
      }
    }
    if (parts.length > 1) add(parts[parts.length - 1]);
    return [...out];
  },

  topicIdForPath(path) {
    const paths = this.linkIndex?.paths || {};
    const suffixes = this.linkIndex?.suffixes || {};
    for (const candidate of this.pathCandidates(path)) {
      if (paths[candidate]) return paths[candidate];
      if (paths[`en/${candidate}`]) return paths[`en/${candidate}`];
    }

    const linkVer = this.parseVersion(path);
    const parts = path.split('/');
    let bestTid = null;
    let bestScore = -1;
    for (let i = 1; i < parts.length; i += 1) {
      const suf = parts.slice(i).join('/');
      if (suf.length < this.MIN_SUFFIX_LEN) continue;
      const tid = suffixes[suf];
      if (!tid) continue;
      let score = suf.length;
      if (linkVer) {
        Object.keys(paths).some((indexedPath) => {
          if (paths[indexedPath] === tid && indexedPath.endsWith(suf)) {
            if (this.parseVersion(indexedPath) === linkVer) score += 1000;
            return true;
          }
          return false;
        });
      }
      if (score > bestScore) {
        bestScore = score;
        bestTid = tid;
      }
    }
    return bestTid;
  },

  slugifyLabel(text) {
    return (text || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
  },

  parseVersionTuple(ver) {
    return (ver || '').split('.').map((p) => parseInt(p, 10)).filter((n) => !Number.isNaN(n));
  },

  tailFromAnchorToken(anchor) {
    const token = (anchor || '').replace(/^#/, '');
    if (!token || !token.includes('--en__')) return null;
    const tail = token.split('--en__').pop() || '';
    return this.slugifyLabel(tail.replace(/_/g, ' '));
  },

  topicIdForTailVersioned(tail) {
    const slug = (tail || '').trim().replace(/\/$/, '');
    if (!slug) return null;
    const candidates = this.tailCandidates?.[slug] || [];
    if (!candidates.length) return null;

    const ctxPath = this.currentPath || '';
    const ctxVer = this.currentVersion || this.parseVersion(ctxPath);
    const ctxProduct = ctxPath.split('/')[0] || '';

    const score = (path) => {
      const ver = this.parseVersion(path);
      const verTuple = this.parseVersionTuple(ver || '');
      let productMatch = ctxProduct && path.startsWith(ctxProduct) ? 1 : 0;
      let cimBoost = 0;
      if (ctxProduct === 'splunk-enterprise' && ctxPath.includes('common-information-model')
        && path.includes('common-information-model')) {
        cimBoost = 1;
      }
      const verMatch = ctxVer && ver === ctxVer ? 1 : 0;
      return [verMatch, productMatch, cimBoost, ...verTuple, path.length];
    };

    candidates.sort((a, b) => {
      const sa = score(a[0]);
      const sb = score(b[0]);
      for (let i = 0; i < Math.max(sa.length, sb.length); i += 1) {
        if ((sa[i] || 0) !== (sb[i] || 0)) return (sb[i] || 0) - (sa[i] || 0);
      }
      return 0;
    });
    return candidates[0][1];
  },

  topicIdForLabel(text) {
    const label = (text || '').trim();
    if (!label) return null;
    const slug = this.slugifyLabel(label);
    if (slug) {
      const byTail = this.topicIdForTailVersioned(slug);
      if (byTail) return byTail;
    }
    const titles = this.linkIndex?.titles || {};
    const lower = label.toLowerCase();
    if (titles[lower]) {
      const paths = this.linkIndex?.paths || {};
      const titleTid = titles[lower];
      const pathKeys = Object.keys(paths);
      for (let i = 0; i < pathKeys.length; i += 1) {
        const path = pathKeys[i];
        if (paths[path] === titleTid && !path.startsWith('en/')) {
          const versioned = this.topicIdForTailVersioned(path.split('/').pop());
          return versioned || titleTid;
        }
      }
      return titleTid;
    }
    return null;
  },

  resolveTopicId(el, href) {
    if (el.dataset.topic) return el.dataset.topic;
    const rid = el.dataset.resourceId || el.dataset.resourceid;
    if (rid && this.linkIndex?.resourceIds?.[rid]) {
      return this.linkIndex.resourceIds[rid];
    }
    const labelTid = this.topicIdForLabel(el.textContent || '');
    if (labelTid) return labelTid;
    const anchorTail = this.tailFromAnchorToken(el.dataset.anchor || '');
    if (anchorTail) {
      const anchorTid = this.topicIdForTailVersioned(anchorTail);
      if (anchorTid) return anchorTid;
    }
    const source = href || this.originalHref(el);
    const parsed = this.normalizePath(source);
    if (!parsed || parsed.external || !parsed.path) return null;
    return this.topicIdForPath(parsed.path);
  },

  resolveFromHref(href) {
    const parsed = this.normalizePath(href);
    if (!parsed) return null;
    if (parsed.external) return { external: true };
    if (parsed.blocked) return { external: false, unresolved: true, blocked: true };
    const topicId = this.topicIdForPath(parsed.path);
    if (!topicId) return { external: false, unresolved: true, path: parsed.path };
    return {
      external: false,
      topicId,
      anchor: parsed.anchor || '',
      path: parsed.path,
    };
  },

  isExternalHref(href) {
    if (!href || href === '#' || href.startsWith('#')) return false;
    const parsed = this.normalizePath(href);
    if (parsed?.external) return true;
    if (/^https?:\/\//i.test(href)) return true;
    if (href.startsWith('/services') || href.startsWith('services')) return true;
    return false;
  },

  looksLikeDocHref(href) {
    if (!href || href === '#' || href.startsWith('#')) return false;
    if (/^https?:\/\//i.test(href)) return /help\.splunk\.com/i.test(href);
    return href.startsWith('/en/') || href.startsWith('en/')
      || href.startsWith('splunk-') || href.startsWith('/splunk-');
  },

  classifyAnchor(el, href) {
    if (el.dataset.topic) {
      el.classList.add('offline-link');
      el.classList.remove('offline-unresolved');
      el.removeAttribute('data-unresolved');
      el.removeAttribute('title');
      return 'internal';
    }

    const source = href || this.originalHref(el);

    if (el.dataset.anchorLocal) {
      return 'anchor';
    }

    const topicId = this.resolveTopicId(el, source);
    if (topicId) {
      el.dataset.topic = topicId;
      const parsed = this.normalizePath(source);
      if (parsed?.anchor && !el.dataset.anchor) {
        el.dataset.anchor = parsed.anchor;
      }
      el.classList.add('offline-link');
      el.classList.remove('offline-unresolved');
      el.removeAttribute('data-unresolved');
      el.removeAttribute('title');
      return 'internal';
    }

    if (source.startsWith('#') && source.length > 1) {
      el.dataset.anchorLocal = source.slice(1);
      return 'anchor';
    }

    if (this.isExternalHref(source)) {
      el.classList.add('offline-external');
      el.title = this.EXTERNAL_TIP;
      return 'external';
    }

    const resolved = this.resolveFromHref(source);
    if (resolved?.topicId) {
      el.dataset.topic = resolved.topicId;
      if (resolved.anchor) el.dataset.anchor = resolved.anchor;
      el.classList.add('offline-link');
      el.classList.remove('offline-unresolved');
      return 'internal';
    }

    if (el.dataset.anchor) {
      const root = document.getElementById('content') || document;
      const esc = typeof CSS !== 'undefined' && CSS.escape
        ? CSS.escape(el.dataset.anchor) : el.dataset.anchor;
      if (root.querySelector(`#${esc}`)) {
        el.dataset.anchorLocal = el.dataset.anchor;
        el.classList.remove('offline-unresolved');
        el.removeAttribute('data-unresolved');
        return 'anchor';
      }
    }

    if (resolved?.unresolved || this.looksLikeDocHref(source)) {
      el.classList.add('offline-unresolved');
      el.title = 'Not available offline';
      return 'unresolved';
    }

    if (/^https?:\/\//i.test(source) || source.startsWith('/')) {
      el.classList.add('offline-external');
      el.title = this.EXTERNAL_TIP;
      return 'external';
    }

    return 'other';
  },
};
