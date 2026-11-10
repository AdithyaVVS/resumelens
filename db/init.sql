-- Runs once, the first time the database container starts with an empty volume.
-- One database per service, plus a separate empty one for each service's tests.
CREATE DATABASE resumelens_auth;
CREATE DATABASE resumelens_resume;
CREATE DATABASE resumelens_analysis;
CREATE DATABASE resumelens_jobs;
CREATE DATABASE resumelens_auth_test;
CREATE DATABASE resumelens_resume_test;
CREATE DATABASE resumelens_analysis_test;
CREATE DATABASE resumelens_jobs_test;
