// lib/supabaseClient.ts
import { createClient } from "@supabase/supabase-js";

const supabaseUrl =  "https://rjiphbklnvavzstkalqi.supabase.co";
const supabaseAnonKey =  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJqaXBoYmtsbnZhdnpzdGthbHFpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njk4NzM1MzEsImV4cCI6MjA4NTQ0OTUzMX0.JhSeMknmJOp8vH_aedWNwrpvJbdtzISltvtrHobEyIE";

export const supabase = createClient(supabaseUrl, supabaseAnonKey);
