#!/usr/bin/env python3
"""
CHROMA // TRACKER
High-performance multi-target circular full-color pixel-pattern tracker.

Dependencies:
    pip install PySide6 opencv-python numpy mss

Controls:
    SELECT REGION
        Captures the primary monitor.

    Click in the video
        Creates a new tracking marker.
        Clicking an existing marker selects it.

    START TRACKING / PAUSE TRACKING
        Tracking can be paused without stopping video capture.

    Resolution
        Percentage of native screen resolution used for:
        - video rendering
        - tracking

    FPS
        Controls capture/update rate.

    Circle Radius
        Controls the selected circular tracking template.

    Tracking Quality
        Selects a performance/accuracy preset.

    Advanced Parameters
        Fine-tunes the currently selected tracker.

IMPORTANT:
    This tracker uses COLOR information only.
    No grayscale conversion is used for tracking.
"""

import sys
import time
import math
import copy

from dataclasses import dataclass
from typing import Optional

import cv2
import mss
import numpy as np

from PySide6.QtCore import (
    Qt,
    QThread,
    QObject,
    Signal,
    Slot,
    QPointF,
    QRectF,
)

from PySide6.QtGui import (
    QColor,
    QImage,
    QPainter,
    QPen,
    QBrush,
    QPixmap,
)

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QPushButton,
    QLabel,
    QSlider,
    QSpinBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QVBoxLayout,
    QGridLayout,
    QFrame,
    QMessageBox,
    QDialog,
    QFormLayout,
    QDialogButtonBox,
    QCheckBox,
    QScrollArea,
    QComboBox,
    QListWidget,
    QListWidgetItem,
)


# ============================================================================
# TRACKING QUALITY
# ============================================================================

@dataclass(frozen=True)
class TrackingQuality:
    name: str
    search_radius: int
    processing_scale: float
    coarse_step: int
    refinement_radius: int
    refinement_step: int
    refinement_passes: int
    use_refinement: bool
    confidence_threshold: float
    max_jump: int


TRACKING_QUALITIES = {
    "Ultra Fast": TrackingQuality(
        name="Ultra Fast",
        search_radius=55,
        processing_scale=0.45,
        coarse_step=4,
        refinement_radius=0,
        refinement_step=1,
        refinement_passes=0,
        use_refinement=False,
        confidence_threshold=0.52,
        max_jump=55,
    ),

    "Fast": TrackingQuality(
        name="Fast",
        search_radius=80,
        processing_scale=0.60,
        coarse_step=3,
        refinement_radius=3,
        refinement_step=1,
        refinement_passes=1,
        use_refinement=True,
        confidence_threshold=0.57,
        max_jump=75,
    ),

    "Balanced": TrackingQuality(
        name="Balanced",
        search_radius=120,
        processing_scale=0.80,
        coarse_step=2,
        refinement_radius=5,
        refinement_step=1,
        refinement_passes=1,
        use_refinement=True,
        confidence_threshold=0.62,
        max_jump=100,
    ),

    "Precise": TrackingQuality(
        name="Precise",
        search_radius=180,
        processing_scale=1.00,
        coarse_step=1,
        refinement_radius=7,
        refinement_step=1,
        refinement_passes=2,
        use_refinement=True,
        confidence_threshold=0.68,
        max_jump=140,
    ),
}


# ============================================================================
# DATA
# ============================================================================

@dataclass
class TrackingParameters:
    """
    Parameters that belong to one tracker.

    Resolution/FPS are intentionally NOT stored here because they are
    global capture settings.
    """

    search_radius: int = 150
    min_search_radius: int = 20

    template_radius: int = 30

    match_threshold: float = 0.60
    color_weight: float = 1.0

    smoothing: float = 0.65
    prediction_weight: float = 0.35
    max_jump: int = 120

    coarse_step: int = 2
    refinement_radius: int = 5
    refinement_step: int = 1

    minimum_valid_pixels: float = 0.55
    confidence_falloff: float = 0.15
    hold_frames: int = 3

    use_prediction: bool = True
    use_color: bool = True
    adaptive_template: bool = False

    tracking_quality: str = "Balanced"


@dataclass
class Marker:
    id: int

    x: float
    y: float

    radius: int = 30

    confidence: float = 0.0
    tracking: bool = False

    lost_frames: int = 0

    velocity_x: float = 0.0
    velocity_y: float = 0.0

    template_color: Optional[np.ndarray] = None
    template_mask: Optional[np.ndarray] = None

    template_center_x: float = 0.0
    template_center_y: float = 0.0

    cached_template: Optional[np.ndarray] = None
    cached_mask: Optional[np.ndarray] = None
    cached_scale: Optional[float] = None
    cached_radius: Optional[int] = None

    # NEW:
    # Every tracker gets its own independent parameter set.
    params: Optional[TrackingParameters] = None


# ============================================================================
# SIMULATED DEVICE
# ============================================================================

class DeviceController:

    def __init__(self):
        self.enabled = False
        self.level = 0

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)

    def set_level(self, level):
        self.level = max(0, min(100, int(level)))

    def status(self):
        if not self.enabled:
            return "OFF"

        return f"ACTIVE • {self.level}%"


# ============================================================================
# TRACKING ENGINE
# ============================================================================

class TrackingEngine:

    def __init__(self):

        self.sct = mss.MSS()

        self.region = None

        # Global capture/default parameters.
        self.params = TrackingParameters()

        self.resolution_percent = 50
        self.target_fps = 30

        self.markers = []

        self.next_marker_id = 1

        self.selected_marker_id = None

        self.tracking_enabled = False

        self.last_frame = None

    # ------------------------------------------------------------------------
    # QUALITY
    # ------------------------------------------------------------------------

    def set_tracking_quality(self, quality_name):

        if quality_name not in TRACKING_QUALITIES:
            return

        self.params.tracking_quality = quality_name

        quality = TRACKING_QUALITIES[quality_name]

        self.params.search_radius = quality.search_radius
        self.params.coarse_step = quality.coarse_step
        self.params.refinement_radius = quality.refinement_radius
        self.params.refinement_step = quality.refinement_step

        for marker in self.markers:
            if marker.params is not None:
                marker.params.tracking_quality = quality_name
                marker.params.search_radius = quality.search_radius
                marker.params.coarse_step = quality.coarse_step
                marker.params.refinement_radius = quality.refinement_radius
                marker.params.refinement_step = quality.refinement_step

            self._invalidate_marker_cache(marker)

    def get_tracking_quality(self, params=None):

        if params is None:
            params = self.params

        return TRACKING_QUALITIES.get(
            params.tracking_quality,
            TRACKING_QUALITIES["Balanced"],
        )

    def _apply_quality_to_params(
        self,
        params,
        quality_name,
    ):

        if quality_name not in TRACKING_QUALITIES:
            return

        quality = TRACKING_QUALITIES[quality_name]

        params.tracking_quality = quality_name
        params.search_radius = quality.search_radius
        params.coarse_step = quality.coarse_step
        params.refinement_radius = quality.refinement_radius
        params.refinement_step = quality.refinement_step

    def _invalidate_marker_cache(self, marker):

        marker.cached_template = None
        marker.cached_mask = None
        marker.cached_scale = None
        marker.cached_radius = None

    # ------------------------------------------------------------------------
    # REGION
    # ------------------------------------------------------------------------

    def set_region(self, region):
        self.region = dict(region)

    # ------------------------------------------------------------------------
    # CAPTURE
    # ------------------------------------------------------------------------

    def capture(self):

        if self.region is None:
            return None

        shot = self.sct.grab(self.region)

        frame = np.asarray(
            shot,
            dtype=np.uint8,
        )[:, :, :3]

        return frame

    # ------------------------------------------------------------------------
    # RESIZE
    # ------------------------------------------------------------------------

    def resize_for_processing(self, frame):

        percent = int(
            np.clip(
                self.resolution_percent,
                10,
                100,
            )
        )

        if percent >= 100:
            return frame, 1.0

        h, w = frame.shape[:2]

        scale = percent / 100.0

        new_w = max(
            160,
            int(round(w * scale)),
        )

        new_h = max(
            90,
            int(round(h * scale)),
        )

        resized = cv2.resize(
            frame,
            (new_w, new_h),
            interpolation=cv2.INTER_AREA,
        )

        actual_scale = new_w / float(w)

        return resized, actual_scale

    # ------------------------------------------------------------------------
    # QUALITY PROCESSING SCALE
    # ------------------------------------------------------------------------

    def _quality_processed_frame(
        self,
        frame,
        params,
    ):

        quality = self.get_tracking_quality(params)

        scale = float(
            np.clip(
                quality.processing_scale,
                0.25,
                1.0,
            )
        )

        if scale >= 0.999:
            return frame, 1.0

        h, w = frame.shape[:2]

        new_w = max(
            160,
            int(round(w * scale)),
        )

        new_h = max(
            90,
            int(round(h * scale)),
        )

        if new_w == w and new_h == h:
            return frame, 1.0

        processed = cv2.resize(
            frame,
            (new_w, new_h),
            interpolation=cv2.INTER_AREA,
        )

        actual_scale = new_w / float(w)

        return processed, actual_scale

    # ------------------------------------------------------------------------
    # MASK
    # ------------------------------------------------------------------------

    def _make_circle_mask(self, radius):

        radius = max(1, int(radius))

        size = radius * 2 + 1

        yy, xx = np.ogrid[:size, :size]

        cx = radius
        cy = radius

        mask = (
            (xx - cx) ** 2
            +
            (yy - cy) ** 2
            <= radius ** 2
        )

        return mask.astype(np.uint8) * 255

    # ------------------------------------------------------------------------
    # CREATE MARKER
    # ------------------------------------------------------------------------

    def create_marker(self, x, y):

        frame = self.last_frame

        if frame is None:
            return None

        h, w = frame.shape[:2]

        x = int(
            np.clip(
                x,
                0,
                w - 1,
            )
        )

        y = int(
            np.clip(
                y,
                0,
                h - 1,
            )
        )

        # Each newly created tracker inherits the current global/default
        # parameter configuration.
        marker_params = copy.deepcopy(
            self.params
        )

        radius = max(
            3,
            int(marker_params.template_radius),
        )

        if (
            radius * 2 + 1 > w
            or
            radius * 2 + 1 > h
        ):
            return None

        x = int(
            np.clip(
                x,
                radius,
                w - radius - 1,
            )
        )

        y = int(
            np.clip(
                y,
                radius,
                h - radius - 1,
            )
        )

        x1 = x - radius
        y1 = y - radius

        x2 = x + radius + 1
        y2 = y + radius + 1

        patch = frame[
            y1:y2,
            x1:x2,
        ].copy()

        size = radius * 2 + 1

        if patch.shape[:2] != (size, size):
            return None

        mask = self._make_circle_mask(radius)

        marker = Marker(
            id=self.next_marker_id,
            x=float(x),
            y=float(y),
            radius=radius,
            confidence=0.0,
            tracking=self.tracking_enabled,
            template_color=patch,
            template_mask=mask,
            template_center_x=float(radius),
            template_center_y=float(radius),
            params=marker_params,
        )

        self.next_marker_id += 1

        self.markers.append(marker)

        self.selected_marker_id = marker.id

        return marker

    # ------------------------------------------------------------------------
    # DELETE MARKER
    # ------------------------------------------------------------------------

    def delete_marker(self, marker_id):

        self.markers = [
            marker
            for marker in self.markers
            if marker.id != marker_id
        ]

        if self.selected_marker_id == marker_id:

            if self.markers:
                self.selected_marker_id = self.markers[-1].id
            else:
                self.selected_marker_id = None

    # ------------------------------------------------------------------------
    # CLEAR ALL
    # ------------------------------------------------------------------------

    def clear_markers(self):

        self.markers.clear()

        self.selected_marker_id = None

    # ------------------------------------------------------------------------
    # GET MARKER
    # ------------------------------------------------------------------------

    def get_marker(self, marker_id):

        for marker in self.markers:

            if marker.id == marker_id:
                return marker

        return None

    def get_selected_marker(self):

        if self.selected_marker_id is None:
            return None

        return self.get_marker(
            self.selected_marker_id
        )

    # ------------------------------------------------------------------------
    # PROCESSING TEMPLATE
    # ------------------------------------------------------------------------

    def _get_processing_template(
        self,
        marker,
        scale,
    ):

        if marker is None:
            return None, None

        radius = max(
            3,
            int(round(marker.radius * scale)),
        )

        cache_valid = (
            marker.cached_template is not None
            and marker.cached_mask is not None
            and marker.cached_scale is not None
            and abs(marker.cached_scale - scale) < 1e-6
            and marker.cached_radius == radius
        )

        if cache_valid:
            return (
                marker.cached_template,
                marker.cached_mask,
            )

        if marker.template_color is None:
            return None, None

        size = radius * 2 + 1

        template = cv2.resize(
            marker.template_color,
            (size, size),
            interpolation=cv2.INTER_AREA,
        )

        mask = self._make_circle_mask(radius)

        marker.cached_template = template
        marker.cached_mask = mask
        marker.cached_scale = scale
        marker.cached_radius = radius

        return template, mask

    # ------------------------------------------------------------------------
    # COLOR TEMPLATE MATCHING
    # ------------------------------------------------------------------------

    def _color_match_map(
        self,
        search,
        template,
        mask,
    ):
        """
        Full-color matching.

        Each B/G/R channel is evaluated independently and the responses
        are averaged.

        NaN / Inf values are explicitly removed before returning.
        """

        if (
            search is None
            or template is None
            or mask is None
        ):
            return None

        if (
            not isinstance(search, np.ndarray)
            or not isinstance(template, np.ndarray)
        ):
            return None

        if (
            search.ndim != 3
            or template.ndim != 3
            or search.shape[2] != 3
            or template.shape[2] != 3
        ):
            return None

        if (
            template.shape[0] > search.shape[0]
            or template.shape[1] > search.shape[1]
        ):
            return None

        channels = []

        for channel in range(3):

            search_channel = np.ascontiguousarray(
                search[:, :, channel]
            )

            template_channel = np.ascontiguousarray(
                template[:, :, channel]
            )

            # Constant templates can cause normalized correlation to
            # produce invalid values. Handle them explicitly.
            t_std = float(
                np.std(
                    template_channel
                )
            )

            if not np.isfinite(t_std) or t_std < 1e-6:

                response = cv2.matchTemplate(
                    search_channel,
                    template_channel,
                    cv2.TM_SQDIFF_NORMED,
                    mask=mask,
                )

                response = 1.0 - response

            else:

                response = cv2.matchTemplate(
                    search_channel,
                    template_channel,
                    cv2.TM_CCORR_NORMED,
                    mask=mask,
                )

            response = np.asarray(
                response,
                dtype=np.float32,
            )

            # Critical numerical safety:
            response = np.nan_to_num(
                response,
                nan=0.0,
                posinf=1.0,
                neginf=0.0,
            )

            channels.append(response)

        if len(channels) != 3:
            return None

        combined = (
            channels[0]
            +
            channels[1]
            +
            channels[2]
        ) / 3.0

        combined = np.nan_to_num(
            combined,
            nan=0.0,
            posinf=1.0,
            neginf=0.0,
        )

        return np.clip(
            combined,
            0.0,
            1.0,
        ).astype(np.float32)

    # ------------------------------------------------------------------------
    # SEARCH WINDOW
    # ------------------------------------------------------------------------

    def _get_search_window(
        self,
        frame,
        predicted_x,
        predicted_y,
        marker,
        search_radius,
    ):

        h, w = frame.shape[:2]

        template_radius = marker.radius

        left = max(
            template_radius,
            int(
                round(
                    predicted_x - search_radius
                )
            ),
        )

        right = min(
            w - template_radius - 1,
            int(
                round(
                    predicted_x + search_radius
                )
            ),
        )

        top = max(
            template_radius,
            int(
                round(
                    predicted_y - search_radius
                )
            ),
        )

        bottom = min(
            h - template_radius - 1,
            int(
                round(
                    predicted_y + search_radius
                )
            ),
        )

        if (
            left > right
            or
            top > bottom
        ):
            return None

        x1 = left - template_radius
        y1 = top - template_radius

        x2 = right + template_radius + 1
        y2 = bottom + template_radius + 1

        x1 = max(0, x1)
        y1 = max(0, y1)

        x2 = min(w, x2)
        y2 = min(h, y2)

        if (
            x2 <= x1
            or
            y2 <= y1
        ):
            return None

        return (
            x1,
            y1,
            x2,
            y2,
            left,
            top,
            right,
            bottom,
        )

    # ------------------------------------------------------------------------
    # TRACK ONE MARKER
    # ------------------------------------------------------------------------

    def _track_marker(
        self,
        tracking_frame,
        marker,
        total_scale,
    ):

        if (
            marker.template_color is None
            or
            marker.params is None
        ):
            return

        params = marker.params

        quality = self.get_tracking_quality(
            params
        )

        tracking_radius = max(
            3,
            int(
                round(
                    marker.radius
                    *
                    total_scale
                )
            ),
        )

        template = cv2.resize(
            marker.template_color,
            (
                tracking_radius * 2 + 1,
                tracking_radius * 2 + 1,
            ),
            interpolation=cv2.INTER_AREA,
        )

        mask = self._make_circle_mask(
            tracking_radius
        )

        # --------------------------------------------------------------
        # PREDICTION
        # --------------------------------------------------------------

        px = marker.x * total_scale
        py = marker.y * total_scale

        predicted_x = px
        predicted_y = py

        if params.use_prediction:

            predicted_x += (
                marker.velocity_x
                *
                params.prediction_weight
                *
                total_scale
            )

            predicted_y += (
                marker.velocity_y
                *
                params.prediction_weight
                *
                total_scale
            )

        # --------------------------------------------------------------
        # SEARCH RADIUS
        # --------------------------------------------------------------

        search_radius = max(
            quality.search_radius * total_scale,
            params.min_search_radius * total_scale,
        )

        processing_marker = Marker(
            id=marker.id,
            x=predicted_x,
            y=predicted_y,
            radius=tracking_radius,
            template_color=template,
            template_mask=mask,
            params=params,
        )

        window = self._get_search_window(
            tracking_frame,
            predicted_x,
            predicted_y,
            processing_marker,
            int(round(search_radius)),
        )

        if window is None:

            marker.lost_frames += 1
            marker.confidence *= 0.90

            marker.velocity_x *= 0.80
            marker.velocity_y *= 0.80

            return

        (
            x1,
            y1,
            x2,
            y2,
            _,
            _,
            _,
            _,
        ) = window

        search = tracking_frame[
            y1:y2,
            x1:x2,
        ]

        # --------------------------------------------------------------
        # COLOR MATCH
        # --------------------------------------------------------------

        response = self._color_match_map(
            search,
            template,
            mask,
        )

        if response is None:

            marker.lost_frames += 1
            marker.confidence *= 0.90

            return

        response = np.nan_to_num(
            response,
            nan=0.0,
            posinf=1.0,
            neginf=0.0,
        )

        if response.size == 0:

            marker.lost_frames += 1
            return

        _, max_score, _, max_loc = cv2.minMaxLoc(
            response
        )

        th, tw = template.shape[:2]

        found_x = (
            x1
            + max_loc[0]
            + tw / 2.0
        )

        found_y = (
            y1
            + max_loc[1]
            + th / 2.0
        )

        score = float(
            np.clip(
                max_score,
                0.0,
                1.0,
            )
        )

        if not np.isfinite(score):
            score = 0.0

        # --------------------------------------------------------------
        # LOCAL REFINEMENT
        # --------------------------------------------------------------

        if (
            quality.use_refinement
            and
            score < 0.90
        ):

            refine_radius = max(
                1,
                int(
                    round(
                        quality.refinement_radius
                        *
                        total_scale
                    )
                ),
            )

            refine_window = self._get_search_window(
                tracking_frame,
                found_x,
                found_y,
                processing_marker,
                refine_radius,
            )

            if refine_window is not None:

                (
                    rx1,
                    ry1,
                    rx2,
                    ry2,
                    _,
                    _,
                    _,
                    _,
                ) = refine_window

                refinement_search = tracking_frame[
                    ry1:ry2,
                    rx1:rx2,
                ]

                refinement_response = (
                    self._color_match_map(
                        refinement_search,
                        template,
                        mask,
                    )
                )

                if refinement_response is not None:

                    (
                        _,
                        refinement_score,
                        _,
                        refinement_loc,
                    ) = cv2.minMaxLoc(
                        refinement_response
                    )

                    refinement_x = (
                        rx1
                        +
                        refinement_loc[0]
                        +
                        tw / 2.0
                    )

                    refinement_y = (
                        ry1
                        +
                        refinement_loc[1]
                        +
                        th / 2.0
                    )

                    refinement_score = float(
                        np.clip(
                            refinement_score,
                            0.0,
                            1.0,
                        )
                    )

                    if np.isfinite(
                        refinement_score
                    ) and refinement_score > score:

                        found_x = refinement_x
                        found_y = refinement_y
                        score = refinement_score

        # --------------------------------------------------------------
        # CONFIDENCE
        # --------------------------------------------------------------

        marker.confidence = float(
            np.clip(
                score,
                0.0,
                1.0,
            )
        )

        # --------------------------------------------------------------
        # MOTION LIMIT
        # --------------------------------------------------------------

        current_x = px
        current_y = py

        dx = found_x - current_x
        dy = found_y - current_y

        distance = math.sqrt(
            dx * dx
            +
            dy * dy
        )

        max_jump = (
            quality.max_jump
            *
            total_scale
        )

        if (
            distance > max_jump
            and
            max_jump > 0
        ):

            factor = (
                max_jump
                /
                distance
            )

            found_x = (
                current_x
                +
                dx * factor
            )

            found_y = (
                current_y
                +
                dy * factor
            )

        # --------------------------------------------------------------
        # CONFIDENCE MOVEMENT
        # --------------------------------------------------------------

        threshold = max(
            0.0,
            min(
                1.0,
                max(
                    params.match_threshold,
                    quality.confidence_threshold,
                ),
            ),
        )

        if score >= threshold:

            smoothing = float(
                np.clip(
                    params.smoothing,
                    0.0,
                    1.0,
                )
            )

            movement = 1.0 - smoothing

            confidence_factor = np.clip(
                (
                    score - threshold
                )
                /
                max(
                    0.01,
                    1.0 - threshold,
                ),
                0.0,
                1.0,
            )

            movement *= (
                0.35
                +
                0.65
                *
                confidence_factor
            )

            new_x = (
                current_x
                +
                (
                    found_x
                    -
                    current_x
                )
                *
                movement
            )

            new_y = (
                current_y
                +
                (
                    found_y
                    -
                    current_y
                )
                *
                movement
            )

            new_original_x = (
                new_x
                /
                total_scale
            )

            new_original_y = (
                new_y
                /
                total_scale
            )

            old_x = marker.x
            old_y = marker.y

            marker.velocity_x = (
                marker.velocity_x * 0.65
                +
                (
                    new_original_x
                    -
                    old_x
                )
                * 0.35
            )

            marker.velocity_y = (
                marker.velocity_y * 0.65
                +
                (
                    new_original_y
                    -
                    old_y
                )
                * 0.35
            )

            # Safety against invalid coordinates.
            if (
                np.isfinite(new_original_x)
                and
                np.isfinite(new_original_y)
            ):

                marker.x = new_original_x
                marker.y = new_original_y

            marker.lost_frames = 0
            marker.tracking = True

            if (
                params.adaptive_template
                and
                score >= 0.80
            ):

                self._update_adaptive_template(
                    self.last_frame,
                    marker,
                )

        else:

            marker.lost_frames += 1

            marker.velocity_x *= 0.80
            marker.velocity_y *= 0.80

            if (
                marker.lost_frames
                >
                params.hold_frames
            ):

                marker.tracking = False

    # ------------------------------------------------------------------------
    # TRACK ALL MARKERS
    # ------------------------------------------------------------------------

    def track(self, frame):

        processed, render_scale = (
            self.resize_for_processing(frame)
        )

        if not self.tracking_enabled:

            for marker in self.markers:
                marker.tracking = False

            return (
                processed,
                render_scale,
            )

        if not self.markers:

            return (
                processed,
                render_scale,
            )

        # Track each marker using its OWN quality/processing scale.
        #
        # This is slightly more expensive than using one common processing
        # scale, but it is necessary because each tracker can now have
        # independent quality settings.

        for marker in self.markers:

            if marker.template_color is None:
                continue

            if marker.params is None:
                marker.params = copy.deepcopy(
                    self.params
                )

            tracking_frame, quality_scale = (
                self._quality_processed_frame(
                    processed,
                    marker.params,
                )
            )

            total_scale = (
                render_scale
                *
                quality_scale
            )

            if total_scale <= 0:
                total_scale = 1.0

            self._track_marker(
                tracking_frame,
                marker,
                total_scale,
            )

        return (
            processed,
            render_scale,
        )

    # ------------------------------------------------------------------------
    # ADAPTIVE TEMPLATE
    # ------------------------------------------------------------------------

    def _update_adaptive_template(
        self,
        native_frame,
        marker,
    ):

        if marker is None:
            return

        radius = marker.radius

        patch = self._extract_patch(
            native_frame,
            marker.x,
            marker.y,
            radius,
        )

        if patch is None:
            return

        if (
            marker.template_color is None
            or
            patch.shape != marker.template_color.shape
        ):
            return

        alpha = 0.015

        marker.template_color = (
            marker.template_color.astype(
                np.float32
            )
            *
            (1.0 - alpha)
            +
            patch.astype(
                np.float32
            )
            *
            alpha
        ).astype(np.uint8)

        self._invalidate_marker_cache(
            marker
        )

    # ------------------------------------------------------------------------
    # EXTRACT PATCH
    # ------------------------------------------------------------------------

    def _extract_patch(
        self,
        frame,
        center_x,
        center_y,
        radius,
    ):

        size = radius * 2 + 1

        x1 = (
            int(round(center_x))
            -
            radius
        )

        y1 = (
            int(round(center_y))
            -
            radius
        )

        x2 = x1 + size
        y2 = y1 + size

        h, w = frame.shape[:2]

        if (
            x1 < 0
            or
            y1 < 0
            or
            x2 > w
            or
            y2 > h
        ):
            return None

        return frame[
            y1:y2,
            x1:x2,
        ]


# ============================================================================
# WORKER
# ============================================================================

class TrackerWorker(QObject):

    frame_ready = Signal(object, float)
    fps_changed = Signal(float)
    confidence_changed = Signal(object)
    error = Signal(str)
    finished = Signal()

    def __init__(self, engine):

        super().__init__()

        self.engine = engine
        self.running = False

    @Slot()
    def run(self):

        self.running = True

        frame_counter = 0
        fps_timer = time.perf_counter()

        try:

            while self.running:

                frame_start = time.perf_counter()

                frame = self.engine.capture()

                if frame is None:

                    time.sleep(0.005)
                    continue

                self.engine.last_frame = frame

                processed, scale = (
                    self.engine.track(frame)
                )

                self.frame_ready.emit(
                    processed,
                    scale,
                )

                confidence_data = [
                    (
                        marker.id,
                        float(
                            np.nan_to_num(
                                marker.confidence,
                                nan=0.0,
                                posinf=1.0,
                                neginf=0.0,
                            )
                        ),
                        marker.tracking,
                    )
                    for marker
                    in self.engine.markers
                ]

                self.confidence_changed.emit(
                    confidence_data
                )

                frame_counter += 1

                now = time.perf_counter()

                if (
                    now - fps_timer
                    >= 1.0
                ):

                    fps = (
                        frame_counter
                        /
                        (
                            now
                            -
                            fps_timer
                        )
                    )

                    self.fps_changed.emit(
                        fps
                    )

                    frame_counter = 0
                    fps_timer = now

                target_fps = max(
                    1,
                    int(
                        self.engine.target_fps
                    ),
                )

                frame_period = (
                    1.0
                    /
                    target_fps
                )

                elapsed = (
                    time.perf_counter()
                    -
                    frame_start
                )

                remaining = (
                    frame_period
                    -
                    elapsed
                )

                if remaining > 0:

                    time.sleep(
                        remaining
                    )

        except Exception as exc:

            self.error.emit(
                f"{type(exc).__name__}: {exc}"
            )

        finally:

            self.running = False
            self.finished.emit()

    def stop(self):

        self.running = False


# ============================================================================
# ADVANCED PARAMETERS
# ============================================================================

class AdvancedParametersDialog(QDialog):

    def __init__(
        self,
        engine,
        selected_marker_id,
        parent=None,
    ):

        super().__init__(parent)

        self.engine = engine

        self.selected_marker_id = (
            selected_marker_id
        )

        self._loading_tracker = False

        self.setWindowTitle(
            "CHROMA // ADVANCED PARAMETERS"
        )

        self.setModal(True)

        self.setMinimumSize(
            540,
            720,
        )

        self.resize(
            560,
            760,
        )

        self.setStyleSheet(
            """
            QDialog {
                background: #11101b;
                color: #eee9ff;
                border: 1px solid #403858;
            }

            QWidget {
                color: #eee9ff;
                font-family: "Segoe UI";
                font-size: 13px;
            }

            #dialogRoot {
                background: #11101b;
                border: 1px solid #403858;
                border-radius: 14px;
            }

            #dialogHeader {
                background: #201c32;
                border: 1px solid #403858;
                border-radius: 10px;
            }

            #dialogTitle {
                color: #eee9ff;
                font-size: 15px;
                font-weight: 700;
            }

            #dialogSubtitle {
                color: #8f89a5;
                font-size: 11px;
            }

            #settingsPanel {
                background: #201c32;
                border: 1px solid #403858;
                border-radius: 12px;
            }

            #groupTitle {
                color: #c5a7ff;
                font-size: 11px;
                font-weight: 800;
                padding: 4px 2px;
            }

            QLabel {
                color: #eee9ff;
            }

            QSpinBox,
            QDoubleSpinBox,
            QComboBox {
                background: #171526;
                color: #eee9ff;
                border: 1px solid #4b4263;
                border-radius: 7px;
                padding: 6px;
                min-height: 24px;
            }

            QSpinBox:hover,
            QDoubleSpinBox:hover,
            QComboBox:hover {
                border-color: #76659d;
            }

            QSpinBox:focus,
            QDoubleSpinBox:focus,
            QComboBox:focus {
                border-color: #c58cff;
            }

            QComboBox QAbstractItemView {
                background: #171526;
                color: #eee9ff;
                border: 1px solid #4b4263;
                selection-background-color: #8c3e76;
            }

            QCheckBox {
                color: #eee9ff;
                spacing: 8px;
                padding: 5px 2px;
            }

            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 5px;
                border: 1px solid #594c78;
                background: #171526;
            }

            QCheckBox::indicator:hover {
                border-color: #c58cff;
            }

            QCheckBox::indicator:checked {
                background: #8c3e76;
                border-color: #e37ac4;
            }

            QPushButton {
                background: #302849;
                color: #eee9ff;
                border: 1px solid #594c78;
                border-radius: 9px;
                padding: 8px 18px;
                min-width: 80px;
            }

            QPushButton:hover {
                background: #3b3158;
            }

            QPushButton:pressed {
                background: #271f3b;
            }

            QDialogButtonBox QPushButton {
                min-height: 28px;
            }

            #okButton {
                background: #8c3e76;
                border-color: #c85aaa;
                font-weight: 700;
            }

            #okButton:hover {
                background: #a44a8c;
            }

            #infoBox {
                background: #171526;
                border: 1px solid #403858;
                border-radius: 10px;
                color: #9690aa;
                padding: 10px;
            }

            QScrollArea {
                border: none;
                background: transparent;
            }

            QScrollBar:vertical {
                background: #171526;
                width: 10px;
                border-radius: 5px;
                margin: 2px;
            }

            QScrollBar::handle:vertical {
                background: #4b4263;
                border-radius: 5px;
                min-height: 30px;
            }

            QScrollBar::handle:vertical:hover {
                background: #675984;
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
            }
            """
        )

        self._build_ui()

        self._populate_tracker_selector()

        self._load_current_tracker()

    # ------------------------------------------------------------------------
    # BUILD
    # ------------------------------------------------------------------------

    def _build_ui(self):

        outer = QVBoxLayout(self)

        outer.setContentsMargins(
            8,
            8,
            8,
            8,
        )

        outer.setSpacing(8)

        root = QFrame()

        root.setObjectName(
            "dialogRoot"
        )

        root_layout = QVBoxLayout(root)

        root_layout.setContentsMargins(
            10,
            10,
            10,
            10,
        )

        root_layout.setSpacing(8)

        # ------------------------------------------------------------
        # HEADER
        # ------------------------------------------------------------

        header = QFrame()

        header.setObjectName(
            "dialogHeader"
        )

        header.setFixedHeight(60)

        header_layout = QVBoxLayout(header)

        header_layout.setContentsMargins(
            14,
            7,
            14,
            7,
        )

        header_layout.setSpacing(0)

        title = QLabel(
            "◈  ADVANCED PARAMETERS"
        )

        title.setObjectName(
            "dialogTitle"
        )

        subtitle = QLabel(
            "Per-tracker full-color tracking configuration"
        )

        subtitle.setObjectName(
            "dialogSubtitle"
        )

        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)

        root_layout.addWidget(header)

        # ------------------------------------------------------------
        # TRACKER SELECTOR
        # ------------------------------------------------------------

        selector_frame, selector_layout = (
            self._create_group(
                "EDIT TRACKER"
            )
        )

        selector_form = QFormLayout()

        selector_form.setHorizontalSpacing(16)
        selector_form.setVerticalSpacing(7)

        self.tracker_combo = QComboBox()

        self.tracker_combo.currentIndexChanged.connect(
            self._tracker_changed
        )

        selector_form.addRow(
            "Parameters for:",
            self.tracker_combo,
        )

        selector_layout.addLayout(
            selector_form
        )

        root_layout.addWidget(
            selector_frame
        )

        # ------------------------------------------------------------
        # SCROLL
        # ------------------------------------------------------------

        scroll = QScrollArea()

        scroll.setWidgetResizable(True)

        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )

        content = QWidget()

        content_layout = QVBoxLayout(content)

        content_layout.setContentsMargins(
            2,
            2,
            2,
            2,
        )

        content_layout.setSpacing(8)

        # ------------------------------------------------------------
        # QUALITY
        # ------------------------------------------------------------

        quality_frame, quality_layout = (
            self._create_group(
                "TRACKING QUALITY"
            )
        )

        quality_form = QFormLayout()

        quality_form.setHorizontalSpacing(16)
        quality_form.setVerticalSpacing(7)

        self.quality_combo = QComboBox()

        for name in TRACKING_QUALITIES:
            self.quality_combo.addItem(name)

        quality_form.addRow(
            "Tracking quality:",
            self.quality_combo,
        )

        quality_layout.addLayout(
            quality_form
        )

        content_layout.addWidget(
            quality_frame
        )

        # ------------------------------------------------------------
        # PERFORMANCE
        # ------------------------------------------------------------

        performance_frame, performance_layout = (
            self._create_group(
                "GLOBAL PERFORMANCE"
            )
        )

        performance_form = QFormLayout()

        performance_form.setHorizontalSpacing(16)
        performance_form.setVerticalSpacing(7)

        self.resolution = QSpinBox()

        self.resolution.setRange(
            10,
            100,
        )

        self.resolution.setSingleStep(5)

        self.resolution.setSuffix("%")

        self.resolution.setValue(
            self.engine.resolution_percent
        )

        performance_form.addRow(
            "Video / tracking resolution:",
            self.resolution,
        )

        self.target_fps = QSpinBox()

        self.target_fps.setRange(
            1,
            240,
        )

        self.target_fps.setValue(
            self.engine.target_fps
        )

        performance_form.addRow(
            "Target FPS:",
            self.target_fps,
        )

        performance_layout.addLayout(
            performance_form
        )

        content_layout.addWidget(
            performance_frame
        )

        # ------------------------------------------------------------
        # SEARCH
        # ------------------------------------------------------------

        search_frame, search_layout = (
            self._create_group(
                "SEARCH BEHAVIOR"
            )
        )

        search_form = QFormLayout()

        search_form.setHorizontalSpacing(16)
        search_form.setVerticalSpacing(7)

        self.search_radius = QSpinBox()

        self.search_radius.setRange(
            10,
            2000,
        )

        search_form.addRow(
            "Search radius:",
            self.search_radius,
        )

        self.min_search_radius = QSpinBox()

        self.min_search_radius.setRange(
            1,
            1000,
        )

        search_form.addRow(
            "Minimum search radius:",
            self.min_search_radius,
        )

        self.template_radius = QSpinBox()

        self.template_radius.setRange(
            3,
            300,
        )

        search_form.addRow(
            "Template radius:",
            self.template_radius,
        )

        self.coarse_step = QSpinBox()

        self.coarse_step.setRange(
            1,
            20,
        )

        search_form.addRow(
            "Search step:",
            self.coarse_step,
        )

        self.refinement_radius = QSpinBox()

        self.refinement_radius.setRange(
            0,
            50,
        )

        search_form.addRow(
            "Refinement radius:",
            self.refinement_radius,
        )

        self.refinement_step = QSpinBox()

        self.refinement_step.setRange(
            1,
            10,
        )

        search_form.addRow(
            "Refinement step:",
            self.refinement_step,
        )

        search_layout.addLayout(
            search_form
        )

        content_layout.addWidget(
            search_frame
        )

        # ------------------------------------------------------------
        # MATCHING
        # ------------------------------------------------------------

        matching_frame, matching_layout = (
            self._create_group(
                "FULL-COLOR MATCHING"
            )
        )

        matching_form = QFormLayout()

        matching_form.setHorizontalSpacing(16)
        matching_form.setVerticalSpacing(7)

        self.threshold = QDoubleSpinBox()

        self.threshold.setRange(
            0.0,
            1.0,
        )

        self.threshold.setSingleStep(0.01)

        self.threshold.setDecimals(2)

        matching_form.addRow(
            "Minimum match:",
            self.threshold,
        )

        matching_layout.addLayout(
            matching_form
        )

        color_info = QLabel(
            "Every tracker uses its own complete BGR "
            "pixel template. Grayscale matching is disabled."
        )

        color_info.setObjectName(
            "infoBox"
        )

        color_info.setWordWrap(True)

        matching_layout.addWidget(
            color_info
        )

        content_layout.addWidget(
            matching_frame
        )

        # ------------------------------------------------------------
        # MOTION
        # ------------------------------------------------------------

        motion_frame, motion_layout = (
            self._create_group(
                "MOTION"
            )
        )

        motion_form = QFormLayout()

        motion_form.setHorizontalSpacing(16)
        motion_form.setVerticalSpacing(7)

        self.smoothing = QDoubleSpinBox()

        self.smoothing.setRange(
            0.0,
            0.99,
        )

        self.smoothing.setSingleStep(0.05)

        self.smoothing.setDecimals(2)

        motion_form.addRow(
            "Movement smoothing:",
            self.smoothing,
        )

        self.prediction = QDoubleSpinBox()

        self.prediction.setRange(
            0.0,
            2.0,
        )

        self.prediction.setSingleStep(0.05)

        self.prediction.setDecimals(2)

        motion_form.addRow(
            "Prediction weight:",
            self.prediction,
        )

        self.max_jump = QSpinBox()

        self.max_jump.setRange(
            1,
            2000,
        )

        motion_form.addRow(
            "Maximum jump:",
            self.max_jump,
        )

        motion_layout.addLayout(
            motion_form
        )

        content_layout.addWidget(
            motion_frame
        )

        # ------------------------------------------------------------
        # ROBUSTNESS
        # ------------------------------------------------------------

        robustness_frame, robustness_layout = (
            self._create_group(
                "ROBUSTNESS"
            )
        )

        robustness_form = QFormLayout()

        robustness_form.setHorizontalSpacing(16)
        robustness_form.setVerticalSpacing(7)

        self.minimum_valid_pixels = QDoubleSpinBox()

        self.minimum_valid_pixels.setRange(
            0.0,
            1.0,
        )

        self.minimum_valid_pixels.setSingleStep(
            0.05
        )

        self.minimum_valid_pixels.setDecimals(
            2
        )

        robustness_form.addRow(
            "Minimum valid pixels:",
            self.minimum_valid_pixels,
        )

        self.hold_frames = QSpinBox()

        self.hold_frames.setRange(
            0,
            30,
        )

        robustness_form.addRow(
            "Hold frames:",
            self.hold_frames,
        )

        robustness_layout.addLayout(
            robustness_form
        )

        content_layout.addWidget(
            robustness_frame
        )

        # ------------------------------------------------------------
        # MODES
        # ------------------------------------------------------------

        modes_frame, modes_layout = (
            self._create_group(
                "TRACKING MODE"
            )
        )

        self.prediction_check = QCheckBox(
            "Use motion prediction"
        )

        modes_layout.addWidget(
            self.prediction_check
        )

        self.color_check = QCheckBox(
            "Use color information"
        )

        self.color_check.setChecked(True)
        self.color_check.setEnabled(False)

        modes_layout.addWidget(
            self.color_check
        )

        self.adaptive_check = QCheckBox(
            "Adaptive template"
        )

        modes_layout.addWidget(
            self.adaptive_check
        )

        content_layout.addWidget(
            modes_frame
        )

        # ------------------------------------------------------------
        # INFORMATION
        # ------------------------------------------------------------

        info = QLabel(
            "<b>PER-TRACKER SETTINGS</b><br><br>"
            "Select a tracker above and modify its parameters "
            "independently. Tracker #1 can use Precise while "
            "Tracker #2 uses Ultra Fast.<br><br>"
            "Resolution and target FPS remain global because "
            "they control the capture pipeline."
        )

        info.setObjectName(
            "infoBox"
        )

        info.setWordWrap(True)

        info.setMinimumHeight(145)

        content_layout.addWidget(info)

        content_layout.addStretch()

        scroll.setWidget(content)

        root_layout.addWidget(
            scroll,
            1,
        )

        # ------------------------------------------------------------
        # BUTTONS
        # ------------------------------------------------------------

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok
            |
            QDialogButtonBox.Cancel
        )

        ok_button = buttons.button(
            QDialogButtonBox.Ok
        )

        if ok_button:

            ok_button.setObjectName(
                "okButton"
            )

        buttons.accepted.connect(
            self._apply_and_accept
        )

        buttons.rejected.connect(
            self.reject
        )

        root_layout.addWidget(
            buttons
        )

        outer.addWidget(root)

    # ------------------------------------------------------------------------
    # GROUP CREATION
    # ------------------------------------------------------------------------

    def _create_group(
        self,
        title,
    ):

        # IMPORTANT:
        # Return BOTH the QFrame and its layout.
        #
        # The previous implementation returned only a QLayout.
        # PySide can then lose the Python ownership wrapper while Qt owns
        # the underlying layout, which can produce:
        #
        #     RuntimeError: Internal C++ object (QVBoxLayout) already deleted
        #
        # Keeping the parent frame alive eliminates that ownership problem.

        frame = QFrame()

        frame.setObjectName(
            "settingsPanel"
        )

        layout = QVBoxLayout(frame)

        layout.setContentsMargins(
            12,
            8,
            12,
            10,
        )

        layout.setSpacing(5)

        label = QLabel(title)

        label.setObjectName(
            "groupTitle"
        )

        layout.addWidget(label)

        return frame, layout

    # ------------------------------------------------------------------------
    # TRACKER SELECTOR
    # ------------------------------------------------------------------------

    def _populate_tracker_selector(self):

        self._loading_tracker = True

        self.tracker_combo.clear()

        if not self.engine.markers:

            self.tracker_combo.addItem(
                "No trackers"
            )

            self.tracker_combo.setEnabled(
                False
            )

        else:

            self.tracker_combo.setEnabled(
                True
            )

            for marker in self.engine.markers:

                self.tracker_combo.addItem(
                    f"Tracker #{marker.id}",
                    marker.id,
                )

            index = 0

            if self.selected_marker_id is not None:

                for i in range(
                    self.tracker_combo.count()
                ):

                    if (
                        self.tracker_combo.itemData(i)
                        ==
                        self.selected_marker_id
                    ):

                        index = i
                        break

            self.tracker_combo.setCurrentIndex(
                index
            )

        self._loading_tracker = False

    # ------------------------------------------------------------------------
    # CURRENT PARAMETERS
    # ------------------------------------------------------------------------

    def _current_marker(self):

        if not self.tracker_combo.isEnabled():
            return None

        marker_id = (
            self.tracker_combo.currentData()
        )

        if marker_id is None:
            return None

        return self.engine.get_marker(
            marker_id
        )

    def _current_params(self):

        marker = self._current_marker()

        if marker is None:
            return self.engine.params

        if marker.params is None:

            marker.params = copy.deepcopy(
                self.engine.params
            )

        return marker.params

    # ------------------------------------------------------------------------
    # LOAD TRACKER
    # ------------------------------------------------------------------------

    def _load_current_tracker(self):

        params = self._current_params()

        self._loading_tracker = True

        self.quality_combo.setCurrentText(
            params.tracking_quality
        )

        self.search_radius.setValue(
            params.search_radius
        )

        self.min_search_radius.setValue(
            params.min_search_radius
        )

        self.template_radius.setValue(
            params.template_radius
        )

        self.coarse_step.setValue(
            params.coarse_step
        )

        self.refinement_radius.setValue(
            params.refinement_radius
        )

        self.refinement_step.setValue(
            params.refinement_step
        )

        self.threshold.setValue(
            params.match_threshold
        )

        self.smoothing.setValue(
            params.smoothing
        )

        self.prediction.setValue(
            params.prediction_weight
        )

        self.max_jump.setValue(
            params.max_jump
        )

        self.minimum_valid_pixels.setValue(
            params.minimum_valid_pixels
        )

        self.hold_frames.setValue(
            params.hold_frames
        )

        self.prediction_check.setChecked(
            params.use_prediction
        )

        self.adaptive_check.setChecked(
            params.adaptive_template
        )

        self.resolution.setValue(
            self.engine.resolution_percent
        )

        self.target_fps.setValue(
            self.engine.target_fps
        )

        self._loading_tracker = False

    # ------------------------------------------------------------------------
    # TRACKER CHANGED
    # ------------------------------------------------------------------------

    def _tracker_changed(
        self,
        index,
    ):

        if self._loading_tracker:
            return

        self._load_current_tracker()

    # ------------------------------------------------------------------------
    # APPLY
    # ------------------------------------------------------------------------

    def _apply_current_tracker(self):

        marker = self._current_marker()

        params = self._current_params()

        # Global
        self.engine.resolution_percent = (
            self.resolution.value()
        )

        self.engine.target_fps = (
            self.target_fps.value()
        )

        # Per tracker
        params.tracking_quality = (
            self.quality_combo.currentText()
        )

        params.search_radius = (
            self.search_radius.value()
        )

        params.min_search_radius = (
            self.min_search_radius.value()
        )

        params.template_radius = (
            self.template_radius.value()
        )

        params.coarse_step = (
            self.coarse_step.value()
        )

        params.refinement_radius = (
            self.refinement_radius.value()
        )

        params.refinement_step = (
            self.refinement_step.value()
        )

        params.match_threshold = (
            self.threshold.value()
        )

        params.color_weight = 1.0

        params.smoothing = (
            self.smoothing.value()
        )

        params.prediction_weight = (
            self.prediction.value()
        )

        params.max_jump = (
            self.max_jump.value()
        )

        params.minimum_valid_pixels = (
            self.minimum_valid_pixels.value()
        )

        params.hold_frames = (
            self.hold_frames.value()
        )

        params.use_prediction = (
            self.prediction_check.isChecked()
        )

        params.use_color = True

        params.adaptive_template = (
            self.adaptive_check.isChecked()
        )

        # Update the quality-dependent values.
        self.engine._apply_quality_to_params(
            params,
            params.tracking_quality,
        )

        if marker is not None:

            marker.params = params

            # If the template radius changed, rebuild the actual template.
            if (
                marker.radius
                !=
                params.template_radius
            ):

                rebuilt = self._rebuild_marker(
                    marker,
                    params.template_radius,
                )

                if rebuilt is not None:
                    marker = rebuilt

            self.engine._invalidate_marker_cache(
                marker
            )

        # Keep global defaults synchronized for newly created trackers.
        self.engine.params.tracking_quality = (
            params.tracking_quality
        )

        self.engine.params.search_radius = (
            params.search_radius
        )

        self.engine.params.min_search_radius = (
            params.min_search_radius
        )

        self.engine.params.template_radius = (
            params.template_radius
        )

    # ------------------------------------------------------------------------
    # REBUILD MARKER
    # ------------------------------------------------------------------------

    def _rebuild_marker(
        self,
        marker,
        radius,
    ):

        frame = self.engine.last_frame

        if frame is None:
            return None

        h, w = frame.shape[:2]

        radius = max(
            3,
            int(radius),
        )

        if (
            radius * 2 + 1 > w
            or
            radius * 2 + 1 > h
        ):
            return None

        x = int(
            np.clip(
                round(marker.x),
                radius,
                w - radius - 1,
            )
        )

        y = int(
            np.clip(
                round(marker.y),
                radius,
                h - radius - 1,
            )
        )

        x1 = x - radius
        y1 = y - radius

        x2 = x + radius + 1
        y2 = y + radius + 1

        patch = frame[
            y1:y2,
            x1:x2,
        ].copy()

        size = radius * 2 + 1

        if patch.shape[:2] != (
            size,
            size,
        ):
            return None

        marker.x = float(x)
        marker.y = float(y)
        marker.radius = radius

        marker.template_color = patch

        marker.template_mask = (
            self.engine._make_circle_mask(
                radius
            )
        )

        marker.velocity_x = 0.0
        marker.velocity_y = 0.0

        self.engine._invalidate_marker_cache(
            marker
        )

        return marker

    # ------------------------------------------------------------------------
    # APPLY / ACCEPT
    # ------------------------------------------------------------------------

    def _apply_and_accept(self):

        self._apply_current_tracker()

        # The selected tracker may have changed while the dialog was open.
        selected = self._current_marker()

        if selected is not None:

            self.engine.selected_marker_id = (
                selected.id
            )

        self.accept()


# ============================================================================
# VIDEO VIEW
# ============================================================================

class TrackingView(QWidget):

    marker_clicked = Signal(int, int)

    def __init__(self):

        super().__init__()

        self.frame = None

        self.markers = []

        self.selected_marker_id = None

        self._resolution_scale = 1.0

        self.setMinimumSize(
            700,
            450,
        )

        self.setMouseTracking(True)

    def set_frame(self, frame):

        self.frame = frame
        self.update()

    def set_markers(
        self,
        markers,
        selected_marker_id,
    ):

        self.markers = list(markers)

        self.selected_marker_id = (
            selected_marker_id
        )

        self.update()

    def set_resolution_scale(
        self,
        scale,
    ):

        self._resolution_scale = float(scale)

        self.update()

    def _image_rect(self):

        if self.frame is None:
            return QRectF()

        h, w = self.frame.shape[:2]

        scale = min(
            self.width() / max(1, w),
            self.height() / max(1, h),
        )

        dw = w * scale
        dh = h * scale

        return QRectF(
            (self.width() - dw) / 2,
            (self.height() - dh) / 2,
            dw,
            dh,
        )

    def _widget_to_image(
        self,
        pos,
    ):

        rect = self._image_rect()

        if (
            self.frame is None
            or
            rect.isNull()
            or
            not rect.contains(pos)
        ):
            return None

        h, w = self.frame.shape[:2]

        x = (
            pos.x()
            -
            rect.left()
        ) * w / rect.width()

        y = (
            pos.y()
            -
            rect.top()
        ) * h / rect.height()

        return (
            int(
                np.clip(
                    x,
                    0,
                    w - 1,
                )
            ),
            int(
                np.clip(
                    y,
                    0,
                    h - 1,
                )
            ),
        )

    def _image_to_widget(
        self,
        x,
        y,
    ):

        rect = self._image_rect()

        if (
            self.frame is None
            or
            rect.isNull()
        ):
            return QPointF()

        h, w = self.frame.shape[:2]

        return QPointF(
            rect.left()
            +
            x * rect.width() / w,

            rect.top()
            +
            y * rect.height() / h,
        )

    def _find_marker_at(
        self,
        x,
        y,
    ):

        if self.frame is None:
            return None

        scale = self._resolution_scale

        if scale <= 0:
            scale = 1.0

        rect = self._image_rect()

        if rect.isNull():
            return None

        display_scale = (
            rect.width()
            /
            self.frame.shape[1]
        )

        best_marker = None
        best_distance = float("inf")

        for marker in self.markers:

            display_x = (
                marker.x
                *
                scale
            )

            display_y = (
                marker.y
                *
                scale
            )

            center = self._image_to_widget(
                display_x,
                display_y,
            )

            radius = (
                marker.radius
                *
                scale
                *
                display_scale
            )

            distance = math.sqrt(
                (
                    center.x()
                    -
                    x
                ) ** 2
                +
                (
                    center.y()
                    -
                    y
                ) ** 2
            )

            hit_radius = max(
                15,
                radius + 8,
            )

            if distance <= hit_radius:

                if distance < best_distance:

                    best_distance = distance
                    best_marker = marker

        return best_marker

    def mousePressEvent(
        self,
        event,
    ):

        if event.button() != Qt.LeftButton:
            return

        point = self._widget_to_image(
            event.position()
        )

        if point is not None:

            self.marker_clicked.emit(
                point[0],
                point[1],
            )

    def paintEvent(
        self,
        event,
    ):

        painter = QPainter(self)

        painter.setRenderHint(
            QPainter.SmoothPixmapTransform
        )

        painter.setRenderHint(
            QPainter.Antialiasing
        )

        painter.fillRect(
            self.rect(),
            QColor("#171526"),
        )

        if self.frame is None:

            painter.setPen(
                QColor("#aaa6c8")
            )

            painter.drawText(
                self.rect(),
                Qt.AlignCenter,
                "SELECT A SCREEN REGION",
            )

            return

        rgb = cv2.cvtColor(
            self.frame,
            cv2.COLOR_BGR2RGB,
        )

        h, w = rgb.shape[:2]

        image = QImage(
            rgb.data,
            w,
            h,
            w * 3,
            QImage.Format_RGB888,
        ).copy()

        pixmap = QPixmap.fromImage(
            image
        )

        rect = self._image_rect()

        painter.drawPixmap(
            rect.toRect(),
            pixmap,
        )

        painter.setPen(
            QPen(
                QColor("#ffffff"),
                1,
            )
        )

        painter.drawRect(
            rect.toRect()
        )

        # ------------------------------------------------------------
        # MARKERS
        # ------------------------------------------------------------

        scale = self._resolution_scale

        if scale <= 0:
            scale = 1.0

        display_scale = (
            rect.width()
            /
            self.frame.shape[1]
        )

        for marker in self.markers:

            display_x = (
                marker.x
                *
                scale
            )

            display_y = (
                marker.y
                *
                scale
            )

            center = self._image_to_widget(
                display_x,
                display_y,
            )

            radius = (
                marker.radius
                *
                scale
                *
                display_scale
            )

            is_selected = (
                marker.id
                ==
                self.selected_marker_id
            )

            if marker.tracking:

                if marker.confidence >= 0.65:

                    circle_color = QColor(
                        "#65ffb3"
                    )

                else:

                    circle_color = QColor(
                        "#ffc857"
                    )

            else:

                circle_color = QColor(
                    "#c58cff"
                )

            if is_selected:

                painter.setPen(
                    QPen(
                        QColor("#ffffff"),
                        3,
                    )
                )

                painter.setBrush(
                    Qt.NoBrush
                )

                painter.drawEllipse(
                    center,
                    radius + 5,
                    radius + 5,
                )

            painter.setBrush(
                Qt.NoBrush
            )

            painter.setPen(
                QPen(
                    circle_color,
                    2,
                )
            )

            painter.drawEllipse(
                center,
                radius,
                radius,
            )

            painter.setPen(
                QPen(
                    QColor("#ffffff"),
                    2,
                )
            )

            painter.drawLine(
                center.x() - 15,
                center.y(),
                center.x() + 15,
                center.y(),
            )

            painter.drawLine(
                center.x(),
                center.y() - 15,
                center.x(),
                center.y() + 15,
            )

            painter.setBrush(
                QBrush(circle_color)
            )

            painter.drawEllipse(
                center,
                5,
                5,
            )

            confidence = float(
                np.clip(
                    marker.confidence,
                    0.0,
                    1.0,
                )
            ) * 100

            painter.setPen(
                QColor("#ffffff")
            )

            painter.drawText(
                QPointF(
                    center.x()
                    +
                    radius
                    +
                    8,

                    center.y()
                    -
                    5,
                ),

                f"#{marker.id}  "
                f"{confidence:.1f}%"
            )


# ============================================================================
# MAIN WINDOW
# ============================================================================

class MainWindow(QMainWindow):

    def __init__(self):

        super().__init__()

        self.engine = TrackingEngine()

        self.device = DeviceController()

        self.thread = None
        self.worker = None

        self.video_running = False

        self.setWindowFlags(
            Qt.FramelessWindowHint
            |
            Qt.Window
        )

        self.setAttribute(
            Qt.WA_TranslucentBackground
        )

        self.setMinimumSize(
            1400,
            900,
        )

        self.resize(
            1900,
            1050,
        )

        self._drag_position = None

        self._build_ui()
        self._apply_style()

    # ------------------------------------------------------------------------
    # BUILD UI
    # ------------------------------------------------------------------------

    def _build_ui(self):

        root = QWidget()

        root.setObjectName(
            "root"
        )

        self.setCentralWidget(
            root
        )

        main = QVBoxLayout(root)

        main.setContentsMargins(
            8,
            8,
            8,
            8,
        )

        main.setSpacing(8)

        # ================================================================
        # TITLE BAR
        # ================================================================

        title_bar = QFrame()

        title_bar.setObjectName(
            "titleBar"
        )

        title_bar.setFixedHeight(
            42
        )

        title_layout = QHBoxLayout(
            title_bar
        )

        title_layout.setContentsMargins(
            14,
            2,
            5,
            2,
        )

        title = QLabel(
            "◈  CHROMA // TRACKER"
        )

        title.setObjectName(
            "title"
        )

        self.status = QLabel(
            "● READY"
        )

        self.status.setObjectName(
            "status"
        )

        minimize = QPushButton("−")
        maximize = QPushButton("□")
        close = QPushButton("×")

        minimize.setObjectName(
            "minimizeButton"
        )

        maximize.setObjectName(
            "maximizeButton"
        )

        close.setObjectName(
            "closeButton"
        )

        minimize.setFixedSize(
            28,
            30,
        )

        maximize.setFixedSize(
            32,
            30,
        )

        close.setFixedSize(
            32,
            30,
        )

        minimize.clicked.connect(
            self.showMinimized
        )

        maximize.clicked.connect(
            self._toggle_maximize
        )

        close.clicked.connect(
            self.close
        )

        title_layout.addWidget(
            title
        )

        title_layout.addStretch()

        title_layout.addWidget(
            self.status
        )

        title_layout.addSpacing(
            8
        )

        title_layout.addWidget(
            minimize
        )

        title_layout.addWidget(
            maximize
        )

        title_layout.addWidget(
            close
        )

        title_bar.mousePressEvent = (
            self._title_mouse_press
        )

        title_bar.mouseMoveEvent = (
            self._title_mouse_move
        )

        main.addWidget(
            title_bar
        )

        # ================================================================
        # BODY
        # ================================================================

        body = QHBoxLayout()

        body.setSpacing(8)

        # ================================================================
        # VIDEO
        # ================================================================

        self.view = TrackingView()

        self.view.marker_clicked.connect(
            self._marker_clicked
        )

        body.addWidget(
            self.view,
            1,
        )

        # ================================================================
        # SIDE PANEL
        # ================================================================

        side = QFrame()

        side.setObjectName(
            "sidePanel"
        )

        side.setFixedWidth(
            330
        )

        side_layout = QVBoxLayout(
            side
        )

        side_layout.setSpacing(
            8
        )

        # ================================================================
        # SOURCE
        # ================================================================

        side_layout.addWidget(
            self._section_label(
                "SOURCE"
            )
        )

        self.region_button = QPushButton(
            "SELECT REGION"
        )

        self.region_button.clicked.connect(
            self._select_region
        )

        side_layout.addWidget(
            self.region_button
        )

        # ================================================================
        # TRACKING
        # ================================================================

        self.start_button = QPushButton(
            "START TRACKING"
        )

        self.start_button.clicked.connect(
            self._toggle_tracking
        )

        side_layout.addWidget(
            self.start_button
        )

        self.place_label = QLabel(
            "Click the video to add a tracker"
        )

        self.place_label.setObjectName(
            "help"
        )

        side_layout.addWidget(
            self.place_label
        )

        # ================================================================
        # TRACKER LIST
        # ================================================================

        side_layout.addWidget(
            self._section_label(
                "TRACKERS"
            )
        )

        self.tracker_list = QListWidget()

        self.tracker_list.setObjectName(
            "trackerList"
        )

        self.tracker_list.setMaximumHeight(
            180
        )

        self.tracker_list.itemClicked.connect(
            self._tracker_list_clicked
        )

        side_layout.addWidget(
            self.tracker_list
        )

        tracker_buttons = QHBoxLayout()

        self.delete_button = QPushButton(
            "DELETE SELECTED"
        )

        self.delete_button.clicked.connect(
            self._delete_selected
        )

        self.clear_button = QPushButton(
            "CLEAR ALL"
        )

        self.clear_button.clicked.connect(
            self._clear_all
        )

        tracker_buttons.addWidget(
            self.delete_button
        )

        tracker_buttons.addWidget(
            self.clear_button
        )

        side_layout.addLayout(
            tracker_buttons
        )

        # ================================================================
        # PERFORMANCE
        # ================================================================

        side_layout.addWidget(
            self._section_label(
                "PERFORMANCE"
            )
        )

        grid = QGridLayout()

        grid.addWidget(
            QLabel("FPS"),
            0,
            0,
        )

        self.fps_spin = QSpinBox()

        self.fps_spin.setRange(
            1,
            240,
        )

        self.fps_spin.setValue(
            self.engine.target_fps
        )

        self.fps_spin.valueChanged.connect(
            self._fps_changed
        )

        grid.addWidget(
            self.fps_spin,
            0,
            1,
        )

        grid.addWidget(
            QLabel("Resolution"),
            1,
            0,
        )

        self.res_spin = QSpinBox()

        self.res_spin.setRange(
            10,
            100,
        )

        self.res_spin.setSingleStep(5)

        self.res_spin.setSuffix("%")

        self.res_spin.setValue(
            self.engine.resolution_percent
        )

        self.res_spin.valueChanged.connect(
            self._resolution_changed
        )

        grid.addWidget(
            self.res_spin,
            1,
            1,
        )

        self.fps_label = QLabel(
            "Capture FPS: --"
        )

        grid.addWidget(
            self.fps_label,
            2,
            0,
            1,
            2,
        )

        side_layout.addLayout(
            grid
        )

        # ================================================================
        # TRACKING QUALITY DEFAULT
        # ================================================================

        side_layout.addWidget(
            self._section_label(
                "DEFAULT TRACKING QUALITY"
            )
        )

        self.quality_combo = QComboBox()

        for quality_name in TRACKING_QUALITIES:

            self.quality_combo.addItem(
                quality_name
            )

        self.quality_combo.setCurrentText(
            self.engine.params.tracking_quality
        )

        self.quality_combo.currentTextChanged.connect(
            self._quality_changed
        )

        side_layout.addWidget(
            self.quality_combo
        )

        self.quality_description = QLabel(
            "Balanced • recommended"
        )

        self.quality_description.setObjectName(
            "help"
        )

        self.quality_description.setWordWrap(
            True
        )

        side_layout.addWidget(
            self.quality_description
        )

        # ================================================================
        # MARKER
        # ================================================================

        side_layout.addWidget(
            self._section_label(
                "SELECTED TRACKER"
            )
        )

        self.selected_label = QLabel(
            "None selected"
        )

        side_layout.addWidget(
            self.selected_label
        )

        self.radius_label = QLabel(
            "Circle radius: 30 px"
        )

        side_layout.addWidget(
            self.radius_label
        )

        self.radius_slider = QSlider(
            Qt.Horizontal
        )

        self.radius_slider.setRange(
            3,
            200,
        )

        self.radius_slider.setValue(
            30
        )

        self.radius_slider.valueChanged.connect(
            self._radius_changed
        )

        side_layout.addWidget(
            self.radius_slider
        )

        self.confidence_label = QLabel(
            "MATCH: --"
        )

        self.confidence_label.setObjectName(
            "confidence"
        )

        side_layout.addWidget(
            self.confidence_label
        )

        # ================================================================
        # ADVANCED
        # ================================================================

        self.advanced_button = QPushButton(
            "ADVANCED PARAMETERS"
        )

        self.advanced_button.clicked.connect(
            self._open_advanced
        )

        side_layout.addWidget(
            self.advanced_button
        )

        # ================================================================
        # DEVICE
        # ================================================================

        side_layout.addWidget(
            self._section_label(
                "DEVICE"
            )
        )

        self.device_status = QLabel(
            "● OFF"
        )

        self.device_status.setObjectName(
            "deviceStatus"
        )

        side_layout.addWidget(
            self.device_status
        )

        self.device_toggle = QPushButton(
            "DEVICE OFF"
        )

        self.device_toggle.setCheckable(
            True
        )

        self.device_toggle.clicked.connect(
            self._device_toggle
        )

        side_layout.addWidget(
            self.device_toggle
        )

        side_layout.addWidget(
            QLabel(
                "Control level"
            )
        )

        self.level_slider = QSlider(
            Qt.Horizontal
        )

        self.level_slider.setRange(
            0,
            100,
        )

        self.level_slider.setValue(
            0
        )

        self.level_slider.valueChanged.connect(
            self._device_level
        )

        side_layout.addWidget(
            self.level_slider
        )

        self.level_label = QLabel(
            "0%"
        )

        side_layout.addWidget(
            self.level_label
        )

        side_layout.addStretch()

        self.help_label = QLabel(
            "Click anywhere on the live video "
            "to create a new circular pixel template.\n\n"
            "Click empty space to create another tracker.\n"
            "Click a tracker to select it."
        )

        self.help_label.setObjectName(
            "help"
        )

        self.help_label.setWordWrap(
            True
        )

        side_layout.addWidget(
            self.help_label
        )

        body.addWidget(
            side
        )

        main.addLayout(
            body,
            1,
        )

    # ------------------------------------------------------------------------
    # SECTION LABEL
    # ------------------------------------------------------------------------

    def _section_label(
        self,
        text,
    ):

        label = QLabel(text)

        label.setObjectName(
            "section"
        )

        return label

    # ------------------------------------------------------------------------
    # STYLE
    # ------------------------------------------------------------------------

    def _apply_style(self):

        self.setStyleSheet(
            """
            QMainWindow {
                background: transparent;
            }

            #root {
                background: #11101b;
                border: 1px solid #403858;
                border-radius: 12px;
            }

            QWidget {
                color: #eee9ff;
                font-family: "Segoe UI";
                font-size: 13px;
            }

            #titleBar {
                background: #201c32;
                border: 1px solid #403858;
                border-radius: 10px;
            }

            #title {
                font-size: 15px;
                font-weight: 700;
            }

            #status {
                color: #7ff0c0;
                font-weight: 700;
            }

            #sidePanel {
                background: #201c32;
                border: 1px solid #403858;
                border-radius: 14px;
                padding: 4px;
            }

            #section {
                color: #c5a7ff;
                font-size: 11px;
                font-weight: 800;
                padding-top: 6px;
            }

            QPushButton {
                background: #302849;
                border: 1px solid #594c78;
                border-radius: 9px;
                padding: 9px;
            }

            QPushButton:hover {
                background: #3b3158;
            }

            QPushButton:checked {
                background: #8c3e76;
                border-color: #e37ac4;
            }

            #minimizeButton,
            #maximizeButton,
            #closeButton {
                background: transparent;
                border: none;
                color: #888298;
                padding: 0px;
                margin: 0px;
                font-family: "Segoe UI";
                font-weight: 400;
            }

            #minimizeButton {
                font-size: 16px;
            }

            #maximizeButton {
                font-size: 14px;
            }

            #closeButton {
                font-size: 17px;
            }

            #minimizeButton:hover,
            #maximizeButton:hover {
                background: #302849;
                color: #eee9ff;
                border-radius: 6px;
            }

            #closeButton:hover {
                background: #c4456b;
                color: #ffffff;
                border-radius: 6px;
            }

            QSlider::groove:horizontal {
                height: 5px;
                background: #39314e;
                border-radius: 2px;
            }

            QSlider::handle:horizontal {
                width: 15px;
                margin: -5px 0;
                border-radius: 7px;
                background: #e6a5ff;
            }

            QSpinBox,
            QDoubleSpinBox,
            QComboBox {
                background: #171526;
                border: 1px solid #4b4263;
                border-radius: 7px;
                padding: 4px;
            }

            QComboBox QAbstractItemView {
                background: #171526;
                border: 1px solid #4b4263;
                selection-background-color: #8c3e76;
            }

            #trackerList {
                background: #171526;
                border: 1px solid #4b4263;
                border-radius: 8px;
                padding: 3px;
            }

            #trackerList::item {
                padding: 6px;
                border-radius: 5px;
            }

            #trackerList::item:selected {
                background: #8c3e76;
            }

            #confidence {
                color: #ffd98a;
                font-weight: 700;
                padding: 6px 0;
            }

            #deviceStatus {
                color: #ffb8d9;
                font-weight: 700;
            }

            #help {
                color: #9690aa;
                padding: 5px;
            }
            """
        )

    # ------------------------------------------------------------------------
    # TITLE BAR
    # ------------------------------------------------------------------------

    def _title_mouse_press(
        self,
        event,
    ):

        if event.button() == Qt.LeftButton:

            self._drag_position = (
                event.globalPosition().toPoint()
                -
                self.frameGeometry().topLeft()
            )

    def _title_mouse_move(
        self,
        event,
    ):

        if (
            event.buttons()
            &
            Qt.LeftButton
            and
            self._drag_position
        ):

            self.move(
                event.globalPosition().toPoint()
                -
                self._drag_position
            )

    def _toggle_maximize(
        self,
    ):

        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    # ------------------------------------------------------------------------
    # REGION
    # ------------------------------------------------------------------------

    def _select_region(
        self,
    ):

        screen = (
            QApplication.primaryScreen()
        )

        geometry = screen.geometry()

        self.engine.set_region(
            {
                "left": geometry.left(),
                "top": geometry.top(),
                "width": geometry.width(),
                "height": geometry.height(),
            }
        )

        self.region_button.setText(
            f"REGION: "
            f"{geometry.width()} × "
            f"{geometry.height()}"
        )

        self.status.setText(
            "● LIVE"
        )

        self._ensure_worker()

    # ------------------------------------------------------------------------
    # WORKER
    # ------------------------------------------------------------------------

    def _ensure_worker(
        self,
    ):

        if (
            self.worker is not None
            and
            self.worker.running
        ):
            return

        self.thread = QThread()

        self.worker = TrackerWorker(
            self.engine
        )

        self.worker.moveToThread(
            self.thread
        )

        self.thread.started.connect(
            self.worker.run
        )

        self.worker.frame_ready.connect(
            self._frame_received
        )

        self.worker.fps_changed.connect(
            self._fps_received
        )

        self.worker.confidence_changed.connect(
            self._confidence_received
        )

        self.worker.error.connect(
            self._worker_error
        )

        self.worker.finished.connect(
            self._worker_finished
        )

        self.thread.start()

        self.video_running = True

    # ------------------------------------------------------------------------
    # TRACKING
    # ------------------------------------------------------------------------

    def _toggle_tracking(
        self,
    ):

        if self.engine.region is None:

            self._select_region()

            return

        self._ensure_worker()

        if self.engine.tracking_enabled:

            self.engine.tracking_enabled = False

            for marker in self.engine.markers:
                marker.tracking = False

            self.start_button.setText(
                "START TRACKING"
            )

            self.status.setText(
                "● LIVE • PAUSED"
            )

        else:

            if not self.engine.markers:

                QMessageBox.information(
                    self,
                    "Place tracker",
                    "Click on the live video "
                    "to create at least one "
                    "tracking marker first.",
                )

                return

            self.engine.tracking_enabled = True

            for marker in self.engine.markers:
                marker.tracking = True

            self.start_button.setText(
                "PAUSE TRACKING"
            )

            self.status.setText(
                "● TRACKING"
            )

    # ------------------------------------------------------------------------
    # FRAME
    # ------------------------------------------------------------------------

    @Slot(object, float)
    def _frame_received(
        self,
        frame,
        scale,
    ):

        self.view.set_frame(
            frame
        )

        self.view.set_resolution_scale(
            scale
        )

        self.view.set_markers(
            self.engine.markers,
            self.engine.selected_marker_id,
        )

        self._update_tracker_list()

    # ------------------------------------------------------------------------
    # FPS
    # ------------------------------------------------------------------------

    @Slot(float)
    def _fps_received(
        self,
        fps,
    ):

        self.fps_label.setText(
            f"Capture FPS: {fps:.1f}"
        )

    # ------------------------------------------------------------------------
    # CONFIDENCE
    # ------------------------------------------------------------------------

    @Slot(object)
    def _confidence_received(
        self,
        data,
    ):

        selected = (
            self.engine.get_selected_marker()
        )

        if selected is None:

            self.confidence_label.setText(
                "MATCH: --"
            )

            return

        confidence = float(
            np.nan_to_num(
                selected.confidence,
                nan=0.0,
                posinf=1.0,
                neginf=0.0,
            )
        )

        self.confidence_label.setText(
            f"MATCH: "
            f"{confidence * 100:.1f}%"
        )

    # ------------------------------------------------------------------------
    # MARKER CLICK
    # ------------------------------------------------------------------------

    def _marker_clicked(
        self,
        x,
        y,
    ):

        if self.view.frame is None:
            return

        if self.engine.last_frame is None:
            return

        # x/y are coordinates in the processed view.
        scale = self.view._resolution_scale

        if scale <= 0:
            scale = 1.0

        native_x = int(
            round(
                x / scale
            )
        )

        native_y = int(
            round(
                y / scale
            )
        )

        # Check existing marker using widget coordinates.
        widget_point = (
            self.view._image_to_widget(
                x,
                y,
            )
        )

        clicked_existing = (
            self.view._find_marker_at(
                widget_point.x(),
                widget_point.y(),
            )
        )

        if clicked_existing is not None:

            self.engine.selected_marker_id = (
                clicked_existing.id
            )

            self._update_tracker_list()

            self._update_selected_controls()

            self.view.set_markers(
                self.engine.markers,
                self.engine.selected_marker_id,
            )

            return

        # New marker inherits current global defaults.
        marker = self.engine.create_marker(
            native_x,
            native_y,
        )

        if marker is None:
            return

        self.place_label.setText(
            f"TRACKER #{marker.id}: "
            f"{native_x}, {native_y}"
        )

        self.help_label.setText(
            "New circular full-color template locked.\n\n"
            "Click empty space to create another tracker.\n"
            "Click a tracker to select it."
        )

        self._update_tracker_list()

        self._update_selected_controls()

        self.view.set_markers(
            self.engine.markers,
            self.engine.selected_marker_id,
        )

    # ------------------------------------------------------------------------
    # TRACKER LIST
    # ------------------------------------------------------------------------

    def _update_tracker_list(
        self,
    ):

        self.tracker_list.blockSignals(
            True
        )

        self.tracker_list.clear()

        for marker in self.engine.markers:

            state = (
                "TRACKING"
                if marker.tracking
                else "PAUSED"
            )

            confidence = float(
                np.nan_to_num(
                    marker.confidence,
                    nan=0.0,
                    posinf=1.0,
                    neginf=0.0,
                )
            ) * 100

            quality = (
                marker.params.tracking_quality
                if marker.params is not None
                else "Balanced"
            )

            text = (
                f"#{marker.id}   "
                f"{confidence:.1f}%   "
                f"R={marker.radius}   "
                f"{quality}   "
                f"{state}"
            )

            item = QListWidgetItem(
                text
            )

            item.setData(
                Qt.UserRole,
                marker.id
            )

            if (
                marker.id
                ==
                self.engine.selected_marker_id
            ):

                item.setSelected(True)

            self.tracker_list.addItem(
                item
            )

        self.tracker_list.blockSignals(
            False
        )

    def _tracker_list_clicked(
        self,
        item,
    ):

        marker_id = item.data(
            Qt.UserRole
        )

        self.engine.selected_marker_id = (
            marker_id
        )

        self._update_selected_controls()

        self.view.set_markers(
            self.engine.markers,
            self.engine.selected_marker_id,
        )

    # ------------------------------------------------------------------------
    # SELECTED CONTROLS
    # ------------------------------------------------------------------------

    def _update_selected_controls(
        self,
    ):

        marker = (
            self.engine.get_selected_marker()
        )

        if marker is None:

            self.selected_label.setText(
                "None selected"
            )

            self.confidence_label.setText(
                "MATCH: --"
            )

            return

        self.selected_label.setText(
            f"Tracker #{marker.id}"
        )

        self.radius_slider.blockSignals(
            True
        )

        self.radius_slider.setValue(
            marker.radius
        )

        self.radius_slider.blockSignals(
            False
        )

        self.radius_label.setText(
            f"Circle radius: "
            f"{marker.radius} px"
        )

        confidence = float(
            np.nan_to_num(
                marker.confidence,
                nan=0.0,
                posinf=1.0,
                neginf=0.0,
            )
        )

        self.confidence_label.setText(
            f"MATCH: "
            f"{confidence * 100:.1f}%"
        )

    # ------------------------------------------------------------------------
    # DELETE SELECTED
    # ------------------------------------------------------------------------

    def _delete_selected(
        self,
    ):

        marker = (
            self.engine.get_selected_marker()
        )

        if marker is None:
            return

        deleted_id = marker.id

        self.engine.delete_marker(
            deleted_id
        )

        self._update_tracker_list()
        self._update_selected_controls()

        self.view.set_markers(
            self.engine.markers,
            self.engine.selected_marker_id,
        )

        if not self.engine.markers:

            self.place_label.setText(
                "Click the video to add a tracker"
            )

    # ------------------------------------------------------------------------
    # CLEAR ALL
    # ------------------------------------------------------------------------

    def _clear_all(
        self,
    ):

        if not self.engine.markers:
            return

        result = QMessageBox.question(
            self,
            "Clear trackers",
            "Delete all tracking markers?",
            QMessageBox.Yes
            |
            QMessageBox.No,
        )

        if result != QMessageBox.Yes:
            return

        self.engine.clear_markers()

        self._update_tracker_list()
        self._update_selected_controls()

        self.view.set_markers(
            self.engine.markers,
            None,
        )

        self.place_label.setText(
            "Click the video to add a tracker"
        )

    # ------------------------------------------------------------------------
    # RADIUS
    # ------------------------------------------------------------------------

    def _radius_changed(
        self,
        value,
    ):

        self.radius_label.setText(
            f"Circle radius: {value} px"
        )

        marker = (
            self.engine.get_selected_marker()
        )

        if marker is None:

            self.engine.params.template_radius = (
                value
            )

            return

        x = int(
            round(
                marker.x
            )
        )

        y = int(
            round(
                marker.y
            )
        )

        frame = self.engine.last_frame

        if frame is None:
            return

        h, w = frame.shape[:2]

        radius = int(value)

        if (
            radius * 2 + 1 > w
            or
            radius * 2 + 1 > h
        ):
            return

        replacement = self._rebuild_marker_at(
            marker,
            x,
            y,
            radius,
        )

        if replacement is None:
            return

        if marker.params is not None:
            marker.params.template_radius = radius

        self._update_tracker_list()

        self.view.set_markers(
            self.engine.markers,
            self.engine.selected_marker_id,
        )

    # ------------------------------------------------------------------------
    # REBUILD MARKER
    # ------------------------------------------------------------------------

    def _rebuild_marker_at(
        self,
        marker,
        x,
        y,
        radius,
    ):

        frame = self.engine.last_frame

        if frame is None:
            return None

        h, w = frame.shape[:2]

        radius = max(
            3,
            int(radius),
        )

        if (
            radius * 2 + 1 > w
            or
            radius * 2 + 1 > h
        ):
            return None

        x = int(
            np.clip(
                x,
                radius,
                w - radius - 1,
            )
        )

        y = int(
            np.clip(
                y,
                radius,
                h - radius - 1,
            )
        )

        size = radius * 2 + 1

        if (
            size > w
            or
            size > h
        ):
            return None

        x1 = x - radius
        y1 = y - radius

        x2 = x + radius + 1
        y2 = y + radius + 1

        patch = frame[
            y1:y2,
            x1:x2,
        ].copy()

        if patch.shape[:2] != (
            size,
            size,
        ):
            return None

        marker.x = float(x)
        marker.y = float(y)
        marker.radius = radius

        marker.template_color = patch

        marker.template_mask = (
            self.engine._make_circle_mask(
                radius
            )
        )

        marker.velocity_x = 0.0
        marker.velocity_y = 0.0

        self.engine._invalidate_marker_cache(
            marker
        )

        return marker

    # ------------------------------------------------------------------------
    # FPS
    # ------------------------------------------------------------------------

    def _fps_changed(
        self,
        value,
    ):

        self.engine.target_fps = int(
            value
        )

    # ------------------------------------------------------------------------
    # RESOLUTION
    # ------------------------------------------------------------------------

    def _resolution_changed(
        self,
        value,
    ):

        self.engine.resolution_percent = int(
            value
        )

    # ------------------------------------------------------------------------
    # QUALITY DEFAULT
    # ------------------------------------------------------------------------

    def _quality_changed(
        self,
        quality_name,
    ):

        if quality_name not in TRACKING_QUALITIES:
            return

        self.engine._apply_quality_to_params(
            self.engine.params,
            quality_name,
        )

        descriptions = {
            "Ultra Fast":
                "Maximum FPS • reduced search and processing resolution",

            "Fast":
                "High FPS • good accuracy",

            "Balanced":
                "Recommended • strong accuracy/performance balance",

            "Precise":
                "Maximum accuracy • largest search and finest refinement",
        }

        self.quality_description.setText(
            descriptions.get(
                quality_name,
                "",
            )
        )

    # ------------------------------------------------------------------------
    # ADVANCED
    # ------------------------------------------------------------------------

    def _open_advanced(
        self,
    ):

        if not self.engine.markers:

            QMessageBox.information(
                self,
                "No tracker selected",
                "Create or select a tracker before "
                "opening Advanced Parameters.",
            )

            return

        dialog = AdvancedParametersDialog(
            self.engine,
            self.engine.selected_marker_id,
            self,
        )

        if dialog.exec() == QDialog.Accepted:

            self._sync_main_controls()

            self._update_tracker_list()

            self._update_selected_controls()

            self.view.set_markers(
                self.engine.markers,
                self.engine.selected_marker_id,
            )

    # ------------------------------------------------------------------------
    # SYNC MAIN CONTROLS
    # ------------------------------------------------------------------------

    def _sync_main_controls(
        self,
    ):

        self.res_spin.blockSignals(
            True
        )

        self.res_spin.setValue(
            self.engine.resolution_percent
        )

        self.res_spin.blockSignals(
            False
        )

        self.fps_spin.blockSignals(
            True
        )

        self.fps_spin.setValue(
            self.engine.target_fps
        )

        self.fps_spin.blockSignals(
            False
        )

        self.quality_combo.blockSignals(
            True
        )

        self.quality_combo.setCurrentText(
            self.engine.params.tracking_quality
        )

        self.quality_combo.blockSignals(
            False
        )

    # ------------------------------------------------------------------------
    # DEVICE
    # ------------------------------------------------------------------------

    def _device_toggle(
        self,
        checked,
    ):

        self.device.set_enabled(
            checked
        )

        if checked:

            self.device_toggle.setText(
                "DEVICE ON"
            )

        else:

            self.device_toggle.setText(
                "DEVICE OFF"
            )

            self.level_slider.setValue(
                0
            )

        self.device_status.setText(
            "● "
            +
            self.device.status()
        )

    def _device_level(
        self,
        value,
    ):

        self.device.set_level(
            value
        )

        self.level_label.setText(
            f"{value}%"
        )

        self.device_status.setText(
            "● "
            +
            self.device.status()
        )

    # ------------------------------------------------------------------------
    # ERRORS
    # ------------------------------------------------------------------------

    def _worker_error(
        self,
        message,
    ):

        QMessageBox.critical(
            self,
            "Tracker error",
            message,
        )

    def _worker_finished(
        self,
    ):

        self.video_running = False

    # ------------------------------------------------------------------------
    # CLOSE
    # ------------------------------------------------------------------------

    def closeEvent(
        self,
        event,
    ):

        self.engine.tracking_enabled = False

        if self.worker:
            self.worker.stop()

        if self.thread:

            self.thread.quit()

            self.thread.wait(
                2000
            )

        self.device.set_enabled(
            False
        )

        try:
            self.engine.sct.close()
        except Exception:
            pass

        super().closeEvent(
            event
        )


# ============================================================================
# MAIN
# ============================================================================

def main():

    app = QApplication(
        sys.argv
    )

    app.setApplicationName(
        "CHROMA // TRACKER"
    )

    window = MainWindow()

    window.show()

    sys.exit(
        app.exec()
    )


if __name__ == "__main__":
    main()
