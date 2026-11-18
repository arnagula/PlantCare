"""Load the bundled, trusted demonstration model for simulated telemetry."""
from functools import lru_cache
from pathlib import Path

from .analysis import valid_metric

FEATURES = ('temperature_c', 'humidity_pct', 'light_lux')
ISSUES = ('too_wet', 'thirsty', 'too_hot', 'too_cold', 'low_humidity', 'low_light')


class IssueModel:
    def __init__(self, estimator):
        self.estimator = estimator

    def predict_issues(self, packet):
        soil = packet['soil']
        values = [valid_metric(packet, key) for key in FEATURES]
        values.append(soil['pct'] if soil['valid'] and soil['calibrated'] else None)
        if any(value is None for value in values):
            return []
        return [issue for issue, flag in zip(ISSUES, self.estimator.predict([values])[0]) if flag]


@lru_cache(maxsize=1)
def load_demo_model():
    import joblib
    path = Path(__file__).resolve().parents[1] / 'ml' / 'synthetic_example_model.joblib'
    return IssueModel(joblib.load(path))
