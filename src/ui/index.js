const tabsRoot = document.getElementById('tabs');
const addTabButton = document.getElementById('add-tab');
const windowMinimizeButton = document.getElementById('window-minimize');
const windowMaximizeButton = document.getElementById('window-maximize');
const windowMaximizeGlyph = document.getElementById('window-maximize-glyph');
const windowCloseButton = document.getElementById('window-close');
const TAB_ANIMATION_MS = 170;

let state = {
  activeTabId: null,
  tabs: []
};
let hasRenderedInitialTabs = false;
const tabElements = new Map();
const closingTabIds = new Set();

function createIconSpan(name) {
  const span = document.createElement('span');
  span.className = `icon icon-${name}`;
  span.setAttribute('aria-hidden', 'true');
  return span;
}

function safeTitle(tab) {
  if (tab.title && tab.title.trim()) {
    return tab.title;
  }

  return tab.url || 'Figma';
}

function requestCloseTab(tabId) {
  if (closingTabIds.has(tabId)) {
    return;
  }

  closingTabIds.add(tabId);
  const tabButton = tabElements.get(tabId);
  if (tabButton) {
    tabButton.classList.add('is-closing');
  }

  setTimeout(() => {
    window.figmuxTabs.close(tabId);
  }, TAB_ANIMATION_MS);
}

function createTabElement(tab) {
  const tabButton = document.createElement('button');
  tabButton.type = 'button';
  tabButton.className = 'tab';
  tabButton.dataset.tabId = tab.id;

  const title = document.createElement('span');
  title.className = 'tab-title';

  const closeButton = document.createElement('button');
  closeButton.type = 'button';
  closeButton.className = 'tab-close';
  closeButton.title = 'Close tab';
  closeButton.append(createIconSpan('close'));
  closeButton.addEventListener('click', (event) => {
    event.stopPropagation();
    requestCloseTab(tab.id);
  });

  tabButton.addEventListener('click', () => {
    window.figmuxTabs.activate(tab.id);
  });

  tabButton.append(title, closeButton);
  return tabButton;
}

function updateTabElement(tabButton, tab) {
  const titleText = safeTitle(tab);
  const title = tabButton.querySelector('.tab-title');
  const closeButton = tabButton.querySelector('.tab-close');

  tabButton.dataset.tabId = tab.id;
  tabButton.title = titleText;
  tabButton.classList.toggle('active', Boolean(tab.isActive));
  tabButton.removeAttribute('data-removing');

  if (!closingTabIds.has(tab.id)) {
    tabButton.classList.remove('is-closing');
  }

  title.textContent = titleText;
  closeButton.setAttribute('aria-label', `Close ${titleText}`);
}

function renderTabs() {
  const fragment = document.createDocumentFragment();
  const nextTabIds = new Set();

  for (const tab of state.tabs) {
    let tabButton = tabElements.get(tab.id);
    const isNew = !tabButton;

    if (!tabButton) {
      tabButton = createTabElement(tab);
      tabElements.set(tab.id, tabButton);
    }

    updateTabElement(tabButton, tab);
    fragment.appendChild(tabButton);
    nextTabIds.add(tab.id);

    if (isNew && hasRenderedInitialTabs) {
      tabButton.classList.add('is-entering');
      requestAnimationFrame(() => {
        tabButton.classList.remove('is-entering');
      });
    }
  }

  if (addTabButton.parentElement !== tabsRoot) {
    tabsRoot.appendChild(addTabButton);
  }
  tabsRoot.insertBefore(fragment, addTabButton);

  for (const [tabId, tabButton] of tabElements.entries()) {
    if (nextTabIds.has(tabId) || tabButton.dataset.removing === 'true') {
      continue;
    }

    tabButton.dataset.removing = 'true';
    tabButton.classList.add('is-closing');
    setTimeout(() => {
      tabButton.remove();
      tabElements.delete(tabId);
      closingTabIds.delete(tabId);
    }, TAB_ANIMATION_MS);
  }

  hasRenderedInitialTabs = true;
}

function applyLayout(layout) {
  if (!layout) {
    return;
  }

  if (typeof layout.titlebarHeight === 'number') {
    document.documentElement.style.setProperty('--titlebar-height', `${layout.titlebarHeight}px`);
  }

  if (typeof layout.windowControlsInset === 'number') {
    document.documentElement.style.setProperty('--controls-inset', `${layout.windowControlsInset}px`);
  }
}

function applyWindowState(windowState) {
  if (!windowState || typeof windowState.isMaximized !== 'boolean') {
    return;
  }

  const maximized = windowState.isMaximized;
  document.body.classList.toggle('is-maximized', maximized);
  document.documentElement.classList.toggle('is-maximized', maximized);
  windowMaximizeButton.setAttribute('aria-label', maximized ? 'Restore window' : 'Maximize window');
  windowMaximizeGlyph.textContent = maximized ? '\u2750' : '\u25A1';
}

addTabButton.append(createIconSpan('plus'));

addTabButton.addEventListener('click', () => {
  window.figmuxTabs.create();
});

windowMinimizeButton.addEventListener('click', () => {
  window.windowControls.minimize();
});

windowMaximizeButton.addEventListener('click', () => {
  window.windowControls.toggleMaximize();
});

windowCloseButton.addEventListener('click', () => {
  window.windowControls.close();
});

window.figmuxTabs.onStateChanged((nextState) => {
  state = nextState;
  renderTabs();
});

window.figmuxTabs.onLayout((layout) => {
  applyLayout(layout);
});

window.windowControls.onStateChanged((windowState) => {
  applyWindowState(windowState);
});

window.figmuxTabs.list().then((initialState) => {
  state = initialState;
  renderTabs();
});
