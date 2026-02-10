create table public.user_documents (
  id serial not null,
  document_id character varying(255) not null,
  session_id character varying(255) not null,
  user_id uuid null,
  filename character varying(500) not null,
  file_type character varying(100) null,
  file_size bigint null,
  chunk_count integer null default 0,
  file_hash character varying(64) null,
  url text null,
  created_at timestamp with time zone null default now(),
  updated_at timestamp with time zone null default now(),
  is_active boolean null default true,
  constraint user_documents_pkey primary key (id),
  constraint user_documents_document_id_key unique (document_id),
  constraint user_documents_user_id_fkey foreign KEY (user_id) references auth.users (id)
) TABLESPACE pg_default;

create table public.ai_chat_history (
  id bigserial not null,
  session_id uuid not null,
  message jsonb not null,
  created_at timestamp with time zone null default now(),
  constraint ai_chat_history_pkey primary key (id),
  constraint ai_chat_history_message_check check (
    (
      (message ? 'type'::text)
      and (
        (message ->> 'type'::text) = any (array['human'::text, 'ai'::text, 'system'::text])
      )
    )
  ),
  constraint ai_chat_history_message_check1 check ((message ? 'content'::text))
) TABLESPACE pg_default;

CREATE TABLE public.chat_session (
  session_id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  is_active boolean DEFAULT true,
  summary text,
  summary_count integer DEFAULT 0,
  updated_at timestamp without time zone DEFAULT now(),
  CONSTRAINT chat_session_pkey PRIMARY KEY (session_id),
  CONSTRAINT chat_session_user_id_fkey FOREIGN KEY (user_id)
      REFERENCES auth.users (id) ON DELETE CASCADE
) TABLESPACE pg_default;

create table public.chat_summaries (
  id serial not null,
  session_id text not null,
  summary text not null,
  covered_until timestamp without time zone not null,
  created_at timestamp without time zone null default now(),
  constraint chat_summaries_pkey primary key (id)
) TABLESPACE pg_default;