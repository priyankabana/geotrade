-- Events that land on a named company rather than on a place or a commodity.
--
-- The watchlist until now was nine supply-chain topics: chokepoints, export
-- controls, port strikes. That shape cannot see "the chief executive of NVIDIA
-- has left", which is a shock to one company and reaches the rest of the graph
-- only through who disclosed depending on that company.
--
-- Which is the thesis. A chokepoint event is seeded by sector and geography and
-- is a reasonable guess about who is affected; a company shock is seeded by the
-- company itself, and every single hop out of it is somebody's filed sentence.
-- It is the one event type where the propagation is evidence end to end.
ALTER TABLE event ADD COLUMN IF NOT EXISTS seed_entity_ids uuid[];

COMMENT ON COLUMN event.seed_entity_ids IS
  'Companies the event lands on directly. Propagation starts here at hop 1, '
  'in addition to anything the sector and geography rules select.';
