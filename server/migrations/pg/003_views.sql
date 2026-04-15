CREATE VIEW v_solar_position AS
SELECT run_id, julian_day_tt, date, catalog_type,
       sun_delta_ra_arcmin, sun_delta_dec_arcmin,
       sqrt(sun_delta_ra_arcmin^2 + sun_delta_dec_arcmin^2) AS error
  FROM eclipse_results
 WHERE sun_delta_ra_arcmin IS NOT NULL;

CREATE VIEW v_moon_position AS
SELECT run_id, julian_day_tt, date, catalog_type,
       moon_delta_ra_arcmin, moon_delta_dec_arcmin,
       sqrt(moon_delta_ra_arcmin^2 + moon_delta_dec_arcmin^2) AS error
  FROM eclipse_results
 WHERE moon_delta_ra_arcmin IS NOT NULL;

CREATE VIEW v_combined_position AS
SELECT run_id, julian_day_tt, date, catalog_type,
       sun_delta_ra_arcmin, sun_delta_dec_arcmin,
       moon_delta_ra_arcmin, moon_delta_dec_arcmin,
       sqrt(sun_delta_ra_arcmin^2 + sun_delta_dec_arcmin^2
          + moon_delta_ra_arcmin^2 + moon_delta_dec_arcmin^2) AS error
  FROM eclipse_results
 WHERE sun_delta_ra_arcmin IS NOT NULL
   AND moon_delta_ra_arcmin IS NOT NULL;
