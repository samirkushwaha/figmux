const fs = require('node:fs');
const path = require('node:path');
const {
  app,
  BrowserWindow,
  WebContentsView,
  shell,
  session,
  ipcMain,
  Menu,
  webContents: electronWebContents
} = require('electron');

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
const inputDebugEnabled = process.env.FIGMUX_INPUT_DEBUG === '1';

function appendCommandLineCsvSwitch(name, values) {
  const existing = app.commandLine.getSwitchValue(name);
  const merged = new Set(
    existing
      .split(',')
      .map((value) => value.trim())
      .filter(Boolean)
  );

  for (const value of values) {
    if (value) {
      merged.add(value);
    }
  }

  if (merged.size > 0) {
    app.commandLine.appendSwitch(name, Array.from(merged).join(','));
  }
}

if (process.platform === 'linux') {
  app.commandLine.appendSwitch('class', 'com.figmux.app');
  app.commandLine.appendSwitch('enable-pinch');
  app.commandLine.appendSwitch('touch-events', 'enabled');
  appendCommandLineCsvSwitch('disable-features', [
    'AcceleratedVideoDecodeLinuxGL',
    'VaapiVideoDecoder'
  ]);

  if (!inputDebugEnabled) {
    // Suppress noisy Chromium driver/runtime logs in normal runs.
    app.commandLine.appendSwitch('disable-logging');
    app.commandLine.appendSwitch('log-level', '3');
  }
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

function isControlModified(input) {
  return (
    Boolean(input && input.control) ||
    (Array.isArray(input && input.modifiers) && input.modifiers.includes('control'))
  );
}

function canCanvasZoom(url) {
  const parsed = parseHttpsUrl(url);
  if (!parsed) {
    return false;
  }

  if (!isFigmaUrl(url) || isOAuthUrl(url)) {
    return false;
  }

  return (
    parsed.pathname.startsWith('/file/') ||
    parsed.pathname.startsWith('/design/') ||
    parsed.pathname.startsWith('/proto/') ||
    parsed.pathname.startsWith('/board/')
  );
}

function findTabIdByWebContents(sourceWebContents) {
  if (!sourceWebContents) {
    return null;
  }

  for (const [tabId, tab] of tabs.entries()) {
    if (tab.view.webContents === sourceWebContents) {
      return tabId;
    }
  }

  return null;
}

function handleTabShortcut(event, input, sourceWebContents = null) {
  const ctrlOrMeta = Boolean(input && (input.control || input.meta));
  if (!ctrlOrMeta || !input || input.type !== 'keyDown') {
    return false;
  }

  const key = (input.key || '').toLowerCase();
  let handled = true;

  if (key === 't') {
    createTab({ activate: true });
  } else if (key === 'w') {
    const tabIdFromSource = findTabIdByWebContents(sourceWebContents);
    const focusedWebContents =
      sourceWebContents ||
      (typeof electronWebContents.getFocusedWebContents === 'function'
        ? electronWebContents.getFocusedWebContents()
        : null);
    const focusedTabId = findTabIdByWebContents(focusedWebContents);
    const tabIdToClose = activeTabId || focusedTabId || tabIdFromSource;
    closeTab(tabIdToClose);
  } else if (key === 'q') {
    app.quit();
  } else if (key === 'tab') {
    cycleTabs(Boolean(input.shift));
  } else {
    handled = false;
  }

  if (handled && event) {
    event.preventDefault();
    if (typeof event.stopPropagation === 'function') {
      event.stopPropagation();
    }
  }

  return handled;
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
  let forwardingSyntheticZoom = false;
  let pinchUpdateQueued = false;
  const logInputDebug = inputDebugEnabled;
  const lastPointer = { x: 0, y: 0 };

  function sendCanvasZoomWheel(zoomIn) {
    forwardingSyntheticZoom = true;
    try {
      webContents.sendInputEvent({
        type: 'mouseWheel',
        x: lastPointer.x,
        y: lastPointer.y,
        deltaX: 0,
        deltaY: zoomIn ? -120 : 120,
        canScroll: true,
        modifiers: ['control']
      });
    } finally {
      forwardingSyntheticZoom = false;
    }
  }

  function extractZoomDirection(input) {
    const numericFields = ['scale', 'deltaY', 'wheelDeltaY', 'wheelTicksY', 'delta'];
    for (const field of numericFields) {
      const value = input && input[field];
      if (typeof value === 'number' && Number.isFinite(value) && value !== 0 && value !== 1) {
        if (field === 'scale') {
          return value > 1;
        }
        return value < 0;
      }
    }
    return null;
  }

  webContents
    .setVisualZoomLevelLimits(1, 3)
    .catch(() => {
      // Ignore platforms where visual zoom limits are unsupported.
    });

  webContents.setZoomFactor(1);

  function handlePinchGestureUpdate() {
    pinchUpdateQueued = false;
    const zoomFactor = webContents.getZoomFactor();
    const zoomIn = zoomFactor > 1.001;
    const zoomOut = zoomFactor < 0.999;

    if ((zoomIn || zoomOut) && canCanvasZoom(tab.url) && !forwardingSyntheticZoom) {
      sendCanvasZoomWheel(zoomIn);
    }

    if (zoomFactor !== 1) {
      webContents.setZoomFactor(1);
    }
  }

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

  webContents.on('input-event', (_event, input) => {
    if (forwardingSyntheticZoom) {
      return;
    }

    if (
      logInputDebug &&
      (input.type.startsWith('gesture') || input.type === 'mouseWheel')
    ) {
      console.log('[figmux-input]', {
        type: input.type,
        input,
        control: input.control,
        modifiers: input.modifiers,
        x: input.x,
        y: input.y
      });
    }

    if (input.type === 'gesturePinchUpdate') {
      const direction = extractZoomDirection(input);
      if (direction !== null) {
        if (canCanvasZoom(tab.url)) {
          sendCanvasZoomWheel(direction);
        }
      } else if (!pinchUpdateQueued) {
        pinchUpdateQueued = true;
        setTimeout(handlePinchGestureUpdate, 0);
      }
    }
  });

  webContents.on('before-mouse-event', (event, mouse) => {
    if (forwardingSyntheticZoom) {
      return;
    }

    if (
      logInputDebug &&
      mouse &&
      mouse.type === 'mouseWheel'
    ) {
      console.log('[figmux-mouse]', {
        type: mouse.type,
        mouse,
        control: mouse.control,
        modifiers: mouse.modifiers,
        x: mouse.x,
        y: mouse.y
      });
    }

    if (Number.isFinite(mouse.x) && Number.isFinite(mouse.y)) {
      lastPointer.x = Math.round(mouse.x);
      lastPointer.y = Math.round(mouse.y);
    }

    if (mouse && mouse.type === 'mouseWheel' && isControlModified(mouse)) {
      event.preventDefault();
      const direction = extractZoomDirection(mouse);
      if (direction !== null && canCanvasZoom(tab.url)) {
        sendCanvasZoomWheel(direction);
      }
    }
  });

  webContents.on('zoom-changed', (_event, zoomDirection) => {
    if (logInputDebug) {
      console.log('[figmux-zoom]', {
        direction: zoomDirection,
        url: tab.url
      });
    }
    // Keep shell/page zoom at 1x; pinch forwarding is handled from gesture updates.
    webContents.setZoomFactor(1);
  });

  webContents.on('before-input-event', (event, input) => {
    handleTabShortcut(event, input, webContents);
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
    transparent: true,
    backgroundColor: '#00000000',
    webPreferences: buildShellWebPreferences()
  };

  if (process.platform === 'linux' && appIconPath) {
    windowOptions.icon = appIconPath;
  }

  mainWindow = new BrowserWindow(windowOptions);

  mainWindow.webContents
    .setVisualZoomLevelLimits(1, 1)
    .catch(() => {
      // Ignore platforms where visual zoom limits are unsupported.
    });
  mainWindow.webContents.setZoomFactor(1);

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

  mainWindow.webContents.on('before-mouse-event', (event, mouse) => {
    if (mouse && mouse.type === 'mouseWheel' && isControlModified(mouse)) {
      event.preventDefault();
    }
  });

  mainWindow.webContents.on('zoom-changed', () => {
    mainWindow.webContents.setZoomFactor(1);
  });

  mainWindow.webContents.on('before-input-event', (event, input) => {
    const focusedWebContents =
      typeof electronWebContents.getFocusedWebContents === 'function'
        ? electronWebContents.getFocusedWebContents()
        : null;

    // Avoid double-handling shortcuts when a tab WebContents is focused.
    if (findTabIdByWebContents(focusedWebContents)) {
      return;
    }

    handleTabShortcut(event, input, focusedWebContents);
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
  if (process.platform === 'linux') {
    Menu.setApplicationMenu(null);
  }

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
