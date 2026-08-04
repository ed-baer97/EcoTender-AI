-- EcoTender AI bootstrap
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE SCHEMA IF NOT EXISTS tender;
CREATE SCHEMA IF NOT EXISTS market;
CREATE SCHEMA IF NOT EXISTS geo;
CREATE SCHEMA IF NOT EXISTS risk;
CREATE SCHEMA IF NOT EXISTS ingest;
CREATE SCHEMA IF NOT EXISTS iam;

COMMENT ON SCHEMA tender IS 'Procurement bounded context';
COMMENT ON SCHEMA market IS 'Market prices bounded context';
COMMENT ON SCHEMA geo IS 'Spatial / eco layers';
COMMENT ON SCHEMA risk IS 'Risk assessments & model registry';
COMMENT ON SCHEMA ingest IS 'Crawl jobs & raw documents';
COMMENT ON SCHEMA iam IS 'Users, roles, audit';
