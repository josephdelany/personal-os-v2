-- Durable source dispatch reuses 0072 meters; no source identity can read core.
CREATE TABLE __OPS__.reference_requests (
    request_id uuid PRIMARY KEY,
    source text NOT NULL CHECK(source IN ('usda_foundation','usda_branded','off_search','off_product')),
    payload_sha256 text NOT NULL CHECK(payload_sha256 ~ '^[a-f0-9]{64}$'),
    egress_id uuid NOT NULL UNIQUE REFERENCES __OPS__.egress_log(egress_id),
    reserved_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    valid_before timestamptz NOT NULL
);
CREATE TABLE __OPS__.reference_results (
    request_id uuid PRIMARY KEY REFERENCES __OPS__.reference_requests(request_id),
    response_sha256 text CHECK(response_sha256 ~ '^[a-f0-9]{64}$'),
    outcome text NOT NULL DEFAULT 'settled' CHECK(outcome IN ('settled','uncertain')),
    provider_status integer CHECK(provider_status BETWEEN 300 AND 599),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK((outcome='settled' AND response_sha256 IS NOT NULL) OR
          (outcome='uncertain' AND response_sha256 IS NULL AND provider_status IS NULL))
);
CREATE TRIGGER reference_requests_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
    ON __OPS__.reference_requests FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();
CREATE TRIGGER reference_results_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
    ON __OPS__.reference_results FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();
REVOKE ALL ON __OPS__.reference_requests,__OPS__.reference_results FROM PUBLIC,anon,authenticated,service_role,reference_egress;
GRANT SELECT ON __OPS__.reference_requests,__OPS__.reference_results TO service_role,reference_egress;

ALTER TABLE __OPS__.rate_limit_cooldowns DROP CONSTRAINT rate_limit_cooldowns_reason_check;
ALTER TABLE __OPS__.rate_limit_cooldowns ADD CONSTRAINT rate_limit_cooldowns_reason_check
    CHECK(reason IN ('provider_429','quota_exhausted','dispatch_uncertain'));

CREATE FUNCTION public.reserve_reference_call(p_request_id uuid,p_source text,p_sha256 text,p_bytes integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE v_meter text; v_limit integer; v_window interval; v_now timestamptz;
    v_log uuid; v_count bigint; v_blocked timestamptz; v_reason text; v_orphan record;
BEGIN
    IF p_request_id IS NULL OR p_source IS NULL OR p_source NOT IN
        ('usda_foundation','usda_branded','off_search','off_product')
        OR p_sha256 IS NULL OR p_sha256 !~ '^[a-f0-9]{64}$'
        OR p_bytes IS NULL OR p_bytes < 1 OR p_bytes > 4096 THEN
        RAISE EXCEPTION 'invalid reference request';
    END IF;
    IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'READ COMMITTED required';
    END IF;
    PERFORM pg_advisory_xact_lock(791554);
    v_now := clock_timestamp();
    IF EXISTS(SELECT 1 FROM __OPS__.reference_requests WHERE request_id=p_request_id) THEN
        RETURN jsonb_build_object('allowed',false,'reason','request_already_reserved');
    END IF;
    v_meter := CASE WHEN p_source LIKE 'usda_%' THEN 'usda' ELSE p_source END;
    v_limit := CASE v_meter WHEN 'usda' THEN 900 WHEN 'off_search' THEN 10 ELSE 15 END;
    v_window := CASE WHEN v_meter='usda' THEN interval '60 minutes' ELSE interval '1 minute' END;
    -- The dispatcher holds this same session lock across HTTP. Once another
    -- session owns it, an unsettled predecessor has lost its owner. Its provider
    -- outcome is unknown, never fabricated as a429 or success. Conservatively
    -- start USDA's full cooldown at this observation time, not reservation time.
    FOR v_orphan IN SELECT r.request_id,r.egress_id FROM __OPS__.reference_requests r
        WHERE (CASE WHEN r.source LIKE 'usda_%' THEN 'usda' ELSE r.source END)=v_meter
        AND NOT EXISTS(SELECT 1 FROM __OPS__.reference_results s WHERE s.request_id=r.request_id)
    LOOP
        INSERT INTO __OPS__.reference_results(request_id,outcome,recorded_at)
        VALUES(v_orphan.request_id,'uncertain',v_now);
        UPDATE __OPS__.egress_log SET detail=detail||jsonb_build_object('state','uncertain')
            WHERE egress_id=v_orphan.egress_id;
        IF v_meter='usda' THEN
            INSERT INTO __OPS__.rate_limit_cooldowns(meter,blocked_until,reason,set_at)
            VALUES('usda',v_now+interval '60 minutes','dispatch_uncertain',v_now)
            ON CONFLICT(meter) DO UPDATE SET
                blocked_until=greatest(__OPS__.rate_limit_cooldowns.blocked_until,EXCLUDED.blocked_until),
                reason='dispatch_uncertain',set_at=EXCLUDED.set_at;
        END IF;
    END LOOP;
    SELECT blocked_until,reason INTO v_blocked,v_reason FROM __OPS__.rate_limit_cooldowns WHERE meter=v_meter;
    IF v_blocked > v_now THEN
        RETURN jsonb_build_object('allowed',false,'reason',
            CASE WHEN v_reason='dispatch_uncertain' THEN 'source_uncertain' ELSE 'source_cooldown' END);
    END IF;
    SELECT count(*) INTO v_count FROM __OPS__.rate_limit_events
        -- A permit can wait60s before sending. Include that lifetime so delayed
        -- sends cannot escape the provider's rolling window.
        WHERE meter=v_meter AND issued_at > v_now-v_window-interval '60 seconds';
    IF v_count >= v_limit THEN
        RETURN jsonb_build_object('allowed',false,'reason','source_quota');
    END IF;
    INSERT INTO __OPS__.rate_limit_events(meter,issued_at) VALUES(v_meter,v_now);
    INSERT INTO __OPS__.egress_log(destination,purpose,request_bytes,detail)
    VALUES(CASE WHEN v_meter='usda' THEN 'api.nal.usda.gov' ELSE 'world.openfoodfacts.org' END,
           'reference:'||p_source,p_bytes,jsonb_build_object('state','reserved','payload_sha256',p_sha256))
    RETURNING egress_id INTO v_log;
    INSERT INTO __OPS__.reference_requests(request_id,source,payload_sha256,egress_id,reserved_at,valid_before)
    VALUES(p_request_id,p_source,p_sha256,v_log,v_now,v_now+interval '60 seconds');
    RETURN jsonb_build_object('allowed',true,'request_id',p_request_id,'egress_id',v_log,
        'reserved_at',v_now,'valid_before',v_now+interval '60 seconds');
END $$;
REVOKE ALL ON FUNCTION public.reserve_reference_call(uuid,text,text,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.reserve_reference_call(uuid,text,text,integer) TO reference_egress;

CREATE FUNCTION public.settle_reference_call(p_request_id uuid,p_sha256 text,p_bytes integer,p_status integer DEFAULT NULL)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE v_request __OPS__.reference_requests; v_old __OPS__.reference_results;
BEGIN
    IF p_sha256 IS NULL OR p_sha256 !~ '^[a-f0-9]{64}$' OR p_bytes IS NULL OR p_bytes < 1
        OR p_bytes > 4194304 OR (p_status IS NOT NULL AND p_status NOT BETWEEN 300 AND 599) THEN
        RAISE EXCEPTION 'invalid reference settlement';
    END IF;
    PERFORM pg_advisory_xact_lock(791554);
    SELECT * INTO v_request FROM __OPS__.reference_requests WHERE request_id=p_request_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'reference reservation required'; END IF;
    SELECT * INTO v_old FROM __OPS__.reference_results WHERE request_id=p_request_id;
    IF FOUND THEN
        IF v_old.response_sha256 IS DISTINCT FROM p_sha256 OR v_old.provider_status IS DISTINCT FROM p_status THEN
            RAISE EXCEPTION 'reference settlement identity reused';
        END IF;
        RETURN;
    END IF;
    INSERT INTO __OPS__.reference_results(request_id,response_sha256,provider_status)
    VALUES(p_request_id,p_sha256,p_status);
    UPDATE __OPS__.egress_log SET response_bytes=p_bytes,
        detail=detail||jsonb_build_object('state','settled','response_sha256',p_sha256,'provider_status',p_status)
        WHERE egress_id=v_request.egress_id;
    IF p_status=429 AND v_request.source LIKE 'usda_%' THEN
        INSERT INTO __OPS__.rate_limit_cooldowns(meter,blocked_until,reason,set_at)
        VALUES('usda',clock_timestamp()+interval '60 minutes','provider_429',clock_timestamp())
        ON CONFLICT(meter) DO UPDATE SET
            blocked_until=greatest(__OPS__.rate_limit_cooldowns.blocked_until,EXCLUDED.blocked_until),
            reason='provider_429',set_at=EXCLUDED.set_at;
    END IF;
END $$;
REVOKE ALL ON FUNCTION public.settle_reference_call(uuid,text,integer,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.settle_reference_call(uuid,text,integer,integer) TO reference_egress;
