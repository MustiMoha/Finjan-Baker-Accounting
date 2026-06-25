import { Outlet } from "react-router-dom";
import { AppContextProvider } from "../context/AppContext";

export function AppContextLayout() {
  return (
    <AppContextProvider>
      <Outlet />
    </AppContextProvider>
  );
}
