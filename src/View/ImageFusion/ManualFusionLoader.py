from PySide6 import QtCore
import logging
import os

from vtkmodules.util import numpy_support

from src.Model.PatientDictContainer import PatientDictContainer
from src.Model.VTKEngine import VTKEngine

class ManualFusionLoader(QtCore.QObject):
    signal_loaded = QtCore.Signal(object)
    signal_error = QtCore.Signal(object)

    def __init__(self, selected_files, parent=None):
        super().__init__(parent)
        self.selected_files = selected_files

    def load(self, interrupt_flag=None, progress_callback=None):
        try:
            self._load_with_vtk(progress_callback)
        except Exception as e:
            if progress_callback is not None:
                progress_callback.emit(("Error loading images", e))
            self.signal_error.emit((False, e))

    def _load_with_vtk(self, progress_callback):
        # Progress: loading fixed image
        if progress_callback is not None:
            progress_callback.emit(("Loading fixed image (VTK)...", 10))

        # Gather fixed filepaths (directory)
        patient_dict_container = PatientDictContainer()
        fixed_dir = patient_dict_container.path
        moving_dir = None
        if self.selected_files:
            # Validate all selected files are from the same directory
            dirs = {os.path.dirname(f) for f in self.selected_files}
            if len(dirs) > 1:
                # Emit error message if invalid
                error_msg = (
                    f"Selected files span multiple directories: {dirs}. "
                    "Manual fusion requires all files to be from the same directory."
                )
                if progress_callback is not None:
                    progress_callback.emit(("Error loading images", error_msg))
                self.signal_error.emit((False, error_msg))
                return
            moving_dir = dirs.pop()

        # Use VTKEngine to load images
        engine = VTKEngine()
        fixed_loaded = engine.load_fixed(fixed_dir)
        if not fixed_loaded:
            raise RuntimeError("Failed to load fixed image with VTK.")

        if progress_callback is not None:
            progress_callback.emit(("Loading overlay image (VTK)...", 50))

        moving_loaded = engine.load_moving(moving_dir)
        if not moving_loaded:
            raise RuntimeError("Failed to load moving image with VTK.")

        if progress_callback is not None:
            progress_callback.emit(("Finalising", 90))

        # Only emit the VTKEngine for downstream use; overlays will be generated on-the-fly
        self.signal_loaded.emit((True, {
            "vtk_engine": engine,
        }))

    def on_manual_fusion_loaded(self, result):
        success, data = result
        if not success:
            print("Manual fusion load failed:", data)
            return

        engine = data["vtk_engine"]

        if hasattr(engine, "get_fixed_image"):
            fixed_image = engine.get_fixed_image()
        elif hasattr(engine, "fixed_reader") and hasattr(engine.fixed_reader, "GetOutput"):
            fixed_image = engine.fixed_reader.GetOutput()
        else:
            fixed_image = None

        if hasattr(engine, "get_moving_image"):
            moving_image = engine.get_moving_image()
        elif hasattr(engine, "moving_reader") and hasattr(engine.moving_reader, "GetOutput"):
            moving_image = engine.moving_reader.GetOutput()
        else:
            moving_image = None

            # Save manual fusion in PatientDictContainer
        patient_dict_container = PatientDictContainer()
        # You can store a tuple (fixed, moving, optional tfm)
        patient_dict_container.set("manual_fusion", (fixed_image, moving_image, None))

        if hasattr(fixed_image, "GetPointData"):  # VTK image
            dims = fixed_image.GetDimensions()
            scalars = fixed_image.GetPointData().GetScalars()
            np_img = numpy_support.vtk_to_numpy(scalars).reshape(dims[::-1])
            fixed_image_array = np_img
        elif hasattr(fixed_image, "GetArrayFromImage"):  # SimpleITK image
            fixed_image_array = fixed_image  # assume already numpy

            # Trigger a refresh of fusion views (forces fusion update)
            from src.Model.Windowing import windowing_model_direct
            window = patient_dict_container.get("window") or 1600
            level = patient_dict_container.get("level") or 0
            # Pass the fixed_image_array to windowing_model_direct for correct pixmap generation
            windowing_model_direct(level=level, window=window, init=[False, False, False, True], fixed_image_array=fixed_image_array)
