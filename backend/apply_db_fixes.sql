-- ==========================================
-- 1. FIX VECTOR DIMENSIONS (768 for Gemini)
-- ==========================================
-- Note: Supabase pg_dump sometimes exports vectors as USER-DEFINED.
-- If these tables are already created, run these ALTERs to enforce 768 dims.
ALTER TABLE public.validations 
ALTER COLUMN idea_embedding TYPE vector(768);

ALTER TABLE public.rag_chunks 
ALTER COLUMN embedding TYPE vector(768);

-- ==========================================
-- 2. FIX CASCADING DELETES
-- ==========================================
ALTER TABLE public.funding_intelligence
DROP CONSTRAINT IF EXISTS funding_intelligence_validation_id_fkey,
ADD CONSTRAINT funding_intelligence_validation_id_fkey FOREIGN KEY (validation_id) REFERENCES public.validations(id) ON DELETE CASCADE;

ALTER TABLE public.jobs_intelligence
DROP CONSTRAINT IF EXISTS jobs_intelligence_validation_id_fkey,
ADD CONSTRAINT jobs_intelligence_validation_id_fkey FOREIGN KEY (validation_id) REFERENCES public.validations(id) ON DELETE CASCADE;

ALTER TABLE public.patent_intelligence
DROP CONSTRAINT IF EXISTS patent_intelligence_validation_id_fkey,
ADD CONSTRAINT patent_intelligence_validation_id_fkey FOREIGN KEY (validation_id) REFERENCES public.validations(id) ON DELETE CASCADE;

ALTER TABLE public.pricing_intelligence
DROP CONSTRAINT IF EXISTS pricing_intelligence_validation_id_fkey,
ADD CONSTRAINT pricing_intelligence_validation_id_fkey FOREIGN KEY (validation_id) REFERENCES public.validations(id) ON DELETE CASCADE;

ALTER TABLE public.rag_chunks
DROP CONSTRAINT IF EXISTS rag_chunks_validation_id_fkey,
ADD CONSTRAINT rag_chunks_validation_id_fkey FOREIGN KEY (validation_id) REFERENCES public.validations(id) ON DELETE CASCADE;

ALTER TABLE public.report_versions
DROP CONSTRAINT IF EXISTS report_versions_validation_id_fkey,
ADD CONSTRAINT report_versions_validation_id_fkey FOREIGN KEY (validation_id) REFERENCES public.validations(id) ON DELETE CASCADE;

ALTER TABLE public.social_sentiment
DROP CONSTRAINT IF EXISTS social_sentiment_validation_id_fkey,
ADD CONSTRAINT social_sentiment_validation_id_fkey FOREIGN KEY (validation_id) REFERENCES public.validations(id) ON DELETE CASCADE;

ALTER TABLE public.traffic_intelligence
DROP CONSTRAINT IF EXISTS traffic_intelligence_validation_id_fkey,
ADD CONSTRAINT traffic_intelligence_validation_id_fkey FOREIGN KEY (validation_id) REFERENCES public.validations(id) ON DELETE CASCADE;

ALTER TABLE public.workspace_members
DROP CONSTRAINT IF EXISTS workspace_members_workspace_id_fkey,
ADD CONSTRAINT workspace_members_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE,
DROP CONSTRAINT IF EXISTS workspace_members_user_id_fkey,
ADD CONSTRAINT workspace_members_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

ALTER TABLE public.workspaces
DROP CONSTRAINT IF EXISTS workspaces_created_by_fkey,
ADD CONSTRAINT workspaces_created_by_fkey FOREIGN KEY (created_by) REFERENCES auth.users(id) ON DELETE CASCADE;

-- ==========================================
-- 3. ADD PERFORMANCE INDEXES FOR FOREIGN KEYS
-- ==========================================
CREATE INDEX IF NOT EXISTS idx_funding_validation_id ON public.funding_intelligence(validation_id);
CREATE INDEX IF NOT EXISTS idx_pricing_validation_id ON public.pricing_intelligence(validation_id);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_validation_id ON public.rag_chunks(validation_id);
CREATE INDEX IF NOT EXISTS idx_report_versions_validation_id ON public.report_versions(validation_id);
CREATE INDEX IF NOT EXISTS idx_social_sentiment_validation_id ON public.social_sentiment(validation_id);
CREATE INDEX IF NOT EXISTS idx_workspace_members_workspace_id ON public.workspace_members(workspace_id);
CREATE INDEX IF NOT EXISTS idx_workspace_members_user_id ON public.workspace_members(user_id);
CREATE INDEX IF NOT EXISTS idx_workspaces_created_by ON public.workspaces(created_by);
CREATE INDEX IF NOT EXISTS idx_patent_validation_id ON public.patent_intelligence(validation_id);
CREATE INDEX IF NOT EXISTS idx_jobs_validation_id ON public.jobs_intelligence(validation_id);
CREATE INDEX IF NOT EXISTS idx_traffic_validation_id ON public.traffic_intelligence(validation_id);
