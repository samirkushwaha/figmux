const fs = require('node:fs');
const path = require('node:path');
const { app, BrowserWindow, WebContentsView, shell, session, ipcMain } = require('electron');

const FIGMA_HOME = 'https://www.figma.com';
const FIGMA_RECENTS = 'https://www.figma.com/files/recent';
const PERSISTENT_PARTITION = 'persist:figmux';
const GOOGLE_OAUTH_HOSTS = new Set([
  'accounts.google.com',
  'oauth2.googleapis.com',
  'apis.google.com'
]);
const GOOGLE_AUTH_RELAY_SUFFIX = '.googleusercontent.com';
const FIGMA_AUTH_PATH_PREFIXES = ['/login', '/signup', '/oauth'];
const ABOUT_BLANK = 'about:blank';
const TITLEBAR_HEIGHT = 36;
const WINDOW_CONTROLS_INSET = 112;
const TAB_STATE_FILE = 'tabs-state.json';
const APP_ICON_PNG_FILENAME = 'com.figmux.app.png';
const APP_ICON_SVG_FILENAME = 'com.figmux.app.svg';
const FLATPAK_BITMAP_ICON_DIR = '/app/share/icons/hicolor/512x512/apps';
const FLATPAK_ICON_DIR = '/app/share/icons/hicolor/scalable/apps';

let mainWindow;
let activeTabId = null;
let tabIdCounter = 0;
let tabStateWriteTimer;
let shellReady = false;

/** @type {Map<string, {id: string, view: import('electron').WebContentsView, title: string, url: string, isLoading: boolean, canGoBack: boolean, canGoForward: boolean}>} */
const tabs = new Map();
/** @type {string[]} */
const tabOrder = [];

function resolveAppIconPath() {
  const candidatePaths = [
    path.join(__dirname, '..', 'assets', APP_ICON_PNG_FILENAME),
    path.join(process.cwd(), 'assets', APP_ICON_PNG_FILENAME),
    path.join(FLATPAK_BITMAP_ICON_DIR, APP_ICON_PNG_FILENAME),
    path.join(__dirname, '..', 'assets', APP_ICON_SVG_FILENAME),
    path.join(process.cwd(), 'assets', APP_ICON_SVG_FILENAME),
    path.join(FLATPAK_ICON_DIR, APP_ICON_SVG_FILENAME)
  ];

  for (const candidatePath of candidatePaths) {
    if (fs.existsSync(candidatePath)) {
      return candidatePath;
    }
  }

  return null;
}

const appIconPath = resolveAppIconPath();

if (process.platform === 'linux') {
  app.commandLine.appendSwitch('class', 'com.figmux.app');
}

function parseHttpsUrl(input) {
  try {
    const parsed = new URL(input);
    if (parsed.protocol !== 'https:') {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function isAboutBlankUrl(input) {
  if (!input) {
    return true;
  }

  return input === ABOUT_BLANK || input.startsWith(`${ABOUT_BLANK}#`);
}

function isGoogleAuthDomain(hostname) {
  return (
    GOOGLE_OAUTH_HOSTS.has(hostname) ||
    hostname === 'google.com' ||
    hostname.endsWith('.google.com') ||
    hostname.endsWith(GOOGLE_AUTH_RELAY_SUFFIX)
  );
}

function isFigmaUrl(input) {
  const parsed = parseHttpsUrl(input);
  if (!parsed) {
    return false;
  }

  return parsed.hostname === 'figma.com' || parsed.hostname.endsWith('.figma.com');
}

function isOAuthUrl(input) {
  const parsed = parseHttpsUrl(input);
  if (!parsed) {
    return false;
  }

  if (isGoogleAuthDomain(parsed.hostname)) {
    return true;
  }

  if (!isFigmaUrl(input)) {
    return false;
  }

  return FIGMA_AUTH_PATH_PREFIXES.some((prefix) => parsed.pathname.startsWith(prefix));
}

function isAllowedAuthOrFigmaUrl(input) {
  return isOAuthUrl(input) || isFigmaUrl(input);
}

function shouldOpenAuthPopup(url, referrerUrl) {
  if (isOAuthUrl(url) || isAboutBlankUrl(url)) {
    return true;
  }

  return isOAuthUrl(referrerUrl) && isFigmaUrl(url);
}

function canRestoreUrl(input) {
  return Boolean(parseHttpsUrl(input)) && (isFigmaUrl(input) || isOAuthUrl(input));
}

function routeExternal(input) {
  try {
    shell.openExternal(input);
  } catch {
    // Ignore malformed or unsupported schemes.
  }
}

function buildShellWebPreferences() {
  return {
    preload: path.join(__dirname, 'preload.js'),
    contextIsolation: true,
    nodeIntegration: false,
    sandbox: true
  };
}

function buildTabWebPreferences() {
  return {
    contextIsolation: true,
    nodeIntegration: false,
    sandbox: true,
    nativeWindowOpen: true,
    partition: PERSISTENT_PARTITION
  };
}

function buildAuthPopupWindowOptions() {
  const options = {
    title: 'Figmux Login',
    width: 520,
    height: 740,
    minWidth: 440,
    minHeight: 600,
    autoHideMenuBar: true,
    webPreferences: buildTabWebPreferences()
  };

  if (process.platform === 'linux' && appIconPath) {
    options.icon = appIconPath;
  }

  return options;
}

function canGoBackCompat(webContents) {
  if (
    webContents.navigationHistory &&
    typeof webContents.navigationHistory.canGoBack === 'function'
  ) {
    return webContents.navigationHistory.canGoBack();
  }

  if (typeof webContents.canGoBack === 'function') {
    return webContents.canGoBack();
  }

  return false;
}

function canGoForwardCompat(webContents) {
  if (
    webContents.navigationHistory &&
    typeof webContents.navigationHistory.canGoForward === 'function'
  ) {
    return webContents.navigationHistory.canGoForward();
  }

  if (typeof webContents.canGoForward === 'function') {
    return webContents.canGoForward();
  }

  return false;
}

function nextTabId() {
  tabIdCounter += 1;
  return `tab-${tabIdCounter}`;
}

function toTabSnapshot(tabId) {
  const tab = tabs.get(tabId);
  if (!tab) {
    return null;
  }

  return {
    id: tab.id,
    title: tab.title,
    url: tab.url,
    isLoading: tab.isLoading,
    canGoBack: tab.canGoBack,
    canGoForward: tab.canGoForward,
    isActive: tab.id === activeTabId
  };
}

function getTabsSnapshot() {
  return {
    activeTabId,
    tabs: tabOrder.map(toTabSnapshot).filter(Boolean)
  };
}

function emitTabsState() {
  if (!mainWindow || mainWindow.isDestroyed() || !shellReady) {
    return;
  }

  mainWindow.webContents.send('tabs:stateChanged', getTabsSnapshot());
}

function emitWindowState() {
  if (!mainWindow || mainWindow.isDestroyed() || !shellReady) {
    return;
  }

  mainWindow.webContents.send('window:stateChanged', {
    isMaximized: mainWindow.isMaximized()
  });
}

function getTabStatePath() {
  return path.join(app.getPath('userData'), TAB_STATE_FILE);
}

function queuePersistTabState() {
  clearTimeout(tabStateWriteTimer);
  tabStateWriteTimer = setTimeout(() => {
    const payload = {
      activeTabId,
      tabs: tabOrder
        .map((tabId) => tabs.get(tabId))
        .filter(Boolean)
        .map((tab) => ({
          id: tab.id,
          url: tab.url,
          title: tab.title
        }))
    };

    try {
      fs.writeFileSync(getTabStatePath(), JSON.stringify(payload), 'utf8');
    } catch {
      // Persistence failures should never crash the app.
    }
  }, 300);
}

function trackTabState(tab) {
  const { webContents } = tab.view;

  webContents.setWindowOpenHandler(({ url, referrer }) => {
    if (shouldOpenAuthPopup(url, referrer.url)) {
      return {
        action: 'allow',
        overrideBrowserWindowOptions: buildAuthPopupWindowOptions()
      };
    }

    if (isFigmaUrl(url)) {
      createTab({ url, activate: true });
      return { action: 'deny' };
    }

    routeExternal(url);
    return { action: 'deny' };
  });

  webContents.on('did-create-window', (authWindow) => {
    authWindow.setMenuBarVisibility(false);
    authWindow.setTitle('Figmux Login');
    authWindow.setMinimumSize(440, 600);

    const popupContents = authWindow.webContents;

    popupContents.on('will-navigate', (event, url) => {
      if (!isAllowedAuthOrFigmaUrl(url)) {
        event.preventDefault();
        routeExternal(url);
      }
    });

    popupContents.setWindowOpenHandler(({ url, referrer }) => {
      if (shouldOpenAuthPopup(url, referrer.url)) {
        return {
          action: 'allow',
          overrideBrowserWindowOptions: buildAuthPopupWindowOptions()
        };
      }

      routeExternal(url);
      return { action: 'deny' };
    });
  });

  webContents.on('will-navigate', (event, url) => {
    if (!isAllowedAuthOrFigmaUrl(url)) {
      event.preventDefault();
      routeExternal(url);
    }
  });

  webContents.on('page-title-updated', (event, title) => {
    event.preventDefault();
    tab.title = title || 'Figma';
    emitTabsState();
    queuePersistTabState();
  });

  webContents.on('did-start-loading', () => {
    tab.isLoading = true;
    emitTabsState();
  });

  webContents.on('did-stop-loading', () => {
    tab.isLoading = false;
    tab.url = webContents.getURL() || tab.url;
    tab.canGoBack = canGoBackCompat(webContents);
    tab.canGoForward = canGoForwardCompat(webContents);
    emitTabsState();
    queuePersistTabState();
  });

  webContents.on('did-navigate', (_event, url) => {
    tab.url = url;
    tab.canGoBack = canGoBackCompat(webContents);
    tab.canGoForward = canGoForwardCompat(webContents);
    emitTabsState();
    queuePersistTabState();
  });

  webContents.on('did-navigate-in-page', (_event, url) => {
    tab.url = url;
    tab.canGoBack = canGoBackCompat(webContents);
    tab.canGoForward = canGoForwardCompat(webContents);
    emitTabsState();
    queuePersistTabState();
  });

  webContents.on('before-input-event', (event, input) => {
    const ctrlOrMeta = input.control || input.meta;
    if (!ctrlOrMeta || input.type !== 'keyDown') {
      return;
    }

    const key = (input.key || '').toLowerCase();

    if (key === 't') {
      event.preventDefault();
      createTab({ activate: true });
      return;
    }

    if (key === 'w') {
      event.preventDefault();
      closeTab(activeTabId);
      return;
    }

    if (key === 'tab') {
      event.preventDefault();
      cycleTabs(input.shift);
    }
  });
}

function updateActiveTabBounds() {
  if (!mainWindow || mainWindow.isDestroyed() || !activeTabId) {
    return;
  }

  const active = tabs.get(activeTabId);
  if (!active) {
    return;
  }

  const [width, height] = mainWindow.getContentSize();
  const tabY = TITLEBAR_HEIGHT;
  active.view.setBounds({
    x: 0,
    y: tabY,
    width,
    height: Math.max(0, height - tabY)
  });
}

function queueActiveTabBoundsSync() {
  updateActiveTabBounds();
  setTimeout(() => {
    updateActiveTabBounds();
  }, 0);
}

function activateTab(tabId) {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }

  const target = tabs.get(tabId);
  if (!target) {
    return;
  }

  if (activeTabId === tabId) {
    target.view.webContents.focus();
    return;
  }

  const previous = tabs.get(activeTabId);
  if (previous) {
    mainWindow.contentView.removeChildView(previous.view);
  }

  activeTabId = tabId;
  mainWindow.contentView.addChildView(target.view);
  updateActiveTabBounds();
  target.view.webContents.focus();
  emitTabsState();
  queuePersistTabState();
}

function createTab({ url = FIGMA_RECENTS, activate = true, id = nextTabId() } = {}) {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return null;
  }

  const safeUrl = parseHttpsUrl(url) ? url : FIGMA_HOME;

  const view = new WebContentsView({
    webPreferences: buildTabWebPreferences()
  });

  const tab = {
    id,
    view,
    title: 'Figma',
    url: safeUrl,
    isLoading: false,
    canGoBack: false,
    canGoForward: false
  };

  tabs.set(id, tab);
  tabOrder.push(id);
  trackTabState(tab);

  if (activate || !activeTabId) {
    activateTab(id);
  }

  view.webContents.loadURL(safeUrl);
  emitTabsState();
  queuePersistTabState();
  return id;
}

function closeTab(tabId) {
  if (!tabId) {
    return;
  }

  const tab = tabs.get(tabId);
  if (!tab) {
    return;
  }

  const tabIndex = tabOrder.indexOf(tabId);
  if (tabIndex >= 0) {
    tabOrder.splice(tabIndex, 1);
  }

  const isActive = activeTabId === tabId;
  if (isActive && mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.contentView.removeChildView(tab.view);
  }

  tabs.delete(tabId);
  tab.view.webContents.destroy();

  if (tabOrder.length === 0) {
    activeTabId = null;
    createTab({ url: FIGMA_RECENTS, activate: true });
    return;
  }

  if (isActive) {
    const nextIndex = Math.min(tabIndex, tabOrder.length - 1);
    activateTab(tabOrder[nextIndex]);
  } else {
    emitTabsState();
    queuePersistTabState();
  }
}

function cycleTabs(reverse) {
  if (tabOrder.length < 2 || !activeTabId) {
    return;
  }

  const currentIndex = tabOrder.indexOf(activeTabId);
  if (currentIndex < 0) {
    return;
  }

  const offset = reverse ? -1 : 1;
  const nextIndex = (currentIndex + offset + tabOrder.length) % tabOrder.length;
  activateTab(tabOrder[nextIndex]);
}

function loadSavedTabState() {
  try {
    const raw = fs.readFileSync(getTabStatePath(), 'utf8');
    const parsed = JSON.parse(raw);
    if (!parsed || !Array.isArray(parsed.tabs)) {
      return null;
    }

    const restoredTabs = [];
    for (const entry of parsed.tabs) {
      if (!entry || typeof entry.id !== 'string' || typeof entry.url !== 'string') {
        continue;
      }

      if (!canRestoreUrl(entry.url)) {
        continue;
      }

      restoredTabs.push({
        id: entry.id,
        url: entry.url
      });

      const suffix = Number(entry.id.replace('tab-', ''));
      if (Number.isFinite(suffix)) {
        tabIdCounter = Math.max(tabIdCounter, suffix);
      }
    }

    return {
      activeTabId: typeof parsed.activeTabId === 'string' ? parsed.activeTabId : null,
      tabs: restoredTabs
    };
  } catch {
    return null;
  }
}

function restoreTabs() {
  const state = loadSavedTabState();
  if (!state || state.tabs.length === 0) {
    createTab({ url: FIGMA_RECENTS, activate: true });
    return;
  }

  for (const tabEntry of state.tabs) {
    createTab({ id: tabEntry.id, url: tabEntry.url, activate: false });
  }

  if (state.activeTabId && tabs.has(state.activeTabId)) {
    activateTab(state.activeTabId);
  } else {
    activateTab(tabOrder[0]);
  }
}

function setupIpc() {
  ipcMain.handle('tabs:list', () => getTabsSnapshot());

  ipcMain.handle('tabs:create', () => {
    createTab({ activate: true });
    return getTabsSnapshot();
  });

  ipcMain.handle('tabs:close', (_event, tabId) => {
    closeTab(tabId);
    return getTabsSnapshot();
  });

  ipcMain.handle('tabs:activate', (_event, tabId) => {
    activateTab(tabId);
    return getTabsSnapshot();
  });

  ipcMain.handle('tabs:navigate', (_event, tabId, url) => {
    const tab = tabs.get(tabId);
    if (tab && parseHttpsUrl(url)) {
      tab.view.webContents.loadURL(url);
      activateTab(tabId);
    }
    return getTabsSnapshot();
  });

  ipcMain.handle('window:minimize', () => {
    if (!mainWindow || mainWindow.isDestroyed()) {
      return;
    }
    mainWindow.minimize();
  });

  ipcMain.handle('window:toggleMaximize', () => {
    if (!mainWindow || mainWindow.isDestroyed()) {
      return;
    }

    if (mainWindow.isMaximized()) {
      mainWindow.unmaximize();
    } else {
      mainWindow.maximize();
    }
  });

  ipcMain.handle('window:close', () => {
    if (!mainWindow || mainWindow.isDestroyed()) {
      return;
    }
    mainWindow.close();
  });
}

function createMainWindow() {
  const windowOptions = {
    width: 1360,
    height: 860,
    minWidth: 960,
    minHeight: 640,
    autoHideMenuBar: true,
    title: 'Figmux',
    frame: false,
    webPreferences: buildShellWebPreferences()
  };

  if (process.platform === 'linux' && appIconPath) {
    windowOptions.icon = appIconPath;
  }

  mainWindow = new BrowserWindow(windowOptions);

  const onWindowGeometryChanged = () => {
    queueActiveTabBoundsSync();
    emitTabsState();
    emitWindowState();
  };

  mainWindow.on('resize', onWindowGeometryChanged);
  mainWindow.on('maximize', onWindowGeometryChanged);
  mainWindow.on('unmaximize', onWindowGeometryChanged);
  mainWindow.on('enter-full-screen', onWindowGeometryChanged);
  mainWindow.on('leave-full-screen', onWindowGeometryChanged);
  mainWindow.on('restore', onWindowGeometryChanged);

  mainWindow.webContents.on('before-input-event', (event, input) => {
    const ctrlOrMeta = input.control || input.meta;
    if (!ctrlOrMeta || input.type !== 'keyDown') {
      return;
    }

    const key = (input.key || '').toLowerCase();

    if (key === 't') {
      event.preventDefault();
      createTab({ activate: true });
      return;
    }

    if (key === 'w') {
      event.preventDefault();
      closeTab(activeTabId);
      return;
    }

    if (key === 'tab') {
      event.preventDefault();
      cycleTabs(input.shift);
    }
  });

  mainWindow.webContents.on('did-finish-load', () => {
    shellReady = true;
    queueActiveTabBoundsSync();
    mainWindow.webContents.send('tabs:layout', {
      titlebarHeight: TITLEBAR_HEIGHT,
      windowControlsInset: WINDOW_CONTROLS_INSET
    });
    emitTabsState();
    emitWindowState();
  });

  mainWindow.on('closed', () => {
    shellReady = false;
    clearTimeout(tabStateWriteTimer);
  });

  mainWindow.loadFile(path.join(__dirname, 'ui', 'index.html'));
}

if (process.platform === 'linux') {
  app.setDesktopName('com.figmux.app.desktop');
}

app.whenReady().then(() => {
  const figmaPartitionSession = session.fromPartition(PERSISTENT_PARTITION);

  figmaPartitionSession.setPermissionRequestHandler((_webContents, _permission, callback) => {
    // This controls Chromium permission prompts (camera/mic/notifications), not cookie banners.
    callback(false);
  });

  setupIpc();
  createMainWindow();
  restoreTabs();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createMainWindow();
      restoreTabs();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
