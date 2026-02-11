const path = require('node:path');
const { app, BrowserWindow, shell, session } = require('electron');

const FIGMA_HOME = 'https://www.figma.com';
const PERSISTENT_PARTITION = 'persist:figmux';
const GOOGLE_OAUTH_HOSTS = new Set([
  'accounts.google.com',
  'oauth2.googleapis.com',
  'apis.google.com'
]);
const GOOGLE_AUTH_RELAY_SUFFIX = '.googleusercontent.com';
const FIGMA_AUTH_PATH_PREFIXES = ['/login', '/signup', '/oauth'];
const ABOUT_BLANK = 'about:blank';

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

  if (GOOGLE_OAUTH_HOSTS.has(parsed.hostname)) {
    return true;
  }

  if (isGoogleAuthDomain(parsed.hostname)) {
    return true;
  }

  if (!isFigmaUrl(input)) {
    return false;
  }

  return FIGMA_AUTH_PATH_PREFIXES.some((prefix) => parsed.pathname.startsWith(prefix));
}

function isAllowedPopupUrl(input) {
  return isOAuthUrl(input) || isAboutBlankUrl(input) || isFigmaUrl(input);
}

function isAllowedAuthOrFigmaUrl(input) {
  return isOAuthUrl(input) || isFigmaUrl(input);
}

function shouldAllowPopupFromFigma(url, referrerUrl) {
  if (isAllowedPopupUrl(url)) {
    return true;
  }

  if (isFigmaUrl(referrerUrl) && parseHttpsUrl(url)) {
    return true;
  }

  return false;
}

function routeExternal(input) {
  const parsed = parseHttpsUrl(input);
  if (!parsed) {
    return;
  }

  shell.openExternal(parsed.toString());
}

function buildWebPreferences(preloadPath) {
  return {
    preload: preloadPath,
    contextIsolation: true,
    nodeIntegration: false,
    sandbox: true,
    nativeWindowOpen: true,
    partition: PERSISTENT_PARTITION
  };
}

function createMainWindow() {
  const preloadPath = path.join(__dirname, 'preload.js');
  const mainWindow = new BrowserWindow({
    width: 1360,
    height: 860,
    minWidth: 960,
    minHeight: 640,
    autoHideMenuBar: true,
    title: 'Figmux',
    webPreferences: buildWebPreferences(preloadPath)
  });

  const webContents = mainWindow.webContents;

  webContents.setWindowOpenHandler(({ url, referrer }) => {
    if (shouldAllowPopupFromFigma(url, referrer.url)) {
      return {
        action: 'allow',
        overrideBrowserWindowOptions: {
          title: 'Figmux Login',
          width: 520,
          height: 740,
          minWidth: 440,
          minHeight: 600,
          autoHideMenuBar: true,
          webPreferences: buildWebPreferences(preloadPath)
        }
      };
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

    popupContents.setWindowOpenHandler(({ url }) => {
      if (isAllowedPopupUrl(url) || shouldAllowPopupFromFigma(url, popupContents.getURL())) {
        return {
          action: 'allow',
          overrideBrowserWindowOptions: {
            title: 'Figmux Login',
            width: 520,
            height: 740,
            minWidth: 440,
            minHeight: 600,
            autoHideMenuBar: true,
            webPreferences: buildWebPreferences(preloadPath)
          }
        };
      }

      routeExternal(url);
      return { action: 'deny' };
    });
  });

  webContents.on('will-navigate', (event, url) => {
    if (!isFigmaUrl(url) && !isOAuthUrl(url)) {
      event.preventDefault();
      routeExternal(url);
    }
  });

  mainWindow.loadURL(FIGMA_HOME);
}

app.whenReady().then(() => {
  const figmaPartitionSession = session.fromPartition(PERSISTENT_PARTITION);

  figmaPartitionSession.setPermissionRequestHandler((_webContents, _permission, callback) => {
    // This controls Chromium permission prompts (camera/mic/notifications), not cookie banners.
    callback(false);
  });

  createMainWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createMainWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
