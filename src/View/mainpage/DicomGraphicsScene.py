from PySide6 import QtWidgets, QtCore, QtGui


class GraphicsScene(QtWidgets.QGraphicsScene):
    """
    A child class of the QGraphicsScene that contains the pixmaps and the cut lines
    """

    def __init__(self, label: QtWidgets.QGraphicsPixmapItem, horizontal_view, vertical_view):
        super(GraphicsScene, self).__init__()
        self.addItem(label)

        if label is not None and not label.pixmap().isNull():
            pixmap_size = label.pixmap().size()
            self.init_width = pixmap_size.width()
            self.init_height = pixmap_size.height()
            # set scene rect so mouse events cover full pixmap
            self.setSceneRect(0, 0, self.init_width, self.init_height)
        else:
            self.init_width = 0
            self.init_height = 0

        self.horizontal_view = horizontal_view
        self.vertical_view = vertical_view
        self.horizontal_line = None
        self.vertical_line = None
        self.init_cut_lines()

    def init_cut_lines(self):
        if self.horizontal_view is not None and self.vertical_view is not None:
            try:
                horizontal_line_y = self.horizontal_view.slider.value()\
                 / self.horizontal_view.slider.maximum() \
                    * self.height()
                vertical_line_x = self.vertical_view.slider.value(
                ) / self.vertical_view.slider.maximum() * self.width()
            except ZeroDivisionError:
                horizontal_line_y = 0
                vertical_line_x = 0
            self.add_cut_lines(vertical_line_x, horizontal_line_y)

    def add_cut_lines(self, vertical_line_x, horizontal_line_y):
        pen = QtGui.QPen(QtCore.Qt.DashLine)
        pen.setWidthF(2)

        # Set the boundary for the cut lines
        if vertical_line_x < 0:
            vertical_line_x = 0
        elif vertical_line_x > self.init_width:
            vertical_line_x = self.init_width
        if horizontal_line_y < 0:
            horizontal_line_y = 0
        elif horizontal_line_y > self.init_height:
            horizontal_line_y = self.init_height

        pen.setColor(self.horizontal_view.cut_lines_color)
        self.horizontal_line = QtWidgets.QGraphicsLineItem(
            0, horizontal_line_y, self.init_width, horizontal_line_y)
        self.horizontal_line.setPen(pen)
        self.addItem(self.horizontal_line)

        pen.setColor(self.vertical_view.cut_lines_color)
        self.vertical_line = QtWidgets.QGraphicsLineItem(
            vertical_line_x, 0, vertical_line_x, self.init_height)
        self.vertical_line.setPen(pen)
        self.addItem(self.vertical_line)

    def remove_cut_lines(self):
        self.removeItem(self.horizontal_line)
        self.removeItem(self.vertical_line)

    def update_slider(self, vertical_line_x, horizontal_line_y):
        self.horizontal_view.set_slider_value(
            horizontal_line_y / self.height())
        self.vertical_view.set_slider_value(vertical_line_x / self.width())

    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        if self.horizontal_view is not None and self.vertical_view is not None:
            self.remove_cut_lines()
            current_position = event.scenePos()
            self._extracted_from_mouseMoveEvent_5(current_position)


    def mouseMoveEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        if self.horizontal_view is not None and self.vertical_view is not None:
            self.remove_cut_lines()
            current_position = event.scenePos()
            view_pos = event.pos()
            print(f"Scene coordinates: x={current_position.x()}, y={current_position.y()}")
            self._extracted_from_mouseMoveEvent_5(current_position)
            print(f"Scene pos: {current_position}, pixmap size: ({self.init_width}, {self.init_height})")

    # TODO Rename this here and in `mousePressEvent` and `mouseMoveEvent`
    def _extracted_from_mouseMoveEvent_5(self, current_position):
        vertical_line_x = current_position.x()
        horizontal_line_y = current_position.y()
        self.add_cut_lines(vertical_line_x, horizontal_line_y)
        self.update_slider(vertical_line_x, horizontal_line_y)

