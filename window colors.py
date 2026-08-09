
import sys
import mss
import numpy as np

from PyQt6.QtCore import (
    Qt,
    QRect,
    QPoint,
    QTimer,
    pyqtSignal,
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
    QSlider,
    QSpinBox,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
)


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
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )

        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground
        )

        screen = QApplication.primaryScreen()
        self.setGeometry(screen.geometry())

        self.show()

    def mousePressEvent(self, event):

        if event.button() == Qt.MouseButton.LeftButton:

            self.start = event.position().toPoint()
            self.current = self.start

            self.update()

    def mouseMoveEvent(self, event):

        if not self.start.isNull():

            self.current = event.position().toPoint()

            self.update()

    def mouseReleaseEvent(self, event):

        if event.button() == Qt.MouseButton.LeftButton:

            rect = QRect(
                self.start,
                self.current
            ).normalized()

            if rect.width() > 10 and rect.height() > 10:

                self.region_selected.emit(rect)

            self.close()

    def paintEvent(self, event):

        painter = QPainter(self)

        # Dark transparent selection background
        painter.fillRect(
            self.rect(),
            Qt.GlobalColor.black
        )

        if not self.start.isNull():

            rect = QRect(
                self.start,
                self.current
            ).normalized()

            # Clear selected region
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_Clear
            )

            painter.fillRect(
                rect,
                Qt.GlobalColor.transparent
            )

            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceOver
            )

            painter.setPen(
                QPen(
                    Qt.GlobalColor.white,
                    2
                )
            )

            painter.drawRect(rect)


# ============================================================
# LIVE MIRROR
# ============================================================

class LiveMirror(QWidget):

    def __init__(self, region):

        super().__init__()

        self.region = region

        self.fps = 30
        self.transparency = 80

        self.drag_position = None

        self.resizing = False
        self.resize_margin = 12

        self.resize_start_mouse = QPoint()
        self.resize_start_size = self.size()

        # New MSS API
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

        # ----------------------------------------------------
        # WINDOW
        # ----------------------------------------------------

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )

        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground
        )

        self.setWindowOpacity(
            self.transparency / 100
        )

        layout = QVBoxLayout(self)

        layout.setContentsMargins(
            0, 0, 0, 0
        )

        layout.addWidget(
            self.label
        )

        # Initial window size
        self.resize(
            region.width(),
            region.height()
        )

        self.setMinimumSize(
            100,
            100
        )

        # ----------------------------------------------------
        # TIMER
        # ----------------------------------------------------

        self.timer = QTimer()

        self.timer.timeout.connect(
            self.update_screen
        )

        self.set_fps(
            self.fps
        )

        self.show()

    # ========================================================
    # FPS
    # ========================================================

    def set_fps(self, fps):

        self.fps = max(
            1,
            fps
        )

        interval = int(
            1000 / self.fps
        )

        self.timer.setInterval(
            interval
        )

        if not self.timer.isActive():

            self.timer.start()

    # ========================================================
    # TRANSPARENCY
    # ========================================================

    def set_transparency(self, value):

        self.transparency = value

        self.setWindowOpacity(
            value / 100
        )

    # ========================================================
    # SIX COLOR CONVERSION
    # ========================================================

    def convert_to_six_colors(self, image):

        # MSS captures BGRA.
        # Convert BGRA -> RGB.
        rgb = image[:, :, :3][:, :, ::-1].astype(
            np.int16
        )

        # ----------------------------------------------------
        # ALLOWED COLORS
        # ----------------------------------------------------

        colors = np.array(
            [
                [255,   0,   0],   # RED
                [  0, 255,   0],   # GREEN
                [255, 255,   0],   # YELLOW
                [  0,   0, 255],   # BLUE
                [  0,   0,   0],   # BLACK
                [255, 255, 255],   # WHITE
            ],
            dtype=np.int16
        )

        # ----------------------------------------------------
        # COLOR DISTANCE
        # ----------------------------------------------------

        # Compare every pixel with every color.
        diff = (
            rgb[:, :, None, :]
            - colors[None, None, :, :]
        )

        # RGB Euclidean distance squared.
        distance = np.sum(
            diff * diff,
            axis=3
        )

        # Pick closest color.
        nearest = np.argmin(
            distance,
            axis=2
        )

        # Replace each pixel.
        result = colors[nearest].astype(
            np.uint8
        )

        return result

    # ========================================================
    # LIVE CAPTURE
    # ========================================================

    def update_screen(self):

        monitor = {
            "left": self.region.x(),
            "top": self.region.y(),
            "width": self.region.width(),
            "height": self.region.height(),
        }

        # Capture selected screen region.
        frame = self.sct.grab(
            monitor
        )

        # Convert MSS image to NumPy.
        image = np.array(
            frame
        )

        # Convert everything to one of six colors.
        quantized = self.convert_to_six_colors(
            image
        )

        height, width, channels = (
            quantized.shape
        )

        # ----------------------------------------------------
        # QIMAGE
        # ----------------------------------------------------

        qimage = QImage(
            quantized.data,
            width,
            height,
            width * 3,
            QImage.Format.Format_RGB888
        )

        # Make an independent copy of the data.
        pixmap = QPixmap.fromImage(
            qimage.copy()
        )

        # ----------------------------------------------------
        # SCALE
        # ----------------------------------------------------

        scaled = pixmap.scaled(
            self.label.size(),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation
        )

        self.label.setPixmap(
            scaled
        )

    # ========================================================
    # WINDOW DRAG / RESIZE
    # ========================================================

    def mousePressEvent(self, event):

        if event.button() != Qt.MouseButton.LeftButton:
            return

        position = (
            event.position().toPoint()
        )

        # ----------------------------------------------------
        # BOTTOM-RIGHT = RESIZE
        # ----------------------------------------------------

        if (
            position.x()
            >= self.width() - self.resize_margin
            and
            position.y()
            >= self.height() - self.resize_margin
        ):

            self.resizing = True

            self.resize_start_mouse = (
                event.globalPosition().toPoint()
            )

            self.resize_start_size = (
                self.size()
            )

            return

        # ----------------------------------------------------
        # OTHERWISE = MOVE
        # ----------------------------------------------------

        self.drag_position = (
            event.globalPosition().toPoint()
            - self.frameGeometry().topLeft()
        )

    def mouseMoveEvent(self, event):

        position = (
            event.position().toPoint()
        )

        # ----------------------------------------------------
        # RESIZE
        # ----------------------------------------------------

        if self.resizing:

            delta = (
                event.globalPosition().toPoint()
                - self.resize_start_mouse
            )

            new_width = max(
                100,
                self.resize_start_size.width()
                + delta.x()
            )

            new_height = max(
                100,
                self.resize_start_size.height()
                + delta.y()
            )

            self.resize(
                new_width,
                new_height
            )

            return

        # ----------------------------------------------------
        # RESIZE CURSOR
        # ----------------------------------------------------

        if (
            position.x()
            >= self.width() - self.resize_margin
            and
            position.y()
            >= self.height() - self.resize_margin
        ):

            self.setCursor(
                Qt.CursorShape.SizeFDiagCursor
            )

        else:

            self.setCursor(
                Qt.CursorShape.ArrowCursor
            )

        # ----------------------------------------------------
        # MOVE
        # ----------------------------------------------------

        if (
            self.drag_position is not None
            and
            event.buttons()
            & Qt.MouseButton.LeftButton
        ):

            self.move(
                event.globalPosition().toPoint()
                - self.drag_position
            )

    def mouseReleaseEvent(self, event):

        self.drag_position = None

        self.resizing = False

        self.setCursor(
            Qt.CursorShape.ArrowCursor
        )

    # ========================================================
    # ESC
    # ========================================================

    def keyPressEvent(self, event):

        if event.key() == Qt.Key.Key_Escape:

            self.close()


# ============================================================
# SETTINGS
# ============================================================

class Settings(QWidget):

    def __init__(
        self,
        mirror,
        select_callback
    ):

        super().__init__()

        self.mirror = mirror

        self.select_callback = (
            select_callback
        )

        self.setWindowTitle(
            "Live Screen Mirror"
        )

        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
        )

        self.setMinimumWidth(
            320
        )

        # ----------------------------------------------------
        # FPS
        # ----------------------------------------------------

        fps_label = QLabel(
            "FPS:"
        )

        self.fps_spin = QSpinBox()

        self.fps_spin.setRange(
            1,
            144
        )

        self.fps_spin.setValue(
            mirror.fps
        )

        self.fps_spin.valueChanged.connect(
            mirror.set_fps
        )

        fps_layout = QHBoxLayout()

        fps_layout.addWidget(
            fps_label
        )

        fps_layout.addWidget(
            self.fps_spin
        )

        # ----------------------------------------------------
        # TRANSPARENCY
        # ----------------------------------------------------

        transparency_label = QLabel(
            "Transparency:"
        )

        self.transparency_slider = QSlider(
            Qt.Orientation.Horizontal
        )

        self.transparency_slider.setRange(
            10,
            100
        )

        self.transparency_slider.setValue(
            mirror.transparency
        )

        self.transparency_value = QLabel(
            f"{mirror.transparency}%"
        )

        self.transparency_slider.valueChanged.connect(
            self.change_transparency
        )

        transparency_layout = QHBoxLayout()

        transparency_layout.addWidget(
            transparency_label
        )

        transparency_layout.addWidget(
            self.transparency_slider
        )

        transparency_layout.addWidget(
            self.transparency_value
        )

        # ----------------------------------------------------
        # SELECT NEW REGION
        # ----------------------------------------------------

        select_button = QPushButton(
            "Select New Region"
        )

        select_button.clicked.connect(
            self.select_callback
        )

        # ----------------------------------------------------
        # CLOSE
        # ----------------------------------------------------

        close_button = QPushButton(
            "Close Mirror"
        )

        close_button.clicked.connect(
            mirror.close
        )

        # ----------------------------------------------------
        # LAYOUT
        # ----------------------------------------------------

        layout = QVBoxLayout()

        layout.addLayout(
            fps_layout
        )

        layout.addLayout(
            transparency_layout
        )

        layout.addWidget(
            select_button
        )

        layout.addWidget(
            close_button
        )

        self.setLayout(
            layout
        )

        self.show()

    def change_transparency(
        self,
        value
    ):

        self.transparency_value.setText(
            f"{value}%"
        )

        self.mirror.set_transparency(
            value
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

        self.select_region()

    # --------------------------------------------------------
    # SELECT REGION
    # --------------------------------------------------------

    def select_region(self):

        if self.mirror is not None:

            self.mirror.close()

            self.mirror = None

        self.selector = RegionSelector()

        self.selector.region_selected.connect(
            self.create_mirror
        )

    # --------------------------------------------------------
    # CREATE MIRROR
    # --------------------------------------------------------

    def create_mirror(
        self,
        region
    ):

        self.mirror = LiveMirror(
            region
        )

        self.settings = Settings(
            self.mirror,
            self.select_region
        )

    # --------------------------------------------------------
    # RUN
    # --------------------------------------------------------

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
