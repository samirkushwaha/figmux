const tabsRoot = document.getElementById('tabs');
const addTabButton = document.getElementById('add-tab');

let state = {
  activeTabId: null,
  tabs: []
};
let layoutState = {
  titlebarHeight: 44,
  windowControlsInset: 160
};

function readOverlayInset() {
  const overlay = window.navigator.windowControlsOverlay;
  if (!overlay || typeof overlay.getTitlebarAreaRect !== 'function') {
    return null;
  }

  const rect = overlay.getTitlebarAreaRect();
  if (!rect || typeof rect.x !== 'number' || typeof rect.width !== 'number') {
    return null;
  }

  const rightInset = Math.max(0, Math.round(window.innerWidth - (rect.x + rect.width)));
  if (!Number.isFinite(rightInset)) {
    return null;
  }

  return rightInset;
}

function applyControlsInset() {
  const overlayInset = readOverlayInset();
  const fallbackInset = Number(layoutState.windowControlsInset) || 0;
  const resolvedInset = Math.max(fallbackInset, overlayInset ?? 0);
  document.documentElement.style.setProperty('--controls-inset', `${resolvedInset}px`);
}

function safeTitle(tab) {
  if (tab.title && tab.title.trim()) {
    return tab.title;
  }

  return tab.url || 'Figma';
}

function renderTabs() {
  tabsRoot.textContent = '';

  for (const tab of state.tabs) {
    const tabButton = document.createElement('button');
    tabButton.type = 'button';
    tabButton.className = `tab${tab.isActive ? ' active' : ''}`;
    tabButton.dataset.tabId = tab.id;
    tabButton.title = safeTitle(tab);

    const loading = document.createElement('span');
    loading.className = 'tab-loading';
    loading.style.visibility = tab.isLoading ? 'visible' : 'hidden';

    const title = document.createElement('span');
    title.className = 'tab-title';
    title.textContent = safeTitle(tab);

    const closeButton = document.createElement('button');
    closeButton.type = 'button';
    closeButton.className = 'tab-close';
    closeButton.textContent = 'x';
    closeButton.title = 'Close tab';
    closeButton.addEventListener('click', (event) => {
      event.stopPropagation();
      window.figmuxTabs.close(tab.id);
    });

    tabButton.addEventListener('click', () => {
      window.figmuxTabs.activate(tab.id);
    });

    tabButton.append(loading, title, closeButton);
    tabsRoot.appendChild(tabButton);
  }
}

function applyLayout(layout) {
  if (!layout) {
    return;
  }

  if (typeof layout.titlebarHeight === 'number') {
    layoutState.titlebarHeight = layout.titlebarHeight;
    document.documentElement.style.setProperty('--titlebar-height', `${layout.titlebarHeight}px`);
  }

  if (typeof layout.windowControlsInset === 'number') {
    layoutState.windowControlsInset = layout.windowControlsInset;
  }

  applyControlsInset();
}

addTabButton.addEventListener('click', () => {
  window.figmuxTabs.create();
});

window.figmuxTabs.onStateChanged((nextState) => {
  state = nextState;
  renderTabs();
});

window.figmuxTabs.onLayout((layout) => {
  applyLayout(layout);
});

const overlay = window.navigator.windowControlsOverlay;
if (overlay && typeof overlay.addEventListener === 'function') {
  overlay.addEventListener('geometrychange', () => {
    applyControlsInset();
  });
}

window.addEventListener('resize', () => {
  applyControlsInset();
});

window.figmuxTabs.list().then((initialState) => {
  state = initialState;
  renderTabs();
});
