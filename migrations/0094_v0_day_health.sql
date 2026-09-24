-- ADR0170: current V0 entries and native imported observations, no legacy blend.
CREATE FUNCTION public.get_v0_day(p_day date DEFAULT NULL) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE d date; t0 timestamptz; t1 timestamptz; known_at timestamptz := statement_timestamp(); health jsonb;
BEGIN
    IF coalesce(auth.jwt()->>'email','') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only' USING ERRCODE='42501';
    END IF;
    d := coalesce(p_day,(known_at AT TIME ZONE 'America/New_York' - interval '4 hours')::date);
    -- Construct each local boundary independently: a DST day need not have 24 hours.
    t0 := (d::timestamp + interval '4 hours') AT TIME ZONE 'America/New_York';
    t1 := ((d+1)::timestamp + interval '4 hours') AT TIME ZONE 'America/New_York';
    WITH current_rows AS MATERIALIZED (
        SELECT a.*, r.recorded_at AS received_at, r.source AS capture_source,
               m.display_name, m.unit AS registry_unit,
               analysis._atom_device(a.evidence_span) AS device
        FROM analysis.f_atom_rows(d,known_at) f
        JOIN __CORE__.atoms a ON a.id=f.atom_id
        JOIN __CORE__.raw_captures r ON r.capture_id=a.raw_capture_id
        JOIN __CORE__.metric_registry m ON m.metric_key=a.metric_key
        WHERE r.source='file_import' AND r.payload->>'importer'='apple_health'
    ), latest AS (
        SELECT DISTINCT ON (metric_key) * FROM current_rows
        WHERE state_class='measurement' AND kind<>'workout'
        ORDER BY metric_key,coalesce(occurred_at,upper(valid_interval),lower(valid_interval)) DESC,
                 recorded_at DESC,id
    ), candidates AS (
        SELECT p.*,m.unit,m.display_name FROM analysis.f_atom_panel(d,known_at) p
        JOIN __CORE__.metric_registry m ON m.metric_key=p.metric
        WHERE p.day=d AND EXISTS(SELECT 1 FROM current_rows a
              WHERE a.subject_day=d AND a.metric_key=p.metric AND a.kind<>'workout')
    ), daily AS (
        SELECT p.* FROM candidates p WHERE NOT EXISTS (
            SELECT 1 FROM analysis.f_atom_rows(d,known_at) f
            JOIN __CORE__.atoms a ON a.id=f.atom_id
            JOIN __CORE__.raw_captures r ON r.capture_id=a.raw_capture_id
            WHERE f.subject_day=d AND f.metric=p.metric AND f.device=p.device AND f.value IS NOT NULL
              AND (r.source IS DISTINCT FROM 'file_import'
                   OR r.payload->>'importer' IS DISTINCT FROM 'apple_health'
                   OR a.unit IS DISTINCT FROM p.unit))
    )
    SELECT jsonb_build_object(
        'latest_measurements',coalesce((SELECT jsonb_agg(jsonb_build_object(
            'metric',a.metric_key,'label',a.display_name,'value',a.value_point,
            'low',a.value_low,'high',a.value_high,'unit',a.unit,'registry_unit',a.registry_unit,
            'atom_id',a.id,'capture_id',a.raw_capture_id,'device',a.device,
            'source',a.capture_source,'estimate_method',a.estimate_method,
            'occurred_at',a.occurred_at,'valid_interval',a.valid_interval,
            'subject_day',a.subject_day,'recorded_at',a.recorded_at,'received_at',a.received_at)
            ORDER BY a.metric_key) FROM latest a),'[]'::jsonb),
        'daily_aggregates',coalesce((SELECT jsonb_agg(jsonb_build_object(
            'metric',p.metric,'label',p.display_name,'value',p.value,'unit',p.unit,
            'day',p.day,'device',p.device,'n_atoms',p.n_atoms,'n_devices',p.n_devices,
            'method',p.method,'method_version',p.method_version,'lane','atoms',
            'trace',(SELECT jsonb_build_object('atom_ids',jsonb_agg(a.id ORDER BY a.id),
                'last_event_at',max(coalesce(a.occurred_at,upper(a.valid_interval),lower(a.valid_interval))),
                'last_recorded_at',max(a.recorded_at),'last_received_at',max(r.recorded_at))
                FROM analysis.f_atom_rows(d,known_at) f
                JOIN __CORE__.atoms a ON a.id=f.atom_id
                JOIN __CORE__.raw_captures r ON r.capture_id=a.raw_capture_id
                WHERE f.subject_day=d AND f.metric=p.metric AND f.device=p.device AND f.value IS NOT NULL))
            ORDER BY p.metric) FROM daily p),'[]'::jsonb),
        'aggregation_unavailable',coalesce((SELECT jsonb_agg(DISTINCT jsonb_build_object(
            'metric',a.metric_key,'reason',CASE WHEN EXISTS(
                SELECT 1 FROM candidates p WHERE p.metric=a.metric_key)
                THEN 'selected_contributors_have_incompatible_source_or_unit'
                ELSE 'no_registered_daily_aggregate' END))
            FROM current_rows a WHERE a.subject_day=d AND a.kind<>'workout'
            AND NOT EXISTS(SELECT 1 FROM daily p WHERE p.metric=a.metric_key)),'[]'::jsonb),
        'recorded_workout_sessions',coalesce((SELECT jsonb_agg(jsonb_build_object(
            'atom_id',a.id,'capture_id',a.raw_capture_id,'active_duration',a.value_point,
            'unit',a.unit,'occurred_at',a.occurred_at,'valid_interval',a.valid_interval,
            'subject_day',a.subject_day,'recorded_at',a.recorded_at,'received_at',a.received_at,
            'device',a.device,'evidence',a.evidence_span) ORDER BY a.occurred_at,a.id)
            FROM current_rows a WHERE a.subject_day=d AND a.metric_key='workout_session_min'),'[]'::jsonb),
        'freshness',jsonb_build_object(
            'last_event_at',(SELECT max(coalesce(occurred_at,upper(valid_interval),lower(valid_interval))) FROM current_rows),
            'last_received_at',(SELECT max(received_at) FROM current_rows),
            'scope','Apple Health imports through selected subject day'),
        'history_mode','current corrections using knowledge available now'
    ) INTO health;
    RETURN jsonb_build_object('day',d,'timezone','America/New_York',
        'day_start',t0,'day_end',t1,'read_at',known_at,
        'checkins',public.get_v0_checkins(d),'meals',public.get_v0_meals(d),
        'workouts',public.get_v0_workouts(d),'health',health);
END $$;
REVOKE ALL ON FUNCTION public.get_v0_day(date) FROM PUBLIC,anon;
GRANT EXECUTE ON FUNCTION public.get_v0_day(date) TO authenticated;
