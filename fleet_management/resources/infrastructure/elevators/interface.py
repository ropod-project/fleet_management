import logging

from ropod.structs.elevator import RobotCallUpdate, ElevatorRequestStatus


class ElevatorControlInterface:

    def __init__(self, elevator_id, ccu_store, api, **kwargs):
        self.logger = logging.getLogger(self.__module__ + __name__)
        self.id = elevator_id
        self.ccu_store = ccu_store
        self.api = api
        self.pending_requests = dict()

    def elevator_cmd_reply_cb(self, msg):
        payload = msg.get('payload')

        query_id = payload.get('queryId')
        query_success = payload.get('querySuccess')

        if not query_success:
            self.logger.warning("Query %s failed", query_id)
            return

        command = payload.get('command')
        self.logger.info('Received reply from elevator control for %s query', query_id)

        if command == 'CALL_ELEVATOR':
            request = self.pending_requests.pop(query_id)
            request.status = ElevatorRequestStatus.ACCEPTED
            self.logger.debug("Set request status as going to start")
        elif command == 'CANCEL_ELEVATOR':
            request = self.pending_requests.pop(query_id)
            request.status = ElevatorRequestStatus.CANCELED
            self.logger.debug("Set request status as canceled")

    def request_elevator(self, elevator_request):
        self.pending_requests[elevator_request.query_id] = elevator_request
        msg = self.api.create_message(elevator_request)
        self.api.publish(msg, groups=['ELEVATOR-CONTROL'])
        self.logger.info("Requested elevator...")

    def cancel_elevator_call(self, elevator_request):
        # TODO To cancel a call, the call ID should be sufficient:
        # read from ccu store, get info to cancel
        self.pending_requests[elevator_request.query_id] = elevator_request
        msg = self.api.create_message(elevator_request)
        self.api.publish(msg, groups=['ELEVATOR-CONTROL'])

    def confirm_robot_action(self, robot_action, query_id):
        if robot_action == 'ROBOT_FINISHED_ENTERING':
            # TODO Remove this hardcoded floor
            update = RobotCallUpdate(query_id,
                                     'CLOSE_DOORS_AFTER_ENTERING', start_floor=1)
        elif robot_action == 'ROBOT_FINISHED_EXITING':
            # TODO Remove this hardcoded floor
            update = RobotCallUpdate(query_id,
                                     'CLOSE_DOORS_AFTER_EXITING', goal_floor=1)

        msg = self.api.create_message(update)

        # TODO This doesn't match the convention
        msg['header']['type'] = 'ELEVATOR-CMD'
        self.api.publish(msg, groups=['ELEVATOR-CONTROL'])
        self.logger.debug('Sent robot confirmation to elevator')

    def configure_api(self, api_config):
        self.api.register_callbacks(self, api_config)


