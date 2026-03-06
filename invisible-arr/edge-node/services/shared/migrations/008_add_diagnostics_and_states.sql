-- 008: Add job_diagnostics table for download pipeline v2

CREATE TABLE IF NOT EXISTS job_diagnostics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES jobs(id),
    category VARCHAR(50) NOT NULL,
    details_json JSON,
    auto_fix_action VARCHAR(200),
    resolved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_job_diagnostics_job_id ON job_diagnostics(job_id);
CREATE INDEX IF NOT EXISTS idx_job_diagnostics_category ON job_diagnostics(category);
