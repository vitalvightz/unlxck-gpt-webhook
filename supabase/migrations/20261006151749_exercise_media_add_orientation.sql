-- Frame shape of each demo video, so a vertical video gets a 9:16 player
-- instead of being letterboxed in the 16:9 one.
--
-- Written by the YouTube check (import + daily sweep) from the Data API's
-- embed dimensions: taller than wide is portrait, square counts as landscape.
-- NULL means not detected yet; the app renders it as landscape, and a check
-- that reports no dimensions never clears a stored value.

alter table public.exercise_media
  add column orientation text
  constraint exercise_media_orientation_check
  check (orientation is null or orientation in ('portrait', 'landscape'));

comment on column public.exercise_media.orientation is
  'Video aspect: portrait | landscape. NULL = not yet detected; clients render as landscape.';
