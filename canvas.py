import os
import json

from PyQt5.QtCore import Qt, QRect, QRectF, pyqtSignal, QObject
from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QImage
import numpy as np

from scipy import interpolate
# from statsmodels.nonparametric.kernel_regression import KernelReg

from _optimize_path_order import optimize_path_order
from _min_enclosing_circle import make_circle
from util import *

class PeenerCanvas(QWidget):
    # path_change_event = pyqtSignal(object)

    FLIP_X = True
    FLIP_Y = True

    PEN_COLOR = "#303030"
    TRAVEL_PEN = "#999999"

    BACK_COLOR = "#EEEEEE"
    CIRCLE_COLOR = "#E1E1E1"
    BORDER_COLOR = "#222222"
    TRACKER_COLOR = "#2222FF"
    BLANK_BRUSH = "#ffffff00"
    MARGIN = 20  # px

    def __init__(self, settings, *args, **kwargs):
        super(PeenerCanvas, self).__init__(*args, **kwargs)
        self.paths = []
        self.redo_paths = []
        self.last_x, self.last_y = None, None
        self.settings = settings

        self._canvas_tracking = False
        self._template = None
        self._machine_pos = None
        self.clear_canvas()

    def update_settings(self, settings):
        self.settings = settings
        self.update()

    def update_machine_pos(self, pos):
        self._machine_pos = pos
        self.update()

    def load_template(self, filename):
        if filename and os.path.isfile(filename):
            self._template = filename
            self.update()

    def clear_template(self):
        self._template = None
        self.update()

    def save_to_file(self, filename):
        json.dump(self.paths, open(filename, "w+"))
        pixmap = self.grab(QRect((self.width() - self.circle_diam) / 2, (self.height() - self.circle_diam) / 2, self.circle_diam, self.circle_diam))
        pixmap.save(filename.replace(".json", ".png"))
        
    def load_from_file(self, filename):
        if os.path.isfile(filename):
            self.set_paths(json.load(open(filename)))
            self.update()

    def getCircleDiam(self):
        return max(min(self.width(), self.height()) - 2 * self.MARGIN, 1)

    def paintEvent(self, e):
        painter = QPainter(self)
        self.circle_diam = self.getCircleDiam()
        self.mm_per_px = self.settings['tag_diam'] / self.circle_diam
        self.pen_width = max(self.settings['line_width'] / self.mm_per_px, 1)
        
        self._set_brush(painter, self.BACK_COLOR)
        self._set_pen(painter, self.BACK_COLOR, 3)
        painter.fillRect(0, 0, self.width(), self.height(), QColor(self.BACK_COLOR))

        if self._template:
            img = QImage(self._template)
            wi, hi = img.width(), img.height()
            cd = self.circle_diam
            size = (cd, hi * cd/wi) if wi / hi > 1 else (wi * cd / hi, cd)
            painter.drawImage(QRectF((self.width() - size[0]) / 2, (self.height() - size[1]) / 2, *size), img)
            self._set_brush(painter, self.CIRCLE_COLOR, Qt.NoBrush)
        else: 
            self._set_brush(painter, self.CIRCLE_COLOR)
        outline_size = 2
        self._set_pen(painter, self.BORDER_COLOR, outline_size)
        painter.drawEllipse(
            (self.width() - self.circle_diam) / 2 - outline_size,
            (self.height() - self.circle_diam) / 2 - outline_size,
            self.circle_diam + 2 * outline_size,
            self.circle_diam + 2 * outline_size
        )

        last_x = None
        last_y = None

        if self.settings['draw_border']:
            self._set_pen(painter, self.PEN_COLOR, self.pen_width)
            margin = self.settings['border_margin'] / self.mm_per_px
            painter.drawEllipse(
                (self.width() - self.circle_diam) / 2 + margin,
                (self.height() - self.circle_diam) / 2 + margin,
                self.circle_diam - 2 * margin - self.pen_width,
                self.circle_diam - 2 * margin - self.pen_width
            )
            last_x = self.width() / 2
            last_y = self.height() / 2 - (self.settings['tag_diam'] / 2 - self.settings['border_margin']) / self.mm_per_px

        path_colours = gen_colours(len(self.paths)) if self.settings['colorful_paths'] else None
        for i, path in enumerate(self.paths):
            first_x = path[0][0] * self.circle_diam + self.width() / 2
            first_y = path[0][1] * self.circle_diam + self.height() / 2

            if self.settings['show_travel_lines'] and last_x is not None and last_y is not None:
                self._set_pen(painter, self.TRAVEL_PEN, self.pen_width)
                painter.drawLine(last_x, last_y, first_x, first_y)

            last_x = first_x
            last_y = first_y
            for pt in path[1:]:
                path_color = self.PEN_COLOR if not self.settings['colorful_paths'] else [int(e * 255) for e in path_colours[i]]
                self._set_pen(painter, path_color, self.pen_width)
                x = pt[0] * self.circle_diam + self.width() / 2
                y = pt[1] * self.circle_diam + self.height() / 2
                painter.drawLine(last_x, last_y, x, y)
                last_x = x
                last_y = y

        if self.settings['show_machine_pos'] and self._machine_pos:
            self._set_brush(painter, self.TRACKER_COLOR)
            self._set_pen(painter, self.TRACKER_COLOR, 1)
            painter.drawEllipse(
                (self.width() - self.circle_diam) / 2 + self._machine_pos[0],
                (self.height() - self.circle_diam) / 2 + self._machine_pos[1],
                self.pen_width * 2,
                self.pen_width * 2
            )
        
        painter.end()

    def set_paths(self, paths):
        self.paths = paths
        # self.path_change_event.emit(self.paths)

    def get_paths(self):
        return [[
            [
                pt[0] * (-1 if self.FLIP_X else 1),
                pt[1] * (-1 if self.FLIP_Y else 1)
            ] for pt in path
        ] for path in self.paths]

    def get_rel_paths(self):
        rel_paths = []
        last_pt = None
        for path in self.get_paths():
            rel_path = []
            for pt in path:
                if last_pt is None:
                    last_pt = pt
                rel_path.append([
                    pt[0] - last_pt[0],
                    pt[1] - last_pt[1]
                ])
            rel_paths.append(rel_path)
        return rel_paths

    def get_path(self, path_index):
        return self.paths[path_index]
    
    def get_last_path(self):
        return self.paths[-1]

    def get_border_path(self):
        return path

    def undo_path(self):
        if len(self.paths) > 0:
            self.redo_paths.append(self.paths.pop())
            self.update()
            # self.path_change_event.emit(self.paths)

    def redo_path(self):
        if len(self.redo_paths) > 0:
            self.paths.append(self.redo_paths.pop())
            self.update()
            # self.path_change_event.emit(self.paths)

    def clear_paths(self):
        self.redo_paths = self.paths
        self.paths = []
        self.update()
        # self.path_change_event.emit(self.paths)

    def add_path(self, *paths):
        self.paths += paths
        # self.path_change_event.emit(self.paths)

    def add_path_pt(self, pt, path_index=-1):
        self.paths[path_index].append(pt)
        # self.path_change_event.emit(self.paths)

    def optimize_path_order(self, iters=1e5):
        print("Optimizing Canvas Path Order")
        self.paths = optimize_path_order(self.paths, iters)
        self.update()
        # self.path_change_event.emit(self.paths)

    def auto_size_paths(self):
        print("Auto Sizing Paths")
        (circle_x, circle_y, circle_r) = make_circle(sum(self.paths, start=[]))
        t_paths = []
        for path in self.paths:
            t_path = []
            for pt in path:
                t_path.append([
                    (pt[0] - circle_x) * (0.49 / circle_r),
                    (pt[1] - circle_y) * (0.49 / circle_r)
                ])
            t_paths.append(t_path)
        self.paths = t_paths
        self.update()
        print("Done")

    def smooth_paths(self):
        print("Smoothing Paths")
        s_paths = []
        for path in self.paths:
            lp = path[0]
            s_path = path[:1]
            for i, pt in enumerate(path[1:-1]):
                dx = abs(pt[0] - lp[0])
                dy = abs(pt[1] - lp[1])
                dist = (dx**2 + dy**2)**(1/2)
                if dist > 0.01:
                    s_path.append(pt)
                    lp = pt
            s_path += path[-1:]
            s_paths.append(s_path)
        self.paths = s_paths
        self.update()
        print("Done")

    def clear_canvas(self):
        self.clear_paths()
        self.redo_paths = []
        self.last_x, self.last_y = None, None

    def _set_pen(self, painter, color, width):
        pen = QPen()
        pen.setWidth(int(width))
        pen.setColor(QColor(color) if type(color) is str else QColor(*color))
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)

    def _set_brush(self, painter, color, style=Qt.SolidPattern):
        brush = QBrush()
        brush.setColor(QColor(color) if type(color) is str else color)
        brush.setStyle(style)
        painter.setBrush(brush)

    def _pt_dist(self, pt):
        dx = abs(self.width() / 2 - pt.x())
        dy = abs(self.height() / 2 - pt.y())
        return (dx**2 + dy**2)**(1/2)

    def _event_in_circle(self, pt):
        return self._pt_dist(pt) < (self.getCircleDiam() / 2)
    
    def mousePressEvent(self, e):
        if self._event_in_circle(e):
            self._canvas_tracking = True
            self.redo_paths = []

    def mouseMoveEvent(self, e):
        if self._canvas_tracking:
            pt = (
                (e.x() -  self.width() / 2) / self.circle_diam,
                (e.y() -  self.height() / 2) / self.circle_diam
            )
            if self.last_x == e.x() and self.last_y == e.y():
                return
            elif self.last_x is None or self.last_y is None:  # If path not started
                if self._event_in_circle(e):
                    self.last_x = e.x()
                    self.last_y = e.y()
                    self.add_path([pt])
            else:
                if self._event_in_circle(e):
                    self.add_path_pt(pt)
                    self.last_x = e.x()
                    self.last_y = e.y()
                elif len(self.get_last_path()) > 0:  # If point not in crcle, end path
                    self.last_x = None
                    self.lasy_y = None
            self.update()

    def mouseReleaseEvent(self, e):
        self.last_x = None
        self.last_y = None
        self._canvas_tracking = False
