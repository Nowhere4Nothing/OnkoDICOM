import numpy as np
from PySide6 import QtGui

from src.Model.PatientDictContainer import PatientDictContainer
from src.Model.PTCTDictContainer import PTCTDictContainer
from src.Model.MovingDictContainer import MovingDictContainer
from src.Model.CalculateImages import get_pixmaps
from src.Model.ImageFusion import get_fused_window


windowing_slider = None


def windowing_model(text, init):
    """
    Function triggered when a window is selected from the menu.
    :param text: The name of the window selected.
    :param init: list of bool to determine which views are chosen
    """
    patient_dict_container = PatientDictContainer()

    # Get the values for window and level from the dict
    if text == "Auto":
        arr = np.array(patient_dict_container.get("pixel_values"))
        window = int(arr.max() - arr.min())
        level = int((arr.max() + arr.min()) / 2)
    else:
        windowing_limits = patient_dict_container.get("dict_windowing")[text]
        # If your data is 0–255, override the presets:
        arr = np.array(patient_dict_container.get("pixel_values"))
        if arr.min() >= 0 and arr.max() <= 255:
            window = int(arr.max() - arr.min())
            level = int((arr.max() + arr.min()) / 2)
        else:
            window = windowing_limits[0]
            level = windowing_limits[1]

    # Use the init argument as passed in (do not overwrite)
    windowing_model_direct(window, level, init)


def windowing_model_direct(window, level, init, fixed_image_array=None):
    """
    Function triggered when a window is selected from the menu,
    or when the windowing slider bars are adjusted
    :param level: The desired level
    :param window: The desired window
    :param init: list of bool to determine which views are chosen
    """
    print(f"[windowing_model_direct] Called with window={window}, level={level}, init={init}")
    if fixed_image_array is not None:
        arr = np.array(fixed_image_array)
        print(
            f"[windowing_model_direct] manual fusion fixed_image_array min={arr.min()}, max={arr.max()}, shape={arr.shape}")
    else:
        patient_dict_container = PatientDictContainer()
        arr = np.array(patient_dict_container.get("pixel_values"))
        print(f"[windowing_model_direct] DICOM pixel_values min={arr.min()}, max={arr.max()}, shape={arr.shape}")

    patient_dict_container = PatientDictContainer()
    moving_dict_container = MovingDictContainer()
    pt_ct_dict_container = PTCTDictContainer()

    # Update the dictionary of pixmaps with the update window and
    # level values
    if init[0]:
        pixel_values = patient_dict_container.get("pixel_values")
        pixmap_aspect = patient_dict_container.get("pixmap_aspect")
        if pixel_values is None or not hasattr(pixel_values, "__len__") or len(pixel_values) == 0:
            print("[windowing_model_direct] pixel_values is empty or invalid, skipping get_pixmaps")
            pixmaps_axial = pixmaps_coronal = pixmaps_sagittal = {}
        else:
            # Print shape/type for debugging
            try:
                arr = np.array(pixel_values)
                print(f"[windowing_model_direct] pixel_values shape: {arr.shape}, type: {type(pixel_values)}")
                if arr.ndim != 3:
                    print("[windowing_model_direct] pixel_values is not 3D, skipping get_pixmaps")
                    pixmaps_axial = pixmaps_coronal = pixmaps_sagittal = {}
                else:
                    pixmaps_axial, pixmaps_coronal, pixmaps_sagittal = \
                        get_pixmaps(pixel_values, window, level, pixmap_aspect)
            except Exception as e:
                print(f"[windowing_model_direct] Exception converting pixel_values to array: {e}")
                pixmaps_axial = pixmaps_coronal = pixmaps_sagittal = {}

        patient_dict_container.set("pixmaps_axial", pixmaps_axial)
        patient_dict_container.set("pixmaps_coronal", pixmaps_coronal)
        patient_dict_container.set("pixmaps_sagittal", pixmaps_sagittal)

        # Store DICOM view window/level
        patient_dict_container.set("window", window)
        patient_dict_container.set("level", level)

    # Update CT
    if init[2]:
        ct_pixel_values = pt_ct_dict_container.get("ct_pixel_values")
        ct_pixmap_aspect = pt_ct_dict_container.get("ct_pixmap_aspect")
        ct_pixmaps_axial, ct_pixmaps_coronal, ct_pixmaps_sagittal = \
            get_pixmaps(ct_pixel_values, window, level, ct_pixmap_aspect,
                        fusion=True)

        pt_ct_dict_container.set("ct_pixmaps_axial", ct_pixmaps_axial)
        pt_ct_dict_container.set("ct_pixmaps_coronal", ct_pixmaps_coronal)
        pt_ct_dict_container.set("ct_pixmaps_sagittal", ct_pixmaps_sagittal)
        pt_ct_dict_container.set("ct_window", window)
        pt_ct_dict_container.set("ct_level", level)

    # Update PT
    if init[1]:
        pt_pixel_values = pt_ct_dict_container.get("pt_pixel_values")
        pt_pixmap_aspect = pt_ct_dict_container.get("pt_pixmap_aspect")
        pt_pixmaps_axial, pt_pixmaps_coronal, pt_pixmaps_sagittal = \
            get_pixmaps(pt_pixel_values, window, level, pt_pixmap_aspect,
                        fusion=True, color="Heat")

        pt_ct_dict_container.set("pt_pixmaps_axial", pt_pixmaps_axial)
        pt_ct_dict_container.set("pt_pixmaps_coronal", pt_pixmaps_coronal)
        pt_ct_dict_container.set("pt_pixmaps_sagittal", pt_pixmaps_sagittal)
        pt_ct_dict_container.set("pt_window", window)
        pt_ct_dict_container.set("pt_level", level)

    if init[3]:
        # For manual fusion (VTK), generate overlays for all slices using the VTK engine.
        # This allows all slices to be updated and displayed quickly.
        moving_dict_container = MovingDictContainer()
        if hasattr(moving_dict_container, "additional_data") and moving_dict_container.additional_data is not None:
            moving_dict_container.set("tfm", None)

        # Store fusion window/level
        patient_dict_container.set("fusion_window", window)
        patient_dict_container.set("fusion_level", level)

        # Generate overlays for all slices in each orientation
        # Generate overlays for all slices in each orientation
        if windowing_slider and hasattr(windowing_slider, "fusion_views") and windowing_slider.fusion_views:
            # Use the callback if available
            if hasattr(windowing_slider, "fusion_window_level_callback"):
                windowing_slider.fusion_window_level_callback(window, level)
            else:
                for view in windowing_slider.fusion_views:
                    if hasattr(view, "vtk_engine") and view.vtk_engine is not None:
                        orientation = view.slice_view
                        vtk_engine = view.vtk_engine
                        # Get the slice range for this orientation
                        extent = vtk_engine.fixed_extent()
                        if not extent:
                            continue
                        if orientation == "axial":
                            min_idx, max_idx = extent[4], extent[5]
                        elif orientation == "coronal":
                            min_idx, max_idx = extent[2], extent[3]
                        elif orientation == "sagittal":
                            min_idx, max_idx = extent[0], extent[1]
                        else:
                            continue
                        overlays = []
                        for idx in range(min_idx, max_idx + 1):
                            qimg = vtk_engine.get_slice_qimage(
                                orientation, idx,
                                fixed_color=view.fixed_color,
                                moving_color=view.moving_color,
                                coloring_enabled=view.coloring_enabled
                            )
                            overlays.append(QtGui.QPixmap.fromImage(qimg))
                        # Store overlays in PatientDictContainer for this orientation
                        patient_dict_container.set(f"color_{orientation}", overlays)
                        # Also update the view's overlay_images
                        view.overlay_images = overlays
                        # print(f"[windowing_model_direct] Generated {len(overlays)} overlays for {orientation}")
                    # Refresh the view
                    if hasattr(view, "update_color_overlay"):
                        view.update_color_overlay()
        else:
            print("[windowing_model_direct] No fusion_views found for manual fusion overlays.")

    # Update Slider
    if windowing_slider is not None:
        windowing_slider.set_bars_from_window(window, level)


def set_windowing_slider(slider, fusion_views = None):
    global windowing_slider
    windowing_slider = slider

    if fusion_views is not None:
        windowing_slider.fusion_views = fusion_views
