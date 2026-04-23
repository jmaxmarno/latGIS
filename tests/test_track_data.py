"""Ported from backend/latgis/tests/latgis/test_track_data.py."""

import unittest

from latgis.location import CameraData, ItemLocation
from latgis.track import TrackData
from latgis.geo.coord_transfers import CoordTransfers


class TrackDataTests(unittest.TestCase):

    def test_add_remove_append(self):
        ct = CoordTransfers()
        metersTraveled = [0, 10, 0]

        # First track
        LatLonEl0 = [0, 0, 10]
        cam0 = CameraData(LatLonEl=LatLonEl0, heading=0, pitch=0)
        pixel0 = [500, 500]
        ECEF0 = ct.LLE_to_ECEF(LatLonEl0)
        ECEF1 = [ECEF0[i] + metersTraveled[i] for i in range(3)]
        LatLonEl1_app = ct.ECEF_to_LLE(ECEF1)
        camForAppend = CameraData(LatLonEl1_app, heading=0, pitch=0)
        pixelForAppend = [480, 500]

        # Second track
        LatLonEl1 = [2, 2, 2]
        cam1 = CameraData(LatLonEl=LatLonEl1, heading=0, pitch=0)
        pixel1 = [512, 490]

        td = TrackData(name='Test object')
        self.assertEqual(td.get_size(), 0)
        self.assertEqual(td.get_ids(), [])

        item0 = ItemLocation(origCameraData=cam0, origPixel=pixel0)
        td.add_track(objectLocation=item0)
        self.assertEqual(len(td.get_ids()), 1)

        item1 = ItemLocation(origCameraData=cam1, origPixel=pixel1)
        td.add_track(objectLocation=item1)
        self.assertEqual(len(td.get_ids()), 2)
        self.assertIn(item0.getObjectID(), td.get_ids())
        self.assertIn(item1.getObjectID(), td.get_ids())

        td.append_to_data_by_id(item1.getObjectID(),
                                cameraData=camForAppend, pixel=pixelForAppend)

        removed = td.remove_by_id(item0.getObjectID())
        self.assertIs(removed, item0)
        self.assertEqual(len(td.get_ids()), 1)
        self.assertEqual(td.get_ids(), [item1.getObjectID()])

        # round-trip getter
        self.assertIs(td.get_data_by_id(item1.getObjectID()), item1)
        self.assertEqual(td.get_name(), 'Test object')


if __name__ == "__main__":
    unittest.main()
