"""Unit tests for ``latgis.track.TargetTracker``.

Covers the cost-matrix builder, the gate function, and the happy-path of
``add_frame_observations`` including promotion of dropped tracks to the
final-tracks list.
"""

import unittest

import numpy as np

from latgis.location import CameraData, ItemLocation
from latgis.track import TargetTracker


class GateTests(unittest.TestCase):
    """``TargetTracker.gate`` is the per-pair overlap term."""

    def setUp(self):
        self.tracker = TargetTracker(gateSize=10, distToDVec=1.0)

    def test_identical_points_full_overlap(self):
        # Identical pred/obs => full overlap == area of the gate circle.
        overlap = self.tracker.gate(prediction=[100, 200],
                                    observation=[100, 200])
        expected = np.pi * self.tracker.gateSize ** 2
        self.assertAlmostEqual(overlap, expected, places=9)

    def test_far_apart_zero_overlap(self):
        # Distance > 2*gateSize => zero overlap.
        overlap = self.tracker.gate(prediction=[0, 0],
                                    observation=[0, 100])
        self.assertEqual(overlap, 0)

    def test_partial_overlap_is_between_zero_and_full(self):
        full = np.pi * self.tracker.gateSize ** 2
        overlap = self.tracker.gate(prediction=[0, 0],
                                    observation=[0, 5])  # half a diameter
        self.assertGreater(overlap, 0)
        self.assertLess(overlap, full)


class BuildCostMatrixTests(unittest.TestCase):
    """``TargetTracker.build_cost_matrix`` shape and values."""

    def setUp(self):
        self.tracker = TargetTracker(gateSize=10, distToDVec=1.0)
        self.best_match = np.pi * self.tracker.gateSize ** 2

    def test_matrix_shape(self):
        observations = [[0, 0], [50, 50], [100, 100]]
        predictions = [[1, 1], [200, 200]]
        m = self.tracker.build_cost_matrix(observations, predictions)
        self.assertEqual(m.shape,
                         (len(observations),
                          len(observations) + len(predictions)))

    def test_perfect_match_gives_zero_cost(self):
        observations = [[10, 10]]
        predictions = [[10, 10]]
        m = self.tracker.build_cost_matrix(observations, predictions)
        # left side: track-vs-obs cost
        self.assertAlmostEqual(m[0, 0], 0.0, places=9)

    def test_far_track_gives_inf_cost(self):
        observations = [[0, 0]]
        predictions = [[1000, 1000]]
        m = self.tracker.build_cost_matrix(observations, predictions)
        self.assertTrue(np.isinf(m[0, 0]))

    def test_right_side_is_new_track_diagonal(self):
        # The right-hand n_obs columns are the "start a new track" slots:
        # diagonal == bestMatch, off-diagonal == LARGE_VAL (inf).
        observations = [[0, 0], [50, 50]]
        predictions = []  # no current tracks
        m = self.tracker.build_cost_matrix(observations, predictions)
        self.assertEqual(m.shape, (2, 2))
        self.assertAlmostEqual(m[0, 0], self.best_match, places=9)
        self.assertAlmostEqual(m[1, 1], self.best_match, places=9)
        self.assertTrue(np.isinf(m[0, 1]))
        self.assertTrue(np.isinf(m[1, 0]))


class AddFrameObservationsTests(unittest.TestCase):
    """End-to-end happy path for ``TargetTracker.add_frame_observations``."""

    def setUp(self):
        # Reset class-level counter between tests for stable IDs.
        ItemLocation.objID = 0

    def _frames(self):
        # A single, stationary camera viewing two distinct sky regions. The
        # predictor returns the input pixel exactly when ``deltaL == 0``,
        # so identical observations across frames are guaranteed to
        # re-associate to the same tracks.
        cam = CameraData(LatLonEl=[40.0, -75.0, 100.0], heading=0, pitch=0)
        obs_a = [400, 400]
        obs_b = [600, 620]
        return cam, obs_a, obs_b

    def test_two_frames_two_observations_creates_two_tracks(self):
        tracker = TargetTracker(gateSize=15, distToDVec=1.0)
        cam, obs_a, obs_b = self._frames()

        # Frame 1: no current tracks => both observations start new tracks.
        tracker.add_frame_observations([obs_a, obs_b], cam)
        # pylint: disable=protected-access
        current = tracker._TargetTracker__currentTrackDataFrame
        final = tracker._TargetTracker__finalTrackDataFrame
        self.assertEqual(current.get_size(), 2)
        self.assertEqual(final.get_size(), 0)

        # Frame 2: identical obs => predictor returns same pixels (camera
        # has not moved) => Munkres re-associates to existing tracks.
        tracker.add_frame_observations([obs_a, obs_b], cam)
        self.assertEqual(current.get_size(), 2,
                         "matching observations should NOT spawn new tracks")
        self.assertEqual(final.get_size(), 0)

    def test_dropped_observation_promotes_track_to_final(self):
        tracker = TargetTracker(gateSize=15, distToDVec=1.0)
        cam, obs_a, obs_b = self._frames()

        tracker.add_frame_observations([obs_a, obs_b], cam)
        tracker.add_frame_observations([obs_a, obs_b], cam)

        # pylint: disable=protected-access
        current = tracker._TargetTracker__currentTrackDataFrame
        final = tracker._TargetTracker__finalTrackDataFrame
        ids_before = set(current.get_ids())
        self.assertEqual(len(ids_before), 2)

        # Frame 3: drop obs_b. Track for obs_b has no matching observation
        # and must migrate from current -> final.
        tracker.add_frame_observations([obs_a], cam)

        self.assertEqual(current.get_size(), 1,
                         "unmatched track should leave the current list")
        self.assertEqual(final.get_size(), 1,
                         "unmatched track should land in the final list")

        remaining = set(current.get_ids())
        promoted = set(final.get_ids())
        self.assertEqual(len(remaining & promoted), 0)
        self.assertEqual(remaining | promoted, ids_before)


if __name__ == "__main__":
    unittest.main()
