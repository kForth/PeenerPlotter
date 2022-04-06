import os
from pathlib import Path
import sys
import glob
import json
import serial
import colorsys

from PyQt5 import uic
from PyQt5.QtCore import QSettings, Qt, QRect, QRectF
from PyQt5.QtWidgets import QWidget, QMainWindow, QHeaderView, QTableWidgetItem, QLabel
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QPixmap, QImage

class PeenerCanvas(QWidget):
    FLIP_X = True
    FLIP_Y = True

    PEN_COLOR = "#303030"
    TRAVEL_PEN = "#999999"

    BACK_COLOR = "#EEEEEE"
    CIRCLE_COLOR = "#E1E1E1"
    BORDER_COLOR = "#222222"
    BLANK_BRUSH = "#ffffff00"
    MARGIN = 20  # px

    def __init__(self, settings, *args, **kwargs):
        super(PeenerCanvas, self).__init__(*args, **kwargs)
        self.paths = []
        self.redo_paths = []
        self.last_x, self.last_y = None, None
        self.path_change_listeners = []
        self.settings = settings

        self._canvas_tracking = False
        self._template = None
        self.clear_canvas()

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
        return min(self.width(), self.height()) - 2 * self.MARGIN

    def paintEvent(self, e):
        painter = QPainter(self)
        self.circle_diam = self.getCircleDiam()
        self.mm_per_px = self.settings['tag_diam'] / self.circle_diam
        self.pen_width = self.settings['line_width'] / self.mm_per_px
        
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
            self._set_pen(painter, self.BORDER_COLOR, 3)
        else: 
            self._set_brush(painter, self.CIRCLE_COLOR)
            self._set_pen(painter, self.BORDER_COLOR, 3)
        painter.drawEllipse((self.width() - self.circle_diam) / 2, (self.height() - self.circle_diam) / 2, self.circle_diam, self.circle_diam)

        last_x = None
        last_y = None
        for path in self.paths:
            first_x = path[0][0] * self.circle_diam + self.width() / 2
            first_y = path[0][1] * self.circle_diam + self.height() / 2
            if self.settings['show_travel_lines'] and last_x is not None and last_y is not None:
                self._set_pen(painter, self.TRAVEL_PEN, self.pen_width)
                painter.drawLine(last_x, last_y, first_x, first_y)

            last_x = first_x
            last_y = first_y
            for pt in path[1:]:
                if self.settings['colorful_paths']:
                    path_color = [int(e * 255) for e in colorsys.hsv_to_rgb(len(self.paths)*5/360, 1, 1)]
                    self._set_pen(painter, path_color, self.pen_width)
                else:
                    self._set_pen(painter, self.PEN_COLOR, self.pen_width)
                x = pt[0] * self.circle_diam + self.width() / 2
                y = pt[1] * self.circle_diam + self.height() / 2
                painter.drawLine(last_x, last_y, x, y)
                last_x = x
                last_y = y
        painter.end()

    def set_paths(self, paths):
        self.paths = paths
        self.trigger_path_change_event()

    def get_paths(self):
        return [
            [
                [
                    pt[0] * (-1 if self.FLIP_X else 1),
                    pt[1] * (-1 if self.FLIP_Y else 1)
                ] for pt in path
            ] for path in self.paths
        ]

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

    def undo_path(self):
        if len(self.paths) > 0:
            self.redo_paths.append(self.paths.pop())
            self.update()
            self.trigger_path_change_event()

    def redo_path(self):
        if len(self.redo_paths) > 0:
            self.paths.append(self.redo_paths.pop())
            self.update()
            self.trigger_path_change_event()

    def clear_paths(self):
        self.paths = []
        self.update()
        self.trigger_path_change_event()

    def add_path(self, *paths):
        self.paths += paths
        self.trigger_path_change_event()

    def add_path_pt(self, pt, path_index=-1):
        self.paths[path_index].append(pt)
        self.trigger_path_change_event()

    def trigger_path_change_event(self):
        for listener in self.path_change_listeners:
            listener(self.paths)

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

    def _event_in_circle(self, e):
        dx = abs(self.width() / 2 - e.x())
        dy = abs(self.height() / 2 - e.y())
        return (dx**2 + dy**2)**(1/2) < (self.getCircleDiam() / 2)
    
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