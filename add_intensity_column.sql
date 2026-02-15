-- Add intensity column for calorie estimation (if migration was not run).
-- Run this with your PostgreSQL client if you get 500s on /workouts or /analytics.
-- Example: psql $DATABASE_URL -f add_intensity_column.sql

ALTER TABLE workouts ADD COLUMN IF NOT EXISTS intensity VARCHAR(20) NULL;
