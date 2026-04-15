CREATE OR REPLACE FUNCTION notify_run_queued() RETURNS trigger AS $$
BEGIN
    IF NEW.status = 'queued' AND (TG_OP = 'INSERT' OR OLD.status IS DISTINCT FROM NEW.status) THEN
        PERFORM pg_notify('run_queued', NEW.id::text);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_run_queued
    AFTER INSERT OR UPDATE ON runs
    FOR EACH ROW EXECUTE FUNCTION notify_run_queued();

CREATE OR REPLACE FUNCTION notify_run_completed() RETURNS trigger AS $$
BEGIN
    IF NEW.status IN ('done', 'failed')
       AND (OLD.status IS NULL OR OLD.status IS DISTINCT FROM NEW.status) THEN
        PERFORM pg_notify('run_status_changed',
            json_build_object('run_id', NEW.id, 'status', NEW.status)::text);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_run_completed
    AFTER UPDATE ON runs
    FOR EACH ROW EXECUTE FUNCTION notify_run_completed();
