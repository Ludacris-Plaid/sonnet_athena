/*
  Single source of truth for frontend configuration.
*/
window.SUPABASE_URL = "https://ygtewmvyhbkzdjyabwwr.supabase.co";
window.SUPABASE_ANON_KEY = "sb_publishable_ytjPJd5rgzpHRlli8MIvfg_-8kV-np-";

// Same-origin API base (nginx proxies backend routes on this host)
var loc = window.location;
window.REALTYAI_API_BASE = loc.protocol + "//" + loc.host;
