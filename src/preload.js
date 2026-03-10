const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('figmuxTabs', {
  list: () => ipcRenderer.invoke('tabs:list'),
  create: (options) => ipcRenderer.invoke('tabs:create', options),
  close: (tabId) => ipcRenderer.invoke('tabs:close', tabId),
  activate: (tabId) => ipcRenderer.invoke('tabs:activate', tabId),
  showContextMenu: (tabId, x, y) => ipcRenderer.invoke('tabs:showContextMenu', { tabId, x, y }),
  move: (tabId, targetIndex) => ipcRenderer.invoke('tabs:move', tabId, targetIndex),
  navigate: (tabId, url) => ipcRenderer.invoke('tabs:navigate', tabId, url),
  onWillClose: (handler) => {
    const listener = (_event, tabId) => handler(tabId);
    ipcRenderer.on('tabs:willClose', listener);
    return () => {
      ipcRenderer.removeListener('tabs:willClose', listener);
    };
  },
  onStateChanged: (handler) => {
    const listener = (_event, state) => handler(state);
    ipcRenderer.on('tabs:stateChanged', listener);
    return () => {
      ipcRenderer.removeListener('tabs:stateChanged', listener);
    };
  },
  onLayout: (handler) => {
    const listener = (_event, layout) => handler(layout);
    ipcRenderer.on('tabs:layout', listener);
    return () => {
      ipcRenderer.removeListener('tabs:layout', listener);
    };
  }
});

contextBridge.exposeInMainWorld('windowControls', {
  minimize: () => ipcRenderer.invoke('window:minimize'),
  toggleMaximize: () => ipcRenderer.invoke('window:toggleMaximize'),
  close: () => ipcRenderer.invoke('window:close'),
  onStateChanged: (handler) => {
    const listener = (_event, state) => handler(state);
    ipcRenderer.on('window:stateChanged', listener);
    return () => {
      ipcRenderer.removeListener('window:stateChanged', listener);
    };
  }
});

contextBridge.exposeInMainWorld('appShell', {
  onToast: (handler) => {
    const listener = (_event, toast) => handler(toast);
    ipcRenderer.on('shell:toast', listener);
    return () => {
      ipcRenderer.removeListener('shell:toast', listener);
    };
  }
});
