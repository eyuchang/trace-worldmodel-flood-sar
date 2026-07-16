# S1-S5 UI Event Contract

The browser is not a privileged state editor. Every control produces one immutable event.

| UI action | Event type | Level | Primary state affected |
|---|---|---|---|
| Apply sensor/noise controls | `SET_S1_PARAMETERS` | S1 | model and observation parameters |
| Apply rain/water controls | `SET_S2_PARAMETERS` | S2 | flood dynamics and validity horizons |
| Apply allocation weights | `SET_S3_PARAMETERS` | S3 | practical-planning objective |
| Add group | `ADD_GROUP` | S3 | truth and controller demand state |
| Add asset | `ADD_ASSET` | S3 | truth and controller fleet state |
| Inject disruption | `INJECT_SHOCK` | S4 | truth, sensors, communications, demand, or resources |
| Apply reconnaissance controls | `SET_S5_PARAMETERS` | S5 | sensing cost/quality/VOI parameters |
| Request route survey | `REQUEST_SURVEY` | S5 | pending reconnaissance request |
| Toggle commander approval | `COMMANDER_AUTHORITY` | CORE | external authority boundary |

All calls use:

```json
{
  "event_type": "SET_S1_PARAMETERS",
  "scenario_level": "S1",
  "visibility": "both",
  "payload": {
    "sensor_noise": 0.25,
    "ood_severity": 0.5
  }
}
```

The backend validates the event, appends it to the event log, invokes the reducer, and broadcasts
a new snapshot. No UI code receives a Python object reference.
