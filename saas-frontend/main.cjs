const { app, BrowserWindow, session } = require("electron");
const path = require("path");

const isDev = !app.isPackaged || process.env.ELECTRON_DEV === "1";
const prodIndexPath = path.join(__dirname, "dist", "index.html");

function createWindow() {
  const win = new BrowserWindow({
    width: 1200,
    height: 800,
    title: "AICCEL",
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      plugins: true,
    },
  });

  // Set Content-Security-Policy to silence Electron security warning
  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        "Content-Security-Policy": [
          isDev
            ? "default-src 'self' http://localhost:* http://127.0.0.1:*; script-src 'self' 'unsafe-inline' 'unsafe-eval' http://localhost:*; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; connect-src 'self' blob: http://localhost:* http://127.0.0.1:* ws://localhost:*; img-src 'self' data: blob:; frame-src 'self' blob: data:; object-src 'self' blob: data:; worker-src 'self' blob:"
            : "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; connect-src 'self' blob:; img-src 'self' data: blob:; frame-src 'self' blob: data:; object-src 'self' blob: data:; worker-src 'self' blob:"
        ],
      },
    });
  });

  win.webContents.on("did-fail-load", (_event, errorCode, errorDescription, validatedURL, isMainFrame) => {
    if (!isMainFrame) return;
    console.error("did-fail-load", { errorCode, errorDescription, validatedURL });
  });

  if (isDev) {
    const devUrl = process.env.ELECTRON_RENDERER_URL || "http://127.0.0.1:5174";
    win.loadURL(devUrl).catch((error) => {
      console.error("Failed to load dev URL, falling back to local dist build.", error);
      win.loadFile(prodIndexPath);
    });
    win.webContents.openDevTools({ mode: "detach" });
  } else {
    win.loadFile(prodIndexPath);
  }
}

app.whenReady().then(() => {
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

