-- ADR0171: private immutable source observations, not canonical transactions.
CREATE TABLE __CORE__.v0_card_files (
    file_id uuid PRIMARY KEY REFERENCES __CORE__.raw_captures(capture_id),
    account_id uuid NOT NULL,
    source_sha256 text NOT NULL CHECK(source_sha256 ~ '^[a-f0-9]{64}$'),
    content_digest text NOT NULL CHECK(content_digest ~ '^[a-f0-9]{64}$'),
    mapping_version text NOT NULL,
    equivalent_to uuid REFERENCES __CORE__.v0_card_files(file_id),
    receipt jsonb NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE(account_id, source_sha256),
    UNIQUE(file_id, account_id)
);
CREATE INDEX v0_card_content ON __CORE__.v0_card_files(account_id, content_digest);

CREATE TABLE __CORE__.v0_card_rows (
    row_id uuid PRIMARY KEY,
    file_id uuid NOT NULL,
    account_id uuid NOT NULL,
    source_row integer NOT NULL CHECK(source_row > 0),
    source_record jsonb NOT NULL CHECK(jsonb_typeof(source_record)='object'),
    row_digest text NOT NULL CHECK(row_digest ~ '^[a-f0-9]{64}$'),
    occurred_on date NOT NULL CHECK(isfinite(occurred_on)),
    posted_on date CHECK(isfinite(posted_on)),
    amount numeric(15,2) NOT NULL CHECK(abs(amount)<=1000000000000),
    currency text NOT NULL CHECK(currency='USD'),
    source_type text NOT NULL,
    source_category text NOT NULL,
    description text NOT NULL,
    memo text NOT NULL,
    initial_status text NOT NULL CHECK(initial_status IN ('distinct','needs_review','equivalent_file')),
    equivalent_row_id uuid,
    candidate_ids uuid[] NOT NULL DEFAULT '{}',
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE(file_id, source_row),
    UNIQUE(row_id, account_id),
    FOREIGN KEY(file_id, account_id) REFERENCES __CORE__.v0_card_files(file_id, account_id),
    FOREIGN KEY(equivalent_row_id, account_id) REFERENCES __CORE__.v0_card_rows(row_id, account_id),
    CHECK((initial_status='equivalent_file')=(equivalent_row_id IS NOT NULL)),
    CHECK((initial_status='needs_review')=(cardinality(candidate_ids)>0))
);
CREATE INDEX v0_card_rows_account_day ON __CORE__.v0_card_rows(account_id, occurred_on);
ALTER TABLE __CORE__.v0_card_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE __CORE__.v0_card_rows ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON __CORE__.v0_card_files, __CORE__.v0_card_rows FROM PUBLIC,anon,authenticated,service_role;
-- Local private importer uses the existing privileged ETL connection. No public import RPC.
CREATE TRIGGER v0_card_files_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
    ON __CORE__.v0_card_files FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();
CREATE TRIGGER v0_card_rows_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
    ON __CORE__.v0_card_rows FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();
CREATE TRIGGER v0_card_files_recorded_at BEFORE INSERT ON __CORE__.v0_card_files
    FOR EACH ROW EXECUTE FUNCTION __CORE__.force_recorded_at();
CREATE TRIGGER v0_card_rows_recorded_at BEFORE INSERT ON __CORE__.v0_card_rows
    FOR EACH ROW EXECUTE FUNCTION __CORE__.force_recorded_at();

CREATE TABLE __CORE__.v0_card_decisions (
    decision_id uuid PRIMARY KEY,
    row_id uuid NOT NULL REFERENCES __CORE__.v0_card_rows(row_id),
    supersedes uuid UNIQUE REFERENCES __CORE__.v0_card_decisions(decision_id),
    action text NOT NULL CHECK(action IN ('distinct','link')),
    target_id uuid REFERENCES __CORE__.v0_card_rows(row_id),
    request jsonb NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK((action='link')=(target_id IS NOT NULL)),
    CHECK(row_id IS DISTINCT FROM target_id)
);
CREATE INDEX v0_card_decision_row ON __CORE__.v0_card_decisions(row_id);
ALTER TABLE __CORE__.v0_card_decisions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON __CORE__.v0_card_decisions FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER v0_card_decisions_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
    ON __CORE__.v0_card_decisions FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();
CREATE TRIGGER v0_card_decisions_recorded_at BEFORE INSERT ON __CORE__.v0_card_decisions
    FOR EACH ROW EXECUTE FUNCTION __CORE__.force_recorded_at();

CREATE VIEW __CORE__.v0_card_current AS
SELECT r.*,d.decision_id,d.target_id,
    CASE WHEN d.action='link' THEN 'linked'
         WHEN d.action='distinct' THEN 'distinct' ELSE r.initial_status END AS current_status
FROM __CORE__.v0_card_rows r
LEFT JOIN __CORE__.v0_card_decisions d ON d.row_id=r.row_id
    AND NOT EXISTS(SELECT 1 FROM __CORE__.v0_card_decisions n WHERE n.supersedes=d.decision_id);
REVOKE ALL ON __CORE__.v0_card_current FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION public.review_v0_card_row(p_request jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE did uuid; rid uuid; tid uuid; previous uuid; verb text; keys text[];
        saved __CORE__.v0_card_decisions; observation __CORE__.v0_card_current;
        target __CORE__.v0_card_current;
BEGIN
    IF coalesce(auth.jwt()->>'email','') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only' USING ERRCODE='42501';
    END IF;
    IF jsonb_typeof(p_request) IS DISTINCT FROM 'object' THEN
        RAISE EXCEPTION 'review object required';
    END IF;
    SELECT array_agg(k ORDER BY k) INTO keys FROM jsonb_object_keys(p_request) k;
    IF keys IS DISTINCT FROM ARRAY['action','decision_id','row_id','supersedes','target_id'] THEN
        RAISE EXCEPTION 'invalid review fields';
    END IF;
    did := (p_request->>'decision_id')::uuid; rid := (p_request->>'row_id')::uuid;
    tid := (p_request->>'target_id')::uuid; previous := (p_request->>'supersedes')::uuid;
    verb := p_request->>'action';
    IF did IS NULL OR rid IS NULL OR verb IS NULL OR verb NOT IN ('link','distinct')
        OR (verb='link') IS DISTINCT FROM (tid IS NOT NULL) THEN
        RAISE EXCEPTION 'invalid review decision';
    END IF;
    IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'card review requires READ COMMITTED isolation';
    END IF;
    PERFORM pg_advisory_xact_lock(9171001);
    SELECT * INTO saved FROM __CORE__.v0_card_decisions WHERE decision_id=did;
    IF FOUND THEN
        IF saved.request IS DISTINCT FROM p_request THEN
            RAISE EXCEPTION 'decision identity reused with changed contents';
        END IF;
        RETURN jsonb_build_object('status','saved','decision_id',did,'row_id',rid,'recorded_at',saved.recorded_at);
    END IF;
    SELECT * INTO observation FROM __CORE__.v0_card_current WHERE row_id=rid;
    IF NOT FOUND OR observation.initial_status='equivalent_file' THEN
        RAISE EXCEPTION 'review original source observation';
    END IF;
    IF observation.decision_id IS DISTINCT FROM previous THEN
        RAISE EXCEPTION 'stale review; reload current decision';
    END IF;
    IF verb='link' THEN
        SELECT * INTO target FROM __CORE__.v0_card_current WHERE row_id=tid;
        IF NOT FOUND OR tid=rid OR target.account_id<>observation.account_id
            OR target.current_status<>'distinct' THEN
            RAISE EXCEPTION 'link target must be a distinct observation in the same account';
        END IF;
        IF EXISTS(SELECT 1 FROM __CORE__.v0_card_current WHERE target_id=rid AND current_status='linked') THEN
            RAISE EXCEPTION 'resolve incoming links before linking this observation';
        END IF;
    END IF;
    INSERT INTO __CORE__.v0_card_decisions(decision_id,row_id,supersedes,action,target_id,request)
        VALUES(did,rid,previous,verb,tid,p_request) RETURNING * INTO saved;
    RETURN jsonb_build_object('status','saved','decision_id',did,'row_id',rid,'recorded_at',saved.recorded_at);
END $$;
REVOKE ALL ON FUNCTION public.review_v0_card_row(jsonb) FROM PUBLIC,anon,service_role;
GRANT EXECUTE ON FUNCTION public.review_v0_card_row(jsonb) TO authenticated;

-- RULE12/14: owner readback stores its exact computed subtotals and input IDs.
CREATE TABLE __CORE__.v0_card_reads (
    read_id uuid PRIMARY KEY,
    account_id uuid NOT NULL,
    period_start date NOT NULL,
    period_end date NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    result jsonb NOT NULL
);
ALTER TABLE __CORE__.v0_card_reads ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON __CORE__.v0_card_reads FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER v0_card_reads_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
    ON __CORE__.v0_card_reads FOR EACH STATEMENT EXECUTE FUNCTION __CORE__.reject_mutation();
CREATE TRIGGER v0_card_reads_recorded_at BEFORE INSERT ON __CORE__.v0_card_reads
    FOR EACH ROW EXECUTE FUNCTION __CORE__.force_recorded_at();

CREATE FUNCTION public.get_v0_card_activity(p_account uuid,p_start date,p_end date) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE answer jsonb; identity uuid := gen_random_uuid();
BEGIN
    IF coalesce(auth.jwt()->>'email','') <> 'joseph.delany21@gmail.com' THEN
        RAISE EXCEPTION 'owner only' USING ERRCODE='42501';
    END IF;
    IF p_account IS NULL OR p_start IS NULL OR p_end IS NULL OR NOT isfinite(p_start)
        OR NOT isfinite(p_end) OR p_end<p_start OR p_end-p_start>365 THEN
        RAISE EXCEPTION 'account and inclusive date range of at most 366 days required';
    END IF;
    -- One SQL snapshot for entries, current decisions, source IDs and arithmetic.
    WITH selected AS MATERIALIZED (
        SELECT * FROM __CORE__.v0_card_current
        WHERE account_id=p_account AND occurred_on BETWEEN p_start AND p_end
            AND initial_status<>'equivalent_file'
    ), subtotals AS (
        SELECT source_type,currency,sum(amount) AS signed_amount,
            'observed'::text AS lane,'imported_statement'::text AS provenance,
            'sum'::text AS method,'v0_card_activity_v1'::text AS code_version,
            array_agg(row_id ORDER BY row_id) AS source_row_ids,
            count(*) AS included_rows
        FROM selected WHERE current_status='distinct' GROUP BY source_type,currency
    ) SELECT jsonb_build_object(
        'read_id',identity,'account_id',p_account,'code_version','v0_card_activity_v1',
        'kind','imported_card_activity','history_basis','current_owner_decisions',
        'date_precision','day','period_start',p_start,'period_end',p_end,
        'computed_at',clock_timestamp(),
        'entries',coalesce((SELECT jsonb_agg(jsonb_build_object(
            'row_id',row_id,'capture_id',file_id,'source_row',source_row,
            'occurred_on',occurred_on,'posted_on',posted_on,'received_at',recorded_at,
            'amount',amount,'currency',currency,'source_type',source_type,
            'source_category',source_category,'description',description,'memo',memo,
            'source_record',source_record,'status',current_status,'candidate_ids',candidate_ids,
            'decision_id',decision_id,'linked_to',target_id,'lane','observed',
            'provenance','imported_statement') ORDER BY occurred_on,recorded_at,source_row)
            FROM selected),'[]'::jsonb),
        'source_subtotals',coalesce((SELECT jsonb_agg(to_jsonb(s) ORDER BY source_type,currency)
            FROM subtotals s),'[]'::jsonb),
        'subtotal_semantics','signed source amounts grouped by original Type; not reconciled spending or income',
        'unresolved_row_ids',coalesce((SELECT jsonb_agg(row_id ORDER BY row_id)
            FROM selected WHERE current_status='needs_review'),'[]'::jsonb),
        'coverage',CASE WHEN NOT EXISTS(SELECT 1 FROM selected) THEN 'missing'
            WHEN EXISTS(SELECT 1 FROM selected WHERE current_status='needs_review') THEN 'incomplete'
            ELSE 'imported_observations_only' END,
        'last_received_at',(SELECT max(recorded_at) FROM selected)
    ) INTO answer;
    INSERT INTO __CORE__.v0_card_reads(read_id,account_id,period_start,period_end,result)
        VALUES(identity,p_account,p_start,p_end,answer);
    RETURN answer;
END $$;
REVOKE ALL ON FUNCTION public.get_v0_card_activity(uuid,date,date) FROM PUBLIC,anon,service_role;
GRANT EXECUTE ON FUNCTION public.get_v0_card_activity(uuid,date,date) TO authenticated;
