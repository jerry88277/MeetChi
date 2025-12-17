const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  // Window Controls
  minimize: () => ipcRenderer.send('window-minimize'),
  maximize: () => ipcRenderer.send('window-maximize'),
  close: () => ipcRenderer.send('window-close'),
  
  // Advanced Features
  setAlwaysOnTop: (flag) => ipcRenderer.send('set-always-on-top', flag),
  setIgnoreMouseEvents: (flag) => ipcRenderer.send('set-ignore-mouse-events', flag),
  setOpacity: (value) => ipcRenderer.send('set-opacity', value),
  
  // Resize (Manual)
  resizeWindowStart: (direction) => ipcRenderer.send('resize-window-start', direction),
  resizeWindowStop: () => ipcRenderer.send('resize-window-stop'),
  resizeWindowContent: (size) => ipcRenderer.send('resize-window-content', size),

  // System Audio (Future)
  getDesktopSources: () => ipcRenderer.invoke('get-desktop-sources')
});

// Legacy support for direct ipcRenderer usage if needed (optional)
contextBridge.exposeInMainWorld('ipcRenderer', {
    send: (channel, data) => ipcRenderer.send(channel, data),
    on: (channel, func) => ipcRenderer.on(channel, (event, ...args) => func(event, ...args)),
    removeListener: (channel, func) => ipcRenderer.removeListener(channel, func)
});
