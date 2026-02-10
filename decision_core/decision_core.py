#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, Int8, Int32
from transitions.extensions import GraphMachine
import threading
import time

# -----------------------------------------------------------
# Vehicle state codes for ROS topic output
# -----------------------------------------------------------
# Each operational mode of the autonomous shuttle is assigned an integer code
# which is published to the /state topic. These can be used by other modules
# (e.g.:Path Planning, L&L Control , Door Operaion Control.) to know the current state of autonomous shuttle.
STATE_CODES = {
    'IDLE': 0,
    'DRIVING_AND_PLANNING': 1,
    'BOARDING': 2,
    'DROP_OFF_AND_DEBOARDING': 3,
    'PARKING': 4,
    'TRIP_CANCELLATION': 5
}

# Simple delay utility used in some state actions
def delay(sec):  # pragma: no cover
    time.sleep(sec)



# -----------------------------------------------------------
# FSM Core Logic Class
# -----------------------------------------------------------
class DecisionUnit:
    """Finite State Machine logic for PaxAuto Shuttle Decision Core."""

    # --- Define all possible FSM states ---
    states = [
        'IDLE',
        'DRIVING_AND_PLANNING',
        'BOARDING',
        'DROP_OFF_AND_DEBOARDING',
        'PARKING',
        'TRIP_CANCELLATION'
    ]

    def __init__(self, node: Node):
        # Reference to the ROS 2 node (to use publishers, etc.)
        self.node = node

        # --- Internal flags mirroring ROS topic inputs ---
        # These variables are updated by ROS subscribers
        # and act as the logical conditions for FSM transitions.
        self.select_shuttle = 0
        self.booking_request = None
        self.destination_reached = None
        self.door_status = None
        self.emergency_button = None
        self.user_inside = None
        self.trip_cancel = None

        # --- Trackers to remember FSM status ---
        self.previous_state = None
        self.current_shuttle_conf = None  
        self.current_trip_cancellation = None


        # Initialize the state machine using transitions.GraphMachine
        # - show_conditions=True displays transition conditions on diagram
        # - ignore_invalid_triggers=True prevents crash on invalid triggers
        self.machine = GraphMachine(
            model=self,
            states=DecisionUnit.states,
            initial='IDLE',
            ignore_invalid_triggers=True,
            show_conditions=True,
            auto_transitions=False,
            title="Decision Unit FSM",
            graph_engine="graphviz"
        )

        # Generate and save the FSM diagram (fsm_live.png)
        self.update_diagram()

        # -----------------------------------------------------------
        # Define all FSM transitions (T1–T9)
        # -----------------------------------------------------------
        # Each transition has: trigger, source state, destination state,
        # conditions,negated conditions (unless), and an action (after).

        # User Story 2.3: From IDLE → DRIVING_AND_PLANNING 
        self.machine.add_transition('try_transition',  # --- Trigger name ---
                                    'IDLE',  # --- Source state ---
                                    'DRIVING_AND_PLANNING',  # --- Destination state ---
                                    conditions=['is_select_shuttle', 'is_booking_request'], 
                                    # --- Above Conditions that must be True for transition ---
                                    after='act_T1')    # --- Callback executed after transition completes ---

        # User Story 3.19: From DRIVING_AND_PLANNING → BOARDING 
        self.machine.add_transition('try_transition', 'DRIVING_AND_PLANNING', 'BOARDING',
                                    conditions=['is_destination_reached'],
                                    # --- Above Condtions Must be True for Transition ---
                                    unless=['is_user_inside'], # --- Condtion Must be False for Transition ---
                                    after='act_T2')

        # User Story 5,1: From BOARDING → DRIVING_AND_PLANNING 
        self.machine.add_transition('try_transition', 'BOARDING', 'DRIVING_AND_PLANNING',
                                    conditions=['is_user_inside','is_door_closed'], after='act_T3')

        # User Story 3.20: From DRIVING_AND_PLANNING → DROP_OFF_AND_DEBOARDING 
        self.machine.add_transition('try_transition', 'DRIVING_AND_PLANNING', 'DROP_OFF_AND_DEBOARDING',
                                    conditions=['is_destination_reached', 'is_user_inside'], after='act_T4')

        # User Story 7.1: From DROP_OFF_AND_DEBOARDING → PARKING 
        self.machine.add_transition('try_transition', 'DROP_OFF_AND_DEBOARDING', 'PARKING',
                                    conditions=['is_door_closed'],
                                    unless=['is_booking_request'],
                                    after='act_T5')

        # User Story 8.1: From PARKING → IDLE when destination reached and no new booking
        self.machine.add_transition('try_transition', 'PARKING', 'IDLE',
                                    conditions=['is_destination_reached'],
                                    unless=['is_booking_request'],
                                    after='act_T6')

        # User Story 3.20(Acceptance Criteria 3.20.2)(Emergency Button is pressed during driving and planning state): 
        # Immediate jump from DRIVING AND PLANNING  → DEBOARDING 
        self.machine.add_transition('try_transition', 'DRIVING_AND_PLANNING', 'DROP_OFF_AND_DEBOARDING',
                                    conditions=['is_emergency_button'], after='act_T4')

        # User Story 7.2: From DROP_OFF_AND_DEBOARDING → DRIVING_AND_PLANNING if a new booking received
        self.machine.add_transition('try_transition', 'DROP_OFF_AND_DEBOARDING', 'DRIVING_AND_PLANNING',
                                    conditions=['is_booking_request'], after='act_T1')

        # User Story 8.2: From PARKING → DRIVING_AND_PLANNING if new booking request received
        self.machine.add_transition('try_transition', 'PARKING', 'DRIVING_AND_PLANNING',
                                    conditions=['is_booking_request'], after='act_T1')
        
        self.machine.add_transition('try_transition', 'DRIVING_AND_PLANNING', 'TRIP_CANCELLATION',
                                    conditions=['is_trip_cancel'], after='act_T7')

        self.machine.add_transition('try_transition', 'TRIP_CANCELLATION', 'DRIVING_AND_PLANNING',
                                    conditions=['is_booking_request'], after='act_T8')    
    # -----------------------------------------------------------
    # Condition Functions — Evaluate ROS topic flags
    # -----------------------------------------------------------
    def is_select_shuttle(self): return self.select_shuttle == 4
    def is_booking_request(self): return self.booking_request is True
    def is_destination_reached(self): return self.destination_reached is True
    def is_emergency_button(self): return self.emergency_button is True
    def is_user_inside(self): return self.user_inside is True
    def is_door_closed(self): return not(self.door_status) is True
    def is_trip_cancel(self): return self.trip_cancel is True

    # -----------------------------------------------------------
    # FSM Diagram Generation
    # -----------------------------------------------------------
    def update_diagram(self):  # pragma: no cover
       filename = "fsm_live.png"
       try:
         graph = self.machine.get_graph()
         graph.draw(filename, prog='dot', format='png')
       except Exception as e:
          self.node.get_logger().error(f"❌ FSM diagram generation failed: {e}")


    # -----------------------------------------------------------
    # Action Functions (T1–T9)
    # -----------------------------------------------------------
    # Each action represents the operational behavior of the vehicle
    # right after a transition has been triggered.
    def act_T1(self):
        # Shuttle starts driving and planning route
        self.publish_state('DRIVING_AND_PLANNING')
        self.publish_shuttle_conf(True)
        # Wait until booking_request becomes False 
        while(True):
            if self.booking_request == False:
                self.publish_shuttle_conf(False)
                break

    def act_T2(self):
        # Boarding process begins
        self.publish_state('BOARDING')
        

    def act_T3(self):
        # Resume driving after boarding
        self.publish_state('DRIVING_AND_PLANNING')
        

    def act_T4(self):
        # Shuttle reaches drop-off area, waiting for door actions
        self.publish_state('DROP_OFF_AND_DEBOARDING')
        

    def act_T5(self):
        # Parking mode after deboarding complete
        self.publish_state('PARKING')
        

    def act_T6(self):
        # Reset system back to IDLE state
        self.publish_state('IDLE')
        

    def act_T7(self):
        self.publish_state('TRIP_CANCELLATION')    
        self.publish_trip_cancellation(True)  
        while(True):
            if self.trip_cancel == False:
                self.publish_trip_cancellation(False)
                break

    def act_T8(self):
        self.publish_state('DRIVING_AND_PLANNING')   
        self.publish_shuttle_conf(True)
        # Wait until booking_request becomes False 
        while(True):
            if self.booking_request == False:
                self.publish_shuttle_conf(False)
                break 

    

    # -----------------------------------------------------------
    # Helper Publishing Functions
    # -----------------------------------------------------------
    def publish_state(self, state_name: str):
        """Publish /state topic whenever the FSM changes state."""
        msg = Int32()
        msg.data = STATE_CODES[state_name]
        self.node.state_pub.publish(msg)
        self.node.get_logger().info(f"/state = {msg.data} ({state_name})")
        self.previous_state = self.state
        self.update_diagram()  # Refresh FSM diagram

    def publish_shuttle_conf(self, value: bool):
        """Publish shuttle confirmation status."""
        msg = Bool()
        msg.data = value
        self.node.shuttle_confirmation_pub.publish(msg)
        self.current_shuttle_conf = value

    def publish_trip_cancellation(self, value: bool):
        msg = Bool()
        msg.data = value
        self.node.trip_cancellation_pub.publish(msg)
        self.current_trip_cancellation = value

    # -----------------------------------------------------------
    # Continuous Monitoring Thread
    # -----------------------------------------------------------
    def monitor(self):  # pragma: no cover
     while rclpy.ok():
        self.try_transition()
        time.sleep(0.5)



# -----------------------------------------------------------
# ROS 2 Node Wrapper for FSM
# -----------------------------------------------------------
class DecisionUnitNode(Node):  # pragma: no cover
    """ROS 2 Node wrapper integrating FSM with ROS topics."""

    def __init__(self):
        super().__init__('decision_core_fsm')

        # --- Publishers ---
        # /state → Int32 code representing FSM state
        # /shuttle_confirmation → Bool flag for booking confirmation to server
        self.state_pub = self.create_publisher(Int32, '/state', 10)
        self.shuttle_confirmation_pub = self.create_publisher(Bool, '/shuttle_confirmation', 10)
        self.trip_cancellation_pub = self.create_publisher(Bool, '/trip_cancellation', 10)


        # --- FSM Instance ---
        self.fsm = DecisionUnit(self)

        # --- Subscribers ---
        # These topics  from other  modules
        # and update FSM condition variables in real time.
        self.create_subscription(Int8, '/select_shuttle', self.cb_select_shuttle, 10)
        self.create_subscription(Bool, '/booking_request', self.cb_booking_request, 10)
        self.create_subscription(Bool, '/destination_reached', self.cb_destination_reached, 10)
        self.create_subscription(Bool, '/door_status', self.cb_door_status, 10)
        self.create_subscription(Bool, '/emergency_button', self.cb_emergency_button, 10)
        self.create_subscription(Bool, '/user_inside', self.cb_user_inside, 10)
        self.create_subscription(Bool, '/trip_cancel', self.cb_trip_cancel, 10)

        # --- Timers ---
        # Regularly republishes the latest /state and /shuttle_confirmation
        self.create_timer(1.0, self.publish_current_state)
        self.create_timer(1.0, self.publish_current_shuttle_conf)
        self.create_timer(1.0, self.publish_current_trip_cancellation)


        # --- Background thread for FSM monitoring ---
        threading.Thread(target=self.fsm.monitor, daemon=True).start()

        # --- Startup Log ---
        self.get_logger().info("✅ Decision Core Node started and ready!")

        # --- Publish initial state as IDLE ---
        self.fsm.publish_state('IDLE')

    # -----------------------------------------------------------
    # Periodic Publishers (used by Timers)
    # -----------------------------------------------------------
    def publish_current_state(self):
        msg = Int32()
        msg.data = STATE_CODES[self.fsm.state]
        self.state_pub.publish(msg)

    def publish_current_shuttle_conf(self):
        msg = Bool()
        msg.data = bool(self.fsm.current_shuttle_conf)
        self.shuttle_confirmation_pub.publish(msg)

    def publish_current_trip_cancellation(self):
        msg = Bool()
        msg.data = bool(self.fsm.current_trip_cancellation)
        self.trip_cancellation_pub.publish(msg)
    

    # -----------------------------------------------------------
    # Subscriber Callbacks — update internal FSM flags
    # -----------------------------------------------------------
    def cb_select_shuttle(self, msg): self.fsm.select_shuttle = msg.data
    def cb_booking_request(self, msg): self.fsm.booking_request = msg.data
    def cb_destination_reached(self, msg): self.fsm.destination_reached = msg.data
    def cb_door_status(self, msg): self.fsm.door_status = msg.data
    def cb_emergency_button(self, msg): self.fsm.emergency_button = msg.data
    def cb_user_inside(self, msg): self.fsm.user_inside = msg.data
    def cb_trip_cancel(self, msg): self.fsm.trip_cancel = msg.data


# -----------------------------------------------------------
# Entry Point — ROS 2 Node Execution
# -----------------------------------------------------------
def main():  # pragma: no cover
    rclpy.init()
    node = DecisionUnitNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()



# -----------------------------------------------------------
# Main Script Trigger
# -----------------------------------------------------------
if __name__ == '__main__':
    main()
