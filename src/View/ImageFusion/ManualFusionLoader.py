import os
from PySide6 import QtCore
import SimpleITK as sitk
from src.Model.PatientDictContainer import PatientDictContainer

class ManualFusionLoader(QtCore.QObject):
    signal_loaded = QtCore.Signal(object)
    signal_error = QtCore.Signal(object)

    def __init__(self, selected_files, parent=None):
        super().__init__(parent)
        self.selected_files = selected_files

    def load(self, interrupt_flag=None, progress_callback=None):
        try:
            # Optionally, emit progress if callback is provided
            if progress_callback is not None:
                progress_callback.emit(("Loading fixed image...", 10))
            # Load fixed (base) and moving (overlay) images as SimpleITK
            patient_dict_container = PatientDictContainer()
            # Validate and sort fixed filepaths
            fixed_filepaths = []
            for i in range(len(patient_dict_container.filepaths)):
                try:
                    fp = patient_dict_container.filepaths[i]
                    if os.path.exists(fp):
                        fixed_filepaths.append(fp)
                except KeyError:
                    continue
            fixed_filepaths = sorted(fixed_filepaths)
            # Validate and sort moving filepaths
            moving_filepaths = [fp for fp in self.selected_files if os.path.exists(fp)]
            moving_filepaths = sorted(moving_filepaths)

            fixed_image = sitk.ReadImage(fixed_filepaths)
            if progress_callback is not None:
                progress_callback.emit(("Loading overlay image...", 50))
            moving_image = sitk.ReadImage(moving_filepaths)

            if progress_callback is not None:
                progress_callback.emit(("Finished loading images", 100))

            self.signal_loaded.emit((True, {
                "fixed_image": fixed_image,
                "moving_image": moving_image
            }))
        except Exception as e:
            self.signal_error.emit((False, e))
