"""Round-trip tests for the WGS84 LLE <-> ECEF transforms.

Ported from the original ``test_coordinate_transformation.py`` print-script:
the original printed the difference between ``LLE -> ECEF -> LLE``; here we
assert that round-trip difference is within tolerance.
"""

import unittest

import numpy as np

from latgis.geo.coord_transfers import CoordTransfers


# Tolerance for round-trip comparisons. The original docstring notes the
# function is accurate to ~2 mm; lat/lon recover to better than 1e-6 deg.
ANGLE_TOL_DEG = 1e-6
ELEV_TOL_M = 1e-2


class CoordTransfersRoundTripTests(unittest.TestCase):

    def setUp(self):
        self.ct = CoordTransfers()

    def _assert_round_trip(self, lle):
        ecef = self.ct.LLE_to_ECEF(lle)
        lle_back = self.ct.ECEF_to_LLE(ecef)

        # Longitude is returned in [0, 360); normalize input to that range.
        lon_in = lle[1] % 360.0

        self.assertAlmostEqual(lle_back[0], lle[0], delta=ANGLE_TOL_DEG)
        self.assertAlmostEqual(lle_back[1], lon_in, delta=ANGLE_TOL_DEG)
        self.assertAlmostEqual(lle_back[2], lle[2], delta=ELEV_TOL_M)

    def test_north_pole(self):
        self._assert_round_trip([90, 0, 1.333])

    def test_mid_latitude(self):
        self._assert_round_trip([30, 30, 10])

    def test_low_latitude(self):
        self._assert_round_trip([2, 80, 0.25])

    def test_southern_hemisphere(self):
        self._assert_round_trip([-42, 10, 5])

    def test_wrap_longitude(self):
        self._assert_round_trip([3, 285, 15])


if __name__ == "__main__":
    unittest.main()
