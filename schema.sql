-- Gala Marshalling: run this once in the Supabase SQL editor (same project as the Swim Gala Hub).
create table if not exists marshal_rooms (
  room_pin text primary key,
  meet_name text default '',
  stations int not null default 5,
  created_at timestamptz default now()
);

create table if not exists marshal_swims (
  id bigint generated always as identity primary key,
  room_pin text not null,
  session int, event_no int, event text, heat int, lane int,
  swimmer text, club text, age text, entry text
);
create index if not exists marshal_swims_room on marshal_swims (room_pin);

create table if not exists marshal_ticks (
  id bigint generated always as identity primary key,
  room_pin text not null,
  session int not null, event_no int not null, heat int not null, station int not null,
  ticked_at timestamptz default now(),
  unique (room_pin, session, event_no, heat, station)
);

create table if not exists marshal_flags (
  id bigint generated always as identity primary key,
  room_pin text not null,
  session int not null, event_no int not null, heat int not null, lane int not null,
  swimmer text,
  unique (room_pin, session, event_no, heat, lane)
);

-- Same open access as the Swim Gala Hub tables (the app uses the public key)
alter table marshal_rooms disable row level security;
alter table marshal_swims disable row level security;
alter table marshal_ticks disable row level security;
alter table marshal_flags disable row level security;
