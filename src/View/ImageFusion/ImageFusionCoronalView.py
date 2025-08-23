from PySide6 import QtWidgets, QtGui
from src.View.mainpage.DicomView import DicomView, GraphicsScene


class ImageFusionCoronalView(DicomView):
    def __init__(self,
                 roi_color=None,
                 iso_color=None,
                 cut_line_color=None):
        self.slice_view = 'coronal'
        super(ImageFusionCoronalView, self).__init__(roi_color,
                                                     iso_color,
                                                     cut_line_color)
        self.update_view()

    def image_display(self, overlay_image=None):
        """
        Update the image to be displayed on the DICOM View.
        If overlay_image is provided, use it as the overlay for this view.
        """
        if overlay_image is not None:
            image = overlay_image
        elif hasattr(self, "overlay_images"):
            slider_id = self.slider.value()
            image = self.overlay_images[slider_id]
        else:
            pixmaps = self.patient_dict_container.get("color_"+self.slice_view)
            if pixmaps is None:
                return  # Prevent NoneType subscriptable error
            slider_id = self.slider.value()
            image = pixmaps[slider_id]

        label = QtWidgets.QGraphicsPixmapItem(image)
        self.scene = GraphicsScene(
            label, self.horizontal_view, self.vertical_view)

    def roi_display(self):
        """
        Display ROI structures on the DICOM Image.
        """
        slider_id = self.slider.value()
        curr_slice = self.patient_dict_container.get("dict_uid")[slider_id]

        selected_rois = self.patient_dict_container.get("selected_rois")
        rois = self.patient_dict_container.get("rois")
        selected_rois_name = []
        for roi in selected_rois:
            selected_rois_name.append(rois[roi]['name'])

        for roi in selected_rois:
            roi_name = rois[roi]['name']
            polygons = self.patient_dict_container.get("dict_polygons_axial")[
                roi_name][curr_slice]
            super().draw_roi_polygons(roi, polygons)

    def update_overlay_offset(self, offset):
        """
        Apply translation to the overlay image.
        offset: tuple (x, y)
        """
        self.overlay_offset = offset
        self.refresh_overlay()

    def refresh_overlay(self):
        """
        Repaint the overlay image with the applied offset.
        """
        if self.overlay_images is not None:
            slider_id = self.slider.value()
            if slider_id >= len(self.overlay_images):
                return

            # Only move the overlay_item if it exists
            if hasattr(self, "overlay_item") and self.overlay_item is not None:
                self.overlay_item.setPos(self.overlay_offset[0], self.overlay_offset[1])
                self.scene.update()
                if hasattr(self, "viewport"):
                    self.viewport().update()
