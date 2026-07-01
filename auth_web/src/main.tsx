import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";
import { fetchPublicConfigCached } from "./lib/runtimeConfig";
import { getSupabase } from "./lib/supabase";

void fetchPublicConfigCached();
void getSupabase();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
