import { PhysicalPosition, PhysicalSize } from "@tauri-apps/api/dpi";
import { getCurrentWebviewWindow } from "@tauri-apps/api/webviewWindow";
import {
  availableMonitors,
  cursorPosition,
  monitorFromPoint,
  primaryMonitor,
} from "@tauri-apps/api/window";

const BOTTOM_MARGIN_LOGICAL_PX = 28;
const INDICATOR_WIDTH_PX = 300;
const INDICATOR_HEIGHT_PX = 44;

export async function syncIndicatorWindow(
  shouldShow: boolean,
  isCancelled: () => boolean = () => false,
): Promise<void> {
  const win = getCurrentWebviewWindow();

  if (!shouldShow) {
    await win.hide();
    return;
  }

  let monitor = null;
  try {
    const cursor = await cursorPosition();
    const monitors = await availableMonitors();
    monitor = monitors.find((m) => {
      const left = m.position.x;
      const right = m.position.x + m.size.width;
      const top = m.position.y;
      const bottom = m.position.y + m.size.height;

      return (
        cursor.x >= left &&
        cursor.x < right &&
        cursor.y >= top &&
        cursor.y < bottom
      );
    }) ?? (await monitorFromPoint(cursor.x, cursor.y));
  } catch (e) {
    console.warn("Failed to resolve monitor from cursor", e);
  }

  if (!monitor) {
    monitor = (await win.currentMonitor()) ?? (await primaryMonitor());
  }
  if (isCancelled()) return;

  if (!monitor) {
    if (!isCancelled()) await win.show();
    return;
  }

  await win.setSize(new PhysicalSize(INDICATOR_WIDTH_PX, INDICATOR_HEIGHT_PX));
  const { workArea } = monitor;
  const width = INDICATOR_WIDTH_PX;
  const height = INDICATOR_HEIGHT_PX;
  const bottomMarginPx = Math.round(BOTTOM_MARGIN_LOGICAL_PX * monitor.scaleFactor);

  const x =
    workArea.position.x + Math.round((workArea.size.width - width) / 2);
  const y =
    workArea.position.y +
    workArea.size.height -
    height -
    bottomMarginPx;

  await win.setPosition(new PhysicalPosition(x, y));
  await win.setAlwaysOnTop(false);
  await win.setAlwaysOnTop(true);
  if (!isCancelled()) await win.show();
}
