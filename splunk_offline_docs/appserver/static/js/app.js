
const DOCS_BASE = 'docs/manifest';
const TOPICS_BASE = 'docs/topics';

const PRODUCT_ORDER = ['enterprise', 'es8', 'soar', 'itsi'];
const PRODUCT_LABELS = {
  enterprise: 'Splunk Enterprise',
  es8: 'Enterprise Security',
  soar: 'SOAR (On-premises)',
  itsi: 'IT Service Intelligence',
};

/** Per-product version filters (latest matching version is selected by default). */
const VERSION_FILTERS = {
  enterprise: (v) => /^10\.\d+$/.test(v),
  es8: (v) => /^8\.\d+(?:\.\d+)?$/.test(v),
  soar: (v) => /^\d+\.\d+\.\d+$/.test(v),
  itsi: (v) => /^\d+\.\d+(?:\.\d+)?$/.test(v),
};

let navData = [];
let searchIndex = [];
let pathIndex = new Map();
let activeProduct = 0;
let activePath = '';
let selectedVersions = {};
let expandedBranches = new Set();
const THEME_KEY = 'splunk_offline_docs_theme';

const LoadingUI = {
  overlay: null,
  overlayFill: null,
  overlayStatus: null,
  overlayTrack: null,
  topBar: null,
  topBarFill: null,
  topicLoads: 0,

  init() {
    if (this.overlay) return;
    this.overlay = document.getElementById('app-loading');
    this.overlayFill = document.getElementById('app-loading-fill');
    this.overlayStatus = document.getElementById('app-loading-status');
    this.overlayTrack = document.getElementById('app-loading-track');
    this.topBar = document.getElementById('app-loading-bar');
    this.topBarFill = document.getElementById('app-loading-bar-fill');
  },

  showOverlay(status = 'Loading documentation…', pct = 0) {
    this.init();
    this.overlay.hidden = false;
    this.overlay.setAttribute('aria-busy', 'true');
    document.body.classList.add('app-booting');
    this.setOverlayProgress(pct, status);
  },

  setOverlayProgress(pct, status) {
    this.init();
    if (status) this.overlayStatus.textContent = status;
    const p = Math.max(0, Math.min(100, pct));
    this.overlayFill.style.width = `${p}%`;
    this.overlayTrack.setAttribute('aria-valuenow', String(Math.round(p)));
  },

  hideOverlay() {
    this.init();
    this.setOverlayProgress(100, 'Ready');
    this.overlay.setAttribute('aria-busy', 'false');
    window.setTimeout(() => {
      this.overlay.hidden = true;
      document.body.classList.remove('app-booting');
    }, 220);
  },

  startTopicLoad() {
    this.init();
    this.topicLoads += 1;
    this.topBar.hidden = false;
    this.topBar.setAttribute('aria-hidden', 'false');
    this.topBar.classList.add('is-active');
    this.topBarFill.style.width = '';
  },

  endTopicLoad() {
    this.init();
    this.topicLoads = Math.max(0, this.topicLoads - 1);
    if (this.topicLoads > 0) return;
    this.topBar.classList.remove('is-active');
    this.topBarFill.style.width = '100%';
    window.setTimeout(() => {
      this.topBar.hidden = true;
      this.topBar.setAttribute('aria-hidden', 'true');
      this.topBarFill.style.width = '0%';
    }, 180);
  },
};

function productLabel(product) {
  const id = product?.id || product;
  return PRODUCT_LABELS[id] || id;
}

function titleFromPath(path) {
  const slug = (path || '').split('/').filter(Boolean).pop() || '';
  if (!slug) return '';
  return slug
    .split('-')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

function navNodeLabel(node) {
  const title = (node.title || '').trim();
  if (title.length >= 3) return title;
  return titleFromPath(node.path) || title;
}

function applyTheme(theme) {
  const next = theme === 'dark' ? 'dark' : 'light';
  document.documentElement.dataset.theme = next;
  localStorage.setItem(THEME_KEY, next);
  const btn = document.getElementById('theme-toggle');
  if (btn) {
    btn.setAttribute('aria-pressed', next === 'dark' ? 'true' : 'false');
    btn.textContent = next === 'dark' ? 'Light mode' : 'Dark mode';
    btn.title = next === 'dark' ? 'Switch to light mode' : 'Switch to dark mode';
  }
}

function initTheme() {
  const stored = localStorage.getItem(THEME_KEY);
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  applyTheme(stored || (prefersDark ? 'dark' : 'light'));
  const btn = document.getElementById('theme-toggle');
  if (btn) {
    btn.addEventListener('click', () => {
      const current = document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';
      applyTheme(current === 'dark' ? 'light' : 'dark');
    });
  }
}

function pathKey(product, path) {
  return `${product || ''}::${path}`;
}

function parseVersion(value) {
  const t = (value || '').trim();
  if (/^\d+\.\d+\.\d+$/.test(t)) return t;
  if (/^\d+\.\d+$/.test(t)) return t;
  return null;
}

function pathVersion(path) {
  for (const seg of (path || '').split('/')) {
    const v = parseVersion(seg);
    if (v) return v;
  }
  return null;
}

function compareVersions(a, b) {
  const pa = a.split('.').map(Number);
  const pb = b.split('.').map(Number);
  for (let i = 0; i < Math.max(pa.length, pb.length); i += 1) {
    const d = (pa[i] || 0) - (pb[i] || 0);
    if (d !== 0) return d;
  }
  return 0;
}

function walkNavForVersions(nodes, vers, filter) {
  if (!nodes?.length) return;
  if (nodes.every((n) => parseVersion((n.title || '').trim()))) {
    nodes.forEach((n) => {
      const v = parseVersion((n.title || '').trim()) || pathVersion(n.path);
      if (v && filter(v)) vers.add(v);
    });
    return;
  }
  nodes.forEach((n) => walkNavForVersions(n.children || [], vers, filter));
}

function discoverVersions(productId) {
  const filter = VERSION_FILTERS[productId];
  if (!filter) return [];
  const vers = new Set();
  searchIndex
    .filter((t) => t.product === productId)
    .forEach((t) => {
      const v = pathVersion(t.path);
      if (v && filter(v)) vers.add(v);
    });
  const product = navData.find((p) => p.id === productId);
  if (product) walkNavForVersions(product.children || [], vers, filter);
  return [...vers].sort(compareVersions).reverse();
}

function productHasVersions(productId) {
  return discoverVersions(productId).length > 0;
}

function getSelectedVersion(product) {
  const id = product?.id || product;
  if (!productHasVersions(id)) return null;
  if (!selectedVersions[id]) {
    const vers = discoverVersions(id);
    selectedVersions[id] = vers[0] || null;
  }
  return selectedVersions[id];
}

function pathMatchesVersion(path, version) {
  if (!version) return true;
  const pv = pathVersion(path);
  if (!pv) return true;
  return pv === version;
}

function isVersionBranch(nodes) {
  return nodes.length > 0
    && nodes.every((n) => parseVersion((n.title || '').trim()));
}

function applyVersionToNav(nodes, version) {
  if (!version) return nodes;
  const out = [];
  nodes.forEach((n) => {
    let children = applyVersionToNav(n.children || [], version);
    if (isVersionBranch(children)) {
      const match = children.find(
        (c) => (c.title || '').trim() === version || pathVersion(c.path) === version,
      );
      children = match ? applyVersionToNav(match.children || [], version) : [];
    }
    const selfOk = pathMatchesVersion(n.path, version);
    if (!selfOk && children.length === 0) return;
    out.push({ ...n, children });
  });
  return out;
}

function swapPathVersion(path, version) {
  const segs = path.split('/');
  for (let i = 0; i < segs.length; i += 1) {
    if (parseVersion(segs[i])) {
      segs[i] = version;
      return segs.join('/');
    }
  }
  return path;
}

function buildPathIndex() {
  pathIndex = new Map();
  searchIndex.forEach((entry) => {
    pathIndex.set(pathKey(entry.product, entry.path), entry);
    pathIndex.set(entry.path, entry);
  });
}

function sortNavProducts(nav) {
  return [...nav].sort((a, b) => {
    const ia = PRODUCT_ORDER.indexOf(a.id);
    const ib = PRODUCT_ORDER.indexOf(b.id);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
  });
}

function currentProduct() {
  return navData[activeProduct] || navData[0];
}

function findNavNodeByPathInProduct(path, product) {
  const pid = product?.id || product;
  const tree = navData.find((p) => p.id === pid);
  if (!tree) return null;
  const nodes = productHasVersions(pid)
    ? applyVersionToNav(tree.children || [], getSelectedVersion(tree))
    : (tree.children || []);
  let found = null;
  (function walk(list) {
    list.forEach((n) => {
      if (n.path === path) found = n;
      if (n.children?.length) walk(n.children);
    });
  })(nodes);
  return found;
}

function findNavNodeByPath(path) {
  return findNavNodeByPathInProduct(path, currentProduct());
}

function topicFromNavPath(path, product) {
  const pid = product?.id || product;
  const node = findNavNodeByPathInProduct(path, product);
  if (!node?.topic_id) return null;
  return {
    id: node.topic_id,
    path,
    product: pid,
    title: navNodeLabel(node),
  };
}

function lookupTopic(path, product) {
  const pid = product?.id || product;
  const version = getSelectedVersion(product);
  const candidates = [path];
  if (version) {
    candidates.push(swapPathVersion(path, version));
    if (!pathVersion(path)) {
      const parts = path.split('/');
      for (let i = 0; i < parts.length; i += 1) {
        if (parts[i] === 'administer' || parts[i] === 'search') {
          const injected = [...parts];
          injected.splice(i + 1, 0, version);
          candidates.push(injected.join('/'));
          break;
        }
      }
    }
  }
  for (const p of candidates) {
    const hit = pathIndex.get(pathKey(pid, p))
      || pathIndex.get(p)
      || searchIndex.find((t) => t.path === p && t.product === pid);
    if (hit) return hit;
    const navHit = topicFromNavPath(p, product);
    if (navHit) return navHit;
  }
  return null;
}

function topicInCurrentContext(entry) {
  const product = currentProduct();
  if (!entry || entry.product !== product.id) return false;
  const version = getSelectedVersion(product);
  if (!version) return true;
  return pathMatchesVersion(entry.path, version);
}

async function loadManifest() {
  LoadingUI.showOverlay('Loading documentation…', 4);
  const cacheBust = window.__OFFLINE_DOCS_BUILD__ || Date.now();
  const searchEl = document.getElementById('search');

  const navStep = { url: `${DOCS_BASE}/nav.json`, label: 'Loading navigation…', weight: 18 };
  const linkStep = { url: `${DOCS_BASE}/link-index.json`, label: 'Loading link map…', weight: 18 };

  let progress = 4;
  const loadStep = async (step) => {
    LoadingUI.setOverlayProgress(progress, step.label);
    const res = await fetch(`${step.url}?v=${cacheBust}`, { cache: 'no-store' });
    if (!res.ok) throw new Error(`Failed to load ${step.url} (${res.status})`);
    const data = await res.json();
    progress += step.weight;
    LoadingUI.setOverlayProgress(progress, step.label);
    return data;
  };

  const [nav, linkIndex] = await Promise.all([
    loadStep(navStep),
    loadStep(linkStep),
  ]);

  LoadingUI.setOverlayProgress(42, 'Preparing interface…');
  navData = sortNavProducts(nav);
  buildPathIndex();
  OfflineLinkResolver.setIndex(linkIndex);
  expandedBranches.clear();
  activeProduct = Math.max(0, navData.findIndex((p) => p.id === 'enterprise'));
  activePath = '';
  renderProductTabs();
  renderSidebar();
  if (location.hash.startsWith('#/')) {
    parseHash();
  } else {
    location.hash = '';
  }
  LoadingUI.hideOverlay();

  if (searchEl) {
    searchEl.placeholder = 'Loading search index…';
    searchEl.disabled = true;
  }

  try {
    LoadingUI.setOverlayProgress(55, 'Loading search index…');
    const res = await fetch(`${DOCS_BASE}/search-index.json?v=${cacheBust}`, { cache: 'no-store' });
    if (!res.ok) throw new Error(`Failed to load search-index.json (${res.status})`);
    searchIndex = await res.json();
    buildPathIndex();
    if (searchEl) {
      searchEl.disabled = false;
      searchEl.placeholder = 'Search documentation…';
    }
  } catch (err) {
    console.error(err);
    if (searchEl) {
      searchEl.disabled = true;
      searchEl.placeholder = 'Search unavailable (index failed to load)';
    }
  }
}

function renderProductTabs() {
  const el = document.getElementById('product-tabs');
  el.innerHTML = '';
  PRODUCT_ORDER.forEach((pid) => {
    const i = navData.findIndex((p) => p.id === pid);
    if (i < 0) return;
    const p = navData[i];
    const b = document.createElement('button');
    b.textContent = productLabel(p);
    b.type = 'button';
    if (i === activeProduct) b.classList.add('active');
    b.onclick = () => {
      activeProduct = i;
      activePath = '';
      expandedBranches.clear();
      delete selectedVersions[p.id];
      renderProductTabs();
      renderSidebar();
      document.getElementById('content').innerHTML =
        '<p class="placeholder">Select a topic from the navigation.</p>';
      document.getElementById('breadcrumbs').innerHTML = '';
      document.getElementById('mini-toc').innerHTML = '';
    };
    el.appendChild(b);
  });
}

function renderVersionSelector(product) {
  const wrap = document.getElementById('version-wrap');
  const select = document.getElementById('version-select');
  const versions = discoverVersions(product.id);

  if (!productHasVersions(product.id) || versions.length === 0) {
    wrap.hidden = true;
    return;
  }

  wrap.hidden = false;
  const current = getSelectedVersion(product);
  select.innerHTML = versions
    .map((v) => `<option value="${v}"${v === current ? ' selected' : ''}>${v}</option>`)
    .join('');

  select.onchange = () => {
    selectedVersions[product.id] = select.value;
    expandedBranches.clear();
    renderSidebar();
    if (activePath) {
      const swapped = swapPathVersion(activePath, select.value);
      const entry = lookupTopic(swapped, product) || lookupTopic(activePath, product);
      if (entry && topicInCurrentContext(entry)) {
        loadTopic(entry.id, entry);
      } else {
        activePath = '';
        document.getElementById('content').innerHTML =
          '<p class="placeholder">Select a topic for this version from the navigation.</p>';
        document.getElementById('breadcrumbs').innerHTML = '';
        document.getElementById('mini-toc').innerHTML = '';
      }
    }
  };
}

function navNodesForProduct(product) {
  const version = getSelectedVersion(product);
  const raw = product.children || [];
  return productHasVersions(product.id) ? applyVersionToNav(raw, version) : raw;
}

function ensureExpandedForPath(path) {
  const nodes = navNodesForProduct(currentProduct());

  function walk(list, ancestors) {
    list.forEach((n) => {
      const chain = [...ancestors, n.path];
      if (n.path === path) {
        chain.slice(0, -1).forEach((p) => expandedBranches.add(p));
      }
      if (n.children?.length) walk(n.children, chain);
    });
  }
  walk(nodes, []);
}

function renderSidebar() {
  const product = currentProduct();
  document.getElementById('product-heading').textContent = productLabel(product);
  renderVersionSelector(product);

  const navEl = document.getElementById('sidebar-nav');
  navEl.innerHTML = '';
  const nodes = navNodesForProduct(product);

  const ul = document.createElement('ul');
  ul.className = 'toc-tree';
  addNavNodes(ul, nodes, product);
  navEl.appendChild(ul);
}

function addNavNodes(parent, nodes, product) {
  nodes.forEach((n) => {
    const li = document.createElement('li');
    const hasKids = (n.children?.length || 0) > 0;
    if (hasKids) li.classList.add('branch');

    const row = document.createElement('div');
    row.className = 'toc-row';

    if (hasKids) {
      const expanded = expandedBranches.has(n.path);
      const toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'toc-toggle';
      toggle.setAttribute('aria-label', expanded ? 'Collapse section' : 'Expand section');
      toggle.textContent = expanded ? '▾' : '▸';
      toggle.onclick = (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (expandedBranches.has(n.path)) expandedBranches.delete(n.path);
        else expandedBranches.add(n.path);
        renderSidebar();
      };
      row.appendChild(toggle);
    }

    const label = navNodeLabel(n);
    const a = document.createElement('a');
    a.href = '#';
    a.textContent = label;
    a.title = label;
    a.dataset.navPath = n.path;
    if (n.path === activePath) a.classList.add('active');
    row.appendChild(a);
    li.appendChild(row);

    if (hasKids) {
      const cul = document.createElement('ul');
      cul.className = expandedBranches.has(n.path) ? 'toc-children is-open' : 'toc-children';
      addNavNodes(cul, n.children, product);
      li.appendChild(cul);
    }

    parent.appendChild(li);
  });
}

function collectNavSubtree(node) {
  const nodes = [];
  (function walk(n) {
    nodes.push(n);
    (n.children || []).forEach(walk);
  })(node);
  return nodes;
}

async function findFirstArticleEntry(node, product) {
  for (const candidate of collectNavSubtree(node)) {
    const entry = lookupTopic(candidate.path, product);
    if (!entry || !topicInCurrentContext(entry)) continue;
    const cacheBust = window.__OFFLINE_DOCS_BUILD__ || Date.now();
    const res = await fetch(`${TOPICS_BASE}/${entry.id}.html?v=${cacheBust}`, { cache: 'no-store' });
    if (!res.ok) continue;
    const html = await res.text();
    if (html.trim()) return entry;
  }
  return null;
}

async function openNavNode(node, product) {
  const hasKids = (node.children?.length || 0) > 0;
  if (hasKids) {
    expandedBranches.add(node.path);
    renderSidebar();
  }

  const entry = await findFirstArticleEntry(node, product);
  if (entry) {
    await loadTopic(entry.id, entry);
    return;
  }

  if (!hasKids) {
    await loadTopicByPath(node.path, product);
    return;
  }

  document.getElementById('content').innerHTML =
    '<p class="placeholder">No articles are available offline in this section yet.</p>';
  document.getElementById('breadcrumbs').innerHTML = '';
  document.getElementById('mini-toc').innerHTML = '';
}

async function loadTopicByPath(path, product) {
  let entry = lookupTopic(path, product);
  if (!entry) {
    for (const pid of PRODUCT_ORDER) {
      entry = lookupTopic(path, { id: pid });
      if (entry) break;
    }
  }
  if (!entry) {
    entry = findTopicForLink(null, path)
      || searchIndex.find((t) => t.path === path);
  }
  if (!entry) {
    document.getElementById('content').innerHTML =
      `<p class="placeholder">Topic not available offline: <code>${path}</code></p>`;
    return;
  }
  await navigateToTopic(entry, '');
}

async function loadTopic(topicId, meta) {
  const content = document.getElementById('content');
  content.innerHTML = '<p class="placeholder">Loading…</p>';
  LoadingUI.startTopicLoad();

  try {
    const cacheBust = window.__OFFLINE_DOCS_BUILD__ || Date.now();
    const res = await fetch(`${TOPICS_BASE}/${topicId}.html?v=${cacheBust}`, { cache: 'no-store' });
    if (!res.ok) {
      content.innerHTML =
        `<p class="placeholder">Failed to load topic <code>${topicId}</code> (${res.status}).</p>`;
      return;
    }

    const html = await res.text();
    if (!html.trim()) {
      content.innerHTML =
        '<p class="placeholder">This topic has no stored content yet.</p>';
      return;
    }

    content.innerHTML = html;
    activePath = meta?.path || '';
    ensureExpandedForPath(activePath);
    renderSidebar();

    const product = currentProduct();
    const crumbs = meta?.breadcrumbs?.length
      ? meta.breadcrumbs.filter((c) => c.title)
      : [{ title: meta?.title || topicId, path: meta?.path || '' }];

    const productTitle = productLabel(product);
    const allCrumbs = productTitle
      ? [{ title: productTitle, path: '' }, ...crumbs]
      : crumbs;

    document.getElementById('breadcrumbs').innerHTML = allCrumbs
      .map((c, i) => {
        const isLast = i === allCrumbs.length - 1;
        if (isLast) return `<span class="crumb-current">${c.title}</span>`;
        if (c.path) {
          return `<a href="#" data-path="${c.path}">${c.title}</a><span class="sep">›</span>`;
        }
        return `<span>${c.title}</span><span class="sep">›</span>`;
      })
      .join('');

    const mini = document.getElementById('mini-toc');
    mini.innerHTML = '<span class="mini-toc-heading">On this page</span>';
    const headings = content.querySelectorAll('h1[id], h2[id], h3[id], h4[id]');
    headings.forEach((h, idx) => {
      if (idx === 0 && h.tagName === 'H1') return;
      const a = document.createElement('a');
      a.href = '#';
      a.textContent = h.textContent;
      a.dataset.anchorLocal = h.id;
      a.onclick = () => {
        mini.querySelectorAll('a').forEach((x) => x.classList.remove('active'));
        a.classList.add('active');
      };
      mini.appendChild(a);
    });

    OfflineLinkResolver.currentPath = meta?.path || '';
    OfflineLinkResolver.currentVersion = getSelectedVersion(product) || '';
    bindLinks(content);
    bindLinks(document.getElementById('breadcrumbs'));
    bindLinks(mini);

    const version = getSelectedVersion(product);
    const hashPath = version && productHasVersions(product.id)
      ? `${meta?.product || ''}/${version}/${meta?.path || topicId}`
      : `${meta?.product || ''}/${meta?.path || topicId}`;
    location.hash = `#/${hashPath}`;
  } finally {
    LoadingUI.endTopicLoad();
  }
}

function findTopicForLink(tid, href) {
  if (tid) {
    const byId = searchIndex.find((t) => t.id === tid);
    if (byId) return byId;
  }
  const resolved = OfflineLinkResolver.resolveFromHref(href);
  if (!resolved?.path) return null;
  const variants = OfflineLinkResolver.pathCandidates(resolved.path);
  for (const pid of PRODUCT_ORDER) {
    for (const p of variants) {
      const hit = lookupTopic(p, { id: pid });
      if (hit) return hit;
    }
  }
  return searchIndex.find((t) => variants.includes(t.path)) || null;
}

async function navigateToTopic(meta, anchor) {
  if (!meta) return;
  const pidx = navData.findIndex((p) => p.id === meta.product);
  if (pidx >= 0 && pidx !== activeProduct) {
    activeProduct = pidx;
    expandedBranches.clear();
    renderProductTabs();
  }
  const version = pathVersion(meta.path);
  if (version && productHasVersions(meta.product)) {
    selectedVersions[meta.product] = version;
  }
  renderSidebar();
  await loadTopic(meta.id, meta);
  if (anchor) {
    const root = document.getElementById('content');
    const esc = typeof CSS !== 'undefined' && CSS.escape ? CSS.escape(anchor) : anchor;
    const el = root.querySelector(`#${esc}`) || document.getElementById(anchor);
    el?.scrollIntoView({ behavior: 'smooth' });
  }
}

function scrollToAnchor(id) {
  if (!id) return;
  const rootEl = document.getElementById('content');
  const esc = typeof CSS !== 'undefined' && CSS.escape ? CSS.escape(id) : id;
  (rootEl.querySelector(`#${esc}`) || document.getElementById(id))
    ?.scrollIntoView({ behavior: 'smooth' });
}

async function activateLink(a) {
  const href = OfflineLinkResolver.originalHref(a);
  OfflineLinkResolver.classifyAnchor(a, href);

  if (a.dataset.anchorLocal) {
    scrollToAnchor(a.dataset.anchorLocal);
    return;
  }

  if (a.classList.contains('offline-external')) {
    return;
  }

  const navPath = a.dataset.navPath;
  if (navPath) {
    const node = findNavNodeByPath(navPath);
    if (node) await openNavNode(node, currentProduct());
    return;
  }

  const pathAttr = a.dataset.path;
  if (pathAttr) {
    await loadTopicByPath(pathAttr, currentProduct());
    return;
  }

  const tid = OfflineLinkResolver.resolveTopicId(a, href);
  const anchor = a.dataset.anchor || '';
  let meta = findTopicForLink(tid, href);
  if (!meta && tid) {
    meta = searchIndex.find((t) => t.id === tid);
  }
  if (meta) {
    await navigateToTopic(meta, anchor);
    return;
  }

  if (tid) {
    await loadTopic(tid, { id: tid, path: '', product: currentProduct().id });
    if (anchor) scrollToAnchor(anchor);
    return;
  }

  if (a.classList.contains('offline-unresolved') && a.dataset.anchor) {
    scrollToAnchor(a.dataset.anchor);
    return;
  }

  if (href.startsWith('#') && href.length > 1) {
    scrollToAnchor(href.slice(1));
  }
}

const APP_LINK_SELECTOR = '#content, #sidebar-nav, #breadcrumbs, #mini-toc, .search-results';

function initGlobalLinkGuard() {
  const guard = (e) => {
    const a = e.target.closest('a[href]');
    if (!a || !a.closest(APP_LINK_SELECTOR)) return;

    e.preventDefault();

    const searchId = a.dataset.searchId || a.dataset.id;
    if (searchId) {
      const box = document.getElementById('search-results');
      if (box) {
        box.hidden = true;
        box.innerHTML = '';
      }
      const searchEl = document.getElementById('search');
      if (searchEl) searchEl.value = '';
      const meta = searchIndex.find((t) => t.id === searchId);
      if (meta) navigateToTopic(meta, '');
      return;
    }

    activateLink(a);
  };

  document.addEventListener('click', guard, true);
  document.addEventListener('auxclick', (e) => {
    if (e.button === 1) guard(e);
  }, true);
}

function bindLinks(root) {
  root.querySelectorAll('a[href]').forEach((a) => {
    if (a.dataset.topic) {
      a.setAttribute('href', '#');
      a.classList.add('offline-link');
      a.classList.remove('offline-unresolved');
      a.removeAttribute('data-unresolved');
      return;
    }
    const original = OfflineLinkResolver.neutralize(a);
    OfflineLinkResolver.classifyAnchor(a, original);
  });
}

function parseHash() {
  const raw = decodeURIComponent(location.hash).replace('#/', '');
  const parts = raw.split('/');
  const product = parts[0];
  let pathStart = 1;
  if (parts[1] && parseVersion(parts[1])) {
    selectedVersions[product] = parts[1];
    pathStart = 2;
  }
  const path = parts.slice(pathStart).join('/');
  const idx = navData.findIndex((p) => p.id === product);
  if (idx >= 0) {
    activeProduct = idx;
    renderProductTabs();
    renderSidebar();
  }
  const meta = searchIndex.find((t) => t.product === product && t.path === path);
  if (meta) loadTopic(meta.id, meta);
}

let searchTimer = null;

function searchResultsBox() {
  return document.getElementById('search-results');
}

function runSearch(query) {
  const q = query.trim().toLowerCase();
  const box = searchResultsBox();
  if (!box) return;
  if (!searchIndex.length) {
    box.innerHTML = '<div class="search-empty">Search index is still loading…</div>';
    box.hidden = false;
    return;
  }
  if (!q) {
    box.hidden = true;
    box.innerHTML = '';
    return;
  }

  const product = currentProduct();
  const version = getSelectedVersion(product);

  const hits = searchIndex
    .filter((t) => {
      if (t.product !== product.id) return false;
      if (version && !pathMatchesVersion(t.path, version)) return false;
      const title = (t.title || '').toLowerCase();
      const text = (t.text || '').toLowerCase();
      return title.includes(q) || text.includes(q);
    })
    .sort((a, b) => {
      const at = (a.title || '').toLowerCase().includes(q) ? 0 : 1;
      const bt = (b.title || '').toLowerCase().includes(q) ? 0 : 1;
      return at - bt;
    })
    .slice(0, 25);

  if (!hits.length) {
    box.innerHTML = '<div class="search-empty">No topics found</div>';
    box.hidden = false;
    return;
  }

  box.innerHTML = hits.map((h) => {
    const snippet = (h.text || '').slice(0, 100);
    return `<a href="#" data-search-id="${h.id}"><strong>${h.title}</strong>${snippet ? `<span>${snippet}…</span>` : ''}</a>`;
  }).join('');
  box.hidden = false;
}

document.getElementById('search').addEventListener('input', (e) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => runSearch(e.target.value), 180);
});

document.getElementById('search').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    const first = document.querySelector('#search-results a');
    if (first) first.click();
  }
  if (e.key === 'Escape') {
    const box = searchResultsBox();
    if (box) {
      box.hidden = true;
      box.innerHTML = '';
    }
  }
});

document.addEventListener('click', (e) => {
  const box = searchResultsBox();
  const searchEl = document.getElementById('search');
  if (box && !box.hidden && !box.contains(e.target) && e.target !== searchEl) {
    box.hidden = true;
  }
});

loadManifest().catch((err) => {
  LoadingUI.hideOverlay();
  document.getElementById('content').innerHTML =
    `<p class="placeholder">Failed to load docs bundle. Run the scraper build first.<br><code>${err}</code></p>`;
});

initTheme();
initGlobalLinkGuard();
window.__offlineDocsActivateLink = activateLink;
