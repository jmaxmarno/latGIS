"""
Author: Nelly Kane
Originated: 12.03.2018

Repo: latGIS
File: lat_gis.py

The defined containers for the latGIS Python architecture.
"""
from typing import Tuple

import numpy as np
from pandas import DataFrame

from .geo.enu_to_ecef import MoreTransfers
from .constants import Constants
from .geo.coord_transfers import CoordTransfers
from .geo.triangulate import minDistPoint_3D


########################################################################################################################
class CameraData:
    """
    This class stores camera metadata
        LatLonEl : list [Lattitude, Longitude, Elevation] 
        heading: 
        pitch:
    """

    def __init__(self, LatLonEl: list, heading: float, pitch: float):
        # instance variable unique to each instance
        self.LatLonEl = LatLonEl
        self.heading = heading
        self.pitch = pitch


######################################################################################################################## 
class ItemLocation:
    """
    This class stores all information regarding an object searched in geo-coordinate
    space. It will also, include functions for coordinate transformations so those 
    operations don't have to clutter up the backend.
    Members:
        - object ID (generated from a static ID counter.)
        - Pandas.DataFrame of a list, size(capture points) of:
            - CameraData data per capture point
            - ENU vector per capture point
            - ECEF vector per capture point
            - triangulation results 
            - triangulation errors
        
    Method:
        - new obseration
        - ENU to ECEF
        - triangulation
        - triangulation error
        
    TODO:
        - write a results getter
        - adapt triangulation for all possible observation combinations
    """
    objID = 0  # object counter
    maxObsPerObj = 10  # maximum observations for each object
    DEG2RAD = np.pi / 180  # degrees to radians
    focalLength = float
    coordTransfers = CoordTransfers()

    ####################################################################################################################
    def __init__(self, origCameraData: CameraData, origPixel: list):
        """
        Construtor
        """

        # calculate virtual focal length
        ItemLocation.focalLength = ItemLocation.calcVirtualFocalLength()

        # incrementing object counter
        ItemLocation.objID += 1  # NOTE how the accessor is the class, not the object
        self.objID = ItemLocation.objID

        # start Pandas.DataFrame
        columns = ['objID', 'cameraData', 'pixel', 'ecefPt', 'enuVec', 'ecefVec', 'objectLocationECEF',
                   'objectLocationLLE', 'triangulationError']
        self.__objectDataArray = DataFrame(columns=columns,
                                           index=np.arange(ItemLocation.maxObsPerObj))

        self.__objectDataArray.at[0, 'objID'] = self.objID
        self.__objectDataArray.at[0, 'cameraData'] = origCameraData
        self.__objectDataArray.at[0, 'pixel'] = origPixel

        # set current observations to zero
        self.curObs = 0

        # convert to ENU
        ItemLocation.sensor_2_ENU(self)

        # get ECEF vector of object location (NOTE: Object can be anywhere on this vector)
        ItemLocation.ENU_2_ECEF(self)

    ####################################################################################################################
    def getObjectID(self) -> int:
        """
        A method to return the object ID.
        """
        return self.objID

    ####################################################################################################################
    def addNewObservation(self, cameraData: CameraData, pixel: list):
        """
        Method for adding new observation to object
            cameraData: CameraData object
            pixel: TODO
        """
        # increment observation counter
        self.curObs += 1

        if self.curObs == ItemLocation.maxObsPerObj:
            print('WARNING: Object list full, increase maximum observations')
            return

        self.__objectDataArray.at[self.curObs, 'objID'] = self.objID
        self.__objectDataArray.at[self.curObs, 'cameraData'] = cameraData
        self.__objectDataArray.at[self.curObs, 'pixel'] = pixel

        # convert to ENU
        self.sensor_2_ENU()

        # get ECEF vector of object location (NOTE: Object can be anywhere on this vector)
        self.ENU_2_ECEF()

        # perform triangulation and get error
        self.triagulation()

        # compute object location Latitude, Longitude, Elevation
        self.getObjectLLE()

        return

    ####################################################################################################################
    def getResults(self) -> list:
        """
        Resturning results as a list.
        """
        # compute results
        location, totalError, numLocations = ItemLocation.computeResults(self)

        return ['ID: ' + str(self.objID), 'Loc: ' + str(location), 'Error: ' + str(totalError),
                'Triangulations: ' + str(numLocations)]

    ####################################################################################################################
    def printResults(self):
        """
        Returning results as a string.
        """
        # compute results
        location, totalError, numLocations = ItemLocation.computeResults(self)
        print('Object ID: ' + str(self.objID))
        print('Lat, Lon, Elev: ' + str(location))
        print('Computed Error: ' + str(totalError))
        print('Number or triangulations: ' + str(numLocations))

        return

    ####################################################################################################################
    # TODO: print DataFrame information
    def printFullResults(self):
        """
        Return results of the full data frame.
        """
        pass

    ####################################################################################################################
    # TODO: Write Results to file.
    def writeResultsToFile(self, filePath):
        """
        write results of data frame to file filePath.
        """
        pass

    ####################################################################################################################
    def getRecentCameraData(self) -> CameraData:
        """
        Get CameraData object of last position in dataFrame.
        """
        return self.__objectDataArray.at[self.curObs, 'cameraData']

    ####################################################################################################################
    def getRecentPixel(self) -> list:
        """
        Get most recent pixel list in  [row, col].
        """
        return self.__objectDataArray.at[self.curObs, 'pixel']

    ####################################################################################################################
    def getRecentECEFPoint(self) -> np.ndarray:
        """
        Get most recent camera point in ECEF coordinates.
        """
        return self.__objectDataArray.at[self.curObs, 'ecefPt']

    ####################################################################################################################
    def getRecentECEFVector(self) -> np.ndarray:
        """
        Get most recent line-of-sight vector in ECEF coordinates.
        """
        return self.__objectDataArray.at[self.curObs, 'ecefVec']

    ####################################################################################################################
    def computeResults(self) -> Tuple[float, float, float]:
        """
        Compute results
        Returns [location: LLE, Error, num locations]
        # TODO: adapt this when triangulation computes on possible each obs. conbination.
        # For now, the results will be:
        #   -> Location: mean of all computed location
        #   -> Error: mean(errors)/sqrt(number of errors)
        # NOTE: Will also output number of computed locations for printing purposes 
        """
        # NOTE: the avg. location is found in ECEF and then converted to LLE
        nonNullObsVals = self.__objectDataArray['objectLocationECEF'][
            self.__objectDataArray['objectLocationECEF'].notnull().values]

        nonNullObsVals = nonNullObsVals.values
        numLocations = len(nonNullObsVals)

        if (numLocations > 0):
            # calculate X, Y and Z
            x = float(0)
            y = float(0)
            z = float(0)
            for idx in np.arange(numLocations):
                x = x + nonNullObsVals[idx][0]
                y = y + nonNullObsVals[idx][1]
                z = z + nonNullObsVals[idx][2]

            x = x / numLocations
            y = y / numLocations
            z = z / numLocations

            location = ItemLocation.coordTransfers.ECEF_to_LLE([x, y, z])

        else:
            location = np.nan

        # TODO: Error computes must be recalculated
        nonNullErrVals = self.__objectDataArray['triangulationError'][
            self.__objectDataArray['triangulationError'].notnull().values]
        numErrors = len(nonNullErrVals.values)

        if (numErrors > 0):
            totalError = np.mean(nonNullErrVals) / np.sqrt(numErrors)
        else:
            totalError = np.nan

        return location, totalError, numLocations

    ####################################################################################################################
    def sensor_2_ENU(self, degFlag: bool = True):
        """
        Convert sensor info (CameraData / Pixel) to Earth North Up (ENU coordinate system)
        """
        cameraData = self.__objectDataArray.at[self.curObs, 'cameraData']
        heading = cameraData.heading
        pitch = cameraData.pitch
        pixel = self.__objectDataArray.at[self.curObs, 'pixel']

        # degrees to radians, if (degFlag == True)
        if (degFlag == 1):
            heading = heading * Constants.DEG2RAD
            pitch = pitch * Constants.DEG2RAD

        # calculate angle-to-target from north contributions from object pixel location
        pitchAdjust, headingAdjust = ItemLocation.calcAngleOffsets(pixel)

        headingForRot = heading + headingAdjust
        pitchForRot = pitch + pitchAdjust

        # start from definition, ENU = <0, 1, 0>
        enuDef = np.array((0, 1, 0))

        # rotate about east by the pitch
        Rx = np.array([[1, 0, 0],
                       [0, np.cos(pitchForRot), -np.sin(pitchForRot)],
                       [0, np.sin(pitchForRot), np.cos(pitchForRot)]])

        ENU = np.matmul(Rx, enuDef)

        # rotate about north by the heading (NOTE: sign change since heading defined in CW)
        headingForRot = -headingForRot
        Rz = np.array([[np.cos(headingForRot), -np.sin(headingForRot), 0],
                       [np.sin(headingForRot), np.cos(headingForRot), 0],
                       [0, 0, 1]])

        objENU = np.matmul(Rz, ENU)  # NOTE: This should now be the object direction in ENU coords.
        self.__objectDataArray.at[self.curObs, 'enuVec'] = objENU

        return

    ####################################################################################################################
    @staticmethod
    def calcAngleOffsets(pixel: list) -> Tuple[float, float]:
        """
        TODO
        """
        # positive col offset pairs with an INCREASE in heading-to-target
        colPixelOffset = pixel[1] - float(Constants.SENSOR_SIZE[1] / 2)
        colAngle = np.arctan(np.abs(colPixelOffset / ItemLocation.focalLength))
        if (colPixelOffset < 0):
            colAngle = -colAngle

        # positive row offset pairs with a DECREASE in pitch-to-target
        rowPixelOffset = pixel[0] - float(Constants.SENSOR_SIZE[0] / 2)
        rowAngle = np.arctan(np.abs(rowPixelOffset / ItemLocation.focalLength))
        if (rowPixelOffset > 0):
            rowAngle = -rowAngle

        return rowAngle, colAngle

    ####################################################################################################################
    def ENU_2_ECEF(self):
        """
        # This function will compute the ecef capture point and the ecef direction vector.
        """
        cameraData = self.__objectDataArray.at[self.curObs, 'cameraData']
        LLE = cameraData.LatLonEl

        enuVec = self.__objectDataArray.at[self.curObs, 'enuVec']

        # To create the ECEF vector there has to be two points in ECEF. The first one will
        # be at the ENU origin, the second one will be on the ENU vector. 
        xECEF1, yECEF1, zECEF1 = MoreTransfers.enu2ecef(0, 0, 0, LLE[0], LLE[1], LLE[2], deg=True)
        ptEcef = np.array((xECEF1, yECEF1, zECEF1))

        LARGE_NUMBER = 100000000
        xECEF2, yECEF2, zECEF2 = MoreTransfers.enu2ecef(LARGE_NUMBER * enuVec[0], LARGE_NUMBER * enuVec[1],
                                                      LARGE_NUMBER * enuVec[2],
                                                      LLE[0], LLE[1], LLE[2], deg=True)

        xECEF = xECEF2 - xECEF1
        yECEF = yECEF2 - yECEF1
        zECEF = zECEF2 - zECEF1

        vecEcef = np.array((xECEF, yECEF, zECEF))
        vecEcef = vecEcef / np.linalg.norm(vecEcef)

        self.__objectDataArray.at[self.curObs, 'ecefPt'] = ptEcef
        self.__objectDataArray.at[self.curObs, 'ecefVec'] = vecEcef

        return

    ####################################################################################################################
    def triagulation(self):
        """
        # grabbing ECEF data from previous observation for triangulation
        # NOTE: TODO:: For now the triangulation will only be computed with data from the 
        # current observation and the previous observation. Adapt this to do triangulation
        # on all possible combinations in the list of observations and use the results 
        # of all of them to compute one final result.
        """
        ecefPt1 = self.__objectDataArray.at[self.curObs - 1, 'ecefPt']
        ecefVec1 = self.__objectDataArray.at[self.curObs - 1, 'ecefVec']
        ecefPt2 = self.__objectDataArray.at[self.curObs, 'ecefPt']
        ecefVec2 = self.__objectDataArray.at[self.curObs, 'ecefVec']
        [objectLocationECEF, minDist] = minDistPoint_3D(ecefVec1, ecefPt1, ecefVec2, ecefPt2)

        # minDistPoint_3D signals failure by returning empty lists for both values.
        # Use isinstance to disambiguate from the ndarray / scalar returned on success
        # (an ndarray == [] comparison broadcasts and raises under numpy >= 2).
        if isinstance(objectLocationECEF, list) and len(objectLocationECEF) == 0:
            objectLocationECEF = np.nan

        if isinstance(minDist, list) and len(minDist) == 0:
            minDist = np.nan

        self.__objectDataArray.at[self.curObs, 'objectLocationECEF'] = objectLocationECEF

        # computing triangulation error
        ItemLocation.triangulationError(self, ecefVec1, ecefVec2, minDist)

        return

    ####################################################################################################################
    def triangulationError(self, vec1: np.ndarray, vec2: np.ndarray, distance: float):

        # TODO: Adapt this function when more than one triangulation can occur per observation

        if isinstance(distance, list) and len(distance) == 0:
            return
        # the error is currently (1/2)*minimumDistance/sin(angle between vectors)
        angle = np.arccos((np.dot(vec1, vec2)) / (np.linalg.norm(vec1) * np.linalg.norm(vec2)))

        SMALL_NUMBER = 1e-8
        if (angle < SMALL_NUMBER):
            calcError = np.inf
        else:
            calcError = (1.0 / 2.0) * distance / np.sin(angle)

        self.__objectDataArray.at[self.curObs, 'triangulationError'] = calcError

        return

    ####################################################################################################################
    def getObjectLLE(self):
        """
        compute object Lattitude Longitude Elevation
        """
        objectLocationECEF = self.__objectDataArray.at[self.curObs, 'objectLocationECEF']

        # Guard against scalar NaN (numpy 2 raises on np.isnan(...).any() for floats);
        # only an array-like ECEF triple is convertible to LLE.
        if isinstance(objectLocationECEF, np.ndarray) and not np.isnan(objectLocationECEF).any():
            LLE = ItemLocation.coordTransfers.ECEF_to_LLE(
                [objectLocationECEF[0], objectLocationECEF[1], objectLocationECEF[2]])
        else:
            LLE = np.nan

        self.__objectDataArray.at[self.curObs, 'objectLocationLLE'] = LLE

    ####################################################################################################################
    @staticmethod
    def calcVirtualFocalLength() -> float:
        """
        Compute virtual focal length in pixel units.
        """
        FOV = Constants.FOV
        # focal length calculation is based off 2nd sensor size value, numCols
        numCols = Constants.SENSOR_SIZE[1]
        focalLength = numCols / (2 * np.arctan(Constants.DEG2RAD * FOV / 2))
        return focalLength


########################################################################################################################
if __name__=='__main__':
    pass
