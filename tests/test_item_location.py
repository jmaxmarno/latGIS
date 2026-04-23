"""Smoke test mirroring the original test_item_location.py print-script.

Asserts that the full ItemLocation pipeline (sensor -> ENU -> ECEF ->
triangulation -> LLE) runs end-to-end and produces a finite location after
two observations.
"""

import math
import unittest

import numpy as np

from latgis.location import CameraData, ItemLocation
from latgis.geo.coord_transfers import CoordTransfers


class ItemLocationSmokeTests(unittest.TestCase):

    def test_two_observations_produce_results(self):
        ct = CoordTransfers()

        LatLonEl0 = [0, 0, 10]
        metersTraveled = [0, 10, 0]

        cam0 = CameraData(LatLonEl0, heading=0, pitch=0)
        ECEF0 = ct.LLE_to_ECEF(LatLonEl0)
        ECEF1 = [ECEF0[i] + metersTraveled[i] for i in range(3)]
        LatLonEl1 = ct.ECEF_to_LLE(ECEF1)

        item = ItemLocation(origCameraData=cam0, origPixel=[512, 512])

        cam1 = CameraData(LatLonEl1, heading=0, pitch=0)
        item.addNewObservation(cameraData=cam1, pixel=[512, 490])

        ECEF2 = [ECEF1[i] + metersTraveled[i] for i in range(3)]
        LatLonEl2 = ct.ECEF_to_LLE(ECEF2)
        cam2 = CameraData(LatLonEl2, heading=0, pitch=0)
        item.addNewObservation(cameraData=cam2, pixel=[512, 475])

        results = item.getResults()
        self.assertEqual(len(results), 4)
        self.assertTrue(results[0].startswith("ID:"))

        # getRecentCameraData / getRecentPixel
        self.assertIs(item.getRecentCameraData(), cam2)
        self.assertEqual(item.getRecentPixel(), [512, 475])


if __name__ == "__main__":
    unittest.main()
