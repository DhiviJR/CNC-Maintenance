from .decoder import FocasDecoder


class CNCSimulator:
    """
    Simulates a FANUC CNC controller's FOCAS telemetry output
    for testing, offline development, and demonstration purposes.
    """

    PRESETS = {
        'RUNNING': {
            'aut': 1,        # MEM
            'run': 2,        # START
            'motion': 1,     # Motion
            'mstb': 0,
            'emergency': 0,
            'alarm': 0,
            'edit': 0,
            'alarm_code': None,
            'alarm_msg': None,
        },
        'IDLE': {
            'aut': 1,
            'run': 0,        # STOP
            'motion': 0,     # Stopped
            'mstb': 0,
            'emergency': 0,
            'alarm': 0,
            'edit': 0,
            'alarm_code': None,
            'alarm_msg': None,
        },
        'ALARM': {
            'aut': 1,
            'run': 0,
            'motion': 0,
            'mstb': 0,
            'emergency': 0,
            'alarm': 1,       # ALARM ACTIVE
            'edit': 0,
            'alarm_code': 'DS0300 (APC) AXIS NEED ZRN',
            'alarm_msg': 'Servo reference return required on X/Z axis.',
        },
        'EMERGENCY_STOP': {
            'aut': 1,
            'run': 0,
            'motion': 0,
            'mstb': 0,
            'emergency': 1,   # EMERGENCY STOP
            'alarm': 0,
            'edit': 0,
            'alarm_code': 'EMG-01',
            'alarm_msg': 'Operator Emergency Stop Button Pressed on Machine Panel.',
        },
    }

    def __init__(self, machine_code="CNC-01", initial_state="RUNNING"):
        self.machine_code = machine_code
        self.current_state = initial_state
        self.custom_alarm_code = None
        self.custom_alarm_msg = None

    def set_state(self, state, alarm_code=None, alarm_msg=None):
        if state not in self.PRESETS:
            raise ValueError(f"Unknown preset state: {state}. Valid: {list(self.PRESETS.keys())}")
        self.current_state = state
        self.custom_alarm_code = alarm_code
        self.custom_alarm_msg = alarm_msg

    def get_telemetry(self):
        raw = dict(self.PRESETS[self.current_state])
        if self.custom_alarm_code:
            raw['alarm_code'] = self.custom_alarm_code
        if self.custom_alarm_msg:
            raw['alarm_msg'] = self.custom_alarm_msg

        decoded = FocasDecoder.decode(raw)
        decoded['alarm_code'] = raw['alarm_code']
        decoded['alarm_msg'] = raw['alarm_msg']
        return decoded
