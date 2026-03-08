const tabsRoot = document.getElementById('tabs');
const addTabButton = document.getElementById('add-tab');
const windowMinimizeButton = document.getElementById('window-minimize');
const windowMaximizeButton = document.getElementById('window-maximize');
const windowMaximizeGlyph = document.getElementById('window-maximize-glyph');
const windowCloseButton = document.getElementById('window-close');
const toastRegion = document.getElementById('toast-region');
const TAB_ANIMATION_MS = 170;
const TOAST_DURATION_MS = 5200;

let state = {
  activeTabId: null,
  tabs: []
};
let hasRenderedInitialTabs = false;
let activeToastTimer = null;
let draggedTabId = null;
const tabElements = new Map();
const closingTabIds = new Set();

function createIconSpan(name) {
  const span = document.createElement('span');
  span.className = `icon icon-${name}`;
  span.setAttribute('aria-hidden', 'true');
  return span;
}

function showToast(toast) {
  if (!toastRegion || !toast || typeof toast.message !== 'string' || !toast.message.trim()) {
    return;
  }

  if (activeToastTimer) {
    clearTimeout(activeToastTimer);
    activeToastTimer = null;
  }

  toastRegion.textContent = '';

  const toastElement = document.createElement('section');
  toastElement.className = 'toast';

  if (typeof toast.title === 'string' && toast.title.trim()) {
    const title = document.createElement('div');
    title.className = 'toast-title';
    title.textContent = toast.title;
    toastElement.append(title);
  }

  const message = document.createElement('div');
  message.className = 'toast-message';
  message.textContent = toast.message;
  toastElement.append(message);

  toastRegion.append(toastElement);
  requestAnimationFrame(() => {
    toastElement.classList.add('is-visible');
  });

  const duration =
    typeof toast.durationMs === 'number' && Number.isFinite(toast.durationMs)
      ? Math.max(2000, toast.durationMs)
      : TOAST_DURATION_MS;

  activeToastTimer = setTimeout(() => {
    toastElement.classList.remove('is-visible');
    setTimeout(() => {
      if (toastElement.parentElement === toastRegion) {
        toastElement.remove();
      }
    }, 180);
    activeToastTimer = null;
  }, duration);
}

function safeTitle(tab) {
  if (tab.title && tab.title.trim()) {
    return tab.title;
  }

  return tab.url || 'Figma';
}

function beginClosingTab(tabId) {
  if (closingTabIds.has(tabId)) {
    return false;
  }

  closingTabIds.add(tabId);
  const tabButton = tabElements.get(tabId);
  if (tabButton) {
    tabButton.dataset.removing = 'true';
    tabButton.classList.add('is-closing');
  }

  return true;
}

function requestCloseTab(tabId) {
  if (!beginClosingTab(tabId)) {
    return;
  }

  setTimeout(() => {
    window.figmuxTabs.close(tabId);
  }, TAB_ANIMATION_MS);
}

function indexOfTab(tabId) {
  return state.tabs.findIndex((tab) => tab.id === tabId);
}

function clearDragState() {
  draggedTabId = null;
  for (const tabButton of tabElements.values()) {
    tabButton.classList.remove('is-dragging', 'drop-before', 'drop-after');
  }
}

function updateDropIndicator(targetButton, clientX) {
  for (const tabButton of tabElements.values()) {
    if (tabButton !== targetButton) {
      tabButton.classList.remove('drop-before', 'drop-after');
    }
  }

  if (!targetButton || !draggedTabId || targetButton.dataset.tabId === draggedTabId) {
    return null;
  }

  const rect = targetButton.getBoundingClientRect();
  const dropAfter = clientX > rect.left + rect.width / 2;
  targetButton.classList.toggle('drop-before', !dropAfter);
  targetButton.classList.toggle('drop-after', dropAfter);

  const targetIndex = indexOfTab(targetButton.dataset.tabId);
  if (targetIndex < 0) {
    return null;
  }

  return dropAfter ? targetIndex + 1 : targetIndex;
}

function createTabElement(tab) {
  const tabButton = document.createElement('button');
  tabButton.type = 'button';
  tabButton.className = 'tab';
  tabButton.dataset.tabId = tab.id;
  tabButton.draggable = true;

  const titleGroup = document.createElement('span');
  titleGroup.className = 'tab-title-group';

  const spinner = document.createElement('span');
  spinner.className = 'tab-spinner';
  spinner.setAttribute('aria-hidden', 'true');

  const title = document.createElement('span');
  title.className = 'tab-title';
  titleGroup.append(spinner, title);

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

  tabButton.addEventListener('dragstart', (event) => {
    draggedTabId = tabButton.dataset.tabId;
    tabButton.classList.add('is-dragging');
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = 'move';
      event.dataTransfer.setData('text/plain', draggedTabId);
    }
  });

  tabButton.addEventListener('dragover', (event) => {
    if (!draggedTabId) {
      return;
    }

    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'move';
    }
    updateDropIndicator(tabButton, event.clientX);
  });

  tabButton.addEventListener('drop', (event) => {
    if (!draggedTabId) {
      return;
    }

    event.preventDefault();
    const rawTargetIndex = updateDropIndicator(tabButton, event.clientX);
    const draggedIndex = indexOfTab(draggedTabId);
    if (rawTargetIndex === null || draggedIndex < 0) {
      clearDragState();
      return;
    }

    let nextIndex = rawTargetIndex;
    if (rawTargetIndex > draggedIndex) {
      nextIndex -= 1;
    }

    window.figmuxTabs.move(draggedTabId, nextIndex);
    clearDragState();
  });

  tabButton.addEventListener('dragend', () => {
    clearDragState();
  });

  tabButton.append(titleGroup, closeButton);
  return tabButton;
}

function updateTabElement(tabButton, tab) {
  const titleText = safeTitle(tab);
  const title = tabButton.querySelector('.tab-title');
  const closeButton = tabButton.querySelector('.tab-close');

  tabButton.dataset.tabId = tab.id;
  tabButton.title = titleText;
  tabButton.classList.toggle('active', Boolean(tab.isActive));
  tabButton.classList.toggle('is-loading', Boolean(tab.isLoading));
  tabButton.removeAttribute('data-removing');

  if (!closingTabIds.has(tab.id)) {
    tabButton.classList.remove('is-closing');
  }

  title.textContent = titleText;
  closeButton.setAttribute('aria-label', `Close ${titleText}`);
}

function renderTabs() {
  const nextTabIds = new Set();
  let orderIndex = 0;

  for (const tab of state.tabs) {
    let tabButton = tabElements.get(tab.id);
    const isNew = !tabButton;

    if (!tabButton) {
      tabButton = createTabElement(tab);
      tabElements.set(tab.id, tabButton);
    }

    updateTabElement(tabButton, tab);
    nextTabIds.add(tab.id);
    const expectedNode = tabsRoot.children[orderIndex] || addTabButton;
    if (expectedNode !== tabButton) {
      tabsRoot.insertBefore(tabButton, expectedNode);
    }
    orderIndex += 1;

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

  if (typeof layout.useNativeWindowControls === 'boolean') {
    document.body.classList.toggle('use-native-window-controls', layout.useNativeWindowControls);
    document.documentElement.classList.toggle('use-native-window-controls', layout.useNativeWindowControls);
  }
}

function applyWindowState(windowState) {
  if (
    !windowState ||
    typeof windowState.isMaximized !== 'boolean' ||
    typeof windowState.isFullScreen !== 'boolean'
  ) {
    return;
  }

  const maximized = windowState.isMaximized;
  const fullScreen = windowState.isFullScreen;
  document.body.classList.toggle('is-maximized', maximized);
  document.documentElement.classList.toggle('is-maximized', maximized);
  document.body.classList.toggle('is-full-screen', fullScreen);
  document.documentElement.classList.toggle('is-full-screen', fullScreen);
  windowMaximizeButton.setAttribute('aria-label', maximized ? 'Restore window' : 'Maximize window');
  windowMaximizeGlyph.textContent = maximized ? '\u2750' : '\u25A1';
}

addTabButton.append(createIconSpan('plus'));

addTabButton.addEventListener('click', () => {
  window.figmuxTabs.create({ sourceTabId: state.activeTabId });
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

window.figmuxTabs.onWillClose((tabId) => {
  beginClosingTab(tabId);
});

window.figmuxTabs.onLayout((layout) => {
  applyLayout(layout);
});

window.windowControls.onStateChanged((windowState) => {
  applyWindowState(windowState);
});

window.appShell.onToast((toast) => {
  showToast(toast);
});

window.figmuxTabs.list().then((initialState) => {
  state = initialState;
  renderTabs();
});
