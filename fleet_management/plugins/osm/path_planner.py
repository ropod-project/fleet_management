import logging

import OBL
import requests
from OBL.local_area_finder import LocalAreaFinder
from fleet_management.exceptions.osm import OSMPlannerException
from fleet_management.plugins.osm import bridge
from ropod.structs.area import Area, SubArea
from fleet_management.exceptions.osm import OSMPlannerException


class _OSMPathPlanner(object):
    """

    Attributes:
        building_ref (string): building name eg. 'AMK' or 'BRSU'
        local_area_finder (OBL LocalAreaFinder):
        osm_bridge (OBL OSMBridge): Description
        path_planner (OBL PathPlanner): Description

    """

    def __init__(self, building, osm_bridge):
        """

        Args:
            building (str): Building reference to make queries
            osm_bridge(osm_bridge instance): osm bridge
        """
        self.logger = logging.getLogger('fms.plugins.path_planner')

        self.osm_bridge = osm_bridge
        self.building_ref = building

        self.path_planner = OBL.PathPlanner(self.osm_bridge)
        self.local_area_finder = LocalAreaFinder(self.osm_bridge)
        try:
            self.set_building(self.building_ref)
        except requests.exceptions.ConnectionError:
            self.logger.error("Cannot connect to overpass")
            return
        self.logger.info("Path planner service ready...")

    def set_building(self, ref):
        """Setter function to switch to different building after initialisation

        Args:
            ref (string): building ref

        """
        if self.osm_bridge:
            self.path_planner.set_building(ref)
            self.building_ref = ref
        else:
            self.logger.error("Path planning service cannot be provided")

    def set_coordinate_system(self, coordinate_system):
        """Set coordinate system

        Args:
            coordinate_system (string): 'spherical' / 'coordinate'

        """
        if self.osm_bridge:
            self.path_planner.set_coordinate_system(coordinate_system)
        else:
            self.logger.error("Path planning service cannot be provided")

    def get_path_plan_from_local_area(self, start_local_area, destination_local_area):
        """ Plans path similar to `get_path_plan` but only needs start and 
        destination local area

        :start_local_area: int or str
        :destination_local_area: int or str
        :returns: list of FMS Area
        """
        if self.osm_bridge:
            start_local_area_obj = self.osm_bridge.get_local_area(start_local_area)
            start_local_area_obj.geometry
            destination_local_area_obj = self.osm_bridge.get_local_area(destination_local_area)
            destination_local_area_obj.geometry
            start_area = start_local_area_obj.parent_id
            destination_area = destination_local_area_obj.parent_id
            start_floor = int(start_local_area_obj.level)
            destination_floor = int(destination_local_area_obj.level)
            return self.get_path_plan(start_floor=start_floor,
                                      destination_floor=destination_floor,
                                      start_area=start_area,
                                      destination_area=destination_area,
                                      start_local_area=start_local_area,
                                      destination_local_area=destination_local_area)
        else:
            self.logger.error("Path planning service cannot be provided")
            raise OSMPlannerException('Could not plan a path. OSM Bridge not available.')

    def get_path_plan(self, start_floor='', destination_floor='',
                      start_area='', destination_area='', *args, **kwargs):
        """Plans path using A* and semantic info in in OSM

        Either start_local_area or robot_position is required
        Either destination_local_area or destination_task id required
        (Destination_task currently works on assumption that only single
        docking,undocking,charging etc. exist in
        OSM world model for specified area)

        Args:
            start_floor (int): start floor
            destination_floor (int): destination floor
            start_area (str): start area ref
            destination_area (str): destination area ref
            start_local_area (str, optional): start sub area ref
            destination_local_area (str, optional): destination sub area ref
            robot_position([double,double], optional): either in x,y or lat,lng coordinate system
            destination_task(string,optional): task to be performed at destination eg. docking, undocking etc.

        Returns:
            TYPE: [FMS Area]

        """
        if self.osm_bridge:
            start_floor = self.get_floor_name(self.building_ref, start_floor)
            destination_floor = self.get_floor_name(
                self.building_ref, destination_floor)

            navigation_path = self.path_planner.get_path_plan(
                start_floor,
                destination_floor,
                start_area,
                destination_area,
                *args, **kwargs)
            navigation_path_fms = []

            for pt in navigation_path:
                temp = self.decode_planner_area(pt)
                if len(temp) == 1:
                    navigation_path_fms.append(temp[0])
                elif len(temp) == 2:
                    navigation_path_fms.append(temp[0])
                    navigation_path_fms.append(temp[1])

            return navigation_path_fms
        else:
            self.logger.error("Path planning service cannot be provided")
            raise OSMPlannerException('Could not plan a path. OSM Bridge not available.')

    def get_estimated_path_distance(self, start_floor, destination_floor,
                                    start_area='', destination_area='', *args,
                                    **kwargs):
        """Returns approximate path distance in meters

        Args:
            start_floor (int): start floor
            destination_floor (int): destination floor
            start_area (str): start area ref
            destination_area (str): destination area ref

        Returns:
            TYPE: double

        """
        try:
            if self.osm_bridge:
                start_floor = self.get_floor_name(self.building_ref, start_floor)
                destination_floor = self.get_floor_name(
                    self.building_ref, destination_floor)
                return self.path_planner.get_estimated_path_distance(
                    start_floor, destination_floor, start_area,
                    destination_area, *args, **kwargs)
        except Exception as e:
            self.logger.error("Path planning service cannot be provided", exc_info=True)
            raise OSMPlannerException('Could not estimate path distance.')
            # TODO raise the right exception here

    def get_area(self, ref, get_level=False):
        """Returns OBL Area in FMS Area format

        Args:
            ref (string/number): semantic or uuid

        Returns:
            TYPE: FMS Area

        """
        if self.osm_bridge:
            area = self.osm_bridge.get_area(ref)
            if get_level:
                area.geometry
            return self.obl_to_fms_area(area)
        else:
            self.logger.error("Path planning service cannot be provided")

    def get_sub_area(self, ref, *args, **kwargs):
        """Returns OBL local area in FMS SubArea format

        Args:
            ref (string/number): semantic or uuid
            behaviour: SubArea will be searched based on specified behaviour (inside specified Area scope)
            robot_position: SubArea will be searched based on robot position (inside specified Area scope)
        Returns:
            TYPE: FMS SubArea

        """
        if self.osm_bridge:
            pointX = kwargs.get("x")
            pointY = kwargs.get("y")
            behaviour = kwargs.get("behaviour")
            sub_area = None
            if (pointX and pointY) or behaviour:
                sub_area = self.local_area_finder.get_local_area(
                    area_name=ref, *args, **kwargs)
                if not sub_area:
                    if behaviour:
                        self.logger.error(
                            "Local area finder did not return a sub area within area %s with behaviour %s" % (
                                ref, behaviour))
                        raise OSMPlannerException("Local area finder did not return a sub area within area %s with "
                                                  "behaviour %s" % (ref, behaviour))
                    else:
                        self.logger.error("Local area finder did not return a sub area within area %s for point ("
                                          "%.2f, %.2f)" % (ref, pointX, pointY))
                        raise OSMPlannerException("Local area finder did not return a sub area within area %s for "
                                                  "point (%.2f, %.2f)" % (ref, pointX, pointY))
                    return
            else:
                sub_area = self.osm_bridge.get_local_area(ref)

            return self.obl_to_fms_subarea(sub_area)
        else:
            # self.logger.error("Path planning service cannot be provided")
            raise OSMPlannerException("Path planning service cannot be provided because OSM Bridge is absent")

    def obl_to_fms_area(self, osm_wm_area):
        """Converts OBL area to FMS area

        Args:
            osm_wm_area (OBL Area): eg. rooms, corridor, elevator etc.

        Returns:
            TYPE: FMS area

        """
        area = Area()
        area.id = osm_wm_area.id
        area.name = osm_wm_area.ref
        area.type = osm_wm_area.type
        if osm_wm_area.level:
            area.floor_number = int(osm_wm_area.level)
        area.sub_areas = []
        if osm_wm_area.navigation_areas is not None:
            for nav_area in osm_wm_area.navigation_areas:
                area.sub_areas.append(self.obl_to_fms_subarea(nav_area))
        return area

    def obl_to_fms_subarea(self, osm_wm_local_area):
        """Converts OBL to FMS subarea

        Args:
            osm_wm_local_area (OBL LocalArea): eg. charging, docking,
                                                   undocking areas
        Returns:
            TYPE: FMS SubArea

        """
        sa = SubArea()
        sa.id = osm_wm_local_area.id
        sa.name = osm_wm_local_area.ref
        return sa

    def decode_planner_area(self, planner_area):
        """OBL Path planner path consist of PlannerAreas which has local areas and exit doors. In FMS we consider door at same level as area.
        This function is used to extract door from OBL PlannerArea and return it as separate area along with door

        Args:
            planner_area (OBL PlannerArea):

        Returns:
            TYPE: [FMS Area]

        """
        area = self.obl_to_fms_area(planner_area)

        if planner_area.exit_door:
            return [area, self.obl_to_fms_area(planner_area.exit_door)]
        else:
            return [area]

    def task_to_behaviour(self, task):
        """Convert FMS task to behaviours modelled in OSM world model

        Args:
            task (string):

        Returns:
            TYPE: Maybe string

        """
        if task == 'DOCK':
            return 'docking'
        elif task == 'UNDOCK':
            return 'undocking'
        elif task == 'CHARGE':
            return 'charging'
        elif task == 'REQUEST_ELEVATOR' or task == 'EXIT_ELEVATOR':
            return 'waiting'
        return None

    def get_floor_name(self, building_ref, floor_number):
        """Constructs FMS compatible floor names given floor number and
        building ref

        Args:
            building_ref (string):
            floor_number (int):

        Returns:
            TYPE: string

        """
        return building_ref + '_L' + str(floor_number)

    @staticmethod
    def _get_osm_bridge(server_ip, server_port):
        return bridge.configure(server_ip=server_ip, server_port=server_port)

    @classmethod
    def overpass_server_config(cls, server_ip, server_port, building):
        osm_bridge = cls._get_osm_bridge(server_ip, server_port)
        return cls(osm_bridge=osm_bridge, building=building)


class OSMPathPlannerBuilder:
    def __init__(self):
        self._instance = None

    def __call__(self, **kwargs):
        if not self._instance:
            self._instance = _OSMPathPlanner(**kwargs)
        return self._instance


configure = OSMPathPlannerBuilder()
