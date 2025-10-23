import os
import platform
from pathlib import Path

from PySide6 import QtCore
from pydicom import dcmread

from src.Model import ImageLoading
from src.Model.MovingDictContainer import MovingDictContainer
from src.Model.MovingModel import create_moving_model
from src.Model.ROI import create_initial_rtss_from_ct
from src.Model.GetPatientInfo import DicomTree
from src.Model.DicomUtils import truncate_ds_fields

from src.View.ImageLoader import ImageLoader


class MovingImageLoader(ImageLoader):
    """
    Loader for moving image datasets.
    Provides modular methods to load specific pieces of data for
    both auto-fusion and manual fusion workflows.
    """

    signal_request_calc_dvh = QtCore.Signal()

    def __init__(self, *args, **kwargs):
        super(MovingImageLoader, self).__init__(*args, **kwargs)

    def get_common_path_and_datasets(self):
        # Use commonpath for correct path handling (not commonprefix)
        path = os.path.commonpath(self.selected_files)
        read_data_dict, file_names_dict = ImageLoading.get_datasets(
            self.selected_files
        )
        return path, read_data_dict, file_names_dict

    def init_container(self, path, read_data_dict, file_names_dict):
        moving_dict_container = MovingDictContainer()
        moving_dict_container.clear()
        moving_dict_container.set_initial_values(
            path,
            read_data_dict,
            file_names_dict,
            existing_rtss_files=self.existing_rtss
        )
        return moving_dict_container

    def handle_rtss(self, file_names_dict, read_data_dict, moving_dict_container):
        dataset_rtss = dcmread(file_names_dict['rtss'])

        rois = ImageLoading.get_roi_info(dataset_rtss)
        dict_raw_contour_data, dict_numpoints = ImageLoading.get_raw_contour_data(dataset_rtss)
        dict_thickness = ImageLoading.get_thickness_dict(dataset_rtss, read_data_dict)
        dict_pixluts = ImageLoading.get_pixluts(read_data_dict)

        moving_dict_container.set("rois", rois)
        moving_dict_container.set("raw_contour", dict_raw_contour_data)
        moving_dict_container.set("num_points", dict_numpoints)
        moving_dict_container.set("pixluts", dict_pixluts)

        return dataset_rtss, rois, dict_thickness

    def handle_dvh(self, dataset_rtss, rois, dict_thickness,
                   file_names_dict, moving_dict_container, interrupt_flag):
        dataset_rtdose = dcmread(file_names_dict['rtdose'])

        fork_safe_platforms = ['Linux']
        if platform.system() in fork_safe_platforms:
            raw_dvh = ImageLoading.multi_calc_dvh(dataset_rtss, dataset_rtdose, rois, dict_thickness)
        else:
            raw_dvh = ImageLoading.calc_dvhs(dataset_rtss, dataset_rtdose, rois,
                                             dict_thickness, interrupt_flag)

        dvh_x_y = ImageLoading.converge_to_0_dvh(raw_dvh)

        moving_dict_container.set("raw_dvh", raw_dvh)
        moving_dict_container.set("dvh_x_y", dvh_x_y)
        moving_dict_container.set("dvh_outdated", False)

        return True

    def create_model_and_rtss(self, path):
        ok = self.load_temp_rtss(path)
        if ok:
            create_moving_model()
        return ok

    def load_temp_rtss(self, path):
        moving_dict_container = MovingDictContainer()
        rtss_path = Path(path).joinpath('rtss.dcm')
        uid_list = ImageLoading.get_image_uid_list(moving_dict_container.dataset)
        rtss = create_initial_rtss_from_ct(moving_dict_container.dataset[0], rtss_path, uid_list)

        truncate_ds_fields(rtss)
        rtss.save_as(str(rtss_path), write_like_original=False)
        
        rois = ImageLoading.get_roi_info(rtss)
        moving_dict_container.set("rois", rois)

        dict_pixluts = ImageLoading.get_pixluts(moving_dict_container.dataset)
        moving_dict_container.set("pixluts", dict_pixluts)

        moving_dict_container.filepaths['rtss'] = rtss_path
        moving_dict_container.dataset['rtss'] = rtss

        moving_dict_container.set("file_rtss", rtss_path)
        moving_dict_container.set("dataset_rtss", rtss)
        ordered_dict = DicomTree(None).dataset_to_dict(rtss)
        moving_dict_container.set("dict_dicom_tree_rtss", ordered_dict)
        moving_dict_container.set("selected_rois", [])

        return True

    # Main Loader
    def load(self, interrupt_flag, progress_callback, manual=False):
        # initial callback
        if manual:
            progress_callback(("Generating Moving Model", 20))
        elif hasattr(progress_callback, "emit"):
            progress_callback.emit(("Creating datasets...", 0))

        # load datasets and common path
        try:
            path, read_data_dict, file_names_dict = self.get_common_path_and_datasets()
        except Exception as e:
            import traceback
            print("TRACE: Exception in get_common_path_and_datasets:", e)
            print(traceback.format_exc())
            if hasattr(progress_callback, "emit"):
                progress_callback.emit(("Error loading datasets", 10))
            return False

        try:
            moving_dict_container = self.init_container(path, read_data_dict, file_names_dict)
        except Exception as e:
            import traceback
            print("TRACE: Exception in init_container:", e)
            print(traceback.format_exc())
            if hasattr(progress_callback, "emit"):
                progress_callback.emit(("Error initializing container", 10))
            return False

        if interrupt_flag.is_set():
            print("TRACE: MovingImageLoader.load - interrupted before RTSS/RTDOSE check")
            return False

        # check for RTSS and RTDOSE, ask to calculate DVH if both present
        if 'rtss' in file_names_dict and 'rtdose' in file_names_dict:
            self.parent_window.signal_advise_calc_dvh.connect(self.update_calc_dvh)
            self.signal_request_calc_dvh.emit()
            while not self.advised_calc_dvh:
                pass
            print("TRACE: MovingImageLoader.load - DVH advice received:", self.advised_calc_dvh)


        # handle RTSS (roi + contour data)
            # handle RTSS (roi + contour data)
            if 'rtss' in file_names_dict:
                if manual:
                    progress_callback(("Getting ROI + Contour data...", 25))
                elif hasattr(progress_callback, "emit"):
                    progress_callback.emit(("Getting ROI + Contour data...", 10))

                try:
                    dataset_rtss, rois, dict_thickness = self.handle_rtss(
                        file_names_dict, read_data_dict, moving_dict_container
                    )
                except Exception as e:
                    import traceback
                    print("TRACE: Exception in handle_rtss:", e)
                    print(traceback.format_exc())
                    if hasattr(progress_callback, "emit"):
                        progress_callback.emit(("Error loading RTSS", 10))
                    return False

                if interrupt_flag.is_set():
                    print("TRACE: MovingImageLoader.load - interrupted after handle_rtss")
                    return False

            # handle DVH calculation
            if 'rtdose' in file_names_dict and self.calc_dvh:
                if manual:
                    progress_callback(("Calculating DVHs...", 40))
                elif hasattr(progress_callback, "emit"):
                    progress_callback.emit(("Calculating DVHs...", 60))
                ok = self.handle_dvh(dataset_rtss, rois, dict_thickness,
                                     file_names_dict, moving_dict_container,
                                     interrupt_flag)
                if not ok or interrupt_flag.is_set():
                    return False
            create_moving_model()
        else:
            # no RTSS present, create temporary RTSS
            if manual:
                progress_callback(("Generating temporary rtss...", 40))
            elif hasattr(progress_callback, "emit"):
                progress_callback.emit(("Generating temporary rtss...", 20))

            ok = self.create_model_and_rtss(path)
            print("TRACE: create_model_and_rtss returned:", ok)
            print("TRACE: interrupt_flag.is_set() after create_model_and_rtss:", interrupt_flag.is_set())
            if not ok:
                print("TRACE: MovingImageLoader.load - create_model_and_rtss failed")
                return False
            if interrupt_flag.is_set():
                print("TRACE: MovingImageLoader.load - interrupted after create_model_and_rtss")
                return False

            # Show moving model loading
            if manual:
                progress_callback(("Loading Moving Model", 45))
            elif hasattr(progress_callback, "emit"):
                progress_callback.emit(("Loading Moving Model", 85))

            print("TRACE: Final interrupt_flag.is_set() =", interrupt_flag.is_set())
            try:
                if interrupt_flag.is_set() and manual:
                    progress_callback(("Stopping", 85))
                    print("TRACE: MovingImageLoader.load - interrupted at end (manual)")
                    return False
                elif interrupt_flag.is_set():
                    progress_callback.emit(("Stopping", 85))
                    print("TRACE: MovingImageLoader.load - interrupted at end (auto)")
                    return False

                # --- 90%+: Add stack trace for any exception in final steps ---
                try:
                    # Place any finalization code here that could fail after 90%
                    # For example, if you have any post-processing, overlays, or emits, wrap them:
                    pass  # (if you have code here, wrap it in this try/except)
                except Exception as e:
                    import traceback
                    print("STACK TRACE: Exception after 90% in MovingImageLoader.load:", e)
                    print(traceback.format_exc())
                    if hasattr(progress_callback, "emit"):
                        progress_callback.emit(("Error after 90%", 95))
                    return False

                print("TRACE: MovingImageLoader.load - returning True (success)")
                return True
            except Exception as e:
                import traceback
                print("STACK TRACE: Unhandled exception in MovingImageLoader.load:", e)
                print(traceback.format_exc())
                if hasattr(progress_callback, "emit"):
                    progress_callback.emit(("Error after 90%", 95))
                return False

    # manual fusion loader
    def load_manual_mode(self, interrupt_flag, progress_callback):
        # We will just use the same loading functions as above but with different progress updates
        return self.load(interrupt_flag, progress_callback, manual=True)
