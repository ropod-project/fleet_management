from __future__ import print_function
import time
import uuid

from fleet_management.structs.task import TaskRequest, Task
from fleet_management.structs.action import Action
from fleet_management.structs.status import TaskStatus
from fleet_management.task_planner import TaskPlanner
from fleet_management.resource_manager import ResourceManager

class TaskManager(ZyreBaseCommunicator):
    '''An interface for handling ropod task requests and managing ropod tasks

    @author Alex Mitrevski
    @maintainer Alex Mitrevski, Argentina Ortega Sainz
    @contact aleksandar.mitrevski@h-brs.de, argentina.ortega@h-brs.de
    '''
    def __init__(self, config_params, ccu_store):
        self.scheduled_tasks = dict()
        self.ongoing_task_ids = list()
        self.task_statuses = dict()
        self.ccu_store = ccu_store
        self.resource_manager = ResourceManager(config_params, ccu_store)

    '''Returns a dictionary of all scheduled tasks
    '''
    def get_scheduled_tasks(self):
        return self.scheduled_tasks

    '''Returns a list of the task IDs of ongoing tasks
    '''
    def get_ongoing_tasks_ids(self):
        return self.ongoing_task_ids

    '''Returns a dictionary containing the statuses of the ongoing tasks
    '''
    def get_ongoing_task_statuses(self):
        return self.task_statuses

    '''Loads any existing task data (ongoing tasks, scheduled tasks) from the CCU store database
    '''
    def restore_task_data(self):
        self.scheduled_tasks = self.ccu_store.get_scheduled_tasks()
        self.ongoing_task_ids = self.ccu_store.get_ongoing_tasks()
        self.task_statuses = self.ccu_store.get_ongoing_task_statuses()
        self.resource_manager.restore_data()

    '''Processes a task request message; ignores all other messages.
    Only responds to messages of type TASK-REQUEST and TASK-PROGRESS

    @param msg_content a dictionary representing a Zyre message
    '''
    def receive_msg_cb(self, msg_content):
        dict_msg = dict() # self.convert_zyre_msg_to_dict(msg_content)
        message_type = dict_msg['header']['type']
        if message_type == 'TASK-REQUEST':
            print('Received a task request; processing request')
            user_id = dict_msg["payload"]["userId"]
            device_type = dict_msg["payload"]["deviceType"]
            device_id = dict_msg["payload"]["deviceId"]
            task_start_time = dict_msg["payload"]["startTime"]

            pickup_location = dict_msg["payload"]["pickupLocation"]
            pickup_location_level = dict_msg["payload"]["pickupLocationLevel"]

            delivery_location = dict_msg["payload"]["deliveryLocation"]
            delivery_location_level = dict_msg["payload"]["deliveryLocationLevel"]

            task_request = TaskRequest()
            task_request.user_id = user_id
            task_request.cart_type = device_type
            task_request.cart_id = device_id
            task_request.start_time = task_start_time

            task_request.pickup_pose.name = pickup_location
            task_request.pickup_pose.floor_number = pickup_location_level

            task_request.delivery_pose.name = delivery_location
            task_request.delivery_pose.floor_number = delivery_location_level
            self.__process_task_request(task_request)
        elif message_type == 'TASK-PROGRESS':
            task_id = dict_msg["payload"]["taskId"]
            robot_id = dict_msg["payload"]["robotId"]
            current_action = dict_msg["payload"]["status"]["currentAction"]
            task_status = dict_msg["payload"]["status"]["taskStatus"]
            self.__update_task_status(task_id, robot_id, current_action, task_status)

    '''Dispatches all scheduled tasks that are ready for dispatching
    '''
    def dispatch_tasks(self):
        for task_id, task in self.scheduled_tasks.items():
            if task_id in self.ongoing_task_ids:
                if self.__can_execute_task(task_id):
                    current_time = self.__get_current_time()
                    print('[{0}] Dispatching task {1}'.format(current_time, task_id))
                    self.dispatch_task(task)
                    self.ongoing_task_ids.append(task_id)
                    self.ccu_store.add_ongoing_task(task_id)
                    self.__initialise_task_status(task_id)
                    self.ccu_store.add_task_status(self.task_statuses[task_id])

    '''Sends a task to the appropriate robot fleet

    @param task a fleet_management.structs.task.Task object
    '''
    def dispatch_task(self, task):
        for robot_id, actions in task.robot_actions.items():
            msg_dict = dict()
            msg_dict['header']['type'] = 'TASK'
            msg_dict['header']['metamodel'] = 'ropod-msg-schema.json'
            msg_dict['header']['msgId'] = uuid.uuid4()
            msg_dict['header']['robotId'] = robot_id
            msg_dict['header']['timestamp'] = -1

            msg_dict['payload']['metamodel'] = 'ropod-task-schema.json'
            msg_dict['payload']['taskId'] = task.id
            msg_dict['payload']['teamRobotIds'] = task.team_robot_ids
            msg_dict['payload']['actions'] = list()
            for action in actions:
                action_dict = action.to_dict()
                msg_dict['payload']['actions'].append(action_dict)
            self.shout(msg_dict)

    '''Returns True if the given task needs to be dispatched
    based on the task schedule; returns False otherwise

    @param task_id UUID representing the ID of a task

    '''
    def __can_execute_task(self, task_id):
        current_time = self.__get_current_time()
        task_start_time = self.scheduled_tasks[task_id].start_time
        if task_start_time < current_time:
            return True
        return False

    '''Processes a task request, namely chooses robots for the task
    and generates an appropriate task plan

    @param request a fleet_management.structs.task.TaskRequest object
    '''
    def __process_task_request(self, request):
        print('Creating a task plan...')
        task_plan = TaskPlanner.get_task_plan(request)
        for action in task_plan:
            action.id = uuid.uuid4()

        print('Allocating robots for the task...')
        task_robots = self.resource_manager.get_robots_for_task(request, task_plan)
        task = Task()
        task.id = uuid.uuid4()
        task.cart_type = request.cart_type
        task.cart_id = request.cart_id
        task.start_time = request.start_time
        task.team_robot_ids = task_robots
        for robot_id in task_robots:
            task.robot_actions[robot_id] = task_plan

        print('Saving task...')
        self.scheduled_tasks[task.id] = task
        self.ccu_store.add_task(task)
        print('Task saved')

    '''Creates a task status entry in 'self.task_statuses' for the task with ID 'task_id'

    @param task_id UUID representing the ID of a task
    '''
    def __initialise_task_status(self, task_id):
        task = self.scheduled_tasks[task_id]
        task_status = TaskStatus()
        task_status.task_id = task_id
        task_status.status = 'ongoing'
        for robot_id in task.team_robot_ids:
            task_status.current_robot_action[robot_id] = task.robot_actions[robot_id][0].id
            task_status.completed_robot_actions[robot_id] = list()
            task_status.estimated_task_duration = task.estimated_duration
        self.task_statuses[task_id] = task_status

    '''Updates the status of the robot with ID 'robot_id' that is performing
    the task with ID 'task_id'

    If 'task_status' is "terminated", removes the task from the list of scheduled
    and ongoing tasks and saves a historical database entry for the task.
    On the other hand, if 'task_status' is "ongoing", the task's entry
    is updated for the appropriate robot.

    @param task_id UUID representing a previously scheduled task
    @param robot_id name of a robot
    @param current_action UUID representing an action
    @param task_status a string representing the status of a task;
           takes the values "ongoing", "terminated", and "completed"
    '''
    def __update_task_status(self, task_id, robot_id, current_action, task_status):
        status = self.task_statuses[task_id]
        status.status = task_status
        if task_status == 'terminated' or task_status == 'completed':
            task = self.scheduled_tasks[task_id]
            self.ccu_store.archive_task(task, status)
            self.scheduled_tasks.pop(task_id)
            self.task_statuses.pop(task_id)
            if task_id in self.ongoing_task_ids:
                self.ongoing_task_ids.remove(task_id)
        elif task_status == 'ongoing':
            previous_action = status.current_robot_action[robot_id]
            status.completed_robot_actions[robot_id].append(previous_action)
            status.current_robot_action[robot_id] = current_action
            self.ccu_store.update_task_status(status)

            # TODO: update the estimated time duration based on the current timestamp
            # and the estimated duration of the rest of the tasks

    '''Returns the action with ID 'action_id' that is part of the task with ID 'task_id'
    and is performed by the robot with ID 'robot_id'

    @param task_id UUID representing a scheduled task
    @param robot_id name of a robot
    @param action_id UUID representing a task
    '''
    def __get_action(self, task_id, robot_id, action_id):
        task = self.scheduled_tasks[task_id]
        desired_action = Action()
        for action in task.robot_actions[robot_id]:
            if action.id == action_id:
                desired_action = action
                break
        return desired_action

    '''Returns the current UNIX timestamp in seconds
    '''
    def __get_current_time(self):
        return int(round(time.time() * 1000))
