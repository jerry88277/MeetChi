# Changelog

## [Unreleased]

### Fixed
- **Windows Transparent Window Artifacts**: Solved an issue where a native Windows title bar frame would appear underneath the transparent, frameless main window when it lost focus or was clicked.
    - **Issue**: On Windows 11/10, setting `transparent: true` and `decorations: false` in Tauri v2 was not sufficient. The DWM (Desktop Window Manager) would still attempt to paint the non-client area during `WM_NCACTIVATE` (focus change) and `WM_NCCALCSIZE` events, resulting in a "ghost" frame visible beneath the UI.
    - **Attempts**:
        1.  *Configuration*: Changed `resizable` to `false`. Result: Caused DWM to fallback to legacy rendering, making the artifact worse.
        2.  *Event Listeners*: Listened to `tauri://blur` and `tauri://focus` to re-apply `WS_POPUP` style. Result: Fighting the OS event loop caused flickering and race conditions.
    - **Solution**: Implemented low-level Win32 `WndProc` subclassing in Rust.
        - Intercepted `WM_NCCALCSIZE` (0x0083): Returns `0` to tell Windows the entire window is the client area.
        - Intercepted `WM_NCACTIVATE` (0x0086): Returns `1` (TRUE) to prevent default non-client painting activation.
        - Applied `WS_POPUP` style and removed `WS_OVERLAPPED` | `WS_CAPTION` | `WS_THICKFRAME` via `SetWindowLongW` during window setup.
    - **Reference**: See `apps/tauri-client/src-tauri/src/lib.rs` -> `subclass_proc`.
