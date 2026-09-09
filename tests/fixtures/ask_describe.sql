-- Synthetic values only in a disposable schema; caller rolls back everything.
INSERT INTO ask_core_pytest.metric_registry
    (metric_key, display_name, family, unit, state_class)
VALUES ('steps', 'Steps', 'activity', 'steps', 'total'),
       ('weight_lb', 'Weight', 'body', 'lb', 'measurement');

INSERT INTO analysis_pytest.panel (day, metric, value, src, code_version)
SELECT DATE '2026-09-08' - (10 - n), 'steps', n * 10, 'fixture', 'test'
  FROM generate_series(1, 10) AS n;
