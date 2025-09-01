import numpy as np

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
    windowing_limits = patient_dict_container.get("dict_windowing")[text]

    # Set window and level to the new values
    window = windowing_limits[0]
    level = windowing_limits[1]

    # Use the init argument as passed in (do not overwrite)
    windowing_model_direct(level, window, init)


def windowing_model_direct(level, window, init, fixed_image_array=None):
    """
    Function triggered when a window is selected from the menu,
    or when the windowing slider bars are adjusted
    :param level: The desired level
    :param window: The desired window
    :param init: list of bool to determine which views are chosen
    """
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
        patient_dict_container = PatientDictContainer()
        manual_fusion_data = patient_dict_container.get("manual_fusion")

        if manual_fusion_data is None:
            print("No manual fusion loaded! Skipping fusion update.")
            fusion_axial = fusion_coronal = fusion_sagittal = {}
        else:
            fixed_image, overlay_image, *_ = manual_fusion_data

            # Use the provided fixed_image_array if available
            pixmap_aspect = patient_dict_container.get("pixmap_aspect")
            arr = np.array(fixed_image_array if fixed_image_array is not None else fixed_image)
            print(f"[windowing_model_direct] fusion fixed_image shape: {arr.shape}, type: {type(arr)}")
            if arr.ndim != 3:
                print("[windowing_model_direct] fusion fixed_image is not 3D, skipping get_pixmaps")
                fusion_axial = fusion_coronal = fusion_sagittal = {}
            else:
                fusion_axial, fusion_coronal, fusion_sagittal = get_pixmaps(
                    arr, window, level, pixmap_aspect
                )

        patient_dict_container.set("color_axial", fusion_axial)
        patient_dict_container.set("color_coronal", fusion_coronal)
        patient_dict_container.set("color_sagittal", fusion_sagittal)

        # Reset transform if needed
        moving_dict_container = MovingDictContainer()
        if hasattr(moving_dict_container, "additional_data") and moving_dict_container.additional_data is not None:
            moving_dict_container.set("tfm", None)

        # Refresh views safely
        try:
            if windowing_slider and hasattr(windowing_slider, "fusion_views") and windowing_slider.fusion_views:
                for view in windowing_slider.fusion_views:
                    if hasattr(view, "update_color_overlay"):
                        view.update_color_overlay()
        except Exception as e:
            print(f"[windowing_model_direct] Skipping fusion view update: {e}")

    # Update Slider
    if windowing_slider is not None:
        windowing_slider.set_bars_from_window(window, level)


def set_windowing_slider(slider, fusion_views = None):
    global windowing_slider
    windowing_slider = slider

    if fusion_views is not None:
        windowing_slider.fusion_views = fusion_views
