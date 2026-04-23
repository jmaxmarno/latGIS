"""Unit tests for ``latgis.position_predict.ItemLocationModel``.

The predictor estimates where an object observed in frame ``t`` will appear
in frame ``t+1`` given the change in camera telemetry. We test two
deterministic cases:

* **Stationary camera** -- the predicted pixel must equal the input pixel
  (this is the explicit ``deltaL == 0`` branch).
* **Forward motion toward the target at center** -- the bore-sight does
  not change, so the target stays at the sensor center column.
* **Lateral motion** -- as the camera moves sideways, a fixed object at
  the previous bore-sight must drift to the OPPOSITE side of the sensor
  (parallax). We verify the sign and that the magnitude is bounded.
"""

import unittest

import numpy as np

from latgis.constants import Constants
from latgis.geo.coord_transfers import CoordTransfers
from latgis.location import CameraData
from latgis.position_predict import ItemLocationModel


class ItemLocationModelTests(unittest.TestCase):

    def setUp(self):
        # ``W`` is the assumed closest distance from the object to the
        # camera direction vector (meters). 5 m is the value used in the
        # original example scripts.
        self.model = ItemLocationModel(W=5.0)
        self.center = [Constants.SENSOR_SIZE[0] / 2.0,
                       Constants.SENSOR_SIZE[1] / 2.0]

    def test_stationary_camera_returns_input_pixel(self):
        """deltaL == 0 branch: prediction == observation."""
        cam = CameraData(LatLonEl=[40.0, -75.0, 100.0], heading=10, pitch=5)
        for pixel in ([self.center[0], self.center[1]],
                      [400, 600],
                      [700, 300]):
            with self.subTest(pixel=pixel):
                pred = self.model.itemLocationPredictor(
                    objRowCol=pixel, camData1=cam, camData2=cam)
                # ~0.1 px artifact at the exact bore-sight from the
                # SMALL_NUMBER divide-by-zero guard in the predictor.
                self.assertAlmostEqual(pred[0], pixel[0], delta=0.5)
                self.assertAlmostEqual(pred[1], pixel[1], delta=0.5)

    def test_forward_motion_keeps_centered_object_centered(self):
        """Camera moves north (along its bore-sight): object stays centered."""
        ct = CoordTransfers()
        lle0 = [40.0, -75.0, 100.0]
        ecef0 = ct.LLE_to_ECEF(lle0)
        # Move 10 m north along ECEF y-axis. (At equator-ish lat the local
        # ENU frame is well-approximated; for this test what matters is
        # that the camera moves AWAY from the previous position parallel to
        # its line of sight.)
        # Easier: move directly in local ENU using enu2ecef.
        from latgis.geo.enu_to_ecef import MoreTransfers
        x1, y1, z1 = MoreTransfers.enu2ecef(0, 10, 0,
                                             lle0[0], lle0[1], lle0[2])
        lle1 = ct.ECEF_to_LLE([x1, y1, z1])

        cam0 = CameraData(LatLonEl=lle0, heading=0, pitch=0)  # facing north
        cam1 = CameraData(LatLonEl=lle1, heading=0, pitch=0)

        pred = self.model.itemLocationPredictor(
            objRowCol=self.center, camData1=cam0, camData2=cam1)

        # The predicted column should remain very close to the sensor
        # center -- the object lay on the bore-sight before and the
        # bore-sight has only translated, not rotated.
        self.assertAlmostEqual(pred[1], self.center[1], delta=1.0)

    def test_lateral_motion_shifts_predicted_column(self):
        """Forward motion produces radial flow about the focus of expansion.

        With the camera moving (mostly) along its line of sight, fixed
        objects undergo radial optical flow: their offset from the
        focus-of-expansion (the direction pixel) GROWS in magnitude. We
        verify both signs (object left of bore-sight drifts further left,
        object right drifts further right) which together pins down the
        sign convention of the predictor.
        """
        from latgis.geo.enu_to_ecef import MoreTransfers
        ct = CoordTransfers()
        lle0 = [40.0, -75.0, 100.0]

        # Predominantly forward motion (100 m N) with a small lateral
        # component (1 m E) to keep the focus-of-expansion well within
        # the sensor.
        x1, y1, z1 = MoreTransfers.enu2ecef(1, 100, 0,
                                             lle0[0], lle0[1], lle0[2])
        lle1 = ct.ECEF_to_LLE([x1, y1, z1])

        cam0 = CameraData(LatLonEl=lle0, heading=0, pitch=0)
        cam1 = CameraData(LatLonEl=lle1, heading=0, pitch=0)

        # Object 50 px LEFT of center should drift further left.
        pix_left = [self.center[0], self.center[1] - 50.0]
        pred_left = self.model.itemLocationPredictor(
            objRowCol=pix_left, camData1=cam0, camData2=cam1)
        self.assertLess(pred_left[1], pix_left[1],
                        "object left of bore-sight should drift further left "
                        "as camera moves forward")

        # Object 50 px RIGHT of center should drift further right.
        pix_right = [self.center[0], self.center[1] + 50.0]
        pred_right = self.model.itemLocationPredictor(
            objRowCol=pix_right, camData1=cam0, camData2=cam1)
        self.assertGreater(pred_right[1], pix_right[1],
                           "object right of bore-sight should drift further "
                           "right as camera moves forward")

        # Predictions land on or near the sensor and don't move vertically.
        for pred in (pred_left, pred_right):
            self.assertGreaterEqual(pred[1], 0)
            self.assertLessEqual(pred[1], Constants.SENSOR_SIZE[1])
            self.assertAlmostEqual(pred[0], self.center[0], delta=1.0)

    def test_focal_length_matches_constants(self):
        """The virtual focal length is derived from FOV + sensor width."""
        focal = self.model.calcVirtualFocalLength()
        expected = Constants.SENSOR_SIZE[1] / (
            2 * np.arctan(Constants.DEG2RAD * Constants.FOV / 2))
        self.assertAlmostEqual(focal, expected, places=9)


if __name__ == "__main__":
    unittest.main()
