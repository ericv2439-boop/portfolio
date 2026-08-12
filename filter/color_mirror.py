import sys
import os
import json
import ctypes
from datetime import datetime

import mss
import cv2
import numpy as np

from PyQt6.QtCore import (
    Qt,
    QRect,
    QPoint,
    QTimer,
    pyqtSignal,
    QThread,
    QAbstractNativeEventFilter,
)
from PyQt6.QtGui import (
    QImage,
    QPixmap,
    QPainter,
    QPen,
)
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QSpinBox,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QCheckBox,
    QGroupBox,
    QGridLayout,
    QMessageBox,
    QLineEdit,
    QListWidget,
    QScrollArea,
    QSizePolicy,
)


# ============================================================
# CONFIGURATION
# ============================================================

PRESET_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "color_mirror_presets.json",
)


# ============================================================
# COLOR PALETTE
# ============================================================

COLOR_NAMES = [
    "Red",
    "Yellow",
    "Blue",
    "Orange",
    "Green",
    "Purple",
    "Red-Orange",
    "Yellow-Orange",
    "Yellow-Green",
    "Blue-Green",
    "Blue-Purple",
    "Red-Purple",
    "Black",
    "White",
]

COLORS = np.array(
    [
        [255, 0, 0],
        [255, 255, 0],
        [0, 0, 255],
        [255, 128, 0],
        [0, 255, 0],
        [128, 0, 255],
        [255, 64, 0],
        [255, 192, 0],
        [128, 255, 0],
        [0, 192, 128],
        [64, 0, 255],
        [192, 0, 128],
        [0, 0, 0],
        [255, 255, 255],
    ],
    dtype=np.float32,
)

COLOR_GROUPS = {
    "Primary": [0, 1, 2],
    "Secondary": [3, 4, 5],
    "Tertiary": [6, 7, 8, 9, 10, 11],
    "Black / White": [12, 13],
}


# ============================================================
# MSS CONVERSION
# ============================================================

def mss_to_rgb(frame):
    image = np.asarray(frame)
    return np.ascontiguousarray(
        image[:, :, :3][:, :, ::-1]
    )


# ============================================================
# WINDOWS GLOBAL HOTKEY
# ============================================================

WM_HOTKEY = 0x0312
MOD_WIN = 0x0008

VK_LEFT = 0x25
VK_RIGHT = 0x27

HOTKEY_PREVIOUS = 1001
HOTKEY_NEXT = 1002


class WindowsHotkeyFilter(QAbstractNativeEventFilter):

    def __init__(self, callback):
        super().__init__()

        self.callback = callback
        self.registered = []

        if sys.platform == "win32":
            user32 = ctypes.windll.user32

            if user32.RegisterHotKey(
                None,
                HOTKEY_PREVIOUS,
                MOD_WIN,
                VK_LEFT,
            ):
                self.registered.append(
                    HOTKEY_PREVIOUS
                )
            else:
                print(
                    "Could not register Win+Left."
                )

            if user32.RegisterHotKey(
                None,
                HOTKEY_NEXT,
                MOD_WIN,
                VK_RIGHT,
            ):
                self.registered.append(
                    HOTKEY_NEXT
                )
            else:
                print(
                    "Could not register Win+Right."
                )

    def nativeEventFilter(
        self,
        event_type,
        message,
    ):
        if sys.platform == "win32":
            msg = ctypes.wintypes.MSG.from_address(
                int(message)
            )

            if msg.message == WM_HOTKEY:

                if msg.wParam == HOTKEY_PREVIOUS:
                    self.callback(-1)
                    return True, 0

                if msg.wParam == HOTKEY_NEXT:
                    self.callback(1)
                    return True, 0

        return False, 0

    def unregister(self):
        if sys.platform == "win32":

            user32 = ctypes.windll.user32

            for hotkey_id in self.registered:
                user32.UnregisterHotKey(
                    None,
                    hotkey_id,
                )

            self.registered.clear()


# ============================================================
# REGION SELECTOR
# ============================================================

class RegionSelector(QWidget):

    region_selected = pyqtSignal(QRect)

    def __init__(self):
        super().__init__()

        self.start = QPoint()
        self.current = QPoint()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )

        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground
        )

        screen = QApplication.primaryScreen()

        if screen:
            self.setGeometry(
                screen.geometry()
            )

        self.show()

    def mousePressEvent(self, event):

        if (
            event.button()
            == Qt.MouseButton.LeftButton
        ):
            self.start = (
                event.position().toPoint()
            )

            self.current = self.start
            self.update()

    def mouseMoveEvent(self, event):

        if not self.start.isNull():
            self.current = (
                event.position().toPoint()
            )

            self.update()

    def mouseReleaseEvent(self, event):

        if (
            event.button()
            == Qt.MouseButton.LeftButton
        ):
            rect = QRect(
                self.start,
                self.current,
            ).normalized()

            if (
                rect.width() > 10
                and rect.height() > 10
            ):
                self.region_selected.emit(
                    rect
                )

            self.close()

    def paintEvent(self, event):

        painter = QPainter(self)

        painter.fillRect(
            self.rect(),
            Qt.GlobalColor.black,
        )

        if not self.start.isNull():

            rect = QRect(
                self.start,
                self.current,
            ).normalized()

            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_Clear
            )

            painter.fillRect(
                rect,
                Qt.GlobalColor.transparent,
            )

            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceOver
            )

            painter.setPen(
                QPen(
                    Qt.GlobalColor.white,
                    2,
                )
            )

            painter.drawRect(rect)


# ============================================================
# LIVE MIRROR
# ============================================================

class LiveMirror(QWidget):

    def __init__(
        self,
        region,
        app_controller=None,
    ):
        super().__init__()

        self.region = region
        self.app_controller = app_controller

        # ----------------------------------------------------
        # DISPLAY
        # ----------------------------------------------------

        self.fps = 30
        self.transparency = 80

        self.fit_to_window = True
        self.fullscreen_mirror = False

        # ----------------------------------------------------
        # DETECTION
        # ----------------------------------------------------

        self.object_threshold = 100
        self.gradient_tolerance = 60
        self.connectivity = 8

        self.closing_kernel_size = 3
        self.closing_iterations = 1

        # ----------------------------------------------------
        # EXCLUDED GRADIENT
        # ----------------------------------------------------

        self.show_excluded_gradient = True
        self.excluded_gradient_range = 100
        self.excluded_gradient_strength = 50

        # ----------------------------------------------------
        # OBJECT DISPLAY
        # ----------------------------------------------------

        self.show_object_frames = True

        # ----------------------------------------------------
        # COLORS
        # ----------------------------------------------------

        self.selected_colors = [
            True for _ in COLOR_NAMES
        ]

        # ----------------------------------------------------
        # SWAP
        # ----------------------------------------------------

        self.swap_colors = False
        self.swap_target_color = 0

        # ----------------------------------------------------
        # MODE
        # ----------------------------------------------------

        self.processing_mode = 0

        # ----------------------------------------------------
        # OBJECT CACHE
        # ----------------------------------------------------

        self.detected_objects = []

        self.last_rgb = None
        self.last_result = None
        self.last_detection_signature = None

        # ----------------------------------------------------
        # WINDOW DRAG / RESIZE
        # ----------------------------------------------------

        self.drag_position = None
        self.resizing = False

        self.resize_margin = 12

        self.resize_start_mouse = QPoint()
        self.resize_start_size = self.size()

        # ----------------------------------------------------
        # MSS
        # ----------------------------------------------------

        self.sct = mss.MSS()

        # ----------------------------------------------------
        # IMAGE
        # ----------------------------------------------------

        self.label = QLabel()

        self.label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.label.setStyleSheet(
            "background: black;"
        )

        self.label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        # ----------------------------------------------------
        # WINDOW
        # ----------------------------------------------------

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )

        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground
        )

        self.setWindowOpacity(
            self.transparency / 100
        )

        layout = QVBoxLayout(self)

        layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        layout.addWidget(self.label)

        self.resize(
            max(100, region.width()),
            max(100, region.height()),
        )

        self.setMinimumSize(
            100,
            100,
        )

        # ----------------------------------------------------
        # TIMER
        # ----------------------------------------------------

        self.timer = QTimer()

        self.timer.timeout.connect(
            self.update_screen
        )

        self.set_fps(self.fps)

        self.show()

    # ========================================================
    # SETTINGS
    # ========================================================

    def set_fps(self, value):

        self.fps = max(
            1,
            int(value),
        )

        self.timer.setInterval(
            max(
                1,
                int(1000 / self.fps),
            )
        )

        if not self.timer.isActive():
            self.timer.start()

    def set_transparency(self, value):

        self.transparency = int(value)

        self.setWindowOpacity(
            self.transparency / 100
        )

    def set_object_threshold(self, value):

        self.object_threshold = max(
            1,
            int(value),
        )

        self.invalidate_detection()

    def set_gradient_tolerance(self, value):

        self.gradient_tolerance = max(
            0,
            min(441, int(value)),
        )

        self.invalidate_detection()

    def set_connectivity(self, value):

        self.connectivity = (
            4 if int(value) == 4 else 8
        )

        self.invalidate_detection()

    def set_closing_kernel(self, value):

        value = max(
            1,
            int(value),
        )

        if value % 2 == 0:
            value += 1

        self.closing_kernel_size = value

        self.invalidate_detection()

    def set_closing_iterations(self, value):

        self.closing_iterations = max(
            0,
            int(value),
        )

        self.invalidate_detection()

    # --------------------------------------------------------
    # FIXED GRADIENT TOGGLE
    # --------------------------------------------------------

    def set_excluded_gradient_enabled(
        self,
        enabled,
    ):
        self.show_excluded_gradient = bool(
            enabled
        )

        self.update_screen()

    def set_excluded_gradient_range(
        self,
        value,
    ):
        self.excluded_gradient_range = max(
            1,
            int(value),
        )

        self.update_screen()

    def set_excluded_gradient_strength(
        self,
        value,
    ):
        self.excluded_gradient_strength = max(
            0,
            min(100, int(value)),
        )

        self.update_screen()

    def set_processing_mode(self, mode):

        self.processing_mode = int(mode)

        self.invalidate_detection()

    def set_color_enabled(
        self,
        index,
        enabled,
    ):

        self.selected_colors[index] = bool(
            enabled
        )

        self.invalidate_detection()

    def set_swap_colors(self, enabled):

        self.swap_colors = bool(enabled)

        self.update_screen()

    def set_swap_target(self, index):

        self.swap_target_color = int(index)

        self.update_screen()

    # --------------------------------------------------------
    # FIXED OBJECT FRAME TOGGLE
    # --------------------------------------------------------

    def set_show_frames(self, enabled):

        self.show_object_frames = bool(
            enabled
        )

        self.update_screen()

    # ========================================================
    # INVALIDATE DETECTION
    # ========================================================

    def invalidate_detection(self):

        self.last_detection_signature = None
        self.detected_objects = []

        self.update_screen()

    # ========================================================
    # DETECTION SIGNATURE
    # ========================================================

    def detection_signature(self):

        return (
            tuple(self.selected_colors),
            self.gradient_tolerance,
            self.object_threshold,
            self.connectivity,
            self.closing_kernel_size,
            self.closing_iterations,
        )

    # ========================================================
    # DISTANCE TO SELECTED COLORS
    # ========================================================

    def distance_to_selected(self, rgb):

        height, width = rgb.shape[:2]

        result = np.full(
            (height, width),
            np.inf,
            dtype=np.float32,
        )

        pixels = rgb.astype(
            np.float32
        )

        for i in range(
            len(COLOR_NAMES)
        ):

            if not self.selected_colors[i]:
                continue

            target = COLORS[i]

            diff = pixels - target

            distance = np.sqrt(
                np.sum(
                    diff * diff,
                    axis=2,
                )
            )

            result = np.minimum(
                result,
                distance,
            )

        return result

    # ========================================================
    # SELECTED MASK
    # ========================================================

    def selected_mask(self, rgb):

        distance = (
            self.distance_to_selected(rgb)
        )

        return (
            distance
            <= self.gradient_tolerance
        )

    # ========================================================
    # EXCLUDED GRADIENT
    # ========================================================

    def excluded_gradient(self, rgb):

        if not self.show_excluded_gradient:

            # Completely black background when
            # excluded gradient is disabled.
            #
            # Selected pixels are restored by the
            # processing functions afterward.

            return np.zeros_like(rgb)

        distance = (
            self.distance_to_selected(rgb)
        )

        tolerance = float(
            self.gradient_tolerance
        )

        gradient_range = float(
            max(
                1,
                self.excluded_gradient_range,
            )
        )

        normalized = (
            distance - tolerance
        ) / gradient_range

        normalized = np.clip(
            normalized,
            0.0,
            1.0,
        )

        strength = (
            self.excluded_gradient_strength
            / 100.0
        )

        visibility = (
            1.0
            - normalized * strength
        )

        visibility = np.clip(
            visibility,
            0.0,
            1.0,
        )

        visibility[
            distance <= tolerance
        ] = 0.0

        result = (
            rgb.astype(np.float32)
            * visibility[:, :, None]
        )

        return np.clip(
            result,
            0,
            255,
        ).astype(np.uint8)

    # ========================================================
    # DETECT OBJECTS
    # ========================================================

    def detect_objects(self, rgb):

        objects = []

        pixels = rgb.astype(
            np.float32
        )

        for color_index in range(
            len(COLOR_NAMES)
        ):

            if not self.selected_colors[
                color_index
            ]:
                continue

            target = COLORS[
                color_index
            ]

            difference = (
                pixels - target
            )

            distance = np.sqrt(
                np.sum(
                    difference * difference,
                    axis=2,
                )
            )

            mask = (
                distance
                <= self.gradient_tolerance
            )

            if not np.any(mask):
                continue

            mask8 = (
                mask.astype(np.uint8)
                * 255
            )

            if (
                self.closing_iterations > 0
                and
                self.closing_kernel_size > 1
            ):

                kernel = np.ones(
                    (
                        self.closing_kernel_size,
                        self.closing_kernel_size,
                    ),
                    np.uint8,
                )

                mask8 = cv2.morphologyEx(
                    mask8,
                    cv2.MORPH_CLOSE,
                    kernel,
                    iterations=(
                        self.closing_iterations
                    ),
                )

            (
                count,
                labels,
                stats,
                centroids,
            ) = (
                cv2.connectedComponentsWithStats(
                    mask8,
                    connectivity=self.connectivity,
                )
            )

            for label in range(
                1,
                count,
            ):

                area = int(
                    stats[
                        label,
                        cv2.CC_STAT_AREA,
                    ]
                )

                if (
                    area
                    < self.object_threshold
                ):
                    continue

                x = int(
                    stats[
                        label,
                        cv2.CC_STAT_LEFT,
                    ]
                )

                y = int(
                    stats[
                        label,
                        cv2.CC_STAT_TOP,
                    ]
                )

                w = int(
                    stats[
                        label,
                        cv2.CC_STAT_WIDTH,
                    ]
                )

                h = int(
                    stats[
                        label,
                        cv2.CC_STAT_HEIGHT,
                    ]
                )

                component = (
                    labels == label
                )

                objects.append(
                    {
                        "color_index":
                            color_index,
                        "mask":
                            component,
                        "size":
                            area,
                        "x":
                            x,
                        "y":
                            y,
                        "w":
                            w,
                        "h":
                            h,
                    }
                )

        objects.sort(
            key=lambda obj: obj["size"],
            reverse=True,
        )

        return objects

    # ========================================================
    # CURRENT OBJECTS
    # ========================================================

    def get_current_objects(self, rgb):

        signature = (
            self.detection_signature()
        )

        if (
            self.last_detection_signature
            != signature
        ):

            self.detected_objects = (
                self.detect_objects(rgb)
            )

            self.last_detection_signature = (
                signature
            )

        return self.detected_objects

    # ========================================================
    # DRAW OBJECT FRAMES
    # ========================================================

    def draw_object_frames(
        self,
        image,
        objects,
    ):

        result = image.copy()

        if not self.show_object_frames:
            return result

        for obj in objects:

            x = obj["x"]
            y = obj["y"]
            w = obj["w"]
            h = obj["h"]

            cv2.rectangle(
                result,
                (x, y),
                (
                    x + w - 1,
                    y + h - 1,
                ),
                (255, 255, 255),
                2,
            )

        return result

    # ========================================================
    # PROCESSING MODES
    # ========================================================

    def process_original(self, rgb):

        return rgb.copy()

    def process_selected(self, rgb):

        mask = self.selected_mask(rgb)

        result = self.excluded_gradient(
            rgb
        )

        result[mask] = rgb[mask]

        return result

    def process_objects(self, rgb):

        objects = self.get_current_objects(
            rgb
        )

        result = self.excluded_gradient(
            rgb
        )

        for obj in objects:

            mask = obj["mask"]

            result[mask] = rgb[mask]

        return self.draw_object_frames(
            result,
            objects,
        )

    def process_grid(self, rgb):

        objects = self.get_current_objects(
            rgb
        )

        if not objects:
            return np.zeros_like(rgb)

        cell = 200
        columns = 4

        rows = int(
            np.ceil(
                len(objects)
                / columns
            )
        )

        canvas = np.zeros(
            (
                rows * cell,
                columns * cell,
                3,
            ),
            dtype=np.uint8,
        )

        for i, obj in enumerate(
            objects
        ):

            x = obj["x"]
            y = obj["y"]
            w = obj["w"]
            h = obj["h"]

            source = rgb[
                y:y + h,
                x:x + w,
            ]

            mask = obj["mask"][
                y:y + h,
                x:x + w,
            ]

            crop = np.zeros_like(
                source
            )

            crop[mask] = source[mask]

            if self.show_object_frames:

                cv2.rectangle(
                    crop,
                    (0, 0),
                    (
                        w - 1,
                        h - 1,
                    ),
                    (255, 255, 255),
                    2,
                )

            scale = min(
                (cell - 10)
                / max(1, w),
                (cell - 10)
                / max(1, h),
            )

            nw = max(
                1,
                int(w * scale),
            )

            nh = max(
                1,
                int(h * scale),
            )

            crop = cv2.resize(
                crop,
                (nw, nh),
                interpolation=cv2.INTER_NEAREST,
            )

            row = i // columns
            col = i % columns

            px = (
                col * cell
                + (cell - nw) // 2
            )

            py = (
                row * cell
                + (cell - nh) // 2
            )

            canvas[
                py:py + nh,
                px:px + nw,
            ] = crop

        return canvas

    def process_filtered(self, rgb):

        objects = self.get_current_objects(
            rgb
        )

        result = self.excluded_gradient(
            rgb
        )

        for obj in objects:

            mask = obj["mask"]

            result[mask] = rgb[mask]

        return self.draw_object_frames(
            result,
            objects,
        )

    def process_swap(self, rgb):

        mask = self.selected_mask(rgb)

        result = self.excluded_gradient(
            rgb
        )

        if not self.swap_colors:

            result[mask] = rgb[mask]

            return result

        replacement = COLORS[
            self.swap_target_color
        ].astype(np.uint8)

        result[mask] = replacement

        return result

    def process_frame(self, rgb):

        if self.processing_mode == 0:
            return self.process_original(rgb)

        if self.processing_mode == 1:
            return self.process_selected(rgb)

        if self.processing_mode == 2:
            return self.process_objects(rgb)

        if self.processing_mode == 3:
            return self.process_grid(rgb)

        if self.processing_mode == 4:
            return self.process_filtered(rgb)

        if self.processing_mode == 5:
            return self.process_swap(rgb)

        return rgb

    # ========================================================
    # DISPLAY
    # ========================================================

    def display_image(self, rgb):

        rgb = np.ascontiguousarray(
            rgb
        )

        h, w = rgb.shape[:2]

        qimage = QImage(
            rgb.data,
            w,
            h,
            w * 3,
            QImage.Format.Format_RGB888,
        )

        pixmap = QPixmap.fromImage(
            qimage.copy()
        )

        if self.fit_to_window:

            pixmap = pixmap.scaled(
                self.label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )

        else:

            pixmap = pixmap.scaled(
                w,
                h,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )

        self.label.setPixmap(
            pixmap
        )

    # ========================================================
    # UPDATE
    # ========================================================

    def update_screen(self):

        if self.isMinimized():
            return

        try:

            monitor = {
                "left":
                    self.region.x(),

                "top":
                    self.region.y(),

                "width":
                    self.region.width(),

                "height":
                    self.region.height(),
            }

            frame = self.sct.grab(
                monitor
            )

            rgb = mss_to_rgb(frame)

            self.last_rgb = rgb

            result = self.process_frame(
                rgb
            )

            self.last_result = result

            self.display_image(
                result
            )

        except Exception as e:

            print(
                "Capture error:",
                e,
            )

    # ========================================================
    # FIT MODE
    # ========================================================

    def set_fit_mode(self, enabled):

        self.fit_to_window = bool(
            enabled
        )

        if self.last_result is not None:

            self.display_image(
                self.last_result
            )

    # ========================================================
    # RESTORE / MINIMIZE
    # ========================================================

    def restore_mirror(self):

        self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

        if self.last_result is not None:

            QTimer.singleShot(
                50,
                lambda:
                self.display_image(
                    self.last_result
                ),
            )

    def minimize_mirror(self):

        self.showMinimized()

    # ========================================================
    # FULLSCREEN
    # ========================================================

    def toggle_fullscreen(self):

        if self.fullscreen_mirror:

            self.showNormal()

            self.fullscreen_mirror = False

        else:

            self.showFullScreen()

            self.fullscreen_mirror = True

        if self.last_result is not None:

            QTimer.singleShot(
                50,
                lambda:
                self.display_image(
                    self.last_result
                ),
            )

        # Tell settings window to adapt.
        if (
            self.app_controller is not None
            and
            self.app_controller.settings
            is not None
        ):

            QTimer.singleShot(
                100,
                self.app_controller.settings
                .adjust_to_screen,
            )

    # ========================================================
    # MOVE TO MONITOR
    # ========================================================

    def move_to_screen(
        self,
        screen_index,
    ):

        screens = QApplication.screens()

        if not screens:
            return

        screen_index %= len(screens)

        target_screen = screens[
            screen_index
        ]

        target_geometry = (
            target_screen.geometry()
        )

        current_center = (
            self.frameGeometry().center()
        )

        current_screen_index = 0

        for i, screen in enumerate(
            screens
        ):

            if screen.geometry().contains(
                current_center
            ):

                current_screen_index = i
                break

        if (
            screen_index
            == current_screen_index
        ):
            return

        old_screen = screens[
            current_screen_index
        ]

        old_geometry = (
            old_screen.geometry()
        )

        rel_x = (
            self.x()
            - old_geometry.x()
        ) / max(
            1,
            old_geometry.width(),
        )

        rel_y = (
            self.y()
            - old_geometry.y()
        ) / max(
            1,
            old_geometry.height(),
        )

        new_x = (
            target_geometry.x()
            + int(
                rel_x
                * target_geometry.width()
            )
        )

        new_y = (
            target_geometry.y()
            + int(
                rel_y
                * target_geometry.height()
            )
        )

        new_x = max(
            target_geometry.left(),
            min(
                new_x,
                target_geometry.right()
                - self.width()
                + 1,
            ),
        )

        new_y = max(
            target_geometry.top(),
            min(
                new_y,
                target_geometry.bottom()
                - self.height()
                + 1,
            ),
        )

        self.move(
            new_x,
            new_y,
        )

        self.raise_()

    # ========================================================
    # RESIZE
    # ========================================================

    def resizeEvent(self, event):

        super().resizeEvent(event)

        if self.last_result is not None:

            QTimer.singleShot(
                0,
                lambda:
                self.display_image(
                    self.last_result
                ),
            )

        if (
            self.app_controller is not None
            and
            self.app_controller.settings
            is not None
        ):

            QTimer.singleShot(
                0,
                self.app_controller.settings
                .adjust_to_screen,
            )

    # ========================================================
    # MOUSE
    # ========================================================

    def mousePressEvent(self, event):

        if (
            event.button()
            != Qt.MouseButton.LeftButton
        ):
            return

        pos = (
            event.position().toPoint()
        )

        if (
            pos.x()
            >= self.width()
            - self.resize_margin
            and
            pos.y()
            >= self.height()
            - self.resize_margin
        ):

            self.resizing = True

            self.resize_start_mouse = (
                event.globalPosition()
                .toPoint()
            )

            self.resize_start_size = (
                self.size()
            )

            return

        self.drag_position = (
            event.globalPosition()
            .toPoint()
            - self.frameGeometry()
            .topLeft()
        )

    def mouseMoveEvent(self, event):

        pos = (
            event.position().toPoint()
        )

        if self.resizing:

            delta = (
                event.globalPosition()
                .toPoint()
                - self.resize_start_mouse
            )

            self.resize(
                max(
                    100,
                    self.resize_start_size
                    .width()
                    + delta.x(),
                ),
                max(
                    100,
                    self.resize_start_size
                    .height()
                    + delta.y(),
                ),
            )

            return

        if (
            pos.x()
            >= self.width()
            - self.resize_margin
            and
            pos.y()
            >= self.height()
            - self.resize_margin
        ):

            self.setCursor(
                Qt.CursorShape.SizeFDiagCursor
            )

        else:

            self.setCursor(
                Qt.CursorShape.ArrowCursor
            )

        if (
            self.drag_position is not None
            and
            event.buttons()
            & Qt.MouseButton.LeftButton
        ):

            self.move(
                event.globalPosition()
                .toPoint()
                - self.drag_position
            )

    def mouseReleaseEvent(self, event):

        self.drag_position = None
        self.resizing = False

        self.setCursor(
            Qt.CursorShape.ArrowCursor
        )

    # ========================================================
    # KEYBOARD
    # ========================================================

    def keyPressEvent(self, event):

        if (
            event.key()
            == Qt.Key.Key_Escape
        ):

            if self.fullscreen_mirror:

                self.showNormal()
                self.fullscreen_mirror = False

            else:

                self.close()

        elif (
            event.key()
            == Qt.Key.Key_M
        ):

            self.minimize_mirror()

        elif (
            event.key()
            == Qt.Key.Key_R
        ):

            self.restore_mirror()


# ============================================================
# PRESET STORAGE
# ============================================================

def load_presets():

    if not os.path.exists(
        PRESET_FILE
    ):
        return {}

    try:

        with open(
            PRESET_FILE,
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(file)

        if isinstance(data, dict):
            return data

    except Exception as e:

        print(
            "Preset load error:",
            e,
        )

    return {}


def save_presets(presets):

    with open(
        PRESET_FILE,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            presets,
            file,
            indent=4,
        )


# ============================================================
# SETTINGS WINDOW
# ============================================================

class Settings(QWidget):

    def __init__(
        self,
        mirror,
        select_callback,
    ):
        super().__init__()

        self.mirror = mirror
        self.select_callback = (
            select_callback
        )

        self.export_worker = None
        self.presets = load_presets()

        self.setWindowTitle(
            "Color Object Analyzer"
        )

        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
        )

        self.setMinimumWidth(420)

        self.resize(
            620,
            850,
        )

        # ====================================================
        # SCROLL AREA
        # ====================================================

        self.scroll = QScrollArea()

        self.scroll.setWidgetResizable(
            True
        )

        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        self.scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        self.content = QWidget()

        self.content_layout = QVBoxLayout(
            self.content
        )

        self.content_layout.setContentsMargins(
            12,
            12,
            12,
            12,
        )

        self.content_layout.setSpacing(
            10
        )

        self.scroll.setWidget(
            self.content
        )

        # ====================================================
        # DISPLAY
        # ====================================================

        display_group = QGroupBox(
            "Display"
        )

        display_layout = QVBoxLayout()

        fps_row = QHBoxLayout()

        fps_row.addWidget(
            QLabel("Capture FPS:")
        )

        self.fps_spin = QSpinBox()

        self.fps_spin.setRange(
            1,
            144,
        )

        self.fps_spin.setValue(
            mirror.fps
        )

        self.fps_spin.valueChanged.connect(
            mirror.set_fps
        )

        fps_row.addWidget(
            self.fps_spin
        )

        display_layout.addLayout(
            fps_row
        )

        transparency_row = QHBoxLayout()

        transparency_row.addWidget(
            QLabel("Window opacity:")
        )

        self.opacity_spin = QSpinBox()

        self.opacity_spin.setRange(
            10,
            100,
        )

        self.opacity_spin.setValue(
            mirror.transparency
        )

        self.opacity_spin.setSuffix(
            "%"
        )

        self.opacity_spin.valueChanged.connect(
            mirror.set_transparency
        )

        transparency_row.addWidget(
            self.opacity_spin
        )

        display_layout.addLayout(
            transparency_row
        )

        self.fit_checkbox = QCheckBox(
            "Fit image to window"
        )

        self.fit_checkbox.setChecked(
            mirror.fit_to_window
        )

        self.fit_checkbox.stateChanged.connect(
            lambda state:
            mirror.set_fit_mode(
                bool(state)
            )
        )

        display_layout.addWidget(
            self.fit_checkbox
        )

        fullscreen_button = QPushButton(
            "Full Screen Mirror"
        )

        fullscreen_button.clicked.connect(
            mirror.toggle_fullscreen
        )

        display_layout.addWidget(
            fullscreen_button
        )

        restore_button = QPushButton(
            "Restore / Show Mirror"
        )

        restore_button.clicked.connect(
            mirror.restore_mirror
        )

        display_layout.addWidget(
            restore_button
        )

        minimize_button = QPushButton(
            "Minimize Mirror"
        )

        minimize_button.clicked.connect(
            mirror.minimize_mirror
        )

        display_layout.addWidget(
            minimize_button
        )

        monitor_help = QLabel(
            "Win + Left / Right: move the "
            "mirror between monitors."
        )

        monitor_help.setWordWrap(
            True
        )

        display_layout.addWidget(
            monitor_help
        )

        display_group.setLayout(
            display_layout
        )

        # ====================================================
        # DETECTION
        # ====================================================

        detection_group = QGroupBox(
            "Detection"
        )

        detection_layout = QVBoxLayout()

        threshold_row = QHBoxLayout()

        threshold_row.addWidget(
            QLabel(
                "Minimum object size:"
            )
        )

        self.threshold_spin = QSpinBox()

        self.threshold_spin.setRange(
            1,
            100000000,
        )

        self.threshold_spin.setValue(
            mirror.object_threshold
        )

        self.threshold_spin.setSuffix(
            " px"
        )

        self.threshold_spin.valueChanged.connect(
            mirror.set_object_threshold
        )

        threshold_row.addWidget(
            self.threshold_spin
        )

        detection_layout.addLayout(
            threshold_row
        )

        tolerance_row = QHBoxLayout()

        tolerance_row.addWidget(
            QLabel("Color tolerance:")
        )

        self.tolerance_edit = QLineEdit(
            str(
                mirror.gradient_tolerance
            )
        )

        self.tolerance_edit.setMaximumWidth(
            100
        )

        self.tolerance_edit.editingFinished.connect(
            self.change_tolerance
        )

        tolerance_row.addWidget(
            self.tolerance_edit
        )

        tolerance_row.addWidget(
            QLabel(
                "0–441 RGB distance"
            )
        )

        detection_layout.addLayout(
            tolerance_row
        )

        connectivity_row = QHBoxLayout()

        connectivity_row.addWidget(
            QLabel("Connectivity:")
        )

        self.connectivity_combo = (
            QComboBox()
        )

        self.connectivity_combo.addItems(
            [
                "4 — orthogonal",
                "8 — orthogonal + diagonal",
            ]
        )

        self.connectivity_combo.setCurrentIndex(
            1
            if mirror.connectivity == 8
            else 0
        )

        self.connectivity_combo.currentIndexChanged.connect(
            self.change_connectivity
        )

        connectivity_row.addWidget(
            self.connectivity_combo
        )

        detection_layout.addLayout(
            connectivity_row
        )

        kernel_row = QHBoxLayout()

        kernel_row.addWidget(
            QLabel("Gap closing:")
        )

        self.kernel_spin = QSpinBox()

        self.kernel_spin.setRange(
            1,
            31,
        )

        self.kernel_spin.setSingleStep(
            2
        )

        self.kernel_spin.setValue(
            mirror.closing_kernel_size
        )

        self.kernel_spin.valueChanged.connect(
            self.change_kernel
        )

        kernel_row.addWidget(
            self.kernel_spin
        )

        detection_layout.addLayout(
            kernel_row
        )

        iteration_row = QHBoxLayout()

        iteration_row.addWidget(
            QLabel(
                "Closing iterations:"
            )
        )

        self.iteration_spin = QSpinBox()

        self.iteration_spin.setRange(
            0,
            20,
        )

        self.iteration_spin.setValue(
            mirror.closing_iterations
        )

        self.iteration_spin.valueChanged.connect(
            mirror.set_closing_iterations
        )

        iteration_row.addWidget(
            self.iteration_spin
        )

        detection_layout.addLayout(
            iteration_row
        )

        # ====================================================
        # EXCLUDED GRADIENT
        # ====================================================

        gradient_group = QGroupBox(
            "Excluded Pixel Gradient"
        )

        gradient_layout = QVBoxLayout()

        self.gradient_checkbox = QCheckBox(
            "Show excluded pixels as gradient"
        )

        self.gradient_checkbox.setChecked(
            mirror.show_excluded_gradient
        )

        # IMPORTANT:
        # bool(state) reliably converts
        # 0 -> False and 2 -> True.

        self.gradient_checkbox.stateChanged.connect(
            lambda state:
            mirror.set_excluded_gradient_enabled(
                bool(state)
            )
        )

        gradient_layout.addWidget(
            self.gradient_checkbox
        )

        range_row = QHBoxLayout()

        range_row.addWidget(
            QLabel("Gradient range:")
        )

        self.gradient_range_spin = (
            QSpinBox()
        )

        self.gradient_range_spin.setRange(
            1,
            441,
        )

        self.gradient_range_spin.setValue(
            mirror.excluded_gradient_range
        )

        self.gradient_range_spin.valueChanged.connect(
            mirror.set_excluded_gradient_range
        )

        range_row.addWidget(
            self.gradient_range_spin
        )

        range_row.addWidget(
            QLabel("RGB distance")
        )

        gradient_layout.addLayout(
            range_row
        )

        strength_row = QHBoxLayout()

        strength_row.addWidget(
            QLabel("Fade strength:")
        )

        self.gradient_strength_spin = (
            QSpinBox()
        )

        self.gradient_strength_spin.setRange(
            0,
            100,
        )

        self.gradient_strength_spin.setValue(
            mirror.excluded_gradient_strength
        )

        self.gradient_strength_spin.setSuffix(
            "%"
        )

        self.gradient_strength_spin.valueChanged.connect(
            mirror.set_excluded_gradient_strength
        )

        strength_row.addWidget(
            self.gradient_strength_spin
        )

        gradient_layout.addLayout(
            strength_row
        )

        gradient_help = QLabel(
            "Pixels inside the tolerance remain "
            "their original colors. Pixels outside "
            "the tolerance gradually fade according "
            "to their RGB distance from the nearest "
            "selected color."
        )

        gradient_help.setWordWrap(
            True
        )

        gradient_layout.addWidget(
            gradient_help
        )

        gradient_group.setLayout(
            gradient_layout
        )

        detection_layout.addWidget(
            gradient_group
        )

        detection_group.setLayout(
            detection_layout
        )

        # ====================================================
        # COLORS
        # ====================================================

        color_group = QGroupBox(
            "Color Selection"
        )

        color_layout = QGridLayout()

        self.color_checks = []

        for i, name in enumerate(
            COLOR_NAMES
        ):

            check = QCheckBox(name)

            check.setChecked(
                mirror.selected_colors[i]
            )

            check.stateChanged.connect(
                lambda state,
                index=i:
                mirror.set_color_enabled(
                    index,
                    bool(state),
                )
            )

            self.color_checks.append(
                check
            )

            color_layout.addWidget(
                check,
                i // 2,
                i % 2,
            )

        color_group.setLayout(
            color_layout
        )

        group_buttons = QGridLayout()

        all_button = QPushButton(
            "All"
        )

        all_button.clicked.connect(
            self.select_all
        )

        group_buttons.addWidget(
            all_button,
            0,
            0,
        )

        none_button = QPushButton(
            "None"
        )

        none_button.clicked.connect(
            self.select_none
        )

        group_buttons.addWidget(
            none_button,
            0,
            1,
        )

        group_names = [
            "Primary",
            "Secondary",
            "Tertiary",
            "Black / White",
        ]

        for position, name in enumerate(
            group_names
        ):

            button = QPushButton(name)

            button.clicked.connect(
                lambda checked=False,
                group=name:
                self.select_group(
                    COLOR_GROUPS[group]
                )
            )

            row = (
                position // 2
                + 1
            )

            column = (
                position % 2
            )

            group_buttons.addWidget(
                button,
                row,
                column,
            )

        # ====================================================
        # OBJECT DISPLAY
        # ====================================================

        object_group = QGroupBox(
            "Object Display"
        )

        object_layout = QVBoxLayout()

        mode_row = QHBoxLayout()

        mode_row.addWidget(
            QLabel("Mode:")
        )

        self.mode_combo = QComboBox()

        self.mode_combo.addItems(
            [
                "Original",
                "Selected Colors",
                "Connected Objects",
                "Object Grid",
                "Objects Above Threshold",
                "Selected Colors / Swap",
            ]
        )

        self.mode_combo.setCurrentIndex(
            mirror.processing_mode
        )

        self.mode_combo.currentIndexChanged.connect(
            mirror.set_processing_mode
        )

        mode_row.addWidget(
            self.mode_combo
        )

        object_layout.addLayout(
            mode_row
        )

        self.frame_checkbox = QCheckBox(
            "Show object boxes"
        )

        self.frame_checkbox.setChecked(
            mirror.show_object_frames
        )

        # IMPORTANT:
        # Use bool(state), not an enum
        # comparison.

        self.frame_checkbox.stateChanged.connect(
            lambda state:
            mirror.set_show_frames(
                bool(state)
            )
        )

        object_layout.addWidget(
            self.frame_checkbox
        )

        self.object_info = QLabel(
            "Objects: 0"
        )

        self.object_info.setWordWrap(
            True
        )

        object_layout.addWidget(
            self.object_info
        )

        legend = QLabel(
            "Mirror shortcuts:\n"
            "M — Minimize mirror\n"
            "R — Restore mirror\n"
            "Esc — Exit fullscreen / close mirror\n"
            "Win + Left / Right — Switch monitor"
        )

        legend.setStyleSheet(
            "color: #AAAAAA; font-size: 10px;"
        )

        object_layout.addWidget(
            legend
        )

        object_group.setLayout(
            object_layout
        )

        # ====================================================
        # SWAP
        # ====================================================

        swap_group = QGroupBox(
            "Color Replacement"
        )

        swap_layout = QVBoxLayout()

        self.swap_checkbox = QCheckBox(
            "Swap selected colors"
        )

        self.swap_checkbox.setChecked(
            mirror.swap_colors
        )

        self.swap_checkbox.stateChanged.connect(
            lambda state:
            mirror.set_swap_colors(
                bool(state)
            )
        )

        swap_layout.addWidget(
            self.swap_checkbox
        )

        swap_row = QHBoxLayout()

        swap_row.addWidget(
            QLabel("Replace with:")
        )

        self.swap_combo = QComboBox()

        self.swap_combo.addItems(
            COLOR_NAMES
        )

        self.swap_combo.setCurrentIndex(
            mirror.swap_target_color
        )

        self.swap_combo.currentIndexChanged.connect(
            mirror.set_swap_target
        )

        swap_row.addWidget(
            self.swap_combo
        )

        swap_layout.addLayout(
            swap_row
        )

        swap_group.setLayout(
            swap_layout
        )

        # ====================================================
        # PRESETS
        # ====================================================

        preset_group = QGroupBox(
            "Presets"
        )

        preset_layout = QVBoxLayout()

        preset_row = QHBoxLayout()

        self.preset_name = QLineEdit()

        self.preset_name.setPlaceholderText(
            "Preset name..."
        )

        preset_row.addWidget(
            self.preset_name
        )

        save_preset_button = QPushButton(
            "Save Preset"
        )

        save_preset_button.clicked.connect(
            self.save_preset
        )

        preset_row.addWidget(
            save_preset_button
        )

        preset_layout.addLayout(
            preset_row
        )

        self.preset_list = QListWidget()

        self.refresh_preset_list()

        self.preset_list.itemDoubleClicked.connect(
            self.load_selected_preset
        )

        self.preset_list.setMinimumHeight(
            120
        )

        preset_layout.addWidget(
            self.preset_list
        )

        preset_buttons = QHBoxLayout()

        load_button = QPushButton(
            "Load Selected"
        )

        load_button.clicked.connect(
            self.load_selected_preset
        )

        preset_buttons.addWidget(
            load_button
        )

        delete_button = QPushButton(
            "Delete Selected"
        )

        delete_button.clicked.connect(
            self.delete_selected_preset
        )

        preset_buttons.addWidget(
            delete_button
        )

        preset_layout.addLayout(
            preset_buttons
        )

        preset_group.setLayout(
            preset_layout
        )

        # ====================================================
        # VIDEO EXPORT
        # ====================================================

        video_group = QGroupBox(
            "Object Video Export"
        )

        video_layout = QVBoxLayout()

        video_fps_row = QHBoxLayout()

        video_fps_row.addWidget(
            QLabel("Video FPS:")
        )

        self.video_fps = QSpinBox()

        self.video_fps.setRange(
            1,
            60,
        )

        self.video_fps.setValue(
            4
        )

        video_fps_row.addWidget(
            self.video_fps
        )

        video_layout.addLayout(
            video_fps_row
        )

        self.export_button = QPushButton(
            "Export Objects"
        )

        self.export_button.clicked.connect(
            self.export_objects
        )

        video_layout.addWidget(
            self.export_button
        )

        self.export_status = QLabel(
            "Export is idle."
        )

        self.export_status.setWordWrap(
            True
        )

        video_layout.addWidget(
            self.export_status
        )

        video_group.setLayout(
            video_layout
        )

        # ====================================================
        # BOTTOM BUTTONS
        # ====================================================

        window_layout = QHBoxLayout()

        select_button = QPushButton(
            "Select New Region"
        )

        select_button.clicked.connect(
            self.select_callback
        )

        window_layout.addWidget(
            select_button
        )

        refresh_button = QPushButton(
            "Refresh Objects"
        )

        refresh_button.clicked.connect(
            self.force_refresh
        )

        window_layout.addWidget(
            refresh_button
        )

        close_button = QPushButton(
            "Close Mirror"
        )

        close_button.clicked.connect(
            mirror.close
        )

        window_layout.addWidget(
            close_button
        )

        # ====================================================
        # ADD EVERYTHING TO SCROLL CONTENT
        # ====================================================

        self.content_layout.addWidget(
            display_group
        )

        self.content_layout.addWidget(
            detection_group
        )

        self.content_layout.addWidget(
            color_group
        )

        self.content_layout.addLayout(
            group_buttons
        )

        self.content_layout.addWidget(
            object_group
        )

        self.content_layout.addWidget(
            swap_group
        )

        self.content_layout.addWidget(
            preset_group
        )

        self.content_layout.addWidget(
            video_group
        )

        self.content_layout.addLayout(
            window_layout
        )

        self.content_layout.addStretch()

        # ====================================================
        # MAIN WINDOW LAYOUT
        # ====================================================

        main_layout = QVBoxLayout(
            self
        )

        main_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        main_layout.addWidget(
            self.scroll
        )

        self.setLayout(
            main_layout
        )

        # ====================================================
        # OBJECT INFO TIMER
        # ====================================================

        self.info_timer = QTimer()

        self.info_timer.timeout.connect(
            self.update_object_info
        )

        self.info_timer.start(
            250
        )

        self.show()

        self.adjust_to_screen()

    # ========================================================
    # RESPONSIVE SETTINGS WINDOW
    # ========================================================

    def adjust_to_screen(self):

        screens = QApplication.screens()

        if not screens:
            return

        current_geometry = (
            self.mirror.frameGeometry()
        )

        mirror_center = (
            current_geometry.center()
        )

        target_screen = (
            QApplication.screenAt(
                mirror_center
            )
        )

        if target_screen is None:
            target_screen = (
                QApplication.primaryScreen()
            )

        if target_screen is None:
            return

        available = (
            target_screen.availableGeometry()
        )

        max_height = int(
            available.height()
            * 0.92
        )

        max_width = int(
            available.width()
            * 0.42
        )

        max_width = max(
            420,
            min(
                max_width,
                700,
            ),
        )

        max_height = max(
            500,
            max_height,
        )

        self.resize(
            max_width,
            min(
                self.height(),
                max_height,
            ),
        )

        if (
            self.height()
            > max_height
        ):
            self.resize(
                self.width(),
                max_height,
            )

        # Keep the settings window visible.

        x = self.x()
        y = self.y()

        x = max(
            available.left(),
            min(
                x,
                available.right()
                - self.width()
                + 1,
            ),
        )

        y = max(
            available.top(),
            min(
                y,
                available.bottom()
                - self.height()
                + 1,
            ),
        )

        self.move(
            x,
            y,
        )

    # ========================================================
    # FORCE REFRESH
    # ========================================================

    def force_refresh(self):

        self.mirror.invalidate_detection()

        self.mirror.update_screen()

    # ========================================================
    # TOLERANCE
    # ========================================================

    def change_tolerance(self):

        try:

            value = int(
                self.tolerance_edit.text()
            )

        except ValueError:

            value = (
                self.mirror.gradient_tolerance
            )

        value = max(
            0,
            min(441, value),
        )

        self.tolerance_edit.setText(
            str(value)
        )

        self.mirror.set_gradient_tolerance(
            value
        )

    # ========================================================
    # CONNECTIVITY
    # ========================================================

    def change_connectivity(
        self,
        index,
    ):

        self.mirror.set_connectivity(
            4 if index == 0 else 8
        )

    # ========================================================
    # KERNEL
    # ========================================================

    def change_kernel(self, value):

        value = max(
            1,
            int(value),
        )

        if value % 2 == 0:

            value += 1

            self.kernel_spin.blockSignals(
                True
            )

            self.kernel_spin.setValue(
                value
            )

            self.kernel_spin.blockSignals(
                False
            )

        self.mirror.set_closing_kernel(
            value
        )

    # ========================================================
    # COLOR GROUPS
    # ========================================================

    def select_all(self):

        for i, check in enumerate(
            self.color_checks
        ):

            check.blockSignals(
                True
            )

            check.setChecked(
                True
            )

            check.blockSignals(
                False
            )

            self.mirror.selected_colors[
                i
            ] = True

        self.force_refresh()

    def select_none(self):

        for i, check in enumerate(
            self.color_checks
        ):

            check.blockSignals(
                True
            )

            check.setChecked(
                False
            )

            check.blockSignals(
                False
            )

            self.mirror.selected_colors[
                i
            ] = False

        self.force_refresh()

    def select_group(
        self,
        indices,
    ):

        for i, check in enumerate(
            self.color_checks
        ):

            enabled = (
                i in indices
            )

            check.blockSignals(
                True
            )

            check.setChecked(
                enabled
            )

            check.blockSignals(
                False
            )

            self.mirror.selected_colors[
                i
            ] = enabled

        self.force_refresh()

    # ========================================================
    # OBJECT INFO
    # ========================================================

    def update_object_info(self):

        objects = (
            self.mirror.detected_objects
        )

        if not objects:

            self.object_info.setText(
                "Objects: 0"
            )

            return

        counts = {}

        for obj in objects:

            index = obj[
                "color_index"
            ]

            counts[index] = (
                counts.get(
                    index,
                    0,
                )
                + 1
            )

        lines = [
            f"Objects: {len(objects)}",
            "",
        ]

        for index in sorted(
            counts
        ):

            lines.append(
                f"{COLOR_NAMES[index]}: "
                f"{counts[index]}"
            )

        lines.extend(
            [
                "",
                f"Connectivity: "
                f"{self.mirror.connectivity}",
                f"Threshold: "
                f"{self.mirror.object_threshold:,} px",
                f"Tolerance: "
                f"{self.mirror.gradient_tolerance}",
                "Frames: "
                + (
                    "ON"
                    if self.mirror.show_object_frames
                    else "OFF"
                ),
                "Excluded gradient: "
                + (
                    "ON"
                    if self.mirror.show_excluded_gradient
                    else "OFF"
                ),
            ]
        )

        self.object_info.setText(
            "\n".join(lines)
        )

    # ========================================================
    # PRESET DATA
    # ========================================================

    def current_preset(self):

        return {
            "fps":
                self.mirror.fps,

            "transparency":
                self.mirror.transparency,

            "fit_to_window":
                self.mirror.fit_to_window,

            "object_threshold":
                self.mirror.object_threshold,

            "gradient_tolerance":
                self.mirror.gradient_tolerance,

            "connectivity":
                self.mirror.connectivity,

            "closing_kernel_size":
                self.mirror.closing_kernel_size,

            "closing_iterations":
                self.mirror.closing_iterations,

            "show_excluded_gradient":
                self.mirror.show_excluded_gradient,

            "excluded_gradient_range":
                self.mirror.excluded_gradient_range,

            "excluded_gradient_strength":
                self.mirror.excluded_gradient_strength,

            "show_object_frames":
                self.mirror.show_object_frames,

            "selected_colors":
                self.mirror.selected_colors,

            "swap_colors":
                self.mirror.swap_colors,

            "swap_target_color":
                self.mirror.swap_target_color,

            "processing_mode":
                self.mirror.processing_mode,
        }

    # ========================================================
    # SAVE PRESET
    # ========================================================

    def save_preset(self):

        name = (
            self.preset_name.text()
            .strip()
        )

        if not name:

            QMessageBox.warning(
                self,
                "Preset",
                "Enter a preset name.",
            )

            return

        self.presets[name] = (
            self.current_preset()
        )

        try:

            save_presets(
                self.presets
            )

        except Exception as e:

            QMessageBox.critical(
                self,
                "Preset Error",
                str(e),
            )

            return

        self.refresh_preset_list()

        self.preset_name.clear()

        QMessageBox.information(
            self,
            "Preset Saved",
            f"Preset '{name}' saved.",
        )

    # ========================================================
    # PRESET LIST
    # ========================================================

    def refresh_preset_list(self):

        self.preset_list.clear()

        for name in sorted(
            self.presets.keys()
        ):

            self.preset_list.addItem(
                name
            )

    # ========================================================
    # LOAD PRESET
    # ========================================================

    def load_selected_preset(self):

        item = (
            self.preset_list.currentItem()
        )

        if item is None:
            return

        name = item.text()

        data = self.presets.get(
            name
        )

        if data is None:
            return

        self.apply_preset(
            data
        )

    def apply_preset(
        self,
        data,
    ):

        mirror = self.mirror

        mirror.set_fps(
            data.get(
                "fps",
                mirror.fps,
            )
        )

        mirror.set_transparency(
            data.get(
                "transparency",
                mirror.transparency,
            )
        )

        mirror.fit_to_window = data.get(
            "fit_to_window",
            mirror.fit_to_window,
        )

        mirror.set_object_threshold(
            data.get(
                "object_threshold",
                mirror.object_threshold,
            )
        )

        mirror.set_gradient_tolerance(
            data.get(
                "gradient_tolerance",
                mirror.gradient_tolerance,
            )
        )

        mirror.set_connectivity(
            data.get(
                "connectivity",
                mirror.connectivity,
            )
        )

        mirror.set_closing_kernel(
            data.get(
                "closing_kernel_size",
                mirror.closing_kernel_size,
            )
        )

        mirror.set_closing_iterations(
            data.get(
                "closing_iterations",
                mirror.closing_iterations,
            )
        )

        mirror.set_excluded_gradient_enabled(
            data.get(
                "show_excluded_gradient",
                mirror.show_excluded_gradient,
            )
        )

        mirror.set_excluded_gradient_range(
            data.get(
                "excluded_gradient_range",
                mirror.excluded_gradient_range,
            )
        )

        mirror.set_excluded_gradient_strength(
            data.get(
                "excluded_gradient_strength",
                mirror.excluded_gradient_strength,
            )
        )

        mirror.set_show_frames(
            data.get(
                "show_object_frames",
                mirror.show_object_frames,
            )
        )

        selected = data.get(
            "selected_colors",
            mirror.selected_colors,
        )

        if (
            len(selected)
            == len(COLOR_NAMES)
        ):

            mirror.selected_colors = [
                bool(x)
                for x in selected
            ]

        mirror.set_swap_colors(
            data.get(
                "swap_colors",
                mirror.swap_colors,
            )
        )

        mirror.set_swap_target(
            data.get(
                "swap_target_color",
                mirror.swap_target_color,
            )
        )

        mirror.set_processing_mode(
            data.get(
                "processing_mode",
                mirror.processing_mode,
            )
        )

        # ----------------------------------------------------
        # UPDATE UI
        # ----------------------------------------------------

        self.fps_spin.setValue(
            mirror.fps
        )

        self.opacity_spin.setValue(
            mirror.transparency
        )

        self.fit_checkbox.setChecked(
            mirror.fit_to_window
        )

        self.threshold_spin.setValue(
            mirror.object_threshold
        )

        self.tolerance_edit.setText(
            str(
                mirror.gradient_tolerance
            )
        )

        self.connectivity_combo.setCurrentIndex(
            0
            if mirror.connectivity == 4
            else 1
        )

        self.kernel_spin.setValue(
            mirror.closing_kernel_size
        )

        self.iteration_spin.setValue(
            mirror.closing_iterations
        )

        self.gradient_checkbox.setChecked(
            mirror.show_excluded_gradient
        )

        self.gradient_range_spin.setValue(
            mirror.excluded_gradient_range
        )

        self.gradient_strength_spin.setValue(
            mirror.excluded_gradient_strength
        )

        self.frame_checkbox.setChecked(
            mirror.show_object_frames
        )

        for i, check in enumerate(
            self.color_checks
        ):

            check.blockSignals(
                True
            )

            check.setChecked(
                mirror.selected_colors[i]
            )

            check.blockSignals(
                False
            )

        self.swap_checkbox.setChecked(
            mirror.swap_colors
        )

        self.swap_combo.setCurrentIndex(
            mirror.swap_target_color
        )

        self.mode_combo.setCurrentIndex(
            mirror.processing_mode
        )

        self.force_refresh()

    # ========================================================
    # DELETE PRESET
    # ========================================================

    def delete_selected_preset(self):

        item = (
            self.preset_list.currentItem()
        )

        if item is None:
            return

        name = item.text()

        answer = QMessageBox.question(
            self,
            "Delete Preset",
            f"Delete '{name}'?",
        )

        if (
            answer
            != QMessageBox.StandardButton.Yes
        ):
            return

        self.presets.pop(
            name,
            None,
        )

        save_presets(
            self.presets
        )

        self.refresh_preset_list()

    # ========================================================
    # EXPORT
    # ========================================================

    def export_objects(self):

        if (
            self.export_worker is not None
            and
            self.export_worker.isRunning()
        ):
            return

        if self.mirror.last_rgb is None:

            QMessageBox.warning(
                self,
                "Export",
                "No captured frame is available yet.",
            )

            return

        objects = (
            self.mirror.detect_objects(
                self.mirror.last_rgb
            )
        )

        self.mirror.detected_objects = (
            objects
        )

        count = len(objects)

        if count == 0:

            QMessageBox.information(
                self,
                "Export",
                "No objects satisfy the current settings.",
            )

            return

        fps = max(
            1,
            self.video_fps.value(),
        )

        duration = count / fps

        answer = QMessageBox.question(
            self,
            "Object Video",
            (
                f"Objects found: {count}\n\n"
                f"Frame rate: {fps} FPS\n\n"
                f"Video duration: "
                f"{duration:.2f} seconds\n\n"
                "Export one object per video frame?"
            ),
        )

        if (
            answer
            != QMessageBox.StandardButton.Yes
        ):
            return

        self.export_button.setEnabled(
            False
        )

        self.export_status.setText(
            "Exporting..."
        )

        self.export_worker = (
            ObjectVideoWorker(
                self.mirror.region,
                fps,
                self.mirror.object_threshold,
                self.mirror.gradient_tolerance,
                self.mirror.selected_colors,
                self.mirror.connectivity,
                self.mirror.closing_kernel_size,
                self.mirror.closing_iterations,
                self.mirror.show_object_frames,
            )
        )

        self.export_worker.progress.connect(
            lambda value:
            self.export_status.setText(
                f"Exporting: {value}%"
            )
        )

        self.export_worker.finished_signal.connect(
            self.export_finished
        )

        self.export_worker.error_signal.connect(
            self.export_error
        )

        self.export_worker.start()

    def export_finished(
        self,
        path,
    ):

        self.export_button.setEnabled(
            True
        )

        self.export_status.setText(
            f"Saved:\n{path}"
        )

        self.export_worker = None

        QMessageBox.information(
            self,
            "Export Complete",
            f"Video saved to:\n\n{path}",
        )

    def export_error(
        self,
        error,
    ):

        self.export_button.setEnabled(
            True
        )

        self.export_status.setText(
            "Export failed."
        )

        self.export_worker = None

        QMessageBox.critical(
            self,
            "Export Error",
            error,
        )


# ============================================================
# VIDEO WORKER
# ============================================================

class ObjectVideoWorker(QThread):

    progress = pyqtSignal(int)

    finished_signal = pyqtSignal(
        str
    )

    error_signal = pyqtSignal(
        str
    )

    def __init__(
        self,
        region,
        fps,
        threshold,
        tolerance,
        selected_colors,
        connectivity,
        kernel,
        iterations,
        show_frames,
    ):

        super().__init__()

        self.region = region
        self.fps = fps
        self.threshold = threshold
        self.tolerance = tolerance

        self.selected_colors = list(
            selected_colors
        )

        self.connectivity = connectivity
        self.kernel = kernel
        self.iterations = iterations
        self.show_frames = show_frames

    def detect_objects(
        self,
        rgb,
    ):

        objects = []

        pixels = rgb.astype(
            np.float32
        )

        for color_index in range(
            len(COLOR_NAMES)
        ):

            if not self.selected_colors[
                color_index
            ]:
                continue

            target = COLORS[
                color_index
            ]

            difference = (
                pixels - target
            )

            distance = np.sqrt(
                np.sum(
                    difference * difference,
                    axis=2,
                )
            )

            mask = (
                distance
                <= self.tolerance
            )

            if not np.any(mask):
                continue

            mask8 = (
                mask.astype(np.uint8)
                * 255
            )

            if (
                self.iterations > 0
                and
                self.kernel > 1
            ):

                kernel = np.ones(
                    (
                        self.kernel,
                        self.kernel,
                    ),
                    np.uint8,
                )

                mask8 = cv2.morphologyEx(
                    mask8,
                    cv2.MORPH_CLOSE,
                    kernel,
                    iterations=self.iterations,
                )

            (
                count,
                labels,
                stats,
                _
            ) = (
                cv2.connectedComponentsWithStats(
                    mask8,
                    connectivity=self.connectivity,
                )
            )

            for label in range(
                1,
                count,
            ):

                area = int(
                    stats[
                        label,
                        cv2.CC_STAT_AREA,
                    ]
                )

                if area < self.threshold:
                    continue

                x = int(
                    stats[
                        label,
                        cv2.CC_STAT_LEFT,
                    ]
                )

                y = int(
                    stats[
                        label,
                        cv2.CC_STAT_TOP,
                    ]
                )

                w = int(
                    stats[
                        label,
                        cv2.CC_STAT_WIDTH,
                    ]
                )

                h = int(
                    stats[
                        label,
                        cv2.CC_STAT_HEIGHT,
                    ]
                )

                objects.append(
                    {
                        "mask":
                            labels == label,
                        "x":
                            x,
                        "y":
                            y,
                        "w":
                            w,
                        "h":
                            h,
                        "size":
                            area,
                    }
                )

        objects.sort(
            key=lambda x:
            x["size"],
            reverse=True,
        )

        return objects

    def run(self):

        writer = None

        try:

            sct = mss.MSS()

            monitor = {
                "left":
                    self.region.x(),

                "top":
                    self.region.y(),

                "width":
                    self.region.width(),

                "height":
                    self.region.height(),
            }

            frame = sct.grab(
                monitor
            )

            rgb = mss_to_rgb(
                frame
            )

            objects = (
                self.detect_objects(
                    rgb
                )
            )

            if not objects:

                raise RuntimeError(
                    "No objects found."
                )

            filename = (
                "objects_"
                + datetime.now().strftime(
                    "%Y%m%d_%H%M%S"
                )
                + ".mp4"
            )

            path = os.path.join(
                os.getcwd(),
                filename,
            )

            fourcc = (
                cv2.VideoWriter_fourcc(
                    *"mp4v"
                )
            )

            writer = cv2.VideoWriter(
                path,
                fourcc,
                self.fps,
                (
                    monitor["width"],
                    monitor["height"],
                ),
            )

            if not writer.isOpened():

                raise RuntimeError(
                    "Unable to create MP4."
                )

            total = len(objects)

            for i, obj in enumerate(
                objects
            ):

                output = np.zeros_like(
                    rgb
                )

                mask = obj["mask"]

                output[mask] = rgb[mask]

                if self.show_frames:

                    x = obj["x"]
                    y = obj["y"]
                    w = obj["w"]
                    h = obj["h"]

                    cv2.rectangle(
                        output,
                        (x, y),
                        (
                            x + w - 1,
                            y + h - 1,
                        ),
                        (255, 255, 255),
                        2,
                    )

                bgr = cv2.cvtColor(
                    output,
                    cv2.COLOR_RGB2BGR,
                )

                writer.write(
                    bgr
                )

                self.progress.emit(
                    int(
                        (
                            (i + 1)
                            / total
                        )
                        * 100
                    )
                )

            writer.release()

            writer = None

            sct.close()

            self.finished_signal.emit(
                path
            )

        except Exception as e:

            if writer is not None:
                writer.release()

            self.error_signal.emit(
                str(e)
            )


# ============================================================
# APPLICATION
# ============================================================

class App:

    def __init__(self):

        self.app = QApplication(
            sys.argv
        )

        self.mirror = None
        self.settings = None
        self.selector = None

        self.hotkey_filter = (
            WindowsHotkeyFilter(
                self.handle_monitor_hotkey
            )
        )

        self.app.installNativeEventFilter(
            self.hotkey_filter
        )

        self.app.aboutToQuit.connect(
            self.cleanup
        )

        # Entire primary monitor by default.
        self.create_default_mirror()

    # ========================================================
    # DEFAULT FULL MONITOR
    # ========================================================

    def create_default_mirror(self):

        screen = (
            QApplication.primaryScreen()
        )

        if screen is None:

            raise RuntimeError(
                "No primary screen detected."
            )

        geometry = (
            screen.geometry()
        )

        self.create_mirror(
            geometry
        )

    # ========================================================
    # REGION SELECTION
    # ========================================================

    def select_region(self):

        if self.settings is not None:

            self.settings.close()

            self.settings = None

        if self.mirror is not None:

            self.mirror.close()

            self.mirror = None

        self.selector = (
            RegionSelector()
        )

        self.selector.region_selected.connect(
            self.create_mirror
        )

    # ========================================================
    # CREATE MIRROR
    # ========================================================

    def create_mirror(
        self,
        region,
    ):

        self.mirror = LiveMirror(
            region,
            self,
        )

        self.settings = Settings(
            self.mirror,
            self.select_region,
        )

    # ========================================================
    # MONITOR HOTKEY
    # ========================================================

    def handle_monitor_hotkey(
        self,
        direction,
    ):

        if self.mirror is None:
            return

        if self.mirror.isMinimized():

            self.mirror.restore_mirror()

        screens = QApplication.screens()

        if len(screens) < 2:
            return

        current_center = (
            self.mirror
            .frameGeometry()
            .center()
        )

        current_index = 0

        for i, screen in enumerate(
            screens
        ):

            if screen.geometry().contains(
                current_center
            ):

                current_index = i
                break

        new_index = (
            current_index
            + direction
        ) % len(screens)

        self.mirror.move_to_screen(
            new_index
        )

        if self.settings is not None:

            QTimer.singleShot(
                50,
                self.settings
                .adjust_to_screen,
            )

    # ========================================================
    # CLEANUP
    # ========================================================

    def cleanup(self):

        if (
            self.hotkey_filter
            is not None
        ):

            self.hotkey_filter.unregister()

        if self.mirror is not None:

            try:
                self.mirror.sct.close()
            except Exception:
                pass

    # ========================================================
    # RUN
    # ========================================================

    def run(self):

        sys.exit(
            self.app.exec()
        )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    app = App()
    app.run()
