"""Ported from backend/latgis/tests/util/test_enu_to_ecef.py."""

import unittest

from latgis.geo.enu_to_ecef import MoreTransfers


EARTH_RADIUS_M = 6378137.0


class EnuToEcefTests(unittest.TestCase):

    def test_prime_meridian(self):
        x, y, z = MoreTransfers.enu2ecef(
            e1=0, n1=0, u1=0, lat0=0, lon0=0, h0=0, deg=True)

        self.assertAlmostEqual(x, EARTH_RADIUS_M, 3)
        self.assertAlmostEqual(y, 0, 3)
        self.assertAlmostEqual(z, 0, 3)


if __name__ == "__main__":
    unittest.main()
