from __future__ import annotations
import sys, os
from pathlib import Path
import numpy as np
from PySide6 import QtCore, QtWidgets, QtGui
import vtk
from vtkmodules.util import numpy_support
import pydicom

# ------------------------------ DICOM Utilities ------------------------------

def get_first_slice_ipp(folder):
    """Return the ImagePositionPatient of the first slice in the folder."""
    # Get all DICOM files
    files = sorted([os.path.join(folder,f) for f in os.listdir(folder) if f.lower().endswith(".dcm")])
    if not files:
        return np.array([0.0,0.0,0.0])
    ds = pydicom.dcmread(files[0])
    return np.array(ds.ImagePositionPatient, dtype=float)

def compute_dicom_matrix(reader, origin_override=None):
    """Return a 4x4 voxel-to-world matrix for vtkDICOMImageReader."""
    image = reader.GetOutput()

    origin = np.array(image.GetOrigin())
    if origin_override is not None:
        origin = origin_override  # override with true DICOM IPP

    spacing = np.array(image.GetSpacing())

    # Direction cosines (IOP)
    direction_matrix = image.GetDirectionMatrix()
    direction = np.eye(3)
    if direction_matrix:  # VTK >=9
        for i in range(3):
            for j in range(3):
                direction[i, j] = direction_matrix.GetElement(i, j)

    M = np.eye(4)
    for i in range(3):
        M[0:3, i] = direction[0:3, i] * spacing[i]
    M[0:3, 3] = origin
    return M

# ------------------------------ VTK Processing Engine ------------------------------

class VTKEngine:
    ORI_AXIAL = "axial"
    ORI_CORONAL = "coronal"
    ORI_SAGITTAL = "sagittal"

    def __init__(self):
        self.fixed_reader = None
        self.moving_reader = None
        self._blend_dirty = True

        # Transform parameters
        self._tx = self._ty = self._tz = 0.0
        self._rx = self._ry = self._rz = 0.0
        self.transform = vtk.vtkTransform()
        self.transform.PostMultiply()

        # Reslice moving image
        self.reslice3d = vtk.vtkImageReslice()
        self.reslice3d.SetInterpolationModeToLinear()
        self.reslice3d.SetBackgroundLevel(0.0)
        self.reslice3d.SetAutoCropOutput(1)

        # Blend
        self.blend = vtk.vtkImageBlend()
        self.blend.SetOpacity(0, 1.0)
        self.blend.SetOpacity(1, 0.5)

        # Offscreen renderer (unused for display but kept for pipeline completeness)
        self.renderer = vtk.vtkRenderer()
        self.render_window = vtk.vtkRenderWindow()
        self.render_window.SetOffScreenRendering(1)
        self.render_window.AddRenderer(self.renderer)
        self.vtk_image_actor = vtk.vtkImageActor()
        self.renderer.AddActor(self.vtk_image_actor)

        # Pre-registration transform
        self.pre_transform = np.eye(4)
        self.fixed_matrix = np.eye(4)
        self.moving_matrix = np.eye(4)
        
        # User transform (rotation + translation applied by user)
        self.user_transform = vtk.vtkTransform()
        self.user_transform.Identity()

    # ---------------- Fixed Volume ----------------
    def load_fixed(self, dicom_dir: str) -> bool:
        files = list(Path(dicom_dir).glob("*"))
        if not any(f.is_file() for f in files):
            return False
        r = vtk.vtkDICOMImageReader()
        r.SetDirectoryName(str(Path(dicom_dir)))
        r.Update()

        # --- Apply flip to correct orientation ---
        flip = vtk.vtkImageFlip()
        flip.SetInputConnection(r.GetOutputPort())
        flip.SetFilteredAxis(1)
        flip.Update()

        self.fixed_reader = flip

        # --- Compute DICOM matrix for pre-registration ---
        origin = get_first_slice_ipp(dicom_dir)
        self.fixed_matrix = compute_dicom_matrix(r, origin_override=origin)

        # --- Set background level to lowest pixel value in fixed DICOM ---
        img = flip.GetOutput()
        scalars = numpy_support.vtk_to_numpy(img.GetPointData().GetScalars())
        if scalars is not None and scalars.size > 0:
            min_val = float(scalars.min())
            self.reslice3d.SetBackgroundLevel(min_val)

        self._wire_blend()
        self._sync_reslice_output_to_fixed()
        return True


    # ---------------- Moving Volume ----------------
    def load_moving(self, dicom_dir: str) -> bool:
        files = list(Path(dicom_dir).glob("*"))
        if not any(f.is_file() for f in files):
            return False

        # --- Read moving DICOM ---
        r = vtk.vtkDICOMImageReader()
        r.SetDirectoryName(str(Path(dicom_dir)))
        r.Update()

        flip = vtk.vtkImageFlip()
        flip.SetInputConnection(r.GetOutputPort())
        flip.SetFilteredAxis(1)
        flip.Update()
        self.moving_reader = flip

        # --- Compute DICOM matrix for moving volume ---
        moving_origin = get_first_slice_ipp(dicom_dir)
        self.moving_matrix = compute_dicom_matrix(r, origin_override=moving_origin)

        # --- Compute pre-registration transform including rotation ---
        fixed_to_world = self.fixed_matrix
        moving_to_world = self.moving_matrix

        # Compute rotation part (direction cosines only, no spacing)
        R_fixed = fixed_to_world[0:3, 0:3] / np.array([np.linalg.norm(fixed_to_world[0:3, i]) for i in range(3)])
        R_moving = moving_to_world[0:3, 0:3] / np.array([np.linalg.norm(moving_to_world[0:3, i]) for i in range(3)])
        R = R_fixed.T @ R_moving   # relative rotation

        # Compute translation in mm (just difference of IPPs, in world coords)
        t = moving_to_world[0:3, 3] - fixed_to_world[0:3, 3]

        # Build prereg transform
        pre_transform = np.eye(4)
        pre_transform[0:3, 0:3] = R
        pre_transform[0:3, 3] = t
        self.pre_transform = pre_transform

        # Debug prints
        print("--- Fixed matrix ---")
        print(fixed_to_world)
        print("--- Moving matrix ---")
        print(moving_to_world)
        print("--- Pre-registration transform ---")
        print(pre_transform)
        print("Pre-reg translation (mm):", t)


        # --- Apply pre-transform in VTK ---
        vtkmat = vtk.vtkMatrix4x4()
        for i in range(4):
            for j in range(4):
                vtkmat.SetElement(i, j, pre_transform[i, j])

        self.reslice3d.SetInputConnection(flip.GetOutputPort())
        self.reslice3d.SetResliceAxes(vtkmat)
        self._sync_reslice_output_to_fixed()
        self._wire_blend()
        return True



    # ---------------- Transformation Utilities ----------------
    def set_translation(self, tx: float, ty: float, tz: float):
        self._tx, self._ty, self._tz = float(tx), float(ty), float(tz)
        self._apply_transform()

    def set_rotation_deg(self, rx: float, ry: float, rz: float, orientation=None, slice_idx=None):
        self._rx, self._ry, self._rz = float(rx), float(ry), float(rz)
        self._apply_transform(orientation, slice_idx)

    def reset_transform(self):
        self._tx = self._ty = self._tz = 0.0
        self._rx = self._ry = self._rz = 0.0
        self.transform.Identity()
        self._blend_dirty = True
        self._apply_transform()

    def set_opacity(self, alpha: float):
        self.blend.SetOpacity(1, float(np.clip(alpha, 0.0, 1.0)))
        self._blend_dirty = True

    def fixed_extent(self):
        if not self.fixed_reader:
            return None
        return self.fixed_reader.GetOutput().GetExtent()


    # ---------------- Slice Extraction ----------------
    def get_slice_numpy(self, orientation: str, slice_idx: int) -> tuple[np.ndarray | None, np.ndarray | None]:
        if self.fixed_reader is None:
            return None, None
        fixed_img = self.fixed_reader.GetOutput()
        moving_img = self.reslice3d.GetOutput() if self.moving_reader else None
        if self.moving_reader:
            self.reslice3d.Update()

        def vtk_to_np_slice(img, orientation, slice_idx, window_center=40, window_width=400):
            if img is None or img.GetPointData() is None:
                return None
            extent = img.GetExtent()
            nx = extent[1] - extent[0] + 1
            ny = extent[3] - extent[2] + 1
            nz = extent[5] - extent[4] + 1
            scalars = numpy_support.vtk_to_numpy(img.GetPointData().GetScalars())
            if scalars is None:
                return None
            arr = scalars.reshape((nz, ny, nx))

            if orientation == VTKEngine.ORI_AXIAL:
                z = int(np.clip(slice_idx - extent[4], 0, nz - 1))
                arr2d = arr[z, :, :]
            elif orientation == VTKEngine.ORI_CORONAL:
                y = int(np.clip(slice_idx - extent[2], 0, ny - 1))
                arr2d = arr[:, y, :]
            elif orientation == VTKEngine.ORI_SAGITTAL:
                x = int(np.clip(slice_idx - extent[0], 0, nx - 1))
                arr2d = arr[:, :, x]
            else:
                return None

            arr2d = arr2d.astype(np.float32)
            c = window_center
            w = window_width
            arr2d = np.clip((arr2d - (c - 0.5)) / (w - 1) + 0.5, 0, 1)
            arr2d = (arr2d * 255.0).astype(np.uint8)
            return np.ascontiguousarray(arr2d)

        fixed_slice = vtk_to_np_slice(fixed_img, orientation, slice_idx)
        moving_slice = vtk_to_np_slice(moving_img, orientation, slice_idx) if moving_img else None
        return fixed_slice, moving_slice

    def get_slice_qimage(self, orientation: str, slice_idx: int, fixed_color="Purple", moving_color="Green", coloring_enabled=True) -> QtGui.QImage:
        fixed_slice, moving_slice = self.get_slice_numpy(orientation, slice_idx)
        if fixed_slice is None:
            return QtGui.QImage()
        h, w = fixed_slice.shape

        blend = self.blend.GetOpacity(1) if self.moving_reader is not None else 0.0
        color_map = {
            "Grayscale":   lambda arr: arr,
            "Green":       lambda arr: np.stack([np.zeros_like(arr), arr, np.zeros_like(arr)], axis=-1),
            "Purple":      lambda arr: np.stack([arr, np.zeros_like(arr), arr], axis=-1),
            "Blue":        lambda arr: np.stack([np.zeros_like(arr), np.zeros_like(arr), arr], axis=-1),
            "Yellow":      lambda arr: np.stack([arr, arr, np.zeros_like(arr)], axis=-1),
            "Red":         lambda arr: np.stack([arr, np.zeros_like(arr), np.zeros_like(arr)], axis=-1),
            "Cyan":        lambda arr: np.stack([np.zeros_like(arr), arr, arr], axis=-1),
        }

        def aspect_ratio_correct(qimg, h, w, orientation):
            if self.fixed_reader is not None:
                spacing = self.fixed_reader.GetOutput().GetSpacing()
                if orientation == VTKEngine.ORI_AXIAL:
                    spacing_y, spacing_x = spacing[1], spacing[0]
                elif orientation == VTKEngine.ORI_CORONAL:
                    spacing_y, spacing_x = spacing[2], spacing[0]
                elif orientation == VTKEngine.ORI_SAGITTAL:
                    spacing_y, spacing_x = spacing[2], spacing[1]
                else:
                    spacing_y, spacing_x = 1.0, 1.0
                phys_h = h * spacing_y
                phys_w = w * spacing_x
                aspect_ratio = phys_w / phys_h if phys_h != 0 else 1.0
                display_h = h
                display_w = int(round(h * aspect_ratio))
                return qimg.scaled(display_w, display_h, QtCore.Qt.IgnoreAspectRatio, QtCore.Qt.SmoothTransformation)
            return qimg

        def grayscale_qimage(arr2d, h, w, orientation):
            qimg = QtGui.QImage(arr2d.data, w, h, w, QtGui.QImage.Format_Grayscale8)
            qimg = qimg.copy()
            return aspect_ratio_correct(qimg, h, w, orientation)

        if not coloring_enabled:
            if moving_slice is None:
                return grayscale_qimage(fixed_slice, h, w, orientation)
            else:
                alpha = self.blend.GetOpacity(1)
                arr2d = (fixed_slice.astype(np.float32) * (1 - alpha) +
                         moving_slice.astype(np.float32) * alpha).astype(np.uint8)
                return grayscale_qimage(arr2d, h, w, orientation)

        fixed_f = fixed_slice.astype(np.float32)
        if moving_slice is None:
            if fixed_color == "Grayscale":
                return grayscale_qimage(fixed_slice, h, w, orientation)
            else:
                rgb = np.clip(color_map.get(fixed_color, color_map["Purple"])(fixed_slice), 0, 255).astype(np.uint8)
        else:
            moving_f = moving_slice.astype(np.float32)
            if blend <= 0.5:
                fixed_opacity = 1.0
                moving_opacity = blend * 2.0
            else:
                fixed_opacity = 2.0 * (1.0 - blend)
                moving_opacity = 1.0
            if fixed_color == "Grayscale":
                fixed_rgb = np.stack([np.clip(fixed_opacity * fixed_f, 0, 255).astype(np.uint8)]*3, axis=-1)
            else:
                fixed_rgb = color_map.get(fixed_color, color_map["Purple"])(np.clip(fixed_opacity * fixed_f, 0, 255).astype(np.uint8))
            if moving_color == "Grayscale":
                moving_rgb = np.stack([np.clip(moving_opacity * moving_f, 0, 255).astype(np.uint8)]*3, axis=-1)
            else:
                moving_rgb = color_map.get(moving_color, color_map["Green"])(np.clip(moving_opacity * moving_f, 0, 255).astype(np.uint8))
            rgb = np.clip(fixed_rgb + moving_rgb, 0, 255).astype(np.uint8)

        qimg = QtGui.QImage(rgb.data, w, h, 3 * w, QtGui.QImage.Format_RGB888)
        qimg = qimg.copy()
        return aspect_ratio_correct(qimg, h, w, orientation)

    # ---------------- Internal Transform Application ----------------
    def _apply_transform(self, orientation=None, slice_idx=None):
        if not self.fixed_reader or not self.moving_reader:
            return

        img = self.fixed_reader.GetOutput()
        spacing = np.array(img.GetSpacing())
        origin = np.array(img.GetOrigin())
        extent = img.GetExtent()

        center_voxel = np.array([
            0.5 * (extent[0] + extent[1]),
            0.5 * (extent[2] + extent[3]),
            0.5 * (extent[4] + extent[5])
        ])
        center_world = origin + center_voxel * spacing

        # ---------------- User transform only ----------------
        user_t = vtk.vtkTransform()
        user_t.PostMultiply()
        user_t.Translate(-center_world)
        user_t.RotateX(self._rx)
        user_t.RotateY(self._ry)
        user_t.RotateZ(self._rz)
        user_t.Translate(center_world)
        user_t.Translate(self._tx, self._ty, self._tz)

        # Save **just the user transform** for GUI
        self.user_transform.DeepCopy(user_t)

        # ---------------- Combined transform for reslice ----------------
        final_t = vtk.vtkTransform()
        final_t.PostMultiply()
        pre_vtk_mat = vtk.vtkMatrix4x4()
        for i in range(4):
            for j in range(4):
                pre_vtk_mat.SetElement(i, j, self.pre_transform[i, j])

        final_t.Concatenate(pre_vtk_mat)  # pre-registration
        final_t.Concatenate(user_t)       # user transform

        self.transform.DeepCopy(final_t)
        self.reslice3d.SetResliceAxes(self.transform.GetMatrix())
        self.reslice3d.Modified()
        self._blend_dirty = True





    # ---------------- Pipeline Utilities ----------------
    def _wire_blend(self):
        self.blend.RemoveAllInputs()
        if self.fixed_reader is not None:
            self.blend.AddInputConnection(self.fixed_reader.GetOutputPort())
        if self.moving_reader is not None:
            self.blend.AddInputConnection(self.reslice3d.GetOutputPort())
        self._blend_dirty = True

    def _sync_reslice_output_to_fixed(self):
        if self.fixed_reader is None:
            return
        fixed = self.fixed_reader.GetOutput()
        self.reslice3d.SetOutputSpacing(fixed.GetSpacing())
        self.reslice3d.SetOutputOrigin(fixed.GetOrigin())
        self.reslice3d.SetOutputExtent(fixed.GetExtent())
        self.reslice3d.Modified()

    def set_interpolation_linear(self, linear: bool = True):
        if linear:
            self.reslice3d.SetInterpolationModeToLinear()
        else:
            self.reslice3d.SetInterpolationModeToNearestNeighbor()
