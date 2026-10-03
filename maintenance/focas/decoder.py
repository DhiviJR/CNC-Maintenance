class FocasDecoder:
    """
    Decodes raw FANUC FOCAS status structure (ODBST) into meaningful
    shop floor operational parameters and machine states.
    """

    AUT_MODES = {
        0: "MDI (Manual Data Input)",
        1: "MEM (Memory / Auto Execution)",
        2: "STANDBY",
        3: "EDIT (Program Edit)",
        4: "HND (Manual Handle MPG)",
        5: "JOG (Manual Jog Feed)",
        6: "TJOG (Teach-in Jog)",
        7: "THND (Teach-in Handle)",
        8: "INC (Incremental Feed)",
        9: "REF (Reference Zero Return)",
        10: "RMT (Remote / DNC)",
    }

    RUN_STATUS = {
        0: "STOP (Stopped)",
        1: "HOLD (Feed Hold)",
        2: "START (Cycle Active)",
        3: "MSTR (Macro Running)",
        4: "RESTART (Program Restart)",
    }

    MOTION_STATUS = {
        0: "STOP (Stationary)",
        1: "MOTION (Axes Moving)",
        2: "DWELL (G04 Dwell)",
    }

    MSTB_STATUS = {
        0: "INACTIVE",
        1: "EXECUTING (M/S/T/B Active)",
    }

    @classmethod
    def decode(cls, odbst):
        """
        Receives an ODBST ctypes Structure (or dictionary) and returns a
        rich dictionary of decoded parameters and the unified machine status.
        """
        if hasattr(odbst, 'aut'):
            tmmode_val = int(getattr(odbst, 'tmmode', 0))
            aut_val = int(odbst.aut)
            run_val = int(odbst.run)
            motion_val = int(odbst.motion)
            mstb_val = int(odbst.mstb)
            emergency_val = int(odbst.emergency)
            alarm_val = int(odbst.alarm)
            edit_val = int(odbst.edit)
        else:
            tmmode_val = int(odbst.get('tmmode', 0))
            aut_val = int(odbst.get('aut', 0))
            run_val = int(odbst.get('run', 0))
            motion_val = int(odbst.get('motion', 0))
            mstb_val = int(odbst.get('mstb', 0))
            emergency_val = int(odbst.get('emergency', 0))
            alarm_val = int(odbst.get('alarm', 0))
            edit_val = int(odbst.get('edit', 0))

        # Operational status resolution
        if emergency_val != 0:
            derived_status = 'EMERGENCY_STOP'
            status_text = 'Emergency Stop Activated'
        elif alarm_val != 0:
            derived_status = 'ALARM'
            status_text = 'CNC Alarm Active'
        elif run_val in [2, 3, 4] or motion_val in [1, 2]:
            # run_val: 2=START (cycle active), 3=MSTR (macro running), 4=RESTART
            # motion_val: 1=MOTION (axes moving), 2=DWELL (G04 program dwell)
            derived_status = 'RUNNING'
            status_text = 'Machining / Cycle Running'
        else:
            derived_status = 'IDLE'
            status_text = 'Machine Idle / Spindle Stopped'

        return {
            'raw': {
                'tmmode': tmmode_val,
                'aut': aut_val,
                'run': run_val,
                'motion': motion_val,
                'mstb': mstb_val,
                'emergency': emergency_val,
                'alarm': alarm_val,
                'edit': edit_val,
            },
            'derived_status': derived_status,
            'status_text': status_text,
            'aut_mode_name': cls.AUT_MODES.get(aut_val, f"Mode {aut_val}"),
            'run_status_name': cls.RUN_STATUS.get(run_val, f"Run {run_val}"),
            'motion_status_name': cls.MOTION_STATUS.get(motion_val, f"Motion {motion_val}"),
            'mstb_status_name': cls.MSTB_STATUS.get(mstb_val, f"MSTB {mstb_val}"),
            'is_emergency': bool(emergency_val != 0),
            'is_alarm': bool(alarm_val != 0),
            'is_running': derived_status == 'RUNNING',
            'is_idle': derived_status == 'IDLE',
        }
