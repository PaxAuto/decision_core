
import pytest
import rclpy
from unittest.mock import MagicMock, patch
from std_msgs.msg import Int32, Bool

from decision_core.decision_core import DecisionUnit, STATE_CODES



# -----------------------------------------------------------
# GLOBAL FIX: stop monitor thread from looping forever
# -----------------------------------------------------------
@pytest.fixture(autouse=True)
def disable_ros_ok(monkeypatch):
    monkeypatch.setattr(rclpy, "ok", lambda: False)


# -----------------------------------------------------------
# Fixtures
# -----------------------------------------------------------
@pytest.fixture
def mock_node():
    node = MagicMock()
    node.state_pub = MagicMock()
    node.shuttle_confirmation_pub = MagicMock()

    logger = MagicMock()
    node.get_logger = MagicMock(return_value=logger)
    return node


@pytest.fixture
def fsm(mock_node):
    du = DecisionUnit(mock_node)
    du.update_diagram = MagicMock()  # disable Graphviz rendering
    return du


# -----------------------------------------------------------
# Core FSM Transitions
# -----------------------------------------------------------

def test_initial_state_idle(fsm):
    assert fsm.state == "IDLE"
    assert STATE_CODES["IDLE"] == 0


def test_t1_idle_to_driving(fsm):
    fsm.select_shuttle = 4
    fsm.booking_request = True

    def stop_booking():
        fsm.booking_request = False

    with patch.object(fsm, "publish_state") as ps, \
         patch.object(fsm, "publish_shuttle_conf") as conf:
        conf.side_effect = lambda *_: stop_booking()
        fsm.try_transition()

    assert fsm.state == "DRIVING_AND_PLANNING"



def test_t2_driving_to_boarding(fsm):
    fsm.state = "DRIVING_AND_PLANNING"
    fsm.destination_reached = True
    fsm.user_inside = False

    with patch.object(fsm, "publish_state") as ps, \
         patch("time.sleep", return_value=None):
        fsm.try_transition()

    assert fsm.state == "BOARDING"
    ps.assert_called_with("BOARDING")


def test_t3_boarding_to_driving(fsm):
    fsm.state = "BOARDING"
    fsm.user_inside = True
    fsm.door_status = False

    with patch.object(fsm, "publish_state") as ps:
        fsm.try_transition()

    assert fsm.state == "DRIVING_AND_PLANNING"
    ps.assert_called_with("DRIVING_AND_PLANNING")


def test_t4_driving_to_dropoff(fsm):
    fsm.state = "DRIVING_AND_PLANNING"
    fsm.destination_reached = True
    fsm.user_inside = True

    with patch.object(fsm, "publish_state") as ps, \
         patch("time.sleep", return_value=None):
        fsm.try_transition()

    assert fsm.state == "DROP_OFF_AND_DEBOARDING"
    ps.assert_called_with("DROP_OFF_AND_DEBOARDING")


def test_t5_dropoff_to_parking(fsm):
    fsm.state = "DROP_OFF_AND_DEBOARDING"
    fsm.door_status = False
    fsm.booking_request = False

    with patch.object(fsm, "publish_state") as ps:
        fsm.try_transition()

    assert fsm.state == "PARKING"
    ps.assert_called_with("PARKING")


def test_t6_parking_to_idle(fsm):
    fsm.state = "PARKING"
    fsm.destination_reached = True
    fsm.booking_request = False

    with patch.object(fsm, "publish_state") as ps, \
         patch("time.sleep", return_value=None):
        fsm.try_transition()

    assert fsm.state == "IDLE"
    ps.assert_called_with("IDLE")


def test_emergency_transition(fsm):
    fsm.state = "DRIVING_AND_PLANNING"
    fsm.emergency_button = True

    with patch.object(fsm, "publish_state") as ps, \
         patch("time.sleep", return_value=None):
        fsm.try_transition()

    assert fsm.state == "DROP_OFF_AND_DEBOARDING"
    ps.assert_called_with("DROP_OFF_AND_DEBOARDING")


# -----------------------------------------------------------
# Condition Functions
# -----------------------------------------------------------

def test_condition_functions(fsm):
    fsm.select_shuttle = 4
    fsm.booking_request = True
    fsm.destination_reached = True
    fsm.emergency_button = True
    fsm.user_inside = True
    fsm.door_status = False

    assert fsm.is_select_shuttle()
    assert fsm.is_booking_request()
    assert fsm.is_destination_reached()
    assert fsm.is_emergency_button()
    assert fsm.is_user_inside()
    assert fsm.is_door_closed()


def test_door_closed_with_none(fsm):
    fsm.door_status = None
    assert fsm.is_door_closed() is True


# -----------------------------------------------------------
# Helper Publishers
# -----------------------------------------------------------

def test_publish_state_and_conf(fsm, mock_node):
    fsm.publish_state("BOARDING")
    msg = mock_node.state_pub.publish.call_args[0][0]
    assert isinstance(msg, Int32)
    assert msg.data == STATE_CODES["BOARDING"]

    fsm.publish_shuttle_conf(True)
    conf = mock_node.shuttle_confirmation_pub.publish.call_args[0][0]
    assert isinstance(conf, Bool)
    assert conf.data is True


def test_previous_state_updated(fsm):
    fsm.state = "DRIVING_AND_PLANNING"
    fsm.publish_state("PARKING")
    assert fsm.previous_state == "DRIVING_AND_PLANNING"
