import pytest
from unittest.mock import MagicMock, patch
from std_msgs.msg import Int32, Bool
from decision_core.decision_core import DecisionUnit, STATE_CODES


# -----------------------------------------------------------
# Fixtures
# -----------------------------------------------------------
@pytest.fixture
def mock_node():
    """Mocked rclpy.Node for FSM testing."""
    node = MagicMock()
    node.state_pub = MagicMock()
    node.shuttle_confirmation_pub = MagicMock()

    # Persistent logger mock that will always be returned
    logger_mock = MagicMock()
    node.get_logger = MagicMock(return_value=logger_mock)
    node.logger = logger_mock  # easy direct access in tests
    return node


@pytest.fixture
def fsm(mock_node):
    """Fixture: DecisionUnit with mocked node and disabled diagram updates."""
    du = DecisionUnit(mock_node)
    du.update_diagram = MagicMock()  # skip Graphviz rendering
    return du


# -----------------------------------------------------------
# Core Transition Tests
# -----------------------------------------------------------

def test_initial_state_is_idle(fsm):
    """FSM should start in IDLE state."""
    assert fsm.state == 'IDLE'
    assert STATE_CODES['IDLE'] == 0


def test_t1_idle_to_driving_and_planning(fsm):
    """T1: IDLE → DRIVING_AND_PLANNING."""
    fsm.select_shuttle = 4
    fsm.booking_request = True

    with patch.object(fsm, 'publish_state') as mock_pub_state, \
         patch.object(fsm, 'publish_shuttle_conf') as mock_conf, \
         patch('time.sleep', return_value=None):

        def fake_act_T1():
            fsm.publish_state('DRIVING_AND_PLANNING')
            fsm.publish_shuttle_conf(True)
            fsm.booking_request = False
            fsm.publish_shuttle_conf(False)

        with patch.object(fsm, 'act_T1', side_effect=fake_act_T1):
            fsm.try_transition()

        assert fsm.state == 'DRIVING_AND_PLANNING'
        mock_pub_state.assert_called_with('DRIVING_AND_PLANNING')
        mock_conf.assert_any_call(True)
        mock_conf.assert_any_call(False)


def test_t2_driving_to_boarding(fsm):
    """T2: DRIVING_AND_PLANNING → BOARDING."""
    fsm.state = 'DRIVING_AND_PLANNING'
    fsm.destination_reached = True
    fsm.authorization_result = True
    fsm.user_inside = False

    with patch.object(fsm, 'publish_state') as mock_pub, \
         patch('time.sleep', return_value=None):
        fsm.try_transition()
        assert fsm.state == 'BOARDING'
        mock_pub.assert_called_with('BOARDING')


def test_t3_boarding_to_driving(fsm):
    """T3: BOARDING → DRIVING_AND_PLANNING."""
    fsm.state = 'BOARDING'
    fsm.user_inside = True
    fsm.door_status = False

    with patch.object(fsm, 'publish_state') as mock_pub:
        fsm.try_transition()
        assert fsm.state == 'DRIVING_AND_PLANNING'
        mock_pub.assert_called_with('DRIVING_AND_PLANNING')


def test_t4_driving_to_dropoff(fsm):
    """T4: DRIVING_AND_PLANNING → DROP_OFF_AND_DEBOARDING."""
    fsm.state = 'DRIVING_AND_PLANNING'
    fsm.destination_reached = True
    fsm.user_inside = True

    with patch.object(fsm, 'publish_state') as mock_pub, \
         patch('time.sleep', return_value=None):
        fsm.try_transition()
        assert fsm.state == 'DROP_OFF_AND_DEBOARDING'
        mock_pub.assert_called_with('DROP_OFF_AND_DEBOARDING')


def test_t5_dropoff_to_parking(fsm):
    """T5: DROP_OFF_AND_DEBOARDING → PARKING."""
    fsm.state = 'DROP_OFF_AND_DEBOARDING'
    fsm.door_status = False
    fsm.booking_request = False

    with patch.object(fsm, 'publish_state') as mock_pub:
        fsm.try_transition()
        assert fsm.state == 'PARKING'
        mock_pub.assert_called_with('PARKING')


def test_t6_parking_to_idle(fsm):
    """T6: PARKING → IDLE."""
    fsm.state = 'PARKING'
    fsm.destination_reached = True
    fsm.booking_request = False

    with patch.object(fsm, 'publish_state') as mock_pub, \
         patch('time.sleep', return_value=None):
        fsm.try_transition()
        assert fsm.state == 'IDLE'
        mock_pub.assert_called_with('IDLE')


def test_emergency_during_driving(fsm):
    """Emergency: DRIVING_AND_PLANNING → DROP_OFF_AND_DEBOARDING."""
    fsm.state = 'DRIVING_AND_PLANNING'
    fsm.emergency_button = True

    with patch.object(fsm, 'publish_state') as mock_pub, \
         patch('time.sleep', return_value=None):
        fsm.try_transition()
        assert fsm.state == 'DROP_OFF_AND_DEBOARDING'
        mock_pub.assert_called_with('DROP_OFF_AND_DEBOARDING')


# -----------------------------------------------------------
# Extra Transitions (T7, T8)
# -----------------------------------------------------------

def test_t7_dropoff_to_driving_on_new_booking(fsm):
    """T7: DROP_OFF_AND_DEBOARDING → DRIVING_AND_PLANNING on new booking."""
    fsm.state = 'DROP_OFF_AND_DEBOARDING'
    fsm.booking_request = True

    def fake_act_T1():
        fsm.publish_state('DRIVING_AND_PLANNING')
        fsm.publish_shuttle_conf(True)
        fsm.booking_request = False
        fsm.publish_shuttle_conf(False)

    with patch.object(fsm, 'publish_state') as mock_pub, \
         patch.object(fsm, 'act_T1', side_effect=fake_act_T1):
        fsm.try_transition()
        assert fsm.state == 'DRIVING_AND_PLANNING'
        mock_pub.assert_called_with('DRIVING_AND_PLANNING')


def test_t8_parking_to_driving_on_new_booking(fsm):
    """T8: PARKING → DRIVING_AND_PLANNING on new booking."""
    fsm.state = 'PARKING'
    fsm.booking_request = True

    def fake_act_T1():
        fsm.publish_state('DRIVING_AND_PLANNING')
        fsm.publish_shuttle_conf(True)
        fsm.booking_request = False
        fsm.publish_shuttle_conf(False)

    with patch.object(fsm, 'publish_state') as mock_pub, \
         patch.object(fsm, 'act_T1', side_effect=fake_act_T1):
        fsm.try_transition()
        assert fsm.state == 'DRIVING_AND_PLANNING'
        mock_pub.assert_called_with('DRIVING_AND_PLANNING')


# -----------------------------------------------------------
# Condition Functions
# -----------------------------------------------------------

def test_condition_functions_true_and_false(fsm):
    """Verify all condition checks work correctly."""
    fsm.select_shuttle = 4
    fsm.booking_request = True
    fsm.destination_reached = True
    fsm.authorization_result = True
    fsm.emergency_button = True
    fsm.user_inside = True
    fsm.door_status = False

    assert fsm.is_select_shuttle()
    assert fsm.is_booking_request()
    assert fsm.is_destination_reached()
    assert fsm.is_authorization_result()
    assert fsm.is_emergency_button()
    assert fsm.is_user_inside()
    assert fsm.is_door_closed()

    fsm.select_shuttle = 2
    fsm.booking_request = False
    fsm.destination_reached = False
    fsm.authorization_result = False
    fsm.emergency_button = False
    fsm.user_inside = False
    fsm.door_status = True

    assert not fsm.is_select_shuttle()
    assert not fsm.is_booking_request()
    assert not fsm.is_destination_reached()
    assert not fsm.is_authorization_result()
    assert not fsm.is_emergency_button()
    assert not fsm.is_user_inside()
    assert not fsm.is_door_closed()


def test_is_door_closed_handles_none(fsm):
    """Door closed logic treats None as closed (matches implementation)."""
    fsm.door_status = None
    assert fsm.is_door_closed() is True


# -----------------------------------------------------------
# FSM Utility / Helper Tests
# -----------------------------------------------------------

def test_publish_state_and_shuttle_conf_send_messages(fsm, mock_node):
    """Verify message contents from publish helpers."""
    fsm.publish_state('BOARDING')
    state_msg = mock_node.state_pub.publish.call_args[0][0]
    assert isinstance(state_msg, Int32)
    assert state_msg.data == STATE_CODES['BOARDING']

    fsm.publish_shuttle_conf(True)
    conf_msg = mock_node.shuttle_confirmation_pub.publish.call_args[0][0]
    assert isinstance(conf_msg, Bool)
    assert conf_msg.data is True


def test_publish_state_sets_previous_state(fsm):
    """Ensure previous_state updates correctly."""
    fsm.state = 'DRIVING_AND_PLANNING'
    fsm.previous_state = 'BOARDING'
    fsm.publish_state('PARKING')
    assert fsm.previous_state == 'DRIVING_AND_PLANNING'

def test_act_t2_t3_t4_t5_t6_publish_correct_states(fsm):
    """Call act_T2–T6 directly and verify published states."""
    with patch.object(fsm, "publish_state") as mock_pub, \
         patch("time.sleep", return_value=None):
        fsm.act_T2()
        fsm.act_T3()
        fsm.act_T4()
        fsm.act_T5()
        fsm.act_T6()
    expected = ["BOARDING", "DRIVING_AND_PLANNING", "DROP_OFF_AND_DEBOARDING", "PARKING", "IDLE"]
    actual = [args[0] for args, _ in mock_pub.call_args_list]
    assert actual == expected


# -----------------------------------------------------------
# Monitor Loop
# -----------------------------------------------------------

def test_monitor_runs_one_cycle(fsm):
    """Ensure monitor loop calls try_transition once."""
    calls = {'count': 0}
    def fake_try_transition(): calls['count'] += 1
    fsm.try_transition = fake_try_transition
    with patch('rclpy.ok', side_effect=[True, False]):
        fsm.monitor()
    assert calls['count'] == 1


def test_monitor_stops_on_exception(fsm):
    """Monitor should stop if rclpy.ok() raises."""
    with patch('rclpy.ok', side_effect=RuntimeError("stop")):
        with pytest.raises(RuntimeError):
            fsm.monitor()


# -----------------------------------------------------------
# Edge Cases
# -----------------------------------------------------------

def test_invalid_transition_does_not_crash(fsm):
    """Invalid trigger should be ignored safely."""
    fsm.state = 'BOARDING'
    fsm.booking_request = None
    fsm.try_transition()
    assert fsm.state == 'BOARDING'


def test_act_t1_breaks_when_booking_false(fsm):
    """act_T1 should stop once booking_request=False."""
    fsm.booking_request = True
    fsm.select_shuttle = 4

    with patch.object(fsm, 'publish_state') as mock_pub, \
         patch.object(fsm, 'publish_shuttle_conf') as mock_conf:
        def flip_booking():
            import time
            time.sleep(0.1)
            fsm.booking_request = False
        import threading
        t = threading.Thread(target=flip_booking)
        t.start()
        fsm.act_T1()
        t.join(timeout=1)
        mock_pub.assert_called_with('DRIVING_AND_PLANNING')
        mock_conf.assert_any_call(True)
        mock_conf.assert_any_call(False)


def test_act_t1_exits_when_booking_false_immediately(fsm):
    """act_T1 exits immediately when booking_request=False."""
    fsm.booking_request = False
    fsm.select_shuttle = 4
    with patch.object(fsm, 'publish_state') as mock_pub, \
         patch.object(fsm, 'publish_shuttle_conf') as mock_conf:
        fsm.act_T1()
        mock_pub.assert_called_with('DRIVING_AND_PLANNING')
        mock_conf.assert_any_call(True)


# -----------------------------------------------------------
# DecisionUnitNode & main() Coverage
# -----------------------------------------------------------

def test_delay_executes(monkeypatch):
    """Verify delay() simply sleeps the given seconds."""
    import decision_core.decision_core as dc
    called = {}
    def fake_sleep(sec): called["sec"] = sec
    monkeypatch.setattr(dc.time, "sleep", fake_sleep)
    dc.delay(5)
    assert called["sec"] == 5


def test_main_entry(monkeypatch):
    """Run main() safely until KeyboardInterrupt."""
    import decision_core.decision_core as dc
    called = {}

    def fake_spin(node):
        called["spun"] = True
        raise KeyboardInterrupt

    class DummyNode:
        def destroy_node(self): called["destroyed"] = True

    monkeypatch.setattr(dc, "DecisionUnitNode", lambda: DummyNode())
    monkeypatch.setattr(dc.rclpy, "init", lambda: called.setdefault("init", True))
    monkeypatch.setattr(dc.rclpy, "spin", fake_spin)
    monkeypatch.setattr(dc.rclpy, "shutdown", lambda: called.setdefault("shutdown", True))

    dc.main()
    assert all(k in called for k in ("init", "spun", "shutdown", "destroyed"))

def test_all_condition_defaults_false(fsm):
    """Ensure all condition checks return False when unset."""
    fsm.select_shuttle = None
    fsm.booking_request = None
    fsm.destination_reached = None
    fsm.authorization_result = None
    fsm.emergency_button = None
    fsm.user_inside = None
    fsm.door_status = None

    assert not fsm.is_select_shuttle()
    assert not fsm.is_booking_request()
    assert not fsm.is_destination_reached()
    assert not fsm.is_authorization_result()
    assert not fsm.is_emergency_button()
    assert not fsm.is_user_inside()
    # None door_status is treated as closed
    assert fsm.is_door_closed() is True

def test_publish_shuttle_conf_sets_current_value(fsm, mock_node):
    """Ensure current_shuttle_conf reflects last published Bool."""
    fsm.publish_shuttle_conf(True)
    assert fsm.current_shuttle_conf is True
    fsm.publish_shuttle_conf(False)
    assert fsm.current_shuttle_conf is False
def test_node_timer_callbacks(monkeypatch):
    """Simulate DecisionUnitNode timer publishers safely."""
    from decision_core.decision_core import DecisionUnitNode, Node

    # Fake Node.__init__ but preserve attributes used in DecisionUnitNode
    def fake_init(self, name=None):
        self._default_callback_group = None
        self._logger = MagicMock()  # Needed for get_logger()
        self.get_logger = lambda: self._logger

    monkeypatch.setattr(Node, "__init__", fake_init)
    monkeypatch.setattr(Node, "create_publisher", lambda *a, **kw: MagicMock())
    monkeypatch.setattr(Node, "create_subscription", lambda *a, **kw: MagicMock())
    monkeypatch.setattr(Node, "create_timer", lambda *a, **kw: MagicMock())

    node = DecisionUnitNode()
    node.state_pub = MagicMock()
    node.shuttle_confirmation_pub = MagicMock()
    node.fsm.state = "PARKING"
    node.fsm.current_shuttle_conf = True

    node.publish_current_state()
    node.publish_current_shuttle_conf()

    state_msg = node.state_pub.publish.call_args[0][0]
    conf_msg = node.shuttle_confirmation_pub.publish.call_args[0][0]
    assert state_msg.data == STATE_CODES["PARKING"]
    assert conf_msg.data is True

