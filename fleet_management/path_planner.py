from __future__ import print_function
import fleet_management.extern.overpass as overpass
from fleet_management.structs.area import Area, Waypoint
from fleet_management.path_planning import GlobalPathPlanner, LocalPathPlanner


class PathPlanner(object):
    def __init__(self, overpass_server):
        self.api_url = "http://" + overpass_server + "/api/interpreter"
        self.api = overpass.API(endpoint=self.api_url)
        self.gpp = GlobalPathPlanner(self.api)
        self.lpp = LocalPathPlanner(self.api)

    '''Returns a list of fleet_management.structs.area.Area objects representing
    the path through which a robot should from "start_location" to "destination"

    @param start_location a fleet_management.structs.area.Area object
    @param destination a fleet_management.structs.area.Area object

    '''
    def get_path_plan(self, start_location, destination):

        final_path = []

        print("Planning global path ..........................")

        if self.gpp.set_start_destination_locations(start_location.name, destination.name):
            if self.gpp.plan_path():
                path = self.gpp.prepare_path()
                print("Generating way points ..................")
                if self.lpp.set_start_destination_locations(start_location.name, destination.name):
                    local_path = self.lpp.plan_path(path)
                    if local_path:
                        final_path = self.lpp.prepare_path(local_path, path)
                        for area in final_path:
                            print('Area name: {} | Area type: {} | Level: {}'.format(area.name,area.type,area.floor_number))
                        print('Processing path...')

        dict_plan = PathPlanner.__generate_osm_plan(final_path)
        path_plan = PathPlanner.__parse_plan(dict_plan)
        print('Successfully processed path')
        return path_plan

    @staticmethod
    def __generate_osm_plan(path_list):
        plan = dict()
        plan['payload'] = dict()
        plan['payload']['topologicalNodes'] = list()

        for area in path_list:
            a = dict()
            a['tags'] = dict()
            a['tags']['id'] = area.id
            a['tags']['name'] = area.name
            a['tags']['floor_number'] = area.floor_number
            a['tags']['type'] = area.type
            a['tags']['waypoints'] = list()

            for wap_pt in area.waypoints:
                wp = dict()
                wp['tags'] = dict()
                wp['tags']['id'] = wap_pt.area_id
                wp['tags']['name'] = wap_pt.semantic_id
                a['tags']['waypoints'].append(wp)

            plan['payload']['topologicalNodes'].append(a)
        print(plan)
        return plan

    @staticmethod
    def __parse_plan(json_plan):
        plan_areas = list()
        for json_area in json_plan['payload']['topologicalNodes']:
            area = Area()
            area.id = json_area['tags']['id']
            area.name = json_area['tags']['name']
            area.floor_number = json_area['tags']["floor_number"]

            for wap_pt in json_area['tags']['waypoints']:
                waypoint = Waypoint()
                waypoint.area_id = wap_pt['tags']['id'] 
                waypoint.semantic_id = wap_pt['tags']['name']
                area.waypoints.append(waypoint) 
            plan_areas.append(area)
        return plan_areas

    @staticmethod
    def __generate_test_osm_plan(start_location, destination):
        plan = dict()
        plan['payload'] = dict()
        plan['payload']['topologicalNodes'] = list()

        if start_location.name == 'pickup_location' and destination.name == 'delivery_location':
            wp1 = {'tags': {}}
            wp1['tags']['id'] = '1'
            wp1['tags']['name'] = 'hallway1'
            wp1['tags']['floor_number'] = 0
            plan['payload']['topologicalNodes'].append(wp1)

            wp2 = {'tags': {}}
            wp2['tags']['id'] = '2'
            wp2['tags']['name'] = 'hallway2'
            wp2['tags']['floor_number'] = 0
            plan['payload']['topologicalNodes'].append(wp2)

            wp3 = {'tags': {}}
            wp3['tags']['id'] = '3'
            wp3['tags']['name'] = 'hallway3'
            wp3['tags']['floor_number'] = 0
            plan['payload']['topologicalNodes'].append(wp3)
        elif start_location.name == 'delivery_location' and destination.name == 'charging_station':
            wp1 = {'tags': {}}
            wp1['tags']['id'] = '1'
            wp1['tags']['name'] = 'hallway3'
            wp1['tags']['floor_number'] = 0
            plan['payload']['topologicalNodes'].append(wp1)

            wp2 = {'tags': {}}
            wp2['tags']['id'] = '2'
            wp2['tags']['name'] = 'hallway2'
            wp2['tags']['floor_number'] = 0
            plan['payload']['topologicalNodes'].append(wp2)

            wp3 = {'tags': {}}
            wp3['tags']['id'] = '3'
            wp3['tags']['name'] = 'hallway1'
            wp3['tags']['floor_number'] = 0
            plan['payload']['topologicalNodes'].append(wp3)

        return plan
