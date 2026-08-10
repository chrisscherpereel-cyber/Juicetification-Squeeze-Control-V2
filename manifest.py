APP_KEY = "spc"
NAME = "Squeeze Control"
SCHEMA_VERSION = 1
MANIFEST = {
  "app_key": APP_KEY, "name": NAME, "schema_version": SCHEMA_VERSION,
  "params": {
    "target_fill_ml":  {"type":"float","default":300.0,"min":100,"max":1000,"group":"Process","label":"Fill target (mL)"},
    "within_sigma":    {"type":"float","default":2.0,"min":0.1,"max":20,"group":"Process","label":"Within-subgroup σ (mL)"},
    "spec_low":        {"type":"float","default":294.0,"group":"Process","label":"Spec low (mL)"},
    "spec_high":       {"type":"float","default":306.0,"group":"Process","label":"Spec high (mL)"},
    "subgroup_n":      {"type":"int","default":5,"choices":[2,3,4,5,6,7],"group":"Sampling","label":"Subgroup size n"},
    "n_baseline":      {"type":"int","default":24,"min":10,"max":60,"group":"Sampling","label":"Baseline subgroups"},
    "p_inspect":       {"type":"int","default":200,"min":50,"max":1000,"group":"Sampling","label":"Bottles inspected/shift"},
    "randomize_sampling": {"type":"bool","default":False,"group":"Sampling","label":"Randomize n & n_p per student (overrides the two above)"},
    "p_baseline_rate": {"type":"float","default":0.04,"min":0.0,"max":0.5,"group":"Quality","label":"In-control fraction defective"},
    "cost_recall":     {"type":"int","default":12000,"min":0,"group":"Economics","label":"$ per missed signal (Type II)"},
    "cost_linestop":   {"type":"int","default":3500,"min":0,"group":"Economics","label":"$ per false alarm (Type I)"},
    "trend_len":       {"type":"int","default":5,"min":3,"max":9,"group":"Rules","label":"Run length = a trend"},
    "completion_salt": {"type":"str","default":"squeeze-control-2026","group":"Admin","label":"Completion-code secret"},
  }
}
