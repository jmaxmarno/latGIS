"""End-to-end "planted target" validation of the ItemLocation pipeline.

Plants a target at a known geodetic point ``T_LLE``, places two cameras at
known geodetic offsets, computes the heading/pitch each camera needs to
bore-sight the target, then runs the full
``calcAngleOffsets -> sensor_2_ENU -> ENU_2_ECEF -> triagulation
-> getObjectLLE -> computeResults`` pipeline and asserts that the recovered
location matches ``T_LLE`` within a tight tolerance.

This is the headline correctness check for the backend: the existing smoke
test only proves the pipeline runs; this test proves it produces the right
answer.
"""

import unittest

import numpy as np

from latgis.constants import Constants
from latgis.geo.enu_to_ecef import MoreTransfers
from latgis.location import CameraData, ItemLocation


def _aim_camera_at_target(camera_LLE, target_LLE):
    """Return ``(heading_deg, pitch_deg)`` so the camera bore-sights the target.

    Uses ECEF geometry consistent with ``MoreTransfers`` (which is the same
    WGS84 transform the pipeline itself uses internally), then projects the
    camera->target vector into the local ENU frame and reads off heading and
    pitch using the convention defined in ``location.sensor_2_ENU``:
    heading is compass-clockwise from North (0=N, 90=E) and positive pitch
    is up.
    """
    cam_ecef = np.asarray(MoreTransfers.geodetic2ecef(
        camera_LLE[0], camera_LLE[1], camera_LLE[2], deg=True))
    tgt_ecef = np.asarray(MoreTransfers.geodetic2ecef(
        target_LLE[0], target_LLE[1], target_LLE[2], deg=True))
    delta = tgt_ecef - cam_ecef

    lat0 = camera_LLE[0] * np.pi / 180.0
    lon0 = camera_LLE[1] * np.pi / 180.0

    # standard ECEF -> ENU rotation matrix at (lat0, lon0)
    R = np.array([
        [-np.sin(lon0),                np.cos(lon0),                0.0          ],
        [-np.sin(lat0)*np.cos(lon0),  -np.sin(lat0)*np.sin(lon0),   np.cos(lat0)],
        [ np.cos(lat0)*np.cos(lon0),   np.cos(lat0)*np.sin(lon0),   np.sin(lat0)],
    ])
    east, north, up = R @ delta

    heading_rad = np.arctan2(east, north)               # 0=N, +pi/2=E
    pitch_rad = np.arctan2(up, np.hypot(east, north))   # +up
    return float(np.degrees(heading_rad)), float(np.degrees(pitch_rad))


def _haversine_meters(lle1, lle2):
    """Great-circle horizontal distance in meters (WGS84 sphere approx)."""
    R = 6371000.0
    lat1, lon1 = np.radians(lle1[0]), np.radians(lle1[1])
    lat2, lon2 = np.radians(lle2[0]), np.radians(lle2[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2)**2 + np.cos(lat1)*np.cos(lat2)*np.sin(dlon/2)**2
    return float(2 * R * np.arcsin(np.sqrt(a)))


class PlantedTargetEndToEndTests(unittest.TestCase):
    """Validate the full ItemLocation pipeline against ground truth."""

    # Reset the class-level ID counter between tests for hermetic ordering.
    def setUp(self):
        ItemLocation.objID = 0

    # Loose enough to absorb the documented integer rounding in
    # geo.rotation.Rotate (which the pipeline does NOT use here, but the
    # WGS84 vs ellipsoid-of-revolution differences between the two transform
    # implementations contribute a few cm), tight enough to fail if the
    # pipeline mis-computes the answer.
    HORIZONTAL_TOL_M = 1.0
    VERTICAL_TOL_M = 5.0

    def _run_pipeline(self, target_LLE, cam0_LLE, cam1_LLE,
                      pixel0=None, pixel1=None):
        """Aim two cameras at ``target_LLE`` and run the full pipeline."""
        center = [Constants.SENSOR_SIZE[0] / 2.0,
                  Constants.SENSOR_SIZE[1] / 2.0]
        if pixel0 is None:
            pixel0 = center
        if pixel1 is None:
            pixel1 = center

        h0, p0 = _aim_camera_at_target(cam0_LLE, target_LLE)
        h1, p1 = _aim_camera_at_target(cam1_LLE, target_LLE)

        cam0 = CameraData(LatLonEl=cam0_LLE, heading=h0, pitch=p0)
        cam1 = CameraData(LatLonEl=cam1_LLE, heading=h1, pitch=p1)

        item = ItemLocation(origCameraData=cam0, origPixel=pixel0)
        item.addNewObservation(cameraData=cam1, pixel=pixel1)

        location, total_error, num_locations = item.computeResults()
        self.assertEqual(num_locations, 1,
                         "expected exactly one triangulated location")
        self.assertFalse(np.isnan(np.asarray(location)).any(),
                         "recovered LLE should be finite")
        return location, total_error

    def _assert_close_to_target(self, recovered_LLE, target_LLE):
        horiz = _haversine_meters(recovered_LLE, target_LLE)
        vert = abs(recovered_LLE[2] - target_LLE[2])
        self.assertLess(
            horiz, self.HORIZONTAL_TOL_M,
            f"recovered horizontal position off by {horiz:.3f} m "
            f"(tol {self.HORIZONTAL_TOL_M} m); recovered={recovered_LLE}, "
            f"target={target_LLE}")
        self.assertLess(
            vert, self.VERTICAL_TOL_M,
            f"recovered elevation off by {vert:.3f} m "
            f"(tol {self.VERTICAL_TOL_M} m); recovered={recovered_LLE}, "
            f"target={target_LLE}")

    def test_center_pixel_two_cameras_recovers_target(self):
        """Bore-sighted target at sensor center is recovered to within ~1 m."""
        target_LLE = [40.0, -75.0, 100.0]

        # Cameras placed ~200 m east and ~200 m north of the target
        # (approximate degree offsets at this latitude).
        cam0_LLE = [40.0, -75.0 + 200.0 / (111320.0 * np.cos(np.radians(40.0))),
                    100.0]
        cam1_LLE = [40.0 + 200.0 / 111320.0, -75.0, 100.0]

        recovered, _err = self._run_pipeline(target_LLE, cam0_LLE, cam1_LLE)
        self._assert_close_to_target(recovered, target_LLE)

    def test_center_pixel_with_elevation_offset(self):
        """Cameras at different elevation than target: pitch is exercised."""
        target_LLE = [37.5, -122.0, 50.0]
        cam0_LLE = [37.5, -122.0 + 250.0 /
                    (111320.0 * np.cos(np.radians(37.5))), 80.0]
        cam1_LLE = [37.5 + 250.0 / 111320.0, -122.0, 30.0]

        recovered, _err = self._run_pipeline(target_LLE, cam0_LLE, cam1_LLE)
        self._assert_close_to_target(recovered, target_LLE)

    def test_off_center_pixels_exercise_angle_offsets(self):
        """Aim each camera ``off`` the target, then put the target at the
        corresponding off-center pixel so calcAngleOffsets / focalLength get
        non-trivially exercised. The recovered LLE must still match.
        """
        target_LLE = [40.0, -75.0, 100.0]
        cam0_LLE = [40.0, -75.0 + 300.0 /
                    (111320.0 * np.cos(np.radians(40.0))), 100.0]
        cam1_LLE = [40.0 + 300.0 / 111320.0, -75.0, 100.0]

        # Aim each camera at the target, then rotate the bore-sight a few
        # degrees so the target falls at a known off-center pixel.
        focal = ItemLocation.calcVirtualFocalLength()
        # Choose a 5-degree column offset for cam0 and a 4-degree row offset
        # for cam1. The pixel offset that corresponds to angle a is
        # focal * tan(a). Sign convention from calcAngleOffsets:
        #   * positive col offset (col > center) <=> larger heading-to-target
        #   * positive row offset (row > center) <=> SMALLER pitch-to-target
        col_angle_deg = 5.0
        row_angle_deg = 4.0
        col_offset_px = focal * np.tan(np.radians(col_angle_deg))
        row_offset_px = focal * np.tan(np.radians(row_angle_deg))
        center = [Constants.SENSOR_SIZE[0] / 2.0,
                  Constants.SENSOR_SIZE[1] / 2.0]
        pixel0 = [center[0], center[1] + col_offset_px]   # right of center
        pixel1 = [center[0] - row_offset_px, center[1]]   # above center

        h0, p0 = _aim_camera_at_target(cam0_LLE, target_LLE)
        h1, p1 = _aim_camera_at_target(cam1_LLE, target_LLE)
        # Mis-aim each camera by the same angle, in the OPPOSITE direction
        # of the off-center pixel, so the LOS to the target still falls on
        # the chosen pixel.
        cam0 = CameraData(LatLonEl=cam0_LLE,
                          heading=h0 - col_angle_deg, pitch=p0)
        cam1 = CameraData(LatLonEl=cam1_LLE,
                          heading=h1, pitch=p1 - row_angle_deg)

        item = ItemLocation(origCameraData=cam0, origPixel=pixel0)
        item.addNewObservation(cameraData=cam1, pixel=pixel1)

        location, _err, num = item.computeResults()
        self.assertEqual(num, 1)
        self._assert_close_to_target(location, target_LLE)


if __name__ == "__main__":
    unittest.main()
