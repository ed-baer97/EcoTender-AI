import React from "react";
import ReactDOM from "react-dom/client";
import { CssBaseline, ThemeProvider, createTheme } from "@mui/material";
import App from "./App";

const theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: "#0B6E4F" },
    secondary: { main: "#1B4965" },
    background: { default: "#F3F6F4", paper: "#FFFFFF" },
  },
  typography: {
    fontFamily: '"IBM Plex Sans", "Segoe UI", sans-serif',
    h1: { fontFamily: '"Fraunces", "Georgia", serif' },
    h5: { fontFamily: '"Fraunces", "Georgia", serif' },
    button: { textTransform: "none" },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <App />
    </ThemeProvider>
  </React.StrictMode>
);
