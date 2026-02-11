const path = require('node:path');
const { app, BrowserWindow, shell, session } = require('electron');

const FIGMA_HOME = 'https://www.figma.com';
const PERSISTENT_PARTITION = 'persist:figmux';

function isAllowedUrl(input) {
  try {
    const parsed = new URL(input);
    if (parsed.protocol !== 'https:') {
      return false;
    }

    return parsed.hostname === 'figma.com' || parsed.hostname.endsWith('.figma.com');
  } catch {
    return false;
  }
}

function createMainWindow() {
  const mainWindow = new BrowserWindow({
    width: 1360,
    height: 860,
    minWidth: 960,
    minHeight: 640,
    autoHideMenuBar: true,
    title: 'Figmux',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      partition: PERSISTENT_PARTITION
    }
  });

  const webContents = mainWindow.webContents;

  webContents.setWindowOpenHandler(({ url }) => {
    if (isAllowedUrl(url)) {
      return { action: 'allow' };
    }

    shell.openExternal(url);
    return { action: 'deny' };
  });

  webContents.on('will-navigate', (event, url) => {
    if (!isAllowedUrl(url)) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });

  mainWindow.loadURL(FIGMA_HOME);
}

app.whenReady().then(() => {
  const figmaPartitionSession = session.fromPartition(PERSISTENT_PARTITION);

  figmaPartitionSession.setPermissionRequestHandler((_webContents, _permission, callback) => {
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
