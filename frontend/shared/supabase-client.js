/*
  Supabase client for the frontend. Loads via the supabase-js CDN script
  (include that <script> tag BEFORE this file), no build step — matching
  the rest of this frontend.

  Set these before this script loads (e.g. in each page's <head>):
    window.SUPABASE_URL = "https://xxxxx.supabase.co";
    window.SUPABASE_ANON_KEY = "eyJ...";

  Include in each app page's <head>, in this order:
    <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.min.js"></script>
    <script>
      window.SUPABASE_URL = "https://xxxxx.supabase.co";
      window.SUPABASE_ANON_KEY = "your-anon-key";
    </script>
    <script src="../shared/supabase-client.js"></script>
    <script src="../shared/api.js"></script>   <!-- api.js's auth.getToken() now reads the Supabase session -->
*/

const supabaseClient = window.supabase.createClient(window.SUPABASE_URL, window.SUPABASE_ANON_KEY);

const supabaseAuth = {
  async signUp(email, password) {
    const { data, error } = await supabaseClient.auth.signUp({ email, password });
    if (error) throw new Error(error.message);
    return data; // data.session may be null if email confirmation is required — check before assuming login
  },

  async signIn(email, password) {
    const { data, error } = await supabaseClient.auth.signInWithPassword({ email, password });
    if (error) throw new Error(error.message);
    return data;
  },

  async signOut() {
    await supabaseClient.auth.signOut();
  },

  async getAccessToken() {
    const { data } = await supabaseClient.auth.getSession();
    return data.session ? data.session.access_token : null;
  },

  async getUser() {
    const { data } = await supabaseClient.auth.getUser();
    return data.user;
  },

  onAuthStateChange(callback) {
    return supabaseClient.auth.onAuthStateChange((_event, session) => callback(session));
  },
};

