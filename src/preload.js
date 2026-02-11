const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('figmuxTabs', {
  list: () => ipcRenderer.invoke('tabs:list'),
  create: () => ipcRenderer.invoke('tabs:create'),
  close: (tabId) => ipcRenderer.invoke('tabs:close', tabId),
  activate: (tabId) => ipcRenderer.invoke('tabs:activate', tabId),
  navigate: (tabId, url) => ipcRenderer.invoke('tabs:navigate', tabId, url),
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
