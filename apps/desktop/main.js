const { app, BrowserWindow, Menu, globalShortcut, ipcMain, desktopCapturer } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const isDev = require('electron-is-dev');

let mainWindow;
let backendProcess;
let llmProcess;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 800,
    height: 600,
    frame: false, // No frame (title bar, close buttons)
    transparent: true, // Transparent background
    alwaysOnTop: true, // Always on top
    hasShadow: false, // Disable shadow for cleaner transparency
    resizable: true, // Allow resizing at edges
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // Load the Next.js app
  const startURL = isDev
    ? 'http://localhost:3000'
    : `file://${path.join(__dirname, '../frontend/out/index.html')}`; // Assuming Next.js exports to 'out' folder

  mainWindow.loadURL(startURL);

  if (isDev) {
    // mainWindow.webContents.openDevTools();
  }

  // Handle window closing
  mainWindow.on('closed', () => (mainWindow = null));

  // Custom menu (optional, can be empty or hidden)
  Menu.setApplicationMenu(null); // Hide default menu bar
  
  // Custom drag area for frameless window
  // Add a CSS rule in your Next.js app: `-webkit-app-region: drag;` to a div
  // and `-webkit-app-region: no-drag;` to interactive elements inside it.

  // Global shortcut to show/hide the window
  globalShortcut.register('CommandOrControl+Shift+T', () => {
    if (mainWindow.isVisible()) {
      mainWindow.hide();
    } else {
      mainWindow.show();
    }
  });
}

// --- IPC Handlers ---
ipcMain.on('window-minimize', () => {
    if (mainWindow) mainWindow.minimize();
});

ipcMain.on('window-maximize', () => {
    if (mainWindow) {
        if (mainWindow.isMaximized()) {
            mainWindow.unmaximize();
        } else {
            mainWindow.maximize();
        }
    }
});

ipcMain.on('window-close', () => {
    if (mainWindow) mainWindow.close();
});

ipcMain.on('set-always-on-top', (event, flag) => {
    if (mainWindow) mainWindow.setAlwaysOnTop(flag);
});

ipcMain.on('set-opacity', (event, value) => {
    if (mainWindow) mainWindow.setOpacity(value);
});

ipcMain.on('set-ignore-mouse-events', (event, flag) => {
    if (mainWindow) {
        if (flag) {
            // Forward mouse events to underlying windows
            mainWindow.setIgnoreMouseEvents(true, { forward: true });
        } else {
            mainWindow.setIgnoreMouseEvents(false);
        }
    }
});

ipcMain.handle('get-desktop-sources', async () => {
    const sources = await desktopCapturer.getSources({ types: ['screen', 'window'] });
    return sources;
});

// --- Manual Resizing Logic for Frameless Transparent Window ---
let isResizing = false;
let resizeDirection = '';
let startMouseX = 0;
let startMouseY = 0;
let startWindowBounds = { x: 0, y: 0, width: 0, height: 0 };

ipcMain.on('resize-window-start', (event, direction) => {
    if (!mainWindow) return;
    const { screen } = require('electron');
    const point = screen.getCursorScreenPoint();
    startMouseX = point.x;
    startMouseY = point.y;
    startWindowBounds = mainWindow.getBounds();
    resizeDirection = direction;
    isResizing = true;
    
    // Start a timer to poll mouse position since we can't capture global mouse events easily in main without native modules
    // A simple interval is often enough for this hack
    const pollInterval = setInterval(() => {
        if (!isResizing || !mainWindow) {
            clearInterval(pollInterval);
            return;
        }
        
        const currentPoint = screen.getCursorScreenPoint();
        const deltaX = currentPoint.x - startMouseX;
        const deltaY = currentPoint.y - startMouseY;
        
        let newBounds = { ...startWindowBounds };
        
        if (resizeDirection.includes('right')) {
            newBounds.width = Math.max(300, startWindowBounds.width + deltaX);
        }
        if (resizeDirection.includes('bottom')) {
            newBounds.height = Math.max(100, startWindowBounds.height + deltaY);
        }
        if (resizeDirection.includes('left')) {
            const newWidth = Math.max(300, startWindowBounds.width - deltaX);
            newBounds.x = startWindowBounds.x + (startWindowBounds.width - newWidth);
            newBounds.width = newWidth;
        }
        if (resizeDirection.includes('top')) {
             const newHeight = Math.max(100, startWindowBounds.height - deltaY);
             newBounds.y = startWindowBounds.y + (startWindowBounds.height - newHeight);
             newBounds.height = newHeight;
        }

        mainWindow.setBounds(newBounds);
    }, 1000 / 60); // 60 FPS
});

ipcMain.on('resize-window-stop', () => {
    isResizing = false;
});

ipcMain.on('resize-window-content', (event, { width, height }) => {
    if (!mainWindow) return;
    const bounds = mainWindow.getBounds();
    // Keep current width if width not provided, but update height
    // We might want to keep x/y stable, or adjust if growing upwards? 
    // Standard behavior is grow downwards.
    mainWindow.setBounds({
        x: bounds.x,
        y: bounds.y,
        width: width || bounds.width,
        height: Math.round(height)
    });
});

// --- Backend and LLM Service Management ---
function startBackend() {
  const backendPath = path.join(__dirname, '../../apps/backend');
  const pythonExecutable = path.join(backendPath, '.venv/Scripts/python.exe'); 
  
  // Use 'python -m uvicorn' which is more robust than looking for uvicorn.exe
  console.log(`Starting Backend from: ${backendPath}`);
  
  backendProcess = spawn(pythonExecutable, ['-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8000'], {
    cwd: backendPath,
    shell: true,
    env: { ...process.env, PYTHONPATH: backendPath } // Ensure PYTHONPATH includes app root
  });

  backendProcess.stdout.on('data', (data) => {
    console.log(`Backend stdout: ${data}`);
  });

  backendProcess.stderr.on('data', (data) => {
    console.error(`Backend stderr: ${data}`);
  });

  backendProcess.on('close', (code) => {
    console.log(`Backend process exited with code ${code}`);
  });
}

function startLlmService() {
  const llmPath = path.join(__dirname, '../../apps/llm_service');
  const pythonExecutable = path.join(llmPath, '.venv/Scripts/python.exe');

  console.log(`Starting LLM Service from: ${llmPath}`);

  llmProcess = spawn(pythonExecutable, ['app.py'], {
    cwd: llmPath,
    shell: true,
    env: { ...process.env, PYTHONPATH: llmPath }
  });

  llmProcess.stdout.on('data', (data) => {
    console.log(`LLM Service stdout: ${data}`);
  });

  llmProcess.stderr.on('data', (data) => {
    console.error(`LLM Service stderr: ${data}`);
  });

  llmProcess.on('close', (code) => {
    console.log(`LLM Service process exited with code ${code}`);
  });
}

function stopServices() {
  if (backendProcess) {
    console.log("Stopping backend service...");
    backendProcess.kill(); // Send SIGTERM
  }
  if (llmProcess) {
    console.log("Stopping LLM service...");
    llmProcess.kill(); // Send SIGTERM
  }
}

app.whenReady().then(() => {
  startBackend();
  startLlmService();
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('will-quit', () => {
  // Unregister all shortcuts.
  globalShortcut.unregisterAll();
  stopServices(); // Ensure services are stopped when Electron app quits
});
