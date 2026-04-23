"""Ported from backend/latgis/tests/latgis/test_triangulate.py."""

import unittest

from numpy import abs, array, ndarray

from latgis.geo.triangulate import minDistPoint_3D


DOUBLE_TOL = 1e-5


class TriangulateTests(unittest.TestCase):

    def assertVectorNearZero(self, vector: ndarray):
        self.assertTrue(abs(vector[0]) < DOUBLE_TOL)
        self.assertTrue(abs(vector[1]) < DOUBLE_TOL)
        self.assertTrue(abs(vector[2]) < DOUBLE_TOL)

    def test_parallel_lines(self):
        lineDir1 = array([0, 2, 0])
        linePt1 = array([1, 0, 0])
        lineDir2 = array([0, 1, 0])
        linePt2 = array([5, 0, 0])
        minPt, minDist = minDistPoint_3D(lineDir1, linePt1, lineDir2, linePt2)
        self.assertTrue(abs(minDist - 4) < DOUBLE_TOL)
        self.assertVectorNearZero(minPt - array([0, 0, 0]))

    def test_intersect_in_xy_plane(self):
        lineDir1 = array([2, 1, 0])
        linePt1 = array([0, 0, 0])
        lineDir2 = array([-1, 1, 0])
        linePt2 = array([3, 0, 0])
        minPt, minDist = minDistPoint_3D(lineDir1, linePt1, lineDir2, linePt2)
        self.assertTrue(abs(minDist - 0) < DOUBLE_TOL)
        self.assertVectorNearZero(minPt - array([2, 1, 0]))

    def test_intersect_in_xz_plane(self):
        lineDir1 = array([1, 0, 2])
        linePt1 = array([-4, 0, -2])
        lineDir2 = array([-1, 0, 0])
        linePt2 = array([5, 0, 2])
        minPt, minDist = minDistPoint_3D(lineDir1, linePt1, lineDir2, linePt2)
        self.assertTrue(abs(minDist - 0) < DOUBLE_TOL)
        self.assertVectorNearZero(minPt - array([-2, 0, 2]))

    def test_intersect_in_yz_plane(self):
        lineDir1 = array([0, 1, -1])
        linePt1 = array([0, -2, 3])
        lineDir2 = array([0, -1, -1])
        linePt2 = array([0, 2, 3])
        minPt, minDist = minDistPoint_3D(lineDir1, linePt1, lineDir2, linePt2)
        self.assertTrue(abs(minDist - 0) < DOUBLE_TOL)
        self.assertVectorNearZero(minPt - array([0, 0, 1]))

    def test_skew_3d(self):
        lineDir1 = array([-2, 0, 1])
        linePt1 = array([3, 2, 0])
        lineDir2 = array([5, 0, 1])
        linePt2 = array([-4, 0, 0])
        minPt, minDist = minDistPoint_3D(lineDir1, linePt1, lineDir2, linePt2)
        self.assertTrue(abs(minDist - 2) < DOUBLE_TOL)
        self.assertVectorNearZero(minPt - array([1, 1, 1]))

    def test_intersection_behind_camera_returns_empty(self):
        lineDir1 = array([1, 1, 0])
        linePt1 = array([3, 0, 0])
        lineDir2 = array([-1, 1, 1])
        linePt2 = array([1, 0, 0])
        minPt, minDist = minDistPoint_3D(lineDir1, linePt1, lineDir2, linePt2)
        # Original behavior: returns [[], []] when intersection is behind both cameras.
        self.assertEqual(minPt, [])
        self.assertEqual(minDist, [])


if __name__ == "__main__":
    unittest.main()
